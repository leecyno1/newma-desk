#!/usr/bin/env python3
"""
Intake 文本与 URL 工具函数

这些函数原本内联在 run_stage1_intake.py 中，现提取为独立模块，
供 intake 相关脚本复用，降低主采集脚本的复杂度。
"""

from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def md_cell(text: str) -> str:
    return clean_text(text).replace("|", "\\|")


def md_link(title: str, url: str) -> str:
    label = clean_text(title) or url
    return f"[{label}]({url})" if url else label


def sha1_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def normalize_slug(text: str) -> str:
    value = re.sub(r"[^0-9A-Za-z\u4e00-\u9fa5]+", "-", text or "").strip("-").lower()
    return value or "unknown"


def normalize_text(*parts: str) -> str:
    return clean_text(" ".join(part for part in parts if part)).lower()


def contains_keyword(text: str, keyword: str) -> bool:
    keyword_lower = keyword.lower()
    if re.search(r"[A-Za-z]", keyword):
        pattern = rf"(?<![A-Za-z0-9]){re.escape(keyword_lower)}(?![A-Za-z0-9])"
        return re.search(pattern, text) is not None
    return keyword_lower in text


def summarize_title(title: str, extra: str = "") -> str:
    title = clean_text(title)
    extra = clean_text(extra)
    if extra:
        return f"{title}；{extra[:72]}"
    return title[:96]


def normalize_url(url: str) -> str:
    parsed = urlparse((url or "").strip())
    if not parsed.scheme or not parsed.netloc:
        return (url or "").strip()
    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower()
        not in {
            "clicktime",
            "enterid",
            "sessionid",
            "subscene",
            "scene",
            "utm_source",
            "utm_medium",
            "utm_campaign",
            "spm",
        }
    ]
    clean_query = urlencode(query_pairs, doseq=True)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", clean_query, ""))


def extract_report_links(html: str, limit: int = 12) -> list[dict[str, str]]:
    pairs = re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.S)
    results: list[dict[str, str]] = []
    seen: set[str] = set()
    for href, text in pairs:
        if not href.startswith("http"):
            continue
        normalized = normalize_url(href)
        if normalized in seen:
            continue
        title = clean_text(re.sub(r"<[^>]+>", "", text))
        if not title:
            continue
        results.append({"title": title, "url": normalized})
        seen.add(normalized)
        if len(results) >= limit:
            break
    return results
