"""Read public source text. Reachability and exact quotes are not claim verification."""
from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timezone
from pathlib import Path
import re
import sys
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from fastapi import APIRouter, Depends, Header, HTTPException, Request
import httpx
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from vibe_visualization_api.control_plane.routes import get_repository
from vibe_visualization_api.control_plane.repository import ModuleRepository
from vibe_visualization_api.data_services.client import UnsafeServiceUrl, public_host_addresses
from vibe_visualization_api.mod_storage.routes import _claims, ModuleId
from vibe_visualization_api.mod_storage.store import ModStorageCorruptError, ModStorageNotFoundError

router = APIRouter(tags=["research sources"])
MAX_BYTES = 2_000_000
MAX_TEXT = 60_000
MAX_PDF_BYTES = 20_000_000


class ReviewRelation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str = Field(min_length=1, max_length=200)
    target: str = Field(min_length=1, max_length=200)


class ChainReviewRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    theme: str = Field(min_length=1, max_length=1000)
    market: str = Field(min_length=1, max_length=20)
    relations: list[ReviewRelation] = Field(max_length=200)


@router.post("/{module_id}/sources/chain-reviews")
async def chain_reviews(module_id: ModuleId, body: ChainReviewRead, request: Request,
                        authorization: str | None = Header(default=None),
                        instance_id: str | None = Header(default=None, alias="X-Newma-Desk-Instance-Id"),
                        repository: ModuleRepository = Depends(get_repository)) -> dict:
    claims = _claims(request, authorization, instance_id)
    if (module_id not in {"instock-stock-research", "instock-research-book"} or claims.module_id != module_id
            or "analysis.read" not in claims.permissions):
        raise HTTPException(403, "Mod session does not grant research review handoff")
    module = await run_in_threadpool(repository.get_published, module_id)
    if claims.revision != module.revision:
        raise HTTPException(403, "Mod session revision changed; reload this module")
    try:
        document = await run_in_threadpool(request.app.state.mod_storage_store.get,
            user_id=claims.user_id, workspace_id=claims.workspace_id,
            module_id="instock-industry-chain", namespace="relation-reviews", key="records")
    except ModStorageNotFoundError:
        document = {"revision": 0, "value": {"schemaVersion": 1, "entries": []}}
    except ModStorageCorruptError as exc:
        raise HTTPException(503, "人工复核记录无法读取，请返回产业链核对") from exc
    value = document["value"]
    if (not isinstance(value, dict) or value.get("schemaVersion") != 1
            or not isinstance(value.get("entries"), list) or len(value["entries"]) > 200):
        raise HTTPException(503, "人工复核记录格式异常")
    requested = {(row.source, row.target) for row in body.relations}
    latest = {}
    # Save order is authoritative, matching the append-only industry-chain UI.
    for row in value["entries"]:
        try:
            target = row["target"]
            pair = (target["source"]["id"], target["target"]["id"])
            if target["theme"] == body.theme and target["market"] == body.market and pair in requested:
                latest[pair] = row
        except (TypeError, KeyError) as exc:
            raise HTTPException(503, "人工复核记录格式异常") from exc
    fields = ("id", "decision", "reviewedAt", "snapshotId", "target", "sourceRef", "sourceDate",
              "locator", "quote", "note", "reviewerUserId", "claimDate", "archiveSource")
    entries = [{key: row[key] for key in fields if key in row} for row in latest.values()]
    archive = {"status": "ready", "revision": 0, "materials": []}
    origins = [row["archiveSource"] for row in entries if row.get("archiveSource")]
    if origins:
        try:
            current = await run_in_threadpool(request.app.state.research_archive_service.relation_inputs,
                                              user_id=claims.user_id, workspace_id=claims.workspace_id)
            archive.update(revision=current["revision"], materials=[item for item in current["materials"]
                if any(isinstance(origin, dict) and item["workbookId"] == origin.get("workbookId")
                       and item["sourceId"] == origin.get("sourceId") for origin in origins)])
        except ModStorageCorruptError:
            archive["status"] = "unavailable"
    return {"revision": document["revision"], "book": {"schemaVersion": 1, "entries": entries}, "archive": archive}


class SourceRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(min_length=1, max_length=2048)
    quote: str = Field(default="", max_length=2000)
    asOf: date | None = None
    pageStart: int = Field(default=1, ge=1, le=10000)
    pageCount: int = Field(default=10, ge=1, le=10)


async def read_pdf(data: bytes, start: int, count: int) -> dict:
    process = await asyncio.create_subprocess_exec(
        sys.executable, str(Path(__file__).with_name("research_pdf.py")), str(start), str(count),
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    try:
        output, _ = await asyncio.wait_for(process.communicate(data), timeout=15)
        return json.loads(output) if process.returncode == 0 else {"status": "unreadable"}
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def extract_text(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    title = normalize(soup.title.get_text(" ")) if soup.title else ""
    if re.search(r"\b404\b|page not found|页面不存在|页面未找到", title, re.I):
        return {"status": "not_found", "title": title}
    if re.search(r"access denied|just a moment|verify.*human|captcha|访问受限|安全验证", title, re.I):
        return {"status": "restricted", "title": title}
    published = None
    for tag in soup.select('meta[property="article:published_time"], meta[name="date"], meta[name="pubdate"], meta[name="publishdate"]'):
        value = tag.get("content", "")[:10]
        try:
            published = date.fromisoformat(value).isoformat()
            break
        except ValueError:
            continue
    root = soup.select_one("article, main, [role=main]") or soup.body
    if root is None:
        return {"status": "unreadable", "title": title}
    scope = "article" if root.name == "article" else "main" if root.name == "main" or root.get("role") == "main" else "page"
    for node in root.select("script, style, noscript, nav, header, footer, aside, form, iframe, template"):
        node.decompose()
    blocks = root.find_all(["p", "h1", "h2", "h3", "h4", "li", "tr"])
    block_ids = {id(node) for node in blocks}
    # Avoid repeating nested lists/table paragraphs as independent source paragraphs.
    parts = [normalize(node.get_text(" ", strip=True)) for node in blocks
             if not any(id(parent) in block_ids for parent in node.parents if parent is not root)]
    parts = [part for part in parts if part]
    if not parts:
        parts = [normalize(line) for line in root.get_text("\n", strip=True).splitlines() if normalize(line)]
    text = "\n".join(parts)
    return {"status": "readable" if len(text) >= 80 else "unreadable", "title": title,
            "publishedAt": published, "extractionScope": scope, "text": text[:MAX_TEXT],
            "paragraphs": [{"locator": f"网页提取段落 {i + 1}", "text": part}
                           for i, part in enumerate(text[:MAX_TEXT].splitlines()) if part],
            "truncated": len(text) > MAX_TEXT}


async def read_source(body: SourceRead, *, client: httpx.AsyncClient | None = None) -> dict:
    url = body.url.strip()
    base = {"sourceUrl": url, "checkedAt": datetime.now(timezone.utc).isoformat(),
            "claimVerified": False, "quoteMatch": "not_requested", "paragraphs": [],
            "note": "仅检查访问、提取文本及逐字摘录；不判断关系真实性，读取时间不是披露日期。"}
    own_client = client is None
    http = client or httpx.AsyncClient(timeout=10, follow_redirects=False, trust_env=False,
                                      limits=httpx.Limits(max_keepalive_connections=0))
    try:
        async with asyncio.timeout(20):
            for _ in range(5):
                if any(ord(c) < 32 for c in url) or "\\" in url:
                    return {**base, "status": "blocked"}
                parsed = httpx.URL(url)
                if (parsed.scheme not in {"http", "https"} or not parsed.host or parsed.username or parsed.password
                        or parsed.port not in {None, 80, 443}):
                    return {**base, "status": "blocked"}
                addresses = await run_in_threadpool(public_host_addresses, parsed.host, parsed.port or (443 if parsed.scheme == "https" else 80))
                # Pin the validated address: do not resolve the user-controlled hostname again at connect time.
                address = sorted(addresses, key=lambda item: (item.version, str(item)))[0]
                pinned = parsed.copy_with(host=str(address), fragment=None)
                headers = {"Host": parsed.netloc.decode("ascii"), "Accept": "text/html, application/pdf, text/plain;q=0.8",
                           "User-Agent": "Newma-Desk source review", "Accept-Encoding": "identity"}
                http.cookies.clear()
                async with http.stream("GET", pinned, headers=headers, extensions={"sni_hostname": parsed.host}, follow_redirects=False) as response:
                    base.update(finalUrl=str(parsed), httpStatus=response.status_code)
                    if response.is_redirect:
                        url = urljoin(str(parsed), response.headers.get("location", ""))
                        continue
                    if response.status_code in {404, 410}:
                        return {**base, "status": "not_found"}
                    if response.status_code in {401, 403, 429, 451}:
                        return {**base, "status": "restricted"}
                    if not 200 <= response.status_code < 300:
                        return {**base, "status": "unavailable"}
                    content_type = response.headers.get("content-type", "").split(";")[0].lower().strip()
                    pdf_type = content_type in {"application/pdf", "application/octet-stream"}
                    if not pdf_type and content_type not in {"text/html", "application/xhtml+xml", "text/plain"}:
                        return {**base, "status": "unsupported", "contentType": content_type}
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        data.extend(chunk)
                        if len(data) > (MAX_PDF_BYTES if pdf_type else MAX_BYTES):
                            return {**base, "status": "too_large"}
                    if pdf_type:
                        if not data.startswith(b"%PDF-"):
                            return {**base, "status": "unreadable" if content_type == "application/pdf" else "unsupported"}
                        result = await read_pdf(bytes(data), body.pageStart, body.pageCount)
                        quote = normalize(body.quote)
                        if quote and result["status"] == "readable":
                            pages = {}
                            for part in result["paragraphs"]:
                                pages[part["page"]] = pages.get(part["page"], "") + part["text"]
                            result["quoteMatch"] = "found" if quote in normalize("\n".join(pages.values())) else "not_found"
                        return {**base, **result, "pageStart": body.pageStart, "afterCutoff": None}
                    charset = re.search(rb"charset\s*=\s*['\"]?([a-zA-Z0-9_-]+)", bytes(data[:4096]))
                    encoding = charset.group(1).decode("ascii") if charset else response.encoding or "utf-8"
                    text = bytes(data).decode(encoding, errors="replace")
                    if content_type == "text/plain":
                        result = {"status": "readable" if len(text.strip()) >= 80 else "unreadable", "text": text[:MAX_TEXT],
                                  "truncated": len(text) > MAX_TEXT, "extractionScope": "plain-text", "publishedAt": None,
                                  "paragraphs": [{"locator": f"文本行 {i + 1}", "text": line} for i, line in enumerate(text[:MAX_TEXT].splitlines()) if line.strip()]}
                    else:
                        result = await run_in_threadpool(extract_text, text)
                    quote = normalize(body.quote)
                    if quote and result["status"] == "readable":
                        result["quoteMatch"] = "found" if quote in normalize(result.get("text", "")) else "not_found"
                    published = result.get("publishedAt")
                    result["afterCutoff"] = published > body.asOf.isoformat() if published and body.asOf else None
                    return {**base, **result}
            return {**base, "status": "redirect_limit"}
    except UnsafeServiceUrl:
        return {**base, "status": "blocked"}
    except (httpx.TimeoutException, TimeoutError):
        return {**base, "status": "timeout"}
    except (httpx.HTTPError, ValueError, LookupError):
        return {**base, "status": "unavailable"}
    finally:
        if own_client:
            await http.aclose()


@router.post("/{module_id}/sources/read")
async def read_mod_source(module_id: ModuleId, body: SourceRead, request: Request,
                          authorization: str | None = Header(default=None),
                          instance_id: str | None = Header(default=None, alias="X-Newma-Desk-Instance-Id"),
                          repository: ModuleRepository = Depends(get_repository)) -> dict:
    claims = _claims(request, authorization, instance_id)
    if claims.module_id != module_id or "analysis.read" not in claims.permissions:
        raise HTTPException(403, "Mod session does not grant source reading")
    module = await run_in_threadpool(repository.get_published, module_id)
    if claims.revision != module.revision:
        raise HTTPException(403, "Mod session revision changed; reload this module")
    # Reuse the app lifecycle rather than a process-global limiter shared by test event loops.
    if not hasattr(request.app.state, "source_read_slots"):
        request.app.state.source_read_slots = asyncio.Semaphore(3)
    slots = request.app.state.source_read_slots
    if slots.locked():
        raise HTTPException(429, "来源读取繁忙，请稍后再试")
    async with slots:
        return await read_source(body)


@router.get("/{module_id}/sources/archive")
async def archived_sources(module_id: ModuleId, request: Request,
                           authorization: str | None = Header(default=None),
                           instance_id: str | None = Header(default=None, alias="X-Newma-Desk-Instance-Id"),
                           repository: ModuleRepository = Depends(get_repository)) -> dict:
    claims = _claims(request, authorization, instance_id)
    if claims.module_id != module_id or "analysis.read" not in claims.permissions:
        raise HTTPException(403, "Mod session does not grant source reading")
    module = await run_in_threadpool(repository.get_published, module_id)
    if claims.revision != module.revision:
        raise HTTPException(403, "Mod session revision changed; reload this module")
    try:
        return await run_in_threadpool(request.app.state.research_archive_service.relation_inputs,
                                      user_id=claims.user_id, workspace_id=claims.workspace_id)
    except ModStorageCorruptError as exc:
        raise HTTPException(503, "财报归档无法读取，请先在财报研究中核对") from exc
