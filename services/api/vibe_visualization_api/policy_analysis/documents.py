from __future__ import annotations

from datetime import date, datetime, timezone
import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
import httpx


OFFICIAL_DOMAINS = (
    "gov.cn", "pbc.gov.cn", "csrc.gov.cn", "ndrc.gov.cn", "mof.gov.cn",
    "nfra.gov.cn", "miit.gov.cn", "mofcom.gov.cn", "stats.gov.cn",
)
BODY_SELECTORS = (
    "#UCAP-CONTENT", ".TRS_Editor", ".TRS_UEDITOR", "#zoom",
    "#正文", ".article-content", ".article_content", ".content-detail",
)
DATE_PATTERN = r"(20\d{2})\s*[年./-]\s*(\d{1,2})\s*[月./-]\s*(\d{1,2})\s*日?"


def official_document_url(url: str) -> bool:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    return (
        parsed.scheme in {"http", "https"} and parsed.port in {None, 80, 443}
        and not parsed.username and not parsed.password
        and any(host == domain or host.endswith("." + domain) for domain in OFFICIAL_DOMAINS)
    )


def _date(value: str) -> str | None:
    match = re.search(DATE_PATTERN, value)
    if not match:
        return None
    try:
        return date(*(int(part) for part in match.groups())).isoformat()
    except ValueError:
        return None


def parse_official_document(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    metadata = {
        (tag.get("name") or "").lower(): tag.get("content", "")
        for tag in soup.find_all("meta")
    }
    root = next((node for selector in BODY_SELECTORS if (node := soup.select_one(selector))), None)
    if root is None:
        raise ValueError("未识别到官方正文区；未将导航或整页 HTML 当作政策正文。")
    for node in root.select("script, style, nav, iframe, .editor, .share, .print"):
        node.decompose()
    blocks = root.find_all(["p", "h1", "h2", "h3", "h4", "li", "tr"])
    paragraphs = [re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip() for node in blocks]
    paragraphs = [part for part in paragraphs if part]
    if not paragraphs:
        paragraphs = [part.strip() for part in root.get_text("\n", strip=True).splitlines() if part.strip()]
    text = "\n".join(paragraphs)
    if len(text) < 80:
        raise ValueError("正文内容不足或页面仅含附件，需另行核验官方附件。")
    attachments = [
        {"title": node.get_text(" ", strip=True), "url": urljoin(url, node["href"])}
        for node in root.select("a[href]")
        if re.search(r"\.(pdf|docx?|xlsx?)(?:[?#]|$)", node["href"], re.I)
        and official_document_url(urljoin(url, node["href"]))
    ]
    fields = {}
    for cell in soup.select("table.bd1 td"):
        label = re.sub(r"[\s：:]", "", cell.get_text("", strip=True))
        value = cell.find_next_sibling("td")
        if label in {"标题", "发文机关", "成文日期", "发布日期", "发文字号"} and value:
            fields[label] = value.get_text(" ", strip=True)
    title = fields.get("标题") or metadata.get("articletitle") or (soup.h1.get_text(" ", strip=True) if soup.h1 else "")
    published = _date(fields.get("发布日期", "") or metadata.get("pubdate", "") or metadata.get("publishdate", ""))
    issued = _date(fields.get("成文日期", ""))
    issuer = fields.get("发文机关") or metadata.get("issuedepartment") or None
    for index, paragraph in enumerate(paragraphs):
        if issued is None and re.fullmatch(DATE_PATTERN, paragraph):
            issued = _date(paragraph)
            # A signature date and adjacent issuer are different from website publication metadata.
            previous = paragraphs[index - 1] if index else ""
            if 2 <= len(previous) <= 60 and not re.search(r"[。；：]", previous):
                issuer = issuer or previous
            break
    effective = None
    effective_quote = None
    for paragraph in paragraphs:
        match = re.search(r"(?:本[办法条例规定细则规则]+|本通知|本公告)[^。；]{0,30}?自(" + DATE_PATTERN + r")[起开始]*(?:施行|实施|执行)", paragraph)
        if match:
            effective, effective_quote = _date(match.group(1)), paragraph
            break
        if re.search(r"(?:本[办法条例规定细则规则]+|本通知|本公告)[^。；]{0,20}?自(?:公布|发布|印发)之日起(?:施行|实施|执行)", paragraph):
            effective_quote = paragraph
            # Do not replace the signature date with the website republishing date.
            effective = issued
            break
    return {
        "status": "available", "sourceUrl": url, "title": title,
        "publishedAt": published, "issuedAt": issued, "issuer": issuer,
        "documentNumber": fields.get("发文字号"),
        "effectiveAt": effective, "effectiveDateQuote": effective_quote,
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
        "text": text[:120_000], "paragraphs": text[:120_000].splitlines(),
        "truncated": len(text) > 120_000, "attachments": attachments,
        "note": "提取官方网页正文；附件、配套文件及政策有效性仍需单独核验。",
    }


async def fetch_official_document(url: str, *, client: httpx.AsyncClient | None = None) -> dict:
    own_client = client is None
    http_client = client or httpx.AsyncClient(timeout=12, follow_redirects=False)
    try:
        for _ in range(5):
            if not official_document_url(url):
                raise ValueError("正文地址或跳转不属于允许的官方来源。")
            async with http_client.stream("GET", url, follow_redirects=False, headers={
                "Accept": "text/html", "User-Agent": "Newma-Desk policy research",
            }) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers.get("location", ""))
                    continue
                response.raise_for_status()
                if "html" not in response.headers.get("content-type", "").lower():
                    raise ValueError("当前来源不是 HTML 正文；PDF 等附件需单独读取。")
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > 2_000_000:
                        raise ValueError("官方页面过大，未截断后冒充完整正文。")
                # Government HTML frequently declares GBK/GB2312 only in meta tags.
                charset = re.search(rb"charset\s*=\s*['\"]?([a-zA-Z0-9_-]+)", bytes(data[:4096]))
                encoding = charset.group(1).decode("ascii") if charset else response.encoding or "utf-8"
                return parse_official_document(bytes(data).decode(encoding, errors="replace"), url)
        raise ValueError("官方页面跳转过多，未取得正文。")
    finally:
        if own_client:
            await http_client.aclose()
