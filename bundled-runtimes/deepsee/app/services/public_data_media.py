"""Expose only retained local media, never upstream WeChat credentials or arbitrary URLs."""
from urllib.parse import urlsplit, urljoin, unquote

import requests
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from ..config import settings


def retained_url(value, *, redirect=False):
    parsed = urlsplit(str(value or ""))
    base = urlsplit(settings.CHATLOG_HTTP_BASE or "")
    path = unquote(parsed.path)
    prefixes = ("/data/msg/",) if redirect else ("/image/", "/voice/", "/video/", "/emoji/", "/file/")
    return bool(base.netloc and parsed.scheme in {"http", "https"}
                and (parsed.scheme, parsed.netloc) == (base.scheme, base.netloc)
                and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment
                and path.startswith(prefixes) and ".." not in path.split("/") and "\\" not in path)


def attachment_response(row):
    url = str(row.media_url or "")
    if not retained_url(url):
        raise HTTPException(404, "attachment_not_retained")
    response = None
    try:
        response = requests.get(url, stream=True, allow_redirects=False, timeout=(5, 30))
        if response.status_code in {301, 302, 303, 307, 308}:
            target = urljoin(url, response.headers.get("location", ""))
            response.close()
            if not retained_url(target, redirect=True):
                raise HTTPException(502, "invalid_media_redirect")
            response = requests.get(target, stream=True, allow_redirects=False, timeout=(5, 30))
    except requests.RequestException:
        if response is not None:
            response.close()
        raise HTTPException(502, "local_media_unavailable") from None
    content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
    allowed = content_type.startswith(("image/", "audio/", "video/")) or content_type in {
        "application/pdf", "application/octet-stream"}
    if response.status_code != 200 or not allowed or content_type == "image/svg+xml":
        status = 404 if response.status_code == 404 else 502
        response.close()
        raise HTTPException(status, "attachment_unavailable")

    def chunks():
        try:
            yield from response.iter_content(chunk_size=64 * 1024)
        finally:
            response.close()

    return StreamingResponse(chunks(), media_type=content_type, headers={
        "Content-Disposition": f'attachment; filename="deepsee-message-{row.id}"',
        "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})
