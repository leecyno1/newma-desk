from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any
from urllib.parse import quote, urlparse
from xml.etree import ElementTree as ET

from ..config import settings


MEDIA_POLICY_CHATLOG = "chatlog"
MEDIA_POLICY_WECHATAPI = "wechatapi"


@dataclass(frozen=True)
class NormalizedWechatMessage:
    message_type: str
    content_text: str
    contents: dict[str, Any]
    media_url: str | None
    display_title: str
    source_username: str


@dataclass(frozen=True)
class WechatMessageIdentity:
    message_type: str
    external_id: str
    strong_fields: tuple[tuple[str, str], ...]
    weak_text: str
    raw_text: str

    @property
    def has_strong_fields(self) -> bool:
        return bool(self.strong_fields)


def parse_contents_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except Exception:
            return {}
        if isinstance(parsed, dict):
            return dict(parsed)
    return {}


def _content_string(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("string", "content", "Content", "text"):
            found = _content_string(value.get(key))
            if found:
                return found
    return ""


def extract_wechat_xml_payload(content: Any) -> str:
    text_value = _content_string(content)
    if not text_value and not isinstance(content, (dict, list, tuple, set)):
        text_value = str(content or "")
    text_value = text_value.strip()
    if not text_value:
        return ""
    lowered = text_value.lower()
    positions = [
        pos
        for pos in (
            lowered.find("<?xml"),
            lowered.find("<msg"),
            lowered.find("<appmsg"),
            lowered.find("<img"),
        )
        if pos >= 0
    ]
    if positions:
        return text_value[min(positions) :].strip()
    return text_value


def _find_text(root: ET.Element, *paths: str) -> str:
    for path in paths:
        try:
            value = root.findtext(path)
        except Exception:
            value = None
        text_value = str(value or "").strip()
        if text_value:
            return text_value
    return ""


def extract_app_message_fields(content: Any) -> dict[str, str]:
    text_value = extract_wechat_xml_payload(content)
    if not text_value or "<appmsg" not in text_value.lower():
        return {}
    try:
        root = ET.fromstring(text_value)
    except Exception:
        return {}

    record_root: ET.Element | None = None
    record_text = _find_text(
        root,
        ".//appmsg/recorditem",
        ".//recorditem",
        ".//appmsg/announcement",
        ".//announcement",
    )
    if record_text and "<" in record_text:
        try:
            record_root = ET.fromstring(record_text)
        except Exception:
            record_root = None

    def find_record_text(*paths: str) -> str:
        if record_root is None:
            return ""
        return _find_text(record_root, *paths)

    return {
        "appmsg_type": _find_text(root, ".//appmsg/type", ".//type"),
        "title": _find_text(root, ".//appmsg/title", ".//title"),
        "desc": _find_text(root, ".//appmsg/des", ".//appmsg/description", ".//des"),
        "url": _find_text(root, ".//appmsg/url", ".//url"),
        "sourceusername": _find_text(root, ".//appmsg/sourceusername", ".//sourceusername"),
        "sourcedisplayname": _find_text(root, ".//appmsg/sourcedisplayname", ".//sourcedisplayname"),
        "thumburl": _find_text(root, ".//appmsg/thumburl", ".//thumburl", ".//weappinfo/weappiconurl"),
        "attachid": _find_text(root, ".//appmsg/appattach/attachid", ".//appattach/attachid"),
        "cdnattachurl": _find_text(root, ".//appmsg/appattach/cdnattachurl", ".//appattach/cdnattachurl"),
        "aeskey": _find_text(root, ".//appmsg/appattach/aeskey", ".//appattach/aeskey"),
        "fileext": _find_text(root, ".//appmsg/appattach/fileext", ".//appattach/fileext"),
        "totallen": _find_text(root, ".//appmsg/appattach/totallen", ".//appattach/totallen"),
        "md5": _find_text(root, ".//appmsg/md5", ".//md5"),
        "cdn_dataurl": find_record_text(".//dataitem/cdn_dataurl", ".//dataitem/cdndataurl"),
        "cdndataurl": find_record_text(".//dataitem/cdndataurl", ".//dataitem/cdn_dataurl"),
        "cdndatakey": find_record_text(".//dataitem/cdn_datakey", ".//dataitem/cdndatakey"),
        "datatitle": find_record_text(".//dataitem/datatitle"),
        "datadesc": find_record_text(".//dataitem/datadesc"),
        "datafmt": find_record_text(".//dataitem/datafmt"),
        "datasize": find_record_text(".//dataitem/datasize", ".//dataitem/fullsize"),
    }


def extract_image_fields(content: Any) -> dict[str, str]:
    text_value = extract_wechat_xml_payload(content)
    if not text_value or "<img" not in text_value.lower():
        return {}
    try:
        root = ET.fromstring(text_value)
    except Exception:
        return {}
    img = root if root.tag.lower() == "img" else root.find(".//img")
    if img is None:
        return {}
    out: dict[str, str] = {}
    for key in (
        "cdnthumburl",
        "cdnmidimgurl",
        "cdnbigimgurl",
        "cdnthumbaeskey",
        "aeskey",
        "md5",
        "length",
        "hdlength",
        "cdnthumblength",
        "cdnthumbheight",
        "cdnthumbwidth",
    ):
        value = str(img.attrib.get(key) or "").strip()
        if value:
            out[key] = value
    return out


def is_file_app_message(app_message: Any) -> bool:
    fields = app_message if isinstance(app_message, dict) else extract_app_message_fields(app_message)
    if not isinstance(fields, dict):
        return False
    appmsg_type = str(fields.get("appmsg_type") or "").strip()
    if appmsg_type == "6":
        return True
    return appmsg_type == "24" and bool(
        fields.get("cdn_dataurl")
        or fields.get("cdndataurl")
        or fields.get("datatitle")
        or fields.get("datafmt")
    )


def normalize_message_type(msg_type: Any, *, app_message: Any = None) -> str:
    aliases = {
        "text": "text",
        "文本": "text",
        "image": "image",
        "img": "image",
        "图片": "image",
        "voice": "voice",
        "audio": "voice",
        "语音": "voice",
        "video": "video",
        "视频": "video",
        "emoji": "emoji",
        "表情": "emoji",
        "location": "location",
        "位置": "location",
        "link": "link",
        "app": "link",
        "链接": "link",
        "file": "file",
        "document": "file",
        "文件": "file",
        "system": "system",
        "系统": "system",
        "other": "other",
    }
    numeric = {
        0: "text",
        1: "text",
        3: "image",
        34: "voice",
        43: "video",
        47: "emoji",
        48: "location",
        49: "link",
        62: "video",
        10000: "system",
        10002: "system",
    }
    text_value = "" if msg_type is None else str(msg_type).strip()
    lowered = text_value.lower()
    if lowered in aliases:
        normalized = aliases[lowered]
    else:
        try:
            normalized = numeric.get(int(text_value), text_value or "other")
        except Exception:
            normalized = text_value or "other"
    if normalized == "link" and is_file_app_message(app_message):
        return "file"
    return normalized


def _normalize_http_base(base: str | None) -> str:
    value = str(base or "").strip()
    if not value:
        value = settings.CHATLOG_HTTP_BASE or "http://127.0.0.1:5030"
    if not re.match(r"^https?://", value, flags=re.IGNORECASE):
        value = f"http://{value}"
    return value.rstrip("/")


def _encode_rel_path(path: str | None) -> str:
    text_value = str(path or "").strip().replace("\\", "/").lstrip("/")
    if not text_value:
        return ""
    return "/".join(quote(segment, safe="") for segment in text_value.split("/") if segment)


def build_chatlog_media_url(
    msg_type: Any,
    contents: dict[str, Any] | None,
    *,
    host: str | None = None,
) -> str | None:
    c = contents or {}
    base = _normalize_http_base(host or c.get("host"))
    normalized_type = normalize_message_type(msg_type, app_message=c)

    if normalized_type in {"link", "file"}:
        direct = str(c.get("url") or "").strip()
        if direct:
            return direct

    direct_image = str(
        c.get("cdnthumburl")
        or c.get("thumbUrl")
        or c.get("thumb_url")
        or c.get("image_url")
        or c.get("imageUrl")
        or ""
    ).strip()
    if direct_image:
        return direct_image

    md5 = str(
        c.get("md5")
        or c.get("imageId")
        or c.get("image_id")
        or c.get("mediaId")
        or c.get("id")
        or ""
    ).strip()
    path_raw = (
        c.get("path")
        or c.get("data")
        or c.get("relative")
        or c.get("image_path")
        or c.get("localPath")
        or c.get("video_path")
    )
    rel = _encode_rel_path(str(path_raw or ""))

    if normalized_type == "image":
        if md5 and rel:
            return f"{base}/image/{quote(md5, safe='')},{rel}"
        if md5:
            return f"{base}/image/{quote(md5, safe='')}"
        if rel:
            return f"{base}/data/{rel}"
        return None

    if normalized_type == "video":
        if md5 and rel:
            return f"{base}/video/{quote(md5, safe='')},{rel}"
        if md5:
            return f"{base}/video/{quote(md5, safe='')}"
        if rel:
            return f"{base}/data/{rel}"
        return None

    if normalized_type == "voice":
        voice_id = str(c.get("voice") or c.get("voiceId") or c.get("id") or c.get("mediaId") or "").strip()
        if voice_id:
            return f"{base}/voice/{quote(voice_id, safe='')}"
        if rel:
            return f"{base}/data/{rel}"
        return None

    if normalized_type in {"link", "file"}:
        if md5:
            return f"{base}/file/{quote(md5, safe='')}"
        if rel:
            return f"{base}/data/{rel}"
        return None

    if rel:
        return f"{base}/data/{rel}"
    return None


def _http_url(value: Any) -> str | None:
    text_value = str(value or "").strip()
    if not text_value:
        return None
    try:
        parsed = urlparse(text_value)
    except Exception:
        return None
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None
    return text_value


def build_wechatapi_media_url(
    msg_type: Any,
    contents: dict[str, Any] | None,
    *,
    media_url: Any = None,
) -> str | None:
    """Return only a directly fetchable HTTP(S) URL from WeChatAPI metadata.

    WeChatAPI CDN fields frequently contain opaque file identifiers rather than URLs.
    Those identifiers must stay in ``contents`` for the dedicated WeChatAPI resolvers.
    """
    explicit = _http_url(media_url)
    if explicit:
        return explicit

    c = contents or {}
    normalized_type = normalize_message_type(msg_type, app_message=c)
    if normalized_type == "image":
        candidates = (
            c.get("cdnthumburl"),
            c.get("cdnmidimgurl"),
            c.get("cdnbigimgurl"),
            c.get("thumbUrl"),
            c.get("thumb_url"),
            c.get("image_url"),
            c.get("imageUrl"),
            c.get("url"),
        )
    elif normalized_type in {"link", "file"}:
        candidates = (
            c.get("url"),
            c.get("cdnattachurl"),
            c.get("cdn_dataurl"),
            c.get("cdndataurl"),
        )
    elif normalized_type == "video":
        candidates = (
            c.get("url"),
            c.get("cdnvideourl"),
            c.get("cdnvideo_url"),
            c.get("playurl"),
        )
    elif normalized_type == "voice":
        candidates = (c.get("url"), c.get("voiceurl"), c.get("voice_url"))
    else:
        candidates = (c.get("url"),)

    for candidate in candidates:
        direct = _http_url(candidate)
        if direct:
            return direct
    return None


def normalize_wechat_message(
    *,
    msg_type: Any,
    content: Any = None,
    contents: Any = None,
    media_url: Any = None,
    host: str | None = None,
    source_username: Any = None,
    media_policy: str = MEDIA_POLICY_CHATLOG,
) -> NormalizedWechatMessage:
    merged_contents = parse_contents_dict(contents)
    app_fields = extract_app_message_fields(content)
    image_fields = extract_image_fields(content)
    for fields in (app_fields, image_fields):
        for key, value in fields.items():
            if value and not merged_contents.get(key):
                merged_contents[key] = value

    message_type = normalize_message_type(msg_type, app_message=merged_contents)
    if image_fields:
        message_type = "image"
    elif app_fields:
        message_type = "file" if is_file_app_message(merged_contents) else "link"

    display_title = str(merged_contents.get("title") or merged_contents.get("datatitle") or "").strip()
    content_text = _content_string(content)
    if not content_text and not isinstance(content, (dict, list, tuple, set)):
        content_text = str(content or "")
    content_text = display_title or content_text.strip()
    policy = str(media_policy or MEDIA_POLICY_CHATLOG).strip().lower()
    if policy == MEDIA_POLICY_WECHATAPI:
        normalized_media_url = build_wechatapi_media_url(
            message_type,
            merged_contents,
            media_url=media_url,
        )
    else:
        normalized_media_url = str(media_url or "").strip() or build_chatlog_media_url(
            message_type,
            merged_contents,
            host=host,
        )
    normalized_source_username = str(
        source_username
        or merged_contents.get("sourceusername")
        or merged_contents.get("userName")
        or merged_contents.get("username")
        or ""
    ).strip()

    return NormalizedWechatMessage(
        message_type=message_type,
        content_text=content_text,
        contents=merged_contents,
        media_url=normalized_media_url,
        display_title=display_title,
        source_username=normalized_source_username,
    )


_IDENTITY_FIELD_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("url", ("url",)),
    ("md5", ("md5",)),
    ("attachid", ("attachid",)),
    ("cdnattachurl", ("cdnattachurl",)),
    ("cdn_dataurl", ("cdn_dataurl", "cdndataurl", "cdnDataUrl")),
    ("path", ("path", "data", "relative", "image_path", "localPath", "video_path")),
    ("media_id", ("mediaId", "media_id", "imageId", "image_id", "id")),
    ("voice_id", ("voice", "voiceId")),
    ("cdnthumburl", ("cdnthumburl", "thumbUrl", "thumb_url")),
    ("cdnmidimgurl", ("cdnmidimgurl",)),
    ("cdnbigimgurl", ("cdnbigimgurl",)),
)


def build_wechat_message_identity(
    *,
    msg_type: Any,
    content: Any = None,
    contents: Any = None,
    external_id: Any = None,
) -> WechatMessageIdentity:
    normalized = normalize_wechat_message(
        msg_type=msg_type,
        content=content,
        contents=contents,
        media_policy=MEDIA_POLICY_WECHATAPI,
    )
    strong_fields: list[tuple[str, str]] = []
    for canonical_key, aliases in _IDENTITY_FIELD_GROUPS:
        value = ""
        for alias in aliases:
            value = str(normalized.contents.get(alias) or "").strip()
            if value:
                break
        if value:
            if canonical_key == "md5":
                value = value.lower()
            strong_fields.append((canonical_key, value))

    raw_text = _content_string(content)
    if not raw_text and not isinstance(content, (dict, list, tuple, set)):
        raw_text = str(content or "")
    return WechatMessageIdentity(
        message_type=normalized.message_type,
        external_id=str(external_id or "").strip(),
        strong_fields=tuple(strong_fields),
        weak_text=str(normalized.content_text or "").strip(),
        raw_text=raw_text.strip(),
    )


def wechat_message_identities_match(
    left: WechatMessageIdentity,
    right: WechatMessageIdentity,
) -> bool:
    if left.message_type != right.message_type:
        return False
    if left.external_id and right.external_id:
        return left.external_id == right.external_id
    if left.has_strong_fields or right.has_strong_fields:
        if not left.has_strong_fields or not right.has_strong_fields:
            return False
        left_fields = dict(left.strong_fields)
        right_fields = dict(right.strong_fields)
        has_common_field = False
        for canonical_key, _aliases in _IDENTITY_FIELD_GROUPS:
            if canonical_key in left_fields and canonical_key in right_fields:
                has_common_field = True
                if left_fields[canonical_key] != right_fields[canonical_key]:
                    return False
        return has_common_field
    left_candidates = {value for value in (left.weak_text, left.raw_text) if value}
    right_candidates = {value for value in (right.weak_text, right.raw_text) if value}
    return bool(left_candidates.intersection(right_candidates))
