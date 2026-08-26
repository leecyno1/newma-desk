#!/usr/bin/env python3
from __future__ import annotations

import re


_DIGITS = "零一二三四五六七八九"
_SMALL_UNITS = ("", "十", "百", "千")
_SECTION_PREFIX = re.compile(r"(?m)^(\s*)0([1-9])(?=\s|[、.．:：])")
_YEAR = re.compile(r"(?<!\d)((?:19|20)\d{2})\s*年")
_DATE = re.compile(r"(?<!\d)(\d{1,2})\s*月\s*(\d{1,2})\s*日")
_PERCENT = re.compile(r"(?<![\w.])(-?\d+(?:\.\d+)?)\s*%")
_MODEL_NUMBER = re.compile(r"\b([A-Za-z])\s*(\d{2,4})\b")
_QUANTITY = re.compile(
    r"(?<![\w.])(\d+(?:\.\d+)?)\s*(万亿美元|亿美元|万亿|万片|万|亿|次|天|年|家|颗|条|个|项)"
)


def integer_to_chinese(value: int) -> str:
    if value == 0:
        return "零"
    if value < 0:
        return "负" + integer_to_chinese(-value)
    if value >= 10000:
        high, low = divmod(value, 10000)
        suffix = "万" + ("零" if 0 < low < 1000 else "") + (integer_to_chinese(low) if low else "")
        return integer_to_chinese(high) + suffix

    parts: list[str] = []
    pending_zero = False
    for power in range(3, -1, -1):
        divisor = 10**power
        digit, value = divmod(value, divisor)
        if digit:
            if pending_zero and parts:
                parts.append("零")
            if not (digit == 1 and power == 1 and not parts):
                parts.append(_DIGITS[digit])
            parts.append(_SMALL_UNITS[power])
            pending_zero = False
        elif parts and value:
            pending_zero = True
    return "".join(parts)


def number_to_chinese(value: str) -> str:
    negative = value.startswith("-")
    clean = value[1:] if negative else value
    if "." in clean:
        whole, fraction = clean.split(".", 1)
        spoken = integer_to_chinese(int(whole)) + "点" + "".join(_DIGITS[int(char)] for char in fraction)
    else:
        spoken = integer_to_chinese(int(clean))
    return "负" + spoken if negative else spoken


def year_to_chinese(value: str) -> str:
    return "".join(_DIGITS[int(char)] for char in value)


def normalize_tts_text(text: str) -> str:
    """Convert display-oriented numerals into natural Mandarin TTS wording."""

    normalized = str(text or "").strip()
    normalized = _SECTION_PREFIX.sub(lambda match: f"{match.group(1)}第{integer_to_chinese(int(match.group(2)))}", normalized)
    normalized = _DATE.sub(
        lambda match: f"{integer_to_chinese(int(match.group(1)))}月{integer_to_chinese(int(match.group(2)))}日",
        normalized,
    )
    normalized = _YEAR.sub(lambda match: f"{year_to_chinese(match.group(1))}年", normalized)
    normalized = _PERCENT.sub(
        lambda match: ("负百分之" + number_to_chinese(match.group(1)[1:]))
        if match.group(1).startswith("-")
        else "百分之" + number_to_chinese(match.group(1)),
        normalized,
    )
    normalized = _MODEL_NUMBER.sub(
        lambda match: f"{match.group(1).upper()} {integer_to_chinese(int(match.group(2)))}",
        normalized,
    )
    normalized = _QUANTITY.sub(lambda match: number_to_chinese(match.group(1)) + match.group(2), normalized)
    return re.sub(r"[ \t]+", " ", normalized)
