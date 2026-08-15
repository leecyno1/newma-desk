from __future__ import annotations

import hashlib
import asyncio
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree
from urllib.parse import urlsplit

import httpx


LEVEL_3_TERMS = ("中央政治局", "国务院", "总体方案", "决定", "意见", "降准", "降息")
LEVEL_2_TERMS = ("办法", "规定", "通知", "指导", "实施方案", "管理办法")


def _text(node: ElementTree.Element, *names: str) -> str:
    for name in names:
        child = node.find(name)
        if child is not None and child.text:
            return child.text.strip()
    return ""


def _published_date(value: str) -> date | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).date()
    except (TypeError, ValueError, OverflowError):
        pass
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _level(title: str) -> tuple[int, list[str]]:
    if any(term in title for term in LEVEL_3_TERMS):
        return 3, ["命中战略级政策关键词", "量级为机器初筛，需研究员复核"]
    if any(term in title for term in LEVEL_2_TERMS):
        return 2, ["涉及制度、行业或执行规则调整", "量级为机器初筛，需研究员复核"]
    return 1, ["暂按常规政策动态归类", "量级为机器初筛，需研究员复核"]


def _is_official_link(link: str, source_url: str) -> bool:
    link_host = (urlsplit(link).hostname or "").removeprefix("www.")
    source_host = (urlsplit(source_url).hostname or "").removeprefix("www.")
    return bool(link_host and source_host and (link_host == source_host or link_host.endswith(f".{source_host}")))


def parse_policy_feed(xml: str, source: dict) -> list[dict]:
    root = ElementTree.fromstring(xml)
    entries = root.findall(".//item")
    atom = False
    if not entries:
        entries = root.findall(".//{http://www.w3.org/2005/Atom}entry")
        atom = True

    events = []
    for entry in entries:
        if atom:
            title = _text(entry, "{http://www.w3.org/2005/Atom}title")
            published = _text(entry, "{http://www.w3.org/2005/Atom}published", "{http://www.w3.org/2005/Atom}updated")
            link_node = entry.find("{http://www.w3.org/2005/Atom}link")
            link = link_node.get("href", "").strip() if link_node is not None else ""
            summary = _text(entry, "{http://www.w3.org/2005/Atom}summary", "{http://www.w3.org/2005/Atom}content")
        else:
            title = _text(entry, "title")
            published = _text(entry, "pubDate", "date")
            link = _text(entry, "link", "guid")
            summary = _text(entry, "description")
        event_date = _published_date(published)
        if not title or not _is_official_link(link, source["url"]) or event_date is None:
            continue
        level, rationale = _level(title)
        digest = hashlib.sha1(f"{source['id']}:{link}".encode()).hexdigest()[:16]
        events.append({
            "id": f"feed-{source['id']}-{digest}", "title": title,
            "date": event_date.isoformat(), "institution": source["name"],
            "category": source["categories"][0], "level": level,
            "status": "published", "certainty": "official",
            "summary": summary[:280] or "由官方渠道采集，详情以原文为准。",
            "rationale": rationale, "sourceUrl": link,
            "marketScope": ["待研判"], "discoveredBy": "rsshub",
        })
    return events


async def collect_policy_feeds(
    sources: list[dict], base_url: str, timeout_seconds: float,
    client: httpx.AsyncClient | None = None,
) -> tuple[list[dict], dict]:
    if not base_url:
        return [], {"mode": "official-source-registry", "status": "not-configured", "feeds": []}

    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True)
    async def collect_source(source: dict) -> tuple[list[dict], dict] | None:
        path = source.get("rssHubPath")
        if not path:
            return None
        url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
        try:
            response = await http_client.get(url, headers={"Accept": "application/rss+xml, application/atom+xml, application/xml"})
            response.raise_for_status()
            parsed = parse_policy_feed(response.text, source)
            return parsed, {"sourceId": source["id"], "status": "ok", "items": len(parsed)}
        except (httpx.HTTPError, ElementTree.ParseError, ValueError) as error:
            return [], {"sourceId": source["id"], "status": "failed", "items": 0, "reason": str(error)[:160]}

    try:
        results = [result for result in await asyncio.gather(*(collect_source(source) for source in sources)) if result is not None]
    finally:
        if owns_client:
            await http_client.aclose()

    events = [event for source_events, _ in results for event in source_events]
    feed_status = [status for _, status in results]
    successful = sum(item["status"] == "ok" for item in feed_status)
    status = "ready" if successful == len(feed_status) else "degraded"
    if not successful:
        status = "unavailable"
    return events, {"mode": "rsshub-live", "status": status, "feeds": feed_status, "collectedAt": datetime.now(timezone.utc).isoformat()}
