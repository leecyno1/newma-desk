"""Translate public RSS titles to Chinese and cache the results."""

from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
import time
from concurrent.futures import ThreadPoolExecutor


HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(HERE, ".cache", "news-translations.json")
BATCH_SIZE = 8
WORKERS = 2
PER_INDUSTRY_LIMIT = 96
TIMEOUT_SECONDS = 15
RETRIES = 2
TRANSLATE_URL = "https://translate.googleapis.com/translate_a/single"


def _has_chinese(value: str) -> bool:
    return re.search(r"[\u3400-\u9fff]", value or "") is not None


def _load_cache() -> dict[str, str]:
    try:
        with open(CACHE_FILE, encoding="utf-8") as handle:
            data = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return {
        str(title): str(translation)
        for title, translation in data.items()
        if isinstance(title, str) and isinstance(translation, str) and _has_chinese(translation)
    }


def _save_cache(cache: dict[str, str]) -> None:
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    temporary = f"{CACHE_FILE}.tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(cache, handle, ensure_ascii=False, separators=(",", ":"))
    os.replace(temporary, CACHE_FILE)


def _translate_batch(titles: list[str]) -> dict[str, str]:
    marked = "\n".join(f"⟦n{index}⟧ {title}" for index, title in enumerate(titles))
    body = urllib.parse.urlencode({
        "client": "gtx",
        "sl": "auto",
        "tl": "zh-CN",
        "dt": "t",
        "q": marked,
    }).encode()
    request = urllib.request.Request(
        TRANSLATE_URL,
        data=body,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        },
    )
    output = ""
    for attempt in range(RETRIES + 1):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                payload = json.load(response)
            output = "".join(
                str(segment[0])
                for segment in payload[0]
                if isinstance(segment, list) and segment and segment[0]
            )
            break
        except (OSError, ValueError, TypeError, IndexError):
            if attempt < RETRIES:
                time.sleep(0.4 * (attempt + 1))
    if not output:
        return {}

    matches = re.findall(r"⟦n(\d+)⟧\s*(.*?)(?=\n?⟦n\d+⟧|$)", output, flags=re.S)
    by_id = {int(index): re.sub(r"\s+", " ", value).strip() for index, value in matches}
    translated = {}
    for index, title in enumerate(titles):
        value = by_id.get(index, "")
        if _has_chinese(value) and len(value) <= 240:
            translated[title] = value
    return translated


def apply_chinese_titles(industries: list[dict], *, translate_missing: bool) -> int:
    cache = _load_cache()
    missing: list[str] = []
    seen: set[str] = set()
    applied = 0
    for industry in industries:
        for index, item in enumerate(industry.get("items") or []):
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            if _has_chinese(title):
                if item.get("zh") != title:
                    item["zh"] = title
                    applied += 1
            elif cache.get(title):
                value = cache[title]
                if item.get("zh") != value:
                    item["zh"] = value
                    applied += 1
            elif translate_missing and index < PER_INDUSTRY_LIMIT and title not in seen:
                seen.add(title)
                missing.append(title)

    if missing:
        batches = [missing[index:index + BATCH_SIZE] for index in range(0, len(missing), BATCH_SIZE)]
        with ThreadPoolExecutor(max_workers=WORKERS) as executor:
            for result in executor.map(_translate_batch, batches):
                if result:
                    cache.update(result)
                    _save_cache(cache)

    for industry in industries:
        for item in industry.get("items") or []:
            title = str(item.get("title") or "").strip()
            if title and cache.get(title):
                value = cache[title]
                if item.get("zh") != value:
                    item["zh"] = value
                    applied += 1
    return applied
