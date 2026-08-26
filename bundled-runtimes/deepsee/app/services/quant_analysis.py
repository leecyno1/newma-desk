from __future__ import annotations

from typing import Any


def _as_str_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, (str, int, float)):
        return [str(value)]
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for x in value:
        if x is None:
            continue
        s = str(x).strip()
        if not s:
            continue
        out.append(s)
    return out


def _dedupe_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def _percent(part: int, total: int) -> int:
    if total <= 0:
        return 0
    return int(round((part / total) * 100))


def normalize_quant(quant: dict | None) -> dict[str, Any]:
    """Validate & normalize model-provided quant block into a safe, deterministic structure.

    Expected input:
      {"topics": [{"topic": str, "bullish_ids": [...], "bearish_ids": [...], "neutral_ids": [...]}]}
    """
    if not isinstance(quant, dict):
        return {"topics": []}
    topics = quant.get("topics")
    if not isinstance(topics, list):
        return {"topics": []}

    norm_topics: list[dict[str, Any]] = []
    for t in topics:
        if not isinstance(t, dict):
            continue
        topic = str(t.get("topic") or "").strip()
        if not topic:
            continue
        bullish = _dedupe_keep_order(_as_str_list(t.get("bullish_ids")))
        bearish = _dedupe_keep_order(_as_str_list(t.get("bearish_ids")))
        neutral = _dedupe_keep_order(_as_str_list(t.get("neutral_ids")))

        # Ensure a single stance per id (avoid double counting); keep precedence bullish > bearish > neutral.
        bullish_set = set(bullish)
        bearish = [x for x in bearish if x not in bullish_set]
        bearish_set = set(bearish)
        neutral = [x for x in neutral if x not in bullish_set and x not in bearish_set]

        # Trim very long lists to keep UI responsive.
        bullish = bullish[:50]
        bearish = bearish[:50]
        neutral = neutral[:50]

        total = len(bullish) + len(bearish) + len(neutral)
        bt = len(bullish)
        br = len(bearish)
        bn = len(neutral)
        norm_topics.append(
            {
                "topic": topic,
                "bullish_ids": bullish,
                "bearish_ids": bearish,
                "neutral_ids": neutral,
                "counts": {"total": total, "bullish": bt, "bearish": br, "neutral": bn},
                "percents": {"bullish": _percent(bt, total), "bearish": _percent(br, total), "neutral": _percent(bn, total)},
            }
        )

    return {"topics": norm_topics}


def _ids_inline(ids: list[str]) -> str:
    # Use #<id> to work with existing frontend badge conversion.
    return " ".join(f"#{x}" for x in ids if x) if ids else "-"


def _tone_cell(percent: int, count: int, cls: str) -> str:
    return f'<span class="quant-tone-{cls}">{percent}% ({count})</span>'


def render_quant_section_markdown(quant: dict[str, Any], *, module: str) -> str:
    topics = quant.get("topics") if isinstance(quant, dict) else None
    if not isinstance(topics, list) or not topics:
        return ""

    lines: list[str] = []
    lines.append("## 量化分析")
    lines.append("")
    lines.append("| 议题 | 样本 | 看好 | 看空 | 中性 |")
    lines.append("| --- | ---: | ---: | ---: | ---: |")
    for t in topics[:12]:
        if not isinstance(t, dict):
            continue
        topic = str(t.get("topic") or "").strip()
        c = t.get("counts") or {}
        p = t.get("percents") or {}
        total = int(c.get("total") or 0)
        b = int(c.get("bullish") or 0)
        r = int(c.get("bearish") or 0)
        n = int(c.get("neutral") or 0)
        bp = int(p.get("bullish") or 0)
        rp = int(p.get("bearish") or 0)
        np = int(p.get("neutral") or 0)
        lines.append(
            "| "
            + f"{topic} | {total} | {_tone_cell(bp, b, 'bullish')} | {_tone_cell(rp, r, 'bearish')} | {_tone_cell(np, n, 'neutral')} |"
        )

    lines.append("")
    return "\n".join(lines).strip() + "\n"
