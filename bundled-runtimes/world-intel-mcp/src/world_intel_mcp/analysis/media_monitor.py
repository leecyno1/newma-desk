"""Lightweight media monitoring derived from existing news and social feeds.

The module is intentionally deterministic and dependency-free. It does not
claim to verify truth or infer political ideology; it surfaces reporting tone,
coverage velocity, cross-language topic overlap, source framing, and explicit
verification cues for a light monitoring dashboard.
"""

from __future__ import annotations

import html
import math
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from hashlib import sha1


_SOURCE_LANGUAGE = {
    "BBC Mundo": "es",
    "DW Español": "es",
    "DW Deutsch": "de",
    "France24 Français": "fr",
    "RFI Français": "fr",
    "UN News Español": "es",
    "UN News Français": "fr",
}

_LANGUAGE_LABELS = {
    "ar": "阿拉伯语",
    "de": "德语",
    "en": "英语",
    "es": "西班牙语",
    "fr": "法语",
    "ru": "俄语",
    "zh": "中文",
    "other": "其他",
}

_CONCEPT_ALIASES: dict[str, tuple[str, ...]] = {
    "ukraine": ("ukraine", "ucrania", "ukraine", "乌克兰"),
    "russia": ("russia", "russie", "rusia", "russland", "俄罗斯"),
    "china": ("china", "chine", "中国"),
    "united_states": ("united states", "u.s.", "usa", "etats-unis", "estados unidos", "美国"),
    "iran": ("iran", "iranian", "伊朗"),
    "israel": ("israel", "israeli", "以色列"),
    "palestine": ("palestine", "palestinian", "palestina", "巴勒斯坦"),
    "gaza": ("gaza", "加沙"),
    "taiwan": ("taiwan", "台海", "台湾"),
    "india": ("india", "inde", "印度"),
    "pakistan": ("pakistan", "巴基斯坦"),
    "sudan": ("sudan", "soudan", "苏丹"),
    "yemen": ("yemen", "yémen", "也门"),
    "syria": ("syria", "syrie", "叙利亚"),
    "korea": ("korea", "corée", "corea", "朝鲜", "韩国", "半岛"),
    "japan": ("japan", "japon", "日本"),
    "europe": ("europe", "europa", "européenne", "欧洲", "欧盟"),
    "africa": ("africa", "afrique", "afrika", "非洲"),
    "hormuz": ("strait of hormuz", "estrecho de hormuz", "détroit d'ormuz", "hormuz", "ormuz", "霍尔木兹"),
    "red_sea": ("red sea", "mer rouge", "mar rojo", "红海"),
    "suez": ("suez", "苏伊士"),
    "black_sea": ("black sea", "mer noire", "mar negro", "黑海"),
    "ceasefire": ("ceasefire", "cease-fire", "truce", "alto el fuego", "cessez-le-feu", "停火"),
    "conflict": ("conflict", "war", "combat", "guerre", "guerra", "krieg", "冲突", "战争", "交火"),
    "missile": ("missile", "rocket attack", "misil", "导弹", "火箭弹"),
    "nuclear": ("nuclear", "nucléaire", "nuklear", "核武", "核动态", "核设施"),
    "sanctions": ("sanction", "sanctions", "sanciones", "制裁"),
    "tariff": ("tariff", "tariffs", "arancel", "关税"),
    "trade": ("trade", "commerce", "comercio", "handel", "贸易"),
    "election": ("election", "elections", "elecciones", "élection", "wahl", "选举", "大选"),
    "protest": ("protest", "demonstration", "manifestation", "抗议", "示威"),
    "cyber": ("cyberattack", "cyber attack", "ransomware", "hack", "网络攻击", "勒索软件"),
    "outage": ("outage", "disruption", "shutdown", "interruption", "中断", "宕机", "停运"),
    "earthquake": ("earthquake", "seisme", "séisme", "terremoto", "地震"),
    "flood": ("flood", "flooding", "inondation", "inundación", "洪水", "洪灾"),
    "wildfire": ("wildfire", "forest fire", "incendie", "山火", "野火"),
    "climate": ("climate", "climat", "klima", "气候", "高温", "热浪"),
    "energy": ("energy", "energie", "energía", "能源"),
    "oil": ("oil", "crude", "petrole", "pétrole", "petróleo", "原油", "石油"),
    "gas": ("natural gas", "lng", "gaz", "天然气"),
    "shipping": ("shipping", "maritime", "cargo", "navire", "航运", "船舶"),
    "ai": ("artificial intelligence", "generative ai", "ai model", "intelligence artificielle", "人工智能", "大模型"),
    "health": ("outbreak", "epidemic", "pandemic", "disease", "épidémie", "疫情", "公共卫生"),
}

_CONCEPT_LABELS = {
    "ukraine": "乌克兰",
    "russia": "俄罗斯",
    "china": "中国",
    "united_states": "美国",
    "iran": "伊朗",
    "israel": "以色列",
    "palestine": "巴勒斯坦",
    "gaza": "加沙",
    "taiwan": "台海",
    "india": "印度",
    "pakistan": "巴基斯坦",
    "sudan": "苏丹",
    "yemen": "也门",
    "syria": "叙利亚",
    "korea": "朝鲜半岛",
    "japan": "日本",
    "europe": "欧洲",
    "africa": "非洲",
    "hormuz": "霍尔木兹海峡",
    "red_sea": "红海",
    "suez": "苏伊士",
    "black_sea": "黑海",
    "ceasefire": "停火",
    "conflict": "冲突",
    "missile": "导弹",
    "nuclear": "核动态",
    "sanctions": "制裁",
    "tariff": "关税",
    "trade": "贸易",
    "election": "选举",
    "protest": "抗议",
    "cyber": "网络攻击",
    "outage": "中断",
    "earthquake": "地震",
    "flood": "洪灾",
    "wildfire": "山火",
    "climate": "气候",
    "energy": "能源",
    "oil": "原油",
    "gas": "天然气",
    "shipping": "航运",
    "ai": "人工智能",
    "health": "公共卫生",
}

_ANCHOR_CONCEPTS = {
    "ukraine", "russia", "china", "united_states", "iran", "israel",
    "palestine", "gaza", "taiwan", "india", "pakistan", "sudan", "yemen",
    "syria", "korea", "japan", "europe", "africa", "hormuz", "red_sea",
    "suez", "black_sea",
}
_DISTINCTIVE_ANCHORS = {"gaza", "hormuz", "red_sea", "suez", "black_sea", "taiwan"}

_POSITIVE_TERMS = (
    "agreement", "ceasefire", "peace", "rescue", "recovery", "reopen", "restore",
    "growth", "gain", "rise", "rally", "improve", "approval", "breakthrough",
    "success", "deal reached", "de-escalation", "survive", "获救", "停火", "和平",
    "恢复", "重开", "增长", "上涨", "改善", "突破", "达成协议", "降温", "救援",
    "accord", "paix", "reprise", "hausse", "mejora", "acuerdo", "crecimiento",
)
_NEGATIVE_TERMS = (
    "attack", "war", "killed", "death", "dead", "crisis", "collapse", "threat",
    "disruption", "outage", "shutdown", "earthquake", "flood", "wildfire", "sanction",
    "escalation", "strike", "missile", "explosion", "shortage", "loss", "fall", "drop",
    "ban", "hostage", "terror", "violence", "破坏", "袭击", "战争", "死亡", "危机",
    "崩溃", "威胁", "中断", "宕机", "地震", "洪水", "山火", "制裁", "升级", "导弹",
    "爆炸", "短缺", "下跌", "禁令", "恐袭", "暴力", "guerre", "attaque", "mort",
    "crise", "effondrement", "guerra", "ataque", "muerte", "crisis",
)

_VERIFICATION_TERMS = {
    "unverified": (
        "unverified", "unconfirmed", "alleged", "reportedly", "rumor", "rumour",
        "claim without evidence", "据称", "传闻", "网传", "未经证实", "尚未证实", "疑似",
        "no confirmado", "sin confirmar", "non confirmé", "rumeur",
    ),
    "denial": (
        "deny", "denies", "denied", "refute", "false claim", "misinformation", "hoax",
        "debunk", "否认", "驳斥", "辟谣", "不实", "虚假信息", "假消息",
        "dément", "démenti", "niega", "desmiente",
    ),
    "correction": (
        "correction", "corrected", "retract", "retracted", "updated account", "更正",
        "修正", "撤稿", "撤回报道", "纠正", "rectific", "correction publiée",
    ),
    "reversal": (
        "reversal", "reverse course", "backtrack", "u-turn", "walks back", "反转",
        "改口", "立场逆转", "推翻此前", "撤销决定", "revirement", "da marcha atrás",
    ),
}

_STOPWORDS = {
    "about", "after", "again", "also", "amid", "been", "before", "being", "could",
    "from", "have", "into", "more", "most", "news", "over", "says", "said", "that",
    "their", "there", "these", "they", "this", "through", "under", "what", "when",
    "where", "which", "while", "with", "would", "world", "update", "latest", "pour",
    "avec", "dans", "après", "sobre", "desde", "entre", "para", "eine", "einer",
    "adds", "advanced", "better", "can", "center", "company", "features", "heres",
    "latest", "launch", "lineup", "makes", "making", "offers", "report", "reports",
    "series", "takes", "today", "unveils", "using", "watch", "with", "your",
}

_FRAME_GROUPS = {
    "wire": ("mainstream", "主流媒体 / 通讯社"),
    "major": ("mainstream", "主流媒体 / 通讯社"),
    "government": ("official", "官方 / 国际组织"),
    "intl_org": ("official", "官方 / 国际组织"),
    "specialty": ("specialist", "专业媒体 / 研究机构"),
    "think_tank": ("specialist", "专业媒体 / 研究机构"),
    "aggregator": ("commentary", "评论 / 聚合来源"),
    "social": ("social", "公共讨论"),
    "unknown": ("other", "其他来源"),
}


def _clean_text(value: object) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_timestamp(value: object) -> datetime | None:
    if not value:
        return None
    raw = str(value).strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(raw)
        except (TypeError, ValueError, OverflowError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalise_language(value: object) -> str:
    raw = str(value or "").strip().lower()
    aliases = {
        "arabic": "ar", "german": "de", "english": "en", "spanish": "es",
        "french": "fr", "russian": "ru", "chinese": "zh", "mandarin": "zh",
    }
    if raw in aliases:
        return aliases[raw]
    return raw[:2] if raw[:2] in _LANGUAGE_LABELS else ""


def _detect_language(text: str, source: str, supplied: object = "") -> str:
    language = _normalise_language(supplied)
    if language:
        return language
    if source in _SOURCE_LANGUAGE:
        return _SOURCE_LANGUAGE[source]
    if re.search(r"[\u4e00-\u9fff]", text):
        return "zh"
    if re.search(r"[\u0600-\u06ff]", text):
        return "ar"
    if re.search(r"[\u0400-\u04ff]", text):
        return "ru"
    lowered = f" {text.casefold()} "
    language_markers = {
        "fr": (" le ", " la ", " les ", " des ", " pour ", " avec ", " après ", "é"),
        "es": (" el ", " los ", " las ", " para ", " desde ", " sobre ", "ñ"),
        "de": (" der ", " die ", " das ", " und ", " für ", " mit ", "über"),
    }
    scores = {lang: sum(marker in lowered for marker in markers) for lang, markers in language_markers.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] >= 2 else "en"


def _contains_term(text: str, term: str) -> bool:
    if re.search(r"[\u4e00-\u9fff]", term):
        return term in text
    return re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text) is not None


def _extract_concepts(text: str) -> set[str]:
    lowered = text.casefold()
    return {
        concept
        for concept, aliases in _CONCEPT_ALIASES.items()
        if any(_contains_term(lowered, alias.casefold()) for alias in aliases)
    }


def _tokens(text: str) -> set[str]:
    lowered = text.casefold()
    latin = {
        token for token in re.findall(r"[a-zà-ÿ][a-zà-ÿ0-9]{3,}", lowered)
        if token not in _STOPWORDS
    }
    cjk = set(re.findall(r"[\u4e00-\u9fff]{2,8}", lowered))
    return latin | cjk


def _core_tokens(tokens: set[str]) -> set[str]:
    """Prefer compact entity-like tokens for lightweight topic matching."""
    if len(tokens) <= 6:
        return set(tokens)
    return set(sorted(tokens, key=lambda token: (-len(token), token))[:10])


def _sentiment(text: str) -> tuple[str, float]:
    lowered = text.casefold()
    positive = sum(_contains_term(lowered, term.casefold()) for term in _POSITIVE_TERMS)
    negative = sum(_contains_term(lowered, term.casefold()) for term in _NEGATIVE_TERMS)
    if positive and negative and abs(positive - negative) <= 1:
        return "mixed", round((positive - negative) / max(positive + negative, 2), 3)
    if positive > negative:
        return "positive", round((positive - negative) / max(positive + negative, 2), 3)
    if negative > positive:
        return "negative", round((positive - negative) / max(positive + negative, 2), 3)
    return "neutral", 0.0


def _verification_flags(text: str) -> list[str]:
    lowered = text.casefold()
    return [
        flag for flag, terms in _VERIFICATION_TERMS.items()
        if any(_contains_term(lowered, term.casefold()) for term in terms)
    ]


def _verification_status(flags: set[str]) -> str:
    if "reversal" in flags:
        return "疑似反转"
    if "correction" in flags:
        return "出现纠正"
    if "unverified" in flags and "denial" in flags:
        return "存在争议"
    if "denial" in flags:
        return "出现否认"
    if "unverified" in flags:
        return "待核实"
    return "常规报道"


def _frame_group(tier: str) -> tuple[str, str]:
    return _FRAME_GROUPS.get(tier, _FRAME_GROUPS["unknown"])


def _item_key(source: str, title: str, url: str) -> str:
    return url or f"{source}|{title}".casefold()


def _build_records(news_items: list[dict], social_posts: list[dict]) -> list[dict]:
    records: list[dict] = []
    for kind, items in (("news", news_items), ("social", social_posts)):
        for item in items:
            title = _clean_text(item.get("title"))
            if not title:
                continue
            detail = _clean_text(item.get("summary") or item.get("content"))
            source = _clean_text(item.get("feed_name") or item.get("source") or item.get("subreddit"))
            if kind == "social" and source and not source.startswith("r/"):
                source = f"r/{source}"
            source = source or ("公共讨论" if kind == "social" else "全球新闻源")
            url = _clean_text(item.get("link") or item.get("url"))
            text = f"{title} {detail}".strip()
            sentiment, sentiment_score = _sentiment(text)
            tier = "social" if kind == "social" else _clean_text(item.get("source_tier") or "unknown")
            language = _detect_language(text, source, item.get("language"))
            published = _parse_timestamp(item.get("published") or item.get("created") or item.get("timestamp"))
            score = float(item.get("score") or 0)
            comments = float(item.get("num_comments") or 0)
            records.append({
                "kind": kind,
                "key": _item_key(source, title, url),
                "title": title,
                "detail": detail,
                "source": source,
                "tier": tier,
                "category": _clean_text(item.get("category") or ("social" if kind == "social" else "news")),
                "url": url,
                "published": published,
                "language": language,
                "concepts": _extract_concepts(text),
                "tokens": _core_tokens(_tokens(title)),
                "identity_tokens": _core_tokens(_tokens(title)),
                "sentiment": sentiment,
                "sentiment_score": sentiment_score,
                "verification_flags": _verification_flags(text),
                "engagement": max(0, score) + max(0, comments) * 2,
            })
    return records


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _matches_topic(record: dict, topic: dict) -> bool:
    shared = record["concepts"] & topic["concepts"]
    shared_anchors = shared & _ANCHOR_CONCEPTS
    shared_subjects = shared - _ANCHOR_CONCEPTS
    token_similarity = _jaccard(record["tokens"], topic["tokens"])
    topic_records = topic["records"]
    pair_similarity = max(
        (_jaccard(record["tokens"], candidate["tokens"]) for candidate in topic_records),
        default=0.0,
    )
    shared_tokens = record["tokens"] & topic["tokens"]
    if len(shared) >= 2 and shared_anchors:
        return True
    if shared_anchors & _DISTINCTIVE_ANCHORS:
        return True
    if shared_anchors and shared_subjects:
        return True
    if shared and token_similarity >= 0.22:
        return True
    if len(shared_tokens) >= 2 and (pair_similarity >= 0.2 or token_similarity >= 0.18):
        return True
    return pair_similarity >= 0.3 or token_similarity >= 0.32


def _cluster_records(records: list[dict]) -> list[dict]:
    ordered = sorted(records, key=lambda item: item["published"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    topics: list[dict] = []
    for record in ordered:
        topic = next((candidate for candidate in topics if _matches_topic(record, candidate)), None)
        if topic is None:
            topics.append({
                "records": [record],
                "concepts": set(record["concepts"]),
                "tokens": set(record["tokens"]),
                "identity_tokens": set(record["identity_tokens"]),
            })
            continue
        topic["records"].append(record)
        topic["concepts"].update(record["concepts"])
        topic["tokens"].update(record["tokens"])
        for token in record["identity_tokens"]:
            if token in topic["identity_tokens"] or sum(
                token in item["identity_tokens"] for item in topic["records"]
            ) >= 2:
                topic["identity_tokens"].add(token)
    return topics


def _velocity(records: list[dict], now: datetime, window_hours: int) -> tuple[int, int, int | None, str]:
    current_start = now - timedelta(hours=window_hours)
    previous_start = current_start - timedelta(hours=window_hours)
    current = sum(bool(item["published"] and current_start <= item["published"] <= now + timedelta(minutes=10)) for item in records)
    previous = sum(bool(item["published"] and previous_start <= item["published"] < current_start) for item in records)
    if previous == 0:
        growth = None if current > 0 else 0
        state = "new" if current > 0 else "flat"
    else:
        growth = round(max(-100, min(999, (current - previous) / previous * 100)))
        state = "rising" if growth >= 20 else "falling" if growth <= -20 else "flat"
    return current, previous, growth, state


def _media_frames(records: list[dict]) -> list[dict]:
    groups: dict[str, dict] = {}
    for record in records:
        group, label = _frame_group(record["tier"])
        frame = groups.setdefault(group, {
            "group": group,
            "label": label,
            "count": 0,
            "positive": 0,
            "negative": 0,
            "neutral": 0,
            "mixed": 0,
            "sources": set(),
        })
        frame["count"] += 1
        frame[record["sentiment"]] += 1
        frame["sources"].add(record["source"])
    frames = []
    sentiment_labels = {"positive": "偏正面", "negative": "偏负面", "neutral": "中性", "mixed": "正负交织"}
    for frame in groups.values():
        dominant = max(("positive", "negative", "neutral", "mixed"), key=lambda key: frame[key])
        frames.append({
            **{key: value for key, value in frame.items() if key != "sources"},
            "dominant_sentiment": dominant,
            "dominant_label": sentiment_labels[dominant],
            "sources": sorted(frame["sources"])[:8],
        })
    return sorted(frames, key=lambda frame: frame["count"], reverse=True)


def _topic_label(topic: dict) -> str:
    concepts = topic["concepts"]
    ordered = sorted(concepts & _ANCHOR_CONCEPTS) + sorted(concepts - _ANCHOR_CONCEPTS)
    labels = [_CONCEPT_LABELS[concept] for concept in ordered[:3] if concept in _CONCEPT_LABELS]
    return " · ".join(labels) if labels else topic["records"][0]["title"][:42]


def _topic_identity(topic: dict) -> str:
    """Return a stable identity that survives new records joining a topic."""
    anchors = sorted(topic["concepts"] & _ANCHOR_CONCEPTS)
    subjects = sorted(topic["concepts"] - _ANCHOR_CONCEPTS)
    signature = anchors[:2] + subjects[:2]
    if not signature:
        signature = sorted(topic.get("identity_tokens") or topic["tokens"])[:5]
    if not signature:
        signature = [topic["records"][0]["title"].casefold()[:80]]
    return "media-topic-" + sha1("|".join(signature).encode()).hexdigest()[:12]


def _verification_timeline(records: list[dict]) -> list[dict]:
    labels = {
        "unverified": "待核实",
        "denial": "出现否认",
        "correction": "出现纠正",
        "reversal": "疑似反转",
    }
    rank = {"unverified": 0, "denial": 1, "correction": 2, "reversal": 3}
    timeline = []
    ordered = sorted(
        records,
        key=lambda record: record["published"] or datetime.min.replace(tzinfo=timezone.utc),
    )
    for record in ordered:
        for flag in sorted(record["verification_flags"], key=lambda value: rank.get(value, 99)):
            timeline.append({
                "status": labels[flag],
                "flag": flag,
                "timestamp": record["published"].isoformat().replace("+00:00", "Z") if record["published"] else None,
                "source": record["source"],
                "title": record["title"],
                "url": record["url"],
            })
    return timeline[-8:]


def _spread_score(records: list[dict]) -> tuple[int, str]:
    sources = {record["source"] for record in records}
    languages = {record["language"] for record in records}
    groups = {_frame_group(record["tier"])[0] for record in records}
    engagement = sum(record["engagement"] for record in records)
    score = min(40, len(sources) * 8)
    score += min(18, 3 + max(0, len(languages) - 1) * 9)
    score += min(18, len(groups) * 6)
    score += min(18, round(math.log10(engagement + 1) * 7))
    if len(languages) > 1:
        score += 5
    score = min(100, score)
    level = "有限传播" if score < 30 else "区域扩散" if score < 55 else "多源扩散" if score < 75 else "广泛传播"
    return score, level


def _topic_payload(topic: dict, now: datetime, window_hours: int) -> dict:
    records = topic["records"]
    sources = sorted({record["source"] for record in records})
    languages = sorted({record["language"] for record in records})
    tiers = sorted({record["tier"] for record in records})
    current, previous, growth, velocity_state = _velocity(records, now, window_hours)
    spread_score, spread_level = _spread_score(records)
    sentiment_counts = Counter(record["sentiment"] for record in records)
    average_sentiment = sum(record["sentiment_score"] for record in records) / len(records)
    dominant_sentiment = max(("positive", "negative", "neutral", "mixed"), key=lambda key: sentiment_counts[key])
    frames = _media_frames(records)
    frame_sentiments = {frame["dominant_sentiment"] for frame in frames if frame["count"]}
    framing_divergence = len(frames) >= 2 and len(frame_sentiments) >= 2
    framing_divergence_score = min(100, len(frame_sentiments) * 24 + max(0, len(frames) - 1) * 10) if framing_divergence else 0
    flags = {flag for record in records for flag in record["verification_flags"]}
    engagement = round(sum(record["engagement"] for record in records))
    heat_score = min(100, round(
        len(records) * 6
        + len(sources) * 6
        + math.log10(engagement + 1) * 10
        + max(0, growth or 0) / 25
        + current * 2
    ))
    verification_status = _verification_status(flags)
    attention_score = min(100, round(
        heat_score * 0.36
        + spread_score * 0.30
        + max(0, -average_sentiment) * 18
        + (18 if verification_status != "常规报道" else 0)
        + (10 if framing_divergence else 0)
        + (6 if len(languages) > 1 else 0)
    ))
    attention_level = "重点" if attention_score >= 62 else "留意" if attention_score >= 40 else "常规"
    latest = max((record["published"] for record in records if record["published"]), default=None)
    topic_id = _topic_identity(topic)
    keyword_concepts = [_CONCEPT_LABELS.get(concept, concept) for concept in sorted(topic["concepts"])]
    keyword_tokens = sorted(topic.get("identity_tokens") or topic["tokens"])
    return {
        "id": topic_id,
        "label": _topic_label(topic),
        "headline": records[0]["title"],
        "mention_count": len(records),
        "current_mentions": current,
        "previous_mentions": previous,
        "heat_velocity_pct": growth,
        "velocity_state": velocity_state,
        "heat_score": heat_score,
        "attention_score": attention_score,
        "attention_level": attention_level,
        "spread_score": spread_score,
        "spread_level": spread_level,
        "source_count": len(sources),
        "sources": sources[:12],
        "source_tiers": tiers,
        "language_count": len(languages),
        "languages": languages,
        "language_labels": [_LANGUAGE_LABELS.get(language, language) for language in languages],
        "cross_language": len(languages) > 1,
        "sentiment": dominant_sentiment,
        "sentiment_score": round(average_sentiment, 3),
        "sentiment_counts": {key: sentiment_counts[key] for key in ("positive", "negative", "neutral", "mixed")},
        "media_frames": frames,
        "framing_divergence": framing_divergence,
        "framing_divergence_score": framing_divergence_score,
        "verification_status": verification_status,
        "verification_flags": sorted(flags),
        "verification_timeline": _verification_timeline(records),
        "social_engagement": engagement,
        "latest_at": latest.isoformat().replace("+00:00", "Z") if latest else None,
        "keywords": list(dict.fromkeys(keyword_concepts + keyword_tokens))[:8],
        "items": [{
            "key": record["key"],
            "title": record["title"],
            "source": record["source"],
            "url": record["url"],
            "language": record["language"],
            "sentiment": record["sentiment"],
            "published": record["published"].isoformat().replace("+00:00", "Z") if record["published"] else None,
            "kind": record["kind"],
        } for record in records[:8]],
        "_records": records,
    }


def analyze_media_monitor(
    news_items: list[dict] | None,
    social_posts: list[dict] | None = None,
    *,
    now: datetime | None = None,
    window_hours: int = 12,
    max_topics: int = 16,
) -> dict:
    """Build a compact media-monitor snapshot from existing feed records."""
    analysis_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    records = _build_records(news_items or [], social_posts or [])
    if not records:
        return {
            "summary": {
                "analyzed_items": 0,
                "topic_count": 0,
                "heat_velocity_pct": 0,
                "velocity_state": "flat",
                "cross_language_topic_count": 0,
                "flagged_topic_count": 0,
                "reversal_topic_count": 0,
                "spread_score": 0,
                "sentiment": {"positive": 0, "negative": 0, "neutral": 0, "mixed": 0, "net_score": 0},
            },
            "topics": [],
            "media_frames": [],
            "annotations": [],
            "method": "lightweight-lexicon-and-concept-clustering",
            "timestamp": analysis_time.isoformat().replace("+00:00", "Z"),
        }

    current, previous, growth, velocity_state = _velocity(records, analysis_time, window_hours)
    topic_payloads = [_topic_payload(topic, analysis_time, window_hours) for topic in _cluster_records(records)]
    topic_payloads.sort(key=lambda topic: (topic["attention_score"], topic["heat_score"], topic["spread_score"]), reverse=True)
    sentiment_counts = Counter(record["sentiment"] for record in records)
    net_score = round(sum(record["sentiment_score"] for record in records) / len(records) * 100)
    average_spread = round(sum(topic["spread_score"] for topic in topic_payloads) / len(topic_payloads)) if topic_payloads else 0
    annotations = []
    for topic in topic_payloads:
        for record in topic.pop("_records"):
            flags = set(record["verification_flags"])
            annotations.append({
                "key": record["key"],
                "title": record["title"],
                "source": record["source"],
                "url": record["url"],
                "topic_id": topic["id"],
                "sentiment": record["sentiment"],
                "sentiment_score": record["sentiment_score"],
                "language": record["language"],
                "verification_status": _verification_status(flags),
                "verification_flags": sorted(flags),
                "heat_velocity_pct": topic["heat_velocity_pct"],
                "velocity_state": topic["velocity_state"],
                "spread_score": topic["spread_score"],
                "cross_language_topic": topic["cross_language"],
            })

    return {
        "summary": {
            "analyzed_items": len(records),
            "news_items": sum(record["kind"] == "news" for record in records),
            "social_items": sum(record["kind"] == "social" for record in records),
            "source_count": len({record["source"] for record in records}),
            "language_count": len({record["language"] for record in records}),
            "topic_count": len(topic_payloads),
            "current_mentions": current,
            "previous_mentions": previous,
            "heat_velocity_pct": growth,
            "velocity_state": velocity_state,
            "window_hours": window_hours,
            "cross_language_topic_count": sum(topic["cross_language"] for topic in topic_payloads),
            "flagged_topic_count": sum(topic["verification_status"] != "常规报道" for topic in topic_payloads),
            "disputed_topic_count": sum(topic["verification_status"] in {"存在争议", "出现否认"} for topic in topic_payloads),
            "reversal_topic_count": sum(topic["verification_status"] in {"疑似反转", "出现纠正"} for topic in topic_payloads),
            "divergent_topic_count": sum(topic["framing_divergence"] for topic in topic_payloads),
            "attention_topic_count": sum(topic["attention_score"] >= 40 for topic in topic_payloads),
            "spread_score": average_spread,
            "sentiment": {
                "positive": sentiment_counts["positive"],
                "negative": sentiment_counts["negative"],
                "neutral": sentiment_counts["neutral"],
                "mixed": sentiment_counts["mixed"],
                "positive_pct": round(sentiment_counts["positive"] / len(records) * 100),
                "negative_pct": round(sentiment_counts["negative"] / len(records) * 100),
                "neutral_pct": round(sentiment_counts["neutral"] / len(records) * 100),
                "mixed_pct": round(sentiment_counts["mixed"] / len(records) * 100),
                "net_score": net_score,
            },
        },
        "topics": topic_payloads[:max_topics],
        "media_frames": _media_frames(records),
        "annotations": annotations,
        "method": "lightweight-lexicon-and-concept-clustering",
        "caveat": "情绪表示报道语气；传播范围表示来源、语言与互动广度；核验提示仅识别显式措辞，不判定真伪。",
        "timestamp": analysis_time.isoformat().replace("+00:00", "Z"),
    }
