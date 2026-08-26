from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


DEFAULT_DRIVER_RULES_PATH = Path("configs/video/video_editing_driver_rules.json")

DATA_RE = re.compile(r"[\d０-９]+|%|％|万亿|亿美元|人民币|指数|利率|IPO|Capex|GDP|PE|PB", re.I)
DOCUMENT_RE = re.compile(r"公告|文件|新闻|报告|政策|来源|截图|监管|交易所|美联储|央行")
LOGIC_RE = re.compile(r"导致|传导|链条|因为|所以|首先|其次|最后|结构|逻辑|机制")
OBJECTION_RE = re.compile(r"有人说|问题是|是不是|但是|但|然而|反过来|吐槽")
CHAPTER_RE = re.compile(r"第一|第二|第三|第四|壹|贰|叁|肆|回到正题|接下来")
HOOK_RE = re.compile(r"反常识|冲突|问题|不是|真正|为什么|可能|救你|崩|最惨|关键")
RECAP_RE = re.compile(r"总结|所以|归根到底|一句话|结论|最后")


def load_driver_rules(path: Path | None = None) -> dict[str, Any]:
    candidate = path or DEFAULT_DRIVER_RULES_PATH
    if candidate.exists():
        return json.loads(candidate.read_text(encoding="utf-8"))
    return {
        "schema_version": "dasheng.video_editing_driver_rules.fallback",
        "shot_selection_weights": {
            "evidence_need": 0.34,
            "attention_debt": 0.18,
            "trust_debt": 0.16,
            "cognitive_load": 0.14,
            "novelty": 0.1,
            "platform_readability": 0.08,
        },
    }


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def has_data_signal(text: str) -> bool:
    return bool(DATA_RE.search(text))


def has_document_signal(text: str) -> bool:
    return bool(DOCUMENT_RE.search(text))


def classify_beat(text: str, *, scene_type: str | None = None, index: int = 1) -> str:
    if scene_type == "hook":
        return "hook"
    if scene_type == "outro" or RECAP_RE.search(text):
        return "recap"
    if scene_type == "table" or has_data_signal(text):
        return "evidence_data"
    if scene_type == "image" or has_document_signal(text):
        return "evidence_document"
    if CHAPTER_RE.search(text):
        return "chapter"
    if LOGIC_RE.search(text):
        return "logic_chain"
    if OBJECTION_RE.search(text):
        return "objection"
    if (HOOK_RE.search(text) or index == 1) and index <= 2:
        return "hook"
    return "claim"


def score_driver(
    text: str,
    *,
    beat_class: str,
    duration: float,
    seconds_since_speaker: float = 0.0,
    seconds_since_evidence: float = 0.0,
    index: int = 1,
    lane: str = "talking_head",
) -> dict[str, float]:
    text_len = len(text)
    evidence_need = 0.25
    if beat_class in {"evidence_data", "evidence_document"}:
        evidence_need = 0.95
    elif beat_class in {"logic_chain", "objection"}:
        evidence_need = 0.68
    elif has_data_signal(text) or has_document_signal(text):
        evidence_need = 0.84

    attention_basis = duration / (4.0 if lane == "talking_head" else 6.0)
    attention_debt = clamp01(0.25 + attention_basis * 0.38 + (index % 4) * 0.07)
    trust_debt = clamp01(seconds_since_speaker / 20.0) if lane == "talking_head" else 0.0
    cognitive_load = clamp01(text_len / 110.0 + (0.22 if has_data_signal(text) else 0.0) + (0.12 if "；" in text or ";" in text else 0.0))
    novelty = clamp01(0.35 + (index % 5) * 0.12)
    if beat_class in {"chapter", "hook", "recap"}:
        novelty = max(novelty, 0.72)
    readability = clamp01(1.0 - max(0, text_len - 52) / 120.0)
    if beat_class in {"evidence_data", "evidence_document"} and seconds_since_evidence > 30:
        evidence_need = 1.0

    return {
        "evidence_need": round(evidence_need, 3),
        "attention_debt": round(attention_debt, 3),
        "trust_debt": round(trust_debt, 3),
        "cognitive_load": round(cognitive_load, 3),
        "novelty": round(novelty, 3),
        "platform_readability": round(readability, 3),
    }


def weighted_driver_score(scores: dict[str, float], rules: dict[str, Any] | None = None) -> float:
    weights = (rules or {}).get("shot_selection_weights") or load_driver_rules().get("shot_selection_weights") or {}
    total = 0.0
    weight_total = 0.0
    for key, weight in weights.items():
        total += float(scores.get(key, 0.0)) * float(weight)
        weight_total += float(weight)
    return round(total / weight_total, 3) if weight_total else 0.0


def transition_for_beat(beat_class: str, *, lane: str, duration: float) -> str:
    if beat_class == "hook":
        return "impact_cut"
    if beat_class == "evidence_data":
        return "data_reveal"
    if beat_class == "evidence_document":
        return "push_zoom"
    if beat_class == "logic_chain":
        return "path_highlight"
    if beat_class == "chapter":
        return "chapter_hit"
    if beat_class == "recap":
        return "resolve_fade"
    if lane == "explainer" and duration >= 6:
        return "fade_or_push"
    return "hard_cut"


def audio_for_beat(beat_class: str) -> dict[str, Any]:
    sfx = {
        "hook": "impact_hit",
        "evidence_data": "soft_tick",
        "evidence_document": "paper_whoosh",
        "logic_chain": "path_tick",
        "chapter": "chapter_hit",
        "recap": "resolve_tail",
    }.get(beat_class)
    return {
        "duck_bgm": True,
        "sfx": sfx,
        "voice_priority": "primary",
    }


def talking_head_shot_for_beat(
    beat_class: str,
    scores: dict[str, float],
    *,
    seconds_since_speaker: float,
    index: int,
) -> str:
    if beat_class == "hook":
        return "speaker_anchor"
    if beat_class == "evidence_data":
        return "chart_card"
    if beat_class == "evidence_document":
        return "document_zoom"
    if seconds_since_speaker >= 16 and beat_class not in {"evidence_data", "evidence_document"}:
        return "speaker_return"
    if beat_class == "logic_chain":
        return "html_logic_overlay"
    if beat_class == "objection":
        return "speaker_full"
    if index % 5 == 0 or scores.get("attention_debt", 0) > 0.72:
        return "broll_with_pip"
    return "claim_closeup"


def explainer_state_for_beat(beat_class: str, *, index: int, seconds_since_evidence: float) -> str:
    if beat_class == "hook":
        return "hook_card"
    if beat_class == "chapter":
        return "chapter_card"
    if beat_class in {"evidence_data", "evidence_document"} or seconds_since_evidence > 35:
        return "evidence_scene"
    if beat_class == "logic_chain":
        return "logic_animation"
    if beat_class == "recap":
        return "recap_card"
    if index % 4 == 0:
        return "cinematic_bridge"
    return "question_setup"
