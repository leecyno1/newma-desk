from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup


_MAX_HTML_BYTES = 6 * 1024 * 1024
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 MicroMessenger/8.0.0"
)


def _clean(value: object, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _meta_content(soup: BeautifulSoup, *keys: str) -> str:
    for key in keys:
        node = soup.find("meta", attrs={"property": key}) or soup.find("meta", attrs={"name": key})
        if node and node.get("content"):
            return str(node.get("content")).strip()
    return ""


def normalize_card_thumbnail_url(url: str) -> str:
    value = str(url or "").strip()
    parsed = urlparse(value)
    if parsed.hostname and parsed.hostname.lower() == "mmbiz.qpic.cn":
        segments = parsed.path.rsplit("/", 1)
        if len(segments) == 2 and segments[1].isdigit():
            parsed = parsed._replace(path=f"{segments[0]}/300")
            return urlunparse(parsed)
    return value


def extract_link_preview(html: str, url: str) -> dict[str, str]:
    soup = BeautifulSoup(str(html or ""), "html.parser")
    title = _meta_content(soup, "og:title", "twitter:title")
    if not title and soup.title:
        title = soup.title.get_text(" ", strip=True)
    desc = _meta_content(soup, "og:description", "twitter:description", "description")
    thumb_url = _meta_content(soup, "og:image", "twitter:image", "twitter:image:src")
    return {
        "url": str(url or "").strip(),
        "title": _clean(title, 120),
        "desc": _clean(desc, 300),
        "thumb_url": normalize_card_thumbnail_url(
            urljoin(str(url or "").strip(), thumb_url) if thumb_url else ""
        ),
    }


def _validate_public_http_url(url: str) -> str:
    value = str(url or "").strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("链接必须是完整的 http(s) 地址")
    host = parsed.hostname.lower().rstrip(".")
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise ValueError("不允许解析本地链接")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)}
    except OSError as exc:
        raise ValueError("链接域名无法解析") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise ValueError("不允许解析内网链接")
    return value


def fetch_link_preview(url: str, timeout: float = 20.0) -> dict[str, str]:
    value = _validate_public_http_url(url)
    session = requests.Session()
    session.trust_env = False
    response = session.get(
        value,
        headers={"User-Agent": _USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
        timeout=timeout,
        allow_redirects=True,
        stream=True,
    )
    response.raise_for_status()
    final_url = _validate_public_http_url(str(response.url or value))
    chunks: list[bytes] = []
    size = 0
    for chunk in response.iter_content(64 * 1024):
        if not chunk:
            continue
        size += len(chunk)
        if size > _MAX_HTML_BYTES:
            raise ValueError("链接页面过大，无法生成卡片")
        chunks.append(chunk)
    encoding = response.encoding or response.apparent_encoding or "utf-8"
    html = b"".join(chunks).decode(encoding, errors="replace")
    preview = extract_link_preview(html, final_url)
    preview["url"] = value
    if not preview["title"]:
        raise ValueError("未解析到链接标题")
    if not preview["thumb_url"]:
        raise ValueError("未解析到链接封面，无法发送微信卡片")
    return preview
