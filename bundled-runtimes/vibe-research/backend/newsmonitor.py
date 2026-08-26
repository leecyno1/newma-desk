"""Deterministic, lightweight news monitoring for the Research news radar.

It turns raw RSS rows into event clusters and exposes reporting tone, coverage
velocity, source spread, explicit verification cues, and risk/opportunity
signals. These labels are monitoring aids, not truth judgements or investment
recommendations.
"""

from __future__ import annotations

import html
import math
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from hashlib import sha1


_POSITIVE_TERMS = (
    "approval", "approved", "beat", "breakthrough", "expand", "gain", "growth",
    "improve", "profit", "recover", "rise",
    "surge", "win", "上调", "上涨", "中标", "创新高", "增长", "扩产", "批准",
    "改善", "盈利", "突破", "获批", "达成",
)
_NEGATIVE_TERMS = (
    "attack", "ban", "breach", "collapse", "crisis", "delay", "drop",
    "failure", "fall", "fraud", "hack", "investigation", "lawsuit", "layoff",
    "loss", "miss", "outage", "plunge", "risk", "sanction", "shortage",
    "warning", "下调", "下跌", "中断", "亏损", "事故", "危机", "召回", "失败",
    "延迟", "漏洞", "调查", "裁员", "诉讼", "违约", "风险", "制裁",
    "job cuts", "production cut", "cuts forecast", "cuts outlook", "recalled", "recalls",
)
_RISK_TERMS = _NEGATIVE_TERMS + (
    "constraint", "constraints", "default", "escalation", "explosion", "hostage",
    "missile", "narrowing", "probe", "strain", "strains", "strike",
    "war", "冲突", "爆炸", "禁令", "导弹", "战争", "监管处罚",
    "冲突升级", "局势升级", "风险升级", "战争升级", "cutting production",
)
_OPPORTUNITY_TERMS = _POSITIVE_TERMS + (
    "adoption", "demand", "funding", "innovation", "launch", "order",
    "partnership", "订单", "需求", "渗透率", "商业化", "量产", "技术验证",
    "签约",
)
_VERIFICATION_TERMS = {
    "unverified": (
        "alleged", "claimed", "claims", "reportedly", "rumor", "rumors", "rumored",
        "rumour", "rumours", "rumoured", "unconfirmed",
        "unverified", "传闻", "据称", "未经证实", "尚未证实", "网传", "疑似",
        "声称", "宣称",
    ),
    "denial": (
        "debunk", "denied", "denies", "deny", "false claim", "hoax", "refute",
        "不实", "否认", "假消息", "虚假信息", "辟谣", "驳斥",
    ),
    "correction": (
        "author correction", "corrected report", "correction notice", "retract",
        "retracted", "updated account",
        "修正", "撤回报道", "撤稿", "更正", "纠正",
    ),
    "reversal": (
        "backtracked", "backtracking", "reversal", "reverse course", "u-turn",
        "walks back",
        "反转", "改口", "撤销决定", "推翻此前", "立场逆转",
    ),
}

_CONCEPT_ALIASES: dict[str, tuple[str, ...]] = {
    "ai": ("artificial intelligence", "generative ai", "large language model", "人工智能", "大模型", "llm"),
    "chips": ("semiconductor", "chip", "gpu", "半导体", "芯片"),
    "memory": ("hbm", "dram", "nand", "memory chip", "存储芯片", "存储器"),
    "robotics": ("robot", "robotics", "automation", "机器人", "自动化"),
    "ev": ("electric vehicle", "ev", "新能源汽车", "电动车"),
    "battery": ("battery", "lithium", "电池", "锂电"),
    "solar": ("solar", "photovoltaic", "光伏", "太阳能"),
    "energy": ("energy", "power grid", "能源", "电力", "电网"),
    "biotech": ("biotech", "biotechnology", "biopharma", "生物科技", "生物医药"),
    "drug": ("drug", "therapy", "clinical trial", "medicine", "药物", "疗法", "临床试验"),
    "space": ("space", "rocket", "satellite", "lunar", "航天", "火箭", "卫星", "月球"),
    "cyber": ("cyberattack", "cyber attack", "ransomware", "vulnerability", "网络攻击", "勒索软件", "漏洞"),
    "rates": ("interest rate", "rate cut", "rate hike", "利率", "降息", "加息"),
    "inflation": ("inflation", "cpi", "通胀", "消费者价格"),
    "fed": ("federal reserve", "fed", "美联储"),
    "gold": ("gold", "黄金"),
    "oil": ("oil", "crude", "petroleum", "原油", "石油"),
    "tariff": ("tariff", "trade barrier", "关税", "贸易壁垒"),
    "sanctions": ("sanction", "export control", "制裁", "出口管制"),
    "earnings": ("earnings", "revenue", "profit", "财报", "营收", "利润"),
    "supply_chain": ("supply chain", "shipment", "inventory", "供应链", "出货", "库存"),
}
_CONCEPT_LABELS = {
    "ai": "人工智能", "chips": "半导体", "memory": "存储", "robotics": "机器人",
    "ev": "新能源车", "battery": "电池", "solar": "光伏", "energy": "能源",
    "biotech": "生物医药", "drug": "药物研发", "space": "航天", "cyber": "网络安全",
    "rates": "利率", "inflation": "通胀", "fed": "美联储", "gold": "黄金",
    "oil": "原油", "tariff": "关税", "sanctions": "制裁", "earnings": "财报",
    "supply_chain": "供应链",
}
_DISTINCTIVE_CONCEPTS = set(_CONCEPT_ALIASES) - {"ai", "energy", "earnings", "supply_chain"}
_TOPIC_GENERIC_TOKENS = {
    "artificial", "intelligence", "generative", "model", "models", "startup", "startups",
    "biotech", "biopharma", "biotechnology", "drug", "drugs", "therapy", "trial",
    "energy", "power", "solar", "solar-plus-storage", "storage", "battery", "project", "grid",
    "semiconductor", "semiconductors", "chip", "chips", "memory",
    "rocket", "satellite", "satellites", "launch", "launches", "launched", "space",
    "cyber", "security", "hacker", "hackers", "attack", "attacks", "exploit", "exploits",
    "vulnerability", "vulnerabilities", "windows", "system", "access", "zero-day",
    "market", "markets", "price", "prices", "growth", "industry", "global", "world",
    "人工智", "工智能", "生物医", "物医药", "半导体", "新能源", "机器人",
    "网络安", "络安全", "科技", "市场", "行业", "全球",
}
_EVENT_GENERIC_TOKENS = {
    "acquires", "acquisition", "alleged", "announces", "author", "charges",
    "australia", "bess", "chinese", "commercial", "completes", "correction",
    "data", "finds", "fraud", "flaw", "flaws", "gain",
    "introduces", "journal", "launches", "million", "months", "operations",
    "outlines", "patches", "project", "report", "reports", "science", "scientists",
    "share", "starts", "street", "study", "tech", "today", "turn", "unveils",
    "wall", "wednesday", "year", "years", "your", "moon",
}
_STOPWORDS = {
    "about", "after", "again", "also", "amid", "been", "before", "business",
    "company", "could", "from", "have", "into", "latest", "market", "more",
    "news", "report", "reports", "said", "says", "that", "their", "there",
    "these", "they", "this", "today", "under", "with", "would", "一个", "公司",
    "关于", "发布", "市场", "最新", "目前", "相关", "表示", "进行", "以及", "报告",
}
_SOURCE_GROUP_LABELS = {
    "official": "官方 / 机构",
    "research": "研究 / 专业媒体",
    "community": "社区 / 聚合",
    "mainstream": "综合 / 财经媒体",
}
_PROMOTIONAL_TITLE = re.compile(
    r"\b(?:coupon|promo code|discount|freebies|savings|app deals|best deals|daily deals|sale with)\b|"
    r"优惠券|促销码|折扣|优惠|好价",
    re.I,
)
_ROUNDUP_TITLE = re.compile(
    r"\b(?:daily|roundup|digest|newsletter)\b|早报|晚报|日报|周报|一周回顾|App\+1",
    re.I,
)
_GUIDE_TITLE = re.compile(
    r"^(?:how to|how .*\b(?:improve|build|choose)|your guide to|a guide to)\b|指南|教程|一文读懂",
    re.I,
)
_MATERIAL_EVENT_TITLE = re.compile(
    r"\b(?:earnings|revenue|profit|acquisition|acquires|funding|approval|approved|tariff|recall|recalls|breach|"
    r"vulnerability|contract|capacity|production|layoff|bankruptcy|default|outage|investigation|lawsuit|sanction)\b|"
    r"财报|营收|净利|利润|同比|环比|收购|并购|融资|批准|获批|关税|召回|数据泄露|漏洞|中标|订单|产能|投产|量产|"
    r"裁员|破产|违约|停产|减产|事故|调查|起诉|制裁",
    re.I,
)


def _clean(value: object) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _contains(text: str, term: str) -> bool:
    lowered = text.casefold()
    candidate = term.casefold()
    if re.search(r"[\u4e00-\u9fff]", candidate):
        return candidate in lowered
    return re.search(rf"(?<!\w){re.escape(candidate)}(?!\w)", lowered) is not None


def _count_terms(text: str, terms: tuple[str, ...]) -> int:
    return sum(_contains(text, term) for term in terms)


def _matched_terms(text: str, terms: tuple[str, ...]) -> set[str]:
    return {term for term in terms if _contains(text, term)}


def _positive_hits(text: str) -> int:
    hits = _matched_terms(text, _POSITIVE_TERMS)
    lowered = text.casefold()
    if re.search(r"\bgain(?:s|ed|ing)?\s+(?:system\s+)?access\b", lowered):
        hits.discard("gain")
    if re.search(r"\blimit(?:s|ed|ing)?\s+growth\b", lowered):
        hits.discard("growth")
    return len(hits)


def _opportunity_hits(text: str) -> int:
    hits = _matched_terms(text, _OPPORTUNITY_TERMS)
    lowered = text.casefold()
    if re.search(r"\bgain(?:s|ed|ing)?\s+(?:system\s+)?access\b", lowered):
        hits.discard("gain")
    if re.search(r"\blimit(?:s|ed|ing)?\s+growth\b", lowered):
        hits.discard("growth")
    if re.search(r"\b(?:no|not|without)\b.{0,24}\bfunding\b", lowered):
        hits.clear()
    financing_market = re.search(r"融资余额|融资净买入|两融", text)
    if not financing_market and re.search(r"(?:完成|获得|获|宣布|启动|新一轮|\d+轮)融资|融资(?:额|数|超|近|达)", text):
        hits.add("融资")
    if text.rstrip().endswith(("?", "？")):
        hits.clear()
    return len(hits)


def _risk_hits(text: str) -> int:
    hits = _matched_terms(text, _RISK_TERMS)
    if re.search(r"\b(?:turf war|war game)\b", text.casefold()):
        hits.discard("war")
    return len(hits)


def _detect_language(text: str) -> str:
    if re.search(r"[\u4e00-\u9fff]", text):
        return "zh"
    if re.search(r"[\u0400-\u04ff]", text):
        return "ru"
    if re.search(r"[\u0600-\u06ff]", text):
        return "ar"
    lowered = f" {text.casefold()} "
    markers = {
        "fr": (" le ", " la ", " les ", " pour ", " avec ", " après "),
        "es": (" el ", " los ", " las ", " para ", " desde ", " sobre "),
        "de": (" der ", " die ", " das ", " und ", " für ", " mit "),
    }
    scores = {language: sum(marker in lowered for marker in values) for language, values in markers.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] >= 2 else "en"


def _sentiment(text: str) -> tuple[str, float]:
    positive = _positive_hits(text)
    negative = _count_terms(text, _NEGATIVE_TERMS)
    if positive and negative and abs(positive - negative) <= 1:
        return "mixed", round((positive - negative) / max(positive + negative, 2), 3)
    if positive > negative:
        return "positive", round((positive - negative) / max(positive + negative, 2), 3)
    if negative > positive:
        return "negative", round((positive - negative) / max(positive + negative, 2), 3)
    return "neutral", 0.0


def _verification_flags(text: str) -> list[str]:
    return [
        flag for flag, terms in _VERIFICATION_TERMS.items()
        if any(_contains(text, term) for term in terms)
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


def _verification_label(flags: list[str]) -> str:
    labels = {
        "unverified": "含未确认表述",
        "denial": "含否认 / 辟谣",
        "correction": "含更正 / 撤稿",
        "reversal": "含立场反转",
    }
    return "、".join(labels[flag] for flag in flags if flag in labels) or "常规报道"


def _concepts(text: str) -> set[str]:
    return {
        concept for concept, aliases in _CONCEPT_ALIASES.items()
        if any(_contains(text, alias) for alias in aliases)
    }


def _tokens(text: str) -> set[str]:
    lowered = text.casefold()
    tokens = {
        token for token in re.findall(r"[a-z][a-z0-9+.-]{2,}", lowered)
        if token not in _STOPWORDS
    }
    for block in re.findall(r"[\u4e00-\u9fff]{2,16}", lowered):
        if block in _STOPWORDS:
            continue
        if len(block) <= 6:
            tokens.add(block)
        else:
            tokens.update(block[index:index + 3] for index in range(len(block) - 2))
    return tokens


def _source_group(name: str, url: str) -> tuple[str, str]:
    text = f"{name} {url}".casefold()
    if any(token in text for token in (
        ".gov", ".int", "federal reserve", "sec.gov", "nasa.gov", "esa.int",
        "openai.com", "deepmind", "research.google", "university", "academy",
    )):
        group = "official"
    elif any(token in text for token in (
        "arxiv", "research", "science", "nature", "ieee", "review", "analysis",
        "journal", "institute", "laboratory", "lab ",
    )):
        group = "research"
    elif any(token in text for token in (
        "hacker news", "v2ex", "juejin", "reddit", "github", "product hunt",
    )):
        group = "community"
    else:
        group = "mainstream"
    return group, _SOURCE_GROUP_LABELS[group]


def _published(value: object) -> datetime | None:
    try:
        timestamp = int(value or 0)
    except (TypeError, ValueError):
        return None
    if timestamp <= 0:
        return None
    if timestamp > 10_000_000_000:
        timestamp //= 1000
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)


def _stable_id(prefix: str, *values: object) -> str:
    raw = "|".join(str(value or "").casefold().strip() for value in values)
    return f"{prefix}-{sha1(raw.encode('utf-8', 'ignore')).hexdigest()[:12]}"


def _record(item: dict, industry: dict) -> dict | None:
    title = _clean(item.get("title"))
    if not title:
        return None
    summary = _clean(item.get("summary"))
    source = _clean(item.get("source")) or "公开来源"
    url = _clean(item.get("url"))
    text = f"{title} {summary}".strip()
    sentiment, sentiment_score = _sentiment(title)
    flags = _verification_flags(text)
    verification_status = _verification_status(set(flags))
    risk_hits = _risk_hits(title)
    opportunity_hits = _opportunity_hits(title)
    if flags:
        opportunity_hits = 0
    if title.rstrip().endswith(("?", "？")) and abs(sentiment_score) <= 0.5:
        sentiment, sentiment_score = "neutral", 0.0
    if risk_hits and opportunity_hits:
        signal = "mixed"
    elif risk_hits:
        signal = "risk"
    elif opportunity_hits:
        signal = "opportunity"
    else:
        signal = "watch"
    source_group, source_group_label = _source_group(source, _clean(item.get("source_url")))
    language = _detect_language(text)
    item_id = _stable_id("news", source, url or title)
    published = _published(item.get("ts"))
    item.update({
        "id": item_id,
        "industry_key": industry.get("key"),
        "industry_name": industry.get("name"),
        "language": language,
        "sentiment": sentiment,
        "sentiment_score": sentiment_score,
        "source_group": source_group,
        "source_group_label": source_group_label,
        "verification_flags": flags,
        "verification_status": verification_status,
        "verification_label": _verification_label(flags),
        "signal": signal,
        "published_at": published.isoformat().replace("+00:00", "Z") if published else None,
    })
    return {
        "item": item,
        "key": url or f"{source}|{title}".casefold(),
        "title": title,
        "summary": summary,
        "source": source,
        "source_group": source_group,
        "source_group_label": source_group_label,
        "url": url,
        "industry_key": str(industry.get("key") or "other"),
        "industry_name": str(industry.get("name") or "其他"),
        "published": published,
        "language": language,
        "sentiment": sentiment,
        "sentiment_score": sentiment_score,
        "verification_flags": flags,
        "risk_hits": risk_hits,
        "opportunity_hits": opportunity_hits,
        "signal": signal,
        "concepts": _concepts(text),
        "tokens": _tokens(title),
    }


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _topic_anchors(tokens: set[str]) -> set[str]:
    anchors = set()
    for token in tokens:
        if token in _TOPIC_GENERIC_TOKENS or token in _STOPWORDS:
            continue
        if re.fullmatch(r"(?:19|20)\d{2}", token):
            continue
        if re.search(r"[\u4e00-\u9fff]", token) or len(token) >= 4:
            anchors.add(token)
    return anchors


def _event_anchors(tokens: set[str]) -> set[str]:
    return _topic_anchors(tokens) - _EVENT_GENERIC_TOKENS


def _records_match(record: dict, existing: dict, same_industry: bool) -> bool:
    shared_tokens = record["tokens"] & existing["tokens"]
    similarity = _jaccard(record["tokens"], existing["tokens"])
    anchors = _event_anchors(shared_tokens)
    shared_concepts = record["concepts"] & existing["concepts"]
    if same_industry:
        if similarity >= 0.52:
            return True
        if len(anchors) >= 3:
            return True
        if len(anchors) >= 2 and similarity >= 0.15:
            return True
        if anchors and shared_concepts & _DISTINCTIVE_CONCEPTS and similarity >= 0.28:
            return True
    elif len(anchors) >= 3 and shared_concepts & _DISTINCTIVE_CONCEPTS and similarity >= 0.24:
        return True
    return False


def _matches_topic(record: dict, topic: dict) -> bool:
    if record["key"] in topic["keys"]:
        return True
    if any(record["title"].casefold() == existing["title"].casefold() for existing in topic["records"]):
        return True
    same_industry = record["industry_key"] in topic["industries"]
    return _records_match(record, topic["records"][0], same_industry)


def _cluster_records(records: list[dict]) -> list[dict]:
    ordered = sorted(
        records,
        key=lambda record: record["published"] or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    topics: list[dict] = []
    for record in ordered:
        topic = next((candidate for candidate in topics if _matches_topic(record, candidate)), None)
        if topic is None:
            topics.append({
                "records": [record],
                "keys": {record["key"]},
                "industries": {record["industry_key"]},
                "concepts": set(record["concepts"]),
                "tokens": set(record["tokens"]),
            })
            continue
        topic["records"].append(record)
        topic["keys"].add(record["key"])
        topic["industries"].add(record["industry_key"])
        topic["concepts"].update(record["concepts"])
        topic["tokens"].update(record["tokens"])
    return topics


def _velocity(records: list[dict], now: datetime, window_hours: int) -> tuple[int, int, int | None, str]:
    current_start = now - timedelta(hours=window_hours)
    previous_start = current_start - timedelta(hours=window_hours)
    current = sum(bool(record["published"] and current_start <= record["published"] <= now + timedelta(minutes=10)) for record in records)
    previous = sum(bool(record["published"] and previous_start <= record["published"] < current_start) for record in records)
    if previous == 0:
        return current, previous, None if current else 0, "new" if current else "flat"
    growth = round(max(-100, min(999, (current - previous) / previous * 100)))
    return current, previous, growth, "rising" if growth >= 20 else "falling" if growth <= -20 else "flat"


def _source_frames(records: list[dict]) -> list[dict]:
    frames: dict[str, dict] = {}
    for record in records:
        frame = frames.setdefault(record["source_group"], {
            "group": record["source_group"],
            "label": record["source_group_label"],
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
    labels = {"positive": "偏正面", "negative": "偏负面", "neutral": "中性", "mixed": "正负交织"}
    result = []
    for frame in frames.values():
        dominant = max(("positive", "negative", "neutral", "mixed"), key=lambda key: frame[key])
        result.append({
            **{key: value for key, value in frame.items() if key != "sources"},
            "dominant_sentiment": dominant,
            "dominant_label": labels[dominant],
            "sources": sorted(frame["sources"])[:8],
        })
    return sorted(result, key=lambda frame: frame["count"], reverse=True)


def _spread(records: list[dict]) -> tuple[int, str]:
    source_count = len({record["source"] for record in records})
    language_count = len({record["language"] for record in records})
    group_count = len({record["source_group"] for record in records})
    score = min(100, source_count * 12 + language_count * 10 + group_count * 8 + min(18, len(records) * 3))
    level = "单源" if score < 30 else "有限扩散" if score < 55 else "多源扩散" if score < 78 else "广泛传播"
    return score, level


def _ranking_adjustment(primary: dict, records: list[dict], signal: str, verification_status: str) -> tuple[int, list[str]]:
    title = primary["title"]
    adjustment = 0
    reasons = []
    if _PROMOTIONAL_TITLE.search(title):
        adjustment -= 14
        reasons.append("促销内容降权")
    elif _ROUNDUP_TITLE.search(title):
        adjustment -= 8
        reasons.append("汇总内容降权")
    elif _GUIDE_TITLE.search(title):
        adjustment -= 6
        reasons.append("教程内容降权")
    if title.rstrip().endswith(("?", "？")):
        adjustment -= 3
        reasons.append("问答标题降权")
    material_event = bool(_MATERIAL_EVENT_TITLE.search(title))
    if material_event:
        adjustment += 3
        reasons.append("实质事件加权")
    if primary["source_group"] == "official":
        adjustment += 3
        reasons.append("官方来源加权")
    if len({record["source"] for record in records}) == 1 and primary["source_group"] == "community":
        adjustment -= 4
        reasons.append("社区单源降权")
    elif len(records) == 1 and signal == "watch" and verification_status == "常规报道" and not material_event:
        adjustment -= 2
        reasons.append("普通单源降权")
    return adjustment, reasons


def _topic_payload(topic: dict, now: datetime, window_hours: int) -> dict:
    records = topic["records"]
    primary = records[0]
    sources = sorted({record["source"] for record in records})
    languages = sorted({record["language"] for record in records})
    current, previous, growth, velocity_state = _velocity(records, now, window_hours)
    spread_score, spread_level = _spread(records)
    sentiment_counts = Counter(record["sentiment"] for record in records)
    average_sentiment = sum(record["sentiment_score"] for record in records) / len(records)
    if sentiment_counts["positive"] and sentiment_counts["negative"] and abs(sentiment_counts["positive"] - sentiment_counts["negative"]) <= 1:
        sentiment = "mixed"
    else:
        sentiment = max(("positive", "negative", "neutral", "mixed"), key=lambda key: sentiment_counts[key])
    frames = _source_frames(records)
    frame_sentiments = {frame["dominant_sentiment"] for frame in frames if frame["dominant_sentiment"] in {"positive", "negative", "mixed"}}
    framing_divergence = "positive" in frame_sentiments and "negative" in frame_sentiments
    framing_divergence_score = min(100, 52 + max(0, len(frames) - 2) * 12) if framing_divergence else 0
    flags = {flag for record in records for flag in record["verification_flags"]}
    verification_status = _verification_status(flags)
    risk_hits = sum(record["risk_hits"] for record in records)
    opportunity_hits = sum(record["opportunity_hits"] for record in records)
    if risk_hits and opportunity_hits:
        signal = "mixed"
    elif risk_hits:
        signal = "risk"
    elif opportunity_hits:
        signal = "opportunity"
    else:
        signal = "watch"
    latest = max((record["published"] for record in records if record["published"]), default=None)
    age_hours = max(0.0, (now - latest).total_seconds() / 3600) if latest else 72.0
    recency_score = max(0.0, 24.0 - age_hours) / 24.0 * 22
    velocity_bonus = 10 if velocity_state == "new" else max(0, min(18, (growth or 0) / 12))
    heat_score = min(100, round(len(records) * 7 + len(sources) * 10 + recency_score + velocity_bonus))
    raw_attention_score = round(
        heat_score * 0.44
        + spread_score * 0.28
        + (14 if signal in {"risk", "mixed"} else 5 if signal == "opportunity" else 0)
        + (14 if verification_status != "常规报道" else 0)
        + (8 if framing_divergence else 0)
    )
    ranking_adjustment, ranking_reasons = _ranking_adjustment(primary, records, signal, verification_status)
    attention_score = max(0, min(100, raw_attention_score + ranking_adjustment))
    attention_level = "重点" if attention_score >= 68 else "留意" if attention_score >= 44 else "常规"
    concept_labels = [_CONCEPT_LABELS[concept] for concept in sorted(topic["concepts"]) if concept in _CONCEPT_LABELS]
    label = " · ".join(concept_labels[:3]) if len(sources) > 1 and concept_labels else primary["title"][:56]
    reasons = []
    if len(sources) > 1:
        reasons.append(f"{len(sources)} 个独立来源")
    if velocity_state == "new":
        reasons.append("当前窗口新出现")
    elif velocity_state == "rising":
        reasons.append(f"报道增速 +{growth}%")
    elif velocity_state == "falling":
        reasons.append(f"报道增速 {growth}%")
    if verification_status != "常规报道":
        reasons.append(verification_status)
    if framing_divergence:
        reasons.append("来源报道语气分化")
    if not reasons:
        reasons.append("单源常规报道，等待更多证据")
    identity = sorted(topic["keys"])[:4] or [primary["title"][:64]]
    return {
        "id": _stable_id("topic", *identity),
        "label": label,
        "headline": primary["title"],
        "summary": primary["summary"],
        "industry_key": primary["industry_key"],
        "industry_name": primary["industry_name"],
        "mention_count": len(records),
        "current_mentions": current,
        "previous_mentions": previous,
        "heat_velocity_pct": growth,
        "velocity_state": velocity_state,
        "heat_score": heat_score,
        "attention_score": attention_score,
        "raw_attention_score": raw_attention_score,
        "ranking_adjustment": ranking_adjustment,
        "ranking_reasons": ranking_reasons,
        "attention_level": attention_level,
        "spread_score": spread_score,
        "spread_level": spread_level,
        "source_count": len(sources),
        "sources": sources[:12],
        "language_count": len(languages),
        "languages": languages,
        "cross_language": len(languages) > 1,
        "sentiment": sentiment,
        "sentiment_score": round(average_sentiment, 3),
        "sentiment_counts": {key: sentiment_counts[key] for key in ("positive", "negative", "neutral", "mixed")},
        "source_frames": frames,
        "framing_divergence": framing_divergence,
        "framing_divergence_score": framing_divergence_score,
        "verification_status": verification_status,
        "verification_label": _verification_label(sorted(flags)),
        "verification_flags": sorted(flags),
        "signal": signal,
        "signal_reasons": reasons[:4],
        "latest_at": latest.isoformat().replace("+00:00", "Z") if latest else None,
        "keywords": list(dict.fromkeys(concept_labels + sorted(topic["tokens"])))[:8],
        "items": [record["item"] for record in records[:8]],
    }


def _keywords(records: list[dict], top_n: int = 14) -> list[dict]:
    counts: Counter[str] = Counter()
    for record in records:
        for concept in record["concepts"]:
            counts[_CONCEPT_LABELS.get(concept, concept)] += 2
        for token in record["tokens"]:
            if token not in _STOPWORDS and (any(character.isdigit() for character in token) or len(token) >= 5):
                counts[token] += 1
    return [{"keyword": keyword, "count": count} for keyword, count in counts.most_common(top_n)]


def build_news_monitor(
    industries: list[dict],
    *,
    now: datetime | None = None,
    window_hours: int = 12,
    max_topics: int = 80,
) -> dict:
    analysis_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    records: list[dict] = []
    seen: set[str] = set()
    for industry in industries:
        for item in industry.get("items") or []:
            record = _record(item, industry)
            if record is None:
                continue
            exact_key = f"{record['source']}|{record['key']}"
            if exact_key in seen:
                continue
            seen.add(exact_key)
            records.append(record)

    if not records:
        return {
            "summary": {
                "analyzed_items": 0, "topic_count": 0, "source_count": 0,
                "heat_velocity_pct": 0, "velocity_state": "flat",
                "attention_topic_count": 0, "risk_topic_count": 0,
                "opportunity_topic_count": 0, "flagged_topic_count": 0,
                "divergent_topic_count": 0, "spread_score": 0,
                "sentiment": {"positive": 0, "negative": 0, "neutral": 0, "mixed": 0, "net_score": 0},
            },
            "topics": [], "keywords": [], "source_frames": [],
            "method": "lightweight-lexicon-and-event-clustering",
            "caveat": "情绪表示报道语气，核验提示只识别显式措辞，不判定真伪。",
            "timestamp": analysis_time.isoformat().replace("+00:00", "Z"),
        }

    current, previous, growth, velocity_state = _velocity(records, analysis_time, window_hours)
    topics = [_topic_payload(topic, analysis_time, window_hours) for topic in _cluster_records(records)]
    topics.sort(key=lambda topic: (topic["attention_score"], topic["heat_score"], topic["spread_score"]), reverse=True)
    sentiment_counts = Counter(record["sentiment"] for record in records)
    net_score = round(sum(record["sentiment_score"] for record in records) / len(records) * 100)
    average_spread = round(sum(topic["spread_score"] for topic in topics) / len(topics)) if topics else 0
    return {
        "summary": {
            "analyzed_items": len(records),
            "topic_count": len(topics),
            "source_count": len({record["source"] for record in records}),
            "language_count": len({record["language"] for record in records}),
            "current_mentions": current,
            "previous_mentions": previous,
            "heat_velocity_pct": growth,
            "velocity_state": velocity_state,
            "window_hours": window_hours,
            "attention_topic_count": sum(topic["attention_score"] >= 44 for topic in topics),
            "risk_topic_count": sum(topic["signal"] in {"risk", "mixed"} for topic in topics),
            "opportunity_topic_count": sum(topic["signal"] in {"opportunity", "mixed"} for topic in topics),
            "rising_topic_count": sum(topic["velocity_state"] in {"new", "rising"} for topic in topics),
            "flagged_topic_count": sum(topic["verification_status"] != "常规报道" for topic in topics),
            "divergent_topic_count": sum(topic["framing_divergence"] for topic in topics),
            "cross_language_topic_count": sum(topic["cross_language"] for topic in topics),
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
        "topics": topics[:max_topics],
        "keywords": _keywords(records),
        "source_frames": _source_frames(records),
        "method": "lightweight-lexicon-and-event-clustering",
        "caveat": "情绪表示报道语气；热度表示时间、来源和报道数量；核验提示仅识别显式措辞，不判定真伪。",
        "timestamp": analysis_time.isoformat().replace("+00:00", "Z"),
    }
