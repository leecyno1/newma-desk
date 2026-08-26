#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

# 确保 scripts/ 目录在路径中，以便导入 intake 子包
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import requests
from intake.text_utils import (
    clean_text,
    contains_keyword,
    extract_report_links,
    md_cell,
    md_link,
    normalize_slug,
    normalize_text,
    normalize_url,
    sha1_text,
    summarize_title,
)
from intake.wechat_cache import load_wechat_cache, save_wechat_cache
from intake_collectors import collect_simple_intake, merge_news_items
from path_config import get_project_root, get_stage_dir


ROOT = get_project_root()
TIME_FMT = "%Y-%m-%d_%H%M%S"
RUN_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")

PORT_5173 = os.getenv("DASHENG_INTAKE_5173_BASE", "http://127.0.0.1:18000").rstrip("/")
PORT_REPORTS = os.getenv("DASHENG_INTAKE_REPORTS_BASE", "http://127.0.0.1:8080").rstrip("/")
PORT_REPORTS_FALLBACK = os.getenv("DASHENG_INTAKE_REPORTS_FALLBACK", "").rstrip("/")
PORT_8000 = os.getenv("DASHENG_INTAKE_8000_BASE", "http://127.0.0.1:8000").rstrip("/")
PORT_8000_API = f"{PORT_8000}/api/v1"
INTAKE_MODE = os.getenv("DASHENG_INTAKE_MODE", "simple").strip().lower()

WECHAT_FETCH_ROUNDS = int(os.getenv("DASHENG_WECHAT_FETCH_ROUNDS", "3"))
WECHAT_WAIT_SECONDS = int(os.getenv("DASHENG_WECHAT_WAIT_SECONDS", "8"))
WECHAT_MIN_VALID_ITEMS = int(os.getenv("DASHENG_WECHAT_MIN_VALID_ITEMS", "5"))  # 降低阈值从8到5

CURATED_CHANNELS = {
    "表舅是养基大户": "MP_WXS_3860767471",
    "硬核姬老板": "MP_WXS_3908717627",
    "Draco正在VibeCoding": "MP_WXS_3267381402",
    "半导体封测": "MP_WXS_3260051847",
}

PLATFORM_FETCH_LIMITS: dict[str, int] = {
    "x": 100,
    "wb": 100,
    "xhs": 50,
    "douyin": 50,
    "bili": 50,
}

CHANNEL_DISPLAY_NAMES = {
    "x": "X",
    "wb": "微博",
    "xhs": "小红书",
    "douyin": "抖音",
    "bili": "B站",
    "ai_hot": "AI热点",
    "wechat": "公众号",
    "reports": "TrendRadar / Reports",
    "content_research": "自媒体文章",
    "local_chat": "本地聊天记录",
    "news": "合并新闻源",
    "local_news": "本地新闻流",
    "public_news": "公开新闻兜底",
    "public_hot": "公开热榜兜底",
}

CHANNEL_ORDER = [
    "local_chat",
    "news",
    "public_hot",
    "ai_hot",
    "wechat",
    "reports",
    "content_research",
    "x",
    "wb",
    "xhs",
    "douyin",
    "bili",
]

SOURCE_TIER_RULES = {
    "official": ["gov", "government", "新华社", "人民网", "央行", "国务院", "发改委", "外交部", "国家统计局", "fed", "federalreserve", "eia", "opec"],
    "mainstream_media": ["reuters", "bloomberg", "financial times", "wsj", "cnn", "bbc", "cnbc", "澎湃", "财新", "第一财经", "界面", "新华"],
    "platform_hotspot": ["5173/", "trendradar", "douyin", "xhs", "bili", "wb", "x", "ai_hot/", "public/", "public_news/", "local_news/"],
    "self_media": [
        "wechat_curated",
        "wechat_latest",
        "local_mp/",
        "local_media/",
        "公众号",
        "博主",
        "自媒体",
        "local_chat/",
    ],
}

NOISE_PATTERNS = {
    "ad_promotional": ["报名", "优惠", "折扣", "套餐", "招商", "加群", "直播带货", "团购", "课程", "爆单", "趸交", "挪储"],
    "irrelevant_life": [
        "美食", "探店", "穿搭", "vlog", "日常", "情感", "旅游", "宠物",
        "口红", "妆容", "护肤", "粉底", "淡颜", "白开水", "发型", "卷发", "头包脸", "拉伸",
        "减脂", "瘦身", "穿衣", "ootd", "makeup", "lipstick", "skincare", "hair", "fit check",
    ],
    "likely_repost": ["搬运", "合集", "转载", "转发", "二创"],
}

ENTITY_PATTERNS: dict[str, list[str]] = {
    "people": [
        "特朗普", "川普", "Biden", "拜登", "Powell", "鲍威尔", "高市早苗", "泽连斯基", "Putin", "普京",
        "马斯克", "OpenAI", "奥特曼", "黄仁勋", "任正非", "董明珠",
    ],
    "orgs": [
        "美联储", "FED", "FOMC", "OPEC", "OPEC+", "EIA", "UNCTAD", "台积电", "英伟达", "OpenAI", "微软",
        "日本央行", "财政部", "国务院", "外交部", "国家统计局",
    ],
    "countries": [
        "美国", "中国", "日本", "伊朗", "以色列", "俄罗斯", "乌克兰", "沙特", "阿联酋", "欧洲", "中东",
    ],
    "commodities": [
        "黄金", "白银", "原油", "油价", "天然气", "铜", "贵金属",
    ],
    "sectors": [
        "半导体", "芯片", "AI", "人工智能", "算力", "封测", "光刻机", "消费电子", "新能源", "航运", "军工",
    ],
    "policies": [
        "降息", "加息", "再通胀", "制裁", "停火", "关税", "补贴", "宽松", "赤字", "预算",
    ],
}

EVENT_ACTIONS = [
    "降息", "加息", "停火", "制裁", "谈判", "冲突", "复苏", "误判", "反弹", "抛售", "上涨", "下跌", "安装", "发布", "接入",
]

SIGNAL_KEYWORDS = {
    "policy_inflation": ["通胀", "再通胀", "利率", "降息", "加息", "美联储", "鲍威尔"],
    "supply_order": ["原油", "油价", "航运", "运费", "库存", "油轮", "霍尔木兹", "供给", "制裁"],
    "technology_adoption": ["openclaw", "agent", "skill", "workflow", "安装", "自动化", "模型", "接入"],
    "semiconductor_cycle": ["半导体", "芯片", "晶圆", "封测", "算力", "英伟达", "台积电", "gpu"],
    "diplomacy_conflict": ["伊朗", "以色列", "美国", "日本", "特朗普", "高市早苗", "冲突", "外交", "停火"],
    "market_sentiment": ["a股", "基金", "市场", "波动", "风险偏好", "上涨", "下跌", "黄金", "白银"],
}

EDITOR_TOPIC_RULES = [
    ("黄金/白银/贵金属", ["黄金", "白银", "贵金属", "gold", "silver"]),
    ("油价/地缘冲突", ["原油", "油价", "伊朗", "中东", "停火", "霍尔木兹", "战火", "制裁"]),
    ("半导体/国产芯片", ["芯片", "半导体", "gpu", "npu", "cpu", "光刻", "asml", "封测"]),
    ("AI工具/工作流", ["claude", "openclaw", "prompt", "agent", "skill", "vibecoding", "模型", "ai"]),
    ("宏观/市场情绪", ["a股", "股民", "行情", "清仓", "看空", "通胀", "经济", "利率"]),
    ("日本/使馆/外交", ["日本", "使馆", "外交", "军国主义", "自卫队", "高市早苗"]),
]

DYNAMIC_TOKEN_STOPWORDS = {
    "今天", "最新", "继续", "目前", "这个", "那个", "已经", "现在", "我们", "你们", "他们", "大家", "相关", "表示",
    "指出", "显示", "消息", "市场", "内容", "情况", "问题", "影响", "数据", "分析", "视频", "文章", "报道", "热度",
    "platform", "latest", "news", "market", "update", "video", "post", "share", "live", "gm", "btc", "eth",
    "热度代理", "score", "财经", "信息差", "早差", "完整版", "完整干货版", "早报", "日报",
}

CLUSTER_TITLE_NOISE_TOKENS = {
    "bili", "wb", "xhs", "douyin", "reports", "report", "content", "research", "channel",
    "mp", "wechat", "leron", "trendradar", "unknown", "财经", "热度代理", "score",
    "ai", "the", "show", "to", "from", "with", "for", "and",
}

GENERIC_CLUSTER_LABELS = {
    "AI工具/工作流",
    "宏观/市场情绪",
    "其他观察",
}

GENERIC_CLUSTER_TITLE_NORMALIZED = {
    "ai-ai工具-工作流",
    "ai工具-工作流",
    "人工智能",
    "人工智能工具与工作流",
    "宏观-市场情绪",
    "宏观市场情绪",
    "其他观察",
}

SOURCE_FRESHNESS_WEIGHTS = {
    "5173/content_research": 1.57,
    "reports/news": 1.35,
    "ai_hot/hn": 1.68,
    "ai_hot/reddit": 1.62,
    "ai_hot/bili": 1.56,
    "ai_hot/content_research": 1.52,
    "5173/x": 1.0,
    "5173/wb": 1.0,
    "5173/xhs": 0.98,
    "5173/douyin": 0.98,
    "5173/bili": 0.96,
    "8000/wechat_curated": 0.92,
    "8000/wechat_latest": 0.9,
    "local_mp/8001": 1.18,
    "local_media/": 1.16,
    "local_chat/messages": 1.45,
    "local_news/8001": 1.38,
    "public_news/": 1.28,
    "public/": 1.05,
}

SOURCE_TIMELINESS_WEIGHTS = {
    "5173/content_research": 1.57,
    "reports/news": 1.4,
    "ai_hot/hn": 1.72,
    "ai_hot/reddit": 1.64,
    "ai_hot/bili": 1.55,
    "ai_hot/content_research": 1.52,
    "5173/x": 1.0,
    "5173/wb": 1.0,
    "5173/xhs": 0.98,
    "5173/douyin": 0.98,
    "5173/bili": 0.96,
    "8000/wechat_curated": 0.9,
    "8000/wechat_latest": 0.88,
    "local_mp/8001": 1.26,
    "local_media/": 1.22,
    "local_chat/messages": 1.58,
    "local_news/8001": 1.42,
    "public_news/": 1.32,
    "public/": 1.12,
}

SOURCE_AUTHORITY_WEIGHTS = {
    "official": 1.35,
    "mainstream_media": 1.22,
    "platform_hotspot": 0.95,
    "self_media": 0.88,
    "personal_opinion": 0.8,
}

AI_HOT_LIMIT = int(os.getenv("DASHENG_AI_HOT_LIMIT", "10"))
AI_REDDIT_FEEDS = {
    "LocalLLaMA": "https://www.reddit.com/r/LocalLLaMA/.rss",
    "OpenAI": "https://www.reddit.com/r/OpenAI/.rss",
    "ClaudeAI": "https://www.reddit.com/r/ClaudeAI/.rss",
    "singularity": "https://www.reddit.com/r/singularity/.rss",
}
AI_HN_QUERIES = [
    "OpenAI",
    "Anthropic Claude",
    "Llama",
    "AI agents",
    "Vibe Coding",
]
AI_TOPIC_KEYWORDS = [
    "ai", "openai", "anthropic", "claude", "llama", "agent", "agents", "vibe", "coding",
    "prompt", "workflow", "skill", "skills", "模型", "大模型", "智能体", "龙虾", "openclaw",
    "hermes", "copilot", "cursor", "machine learning", "ml", "gpt",
]


@dataclass
class ChannelTaskResult:
    channel: str
    source: str
    label: str
    items: list[dict[str, Any]] = field(default_factory=list)
    total: int = 0
    status: str = "ready"
    attempts: int = 1
    waited_seconds: int = 0
    issues: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


def now() -> datetime:
    return datetime.now().astimezone()


def iso(ts: datetime) -> str:
    return ts.isoformat()


def dump_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def dump_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def get_json(url: str, **kwargs: Any) -> Any:
    response = requests.get(url, timeout=30, **kwargs)
    response.raise_for_status()
    return response.json()


def get_text(url: str, **kwargs: Any) -> str:
    response = requests.get(url, timeout=30, **kwargs)
    response.raise_for_status()
    return response.text


def post_form_json(url: str, data: dict[str, Any]) -> Any:
    response = requests.post(url, data=data, timeout=30)
    response.raise_for_status()
    return response.json()



def ai_keyword_hits(*parts: str) -> int:
    text = normalize_text(*parts)
    return sum(1 for keyword in AI_TOPIC_KEYWORDS if contains_keyword(text, keyword))


def is_ai_topic(*parts: str) -> bool:
    return ai_keyword_hits(*parts) > 0


def extract_atom_entries(xml_text: str, limit: int = 8) -> list[dict[str, str]]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entries: list[dict[str, str]] = []
    for entry in root.findall("atom:entry", ns)[:limit]:
        title = clean_text(entry.findtext("atom:title", default="", namespaces=ns))
        updated = clean_text(entry.findtext("atom:updated", default="", namespaces=ns))
        author = clean_text(entry.findtext("atom:author/atom:name", default="", namespaces=ns))
        link = ""
        for link_node in entry.findall("atom:link", ns):
            href = clean_text(link_node.attrib.get("href", ""))
            if href:
                link = href
                break
        if title and link:
            entries.append({"title": title, "url": link, "updated": updated, "author": author})
    return entries


def resolve_trendradar_base() -> str:
    candidates = [PORT_REPORTS]
    if PORT_REPORTS_FALLBACK:
        candidates.append(PORT_REPORTS_FALLBACK)
    for base in candidates:
        try:
            response = requests.get(f"{base}/api/reports", timeout=8)
            response.raise_for_status()
            return base
        except Exception:
            continue
    raise RuntimeError(f"Reports 端点不可用：{', '.join(candidates)}")


def to_dt_text(value: Any) -> str:
    if value in (None, "", 0):
        return ""
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def parse_datetime_any(value: Any) -> datetime | None:
    if value in (None, "", 0):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc).astimezone()
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value).astimezone()
        except Exception:
            return None
    text = str(value).strip()
    if not text:
        return None
    candidates = [
        text,
        text.replace("Z", "+00:00"),
    ]
    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc).astimezone()
        except Exception:
            pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc).astimezone()
        except Exception:
            continue
    return None


def classify_source_tier(source: str, title: str, payload: dict[str, Any]) -> str:
    payload_parts = [
        source,
        title,
        str(payload.get("author_name") or ""),
        str(payload.get("platform") or ""),
        str(payload.get("mp_name") or ""),
        str(payload.get("channel_name") or ""),
        str(payload.get("source") or ""),
    ]
    text = normalize_text(*payload_parts)
    for tier, keywords in SOURCE_TIER_RULES.items():
        if any(contains_keyword(text, keyword) for keyword in keywords):
            return tier
    return "personal_opinion"


def extract_entities(text: str) -> dict[str, list[str]]:
    cleaned = clean_text(text)
    entities: dict[str, list[str]] = {}
    lowered = cleaned.lower()
    for category, candidates in ENTITY_PATTERNS.items():
        matched: list[str] = []
        for candidate in candidates:
            candidate_lower = candidate.lower()
            if re.search(r"[A-Za-z]", candidate):
                pattern = rf"(?<![A-Za-z0-9]){re.escape(candidate_lower)}(?![A-Za-z0-9])"
                if re.search(pattern, lowered):
                    matched.append(candidate)
            elif candidate_lower in lowered:
                matched.append(candidate)
        if matched:
            entities[category] = sorted(set(matched))
    return entities


def extract_dynamic_tokens(*parts: str) -> list[str]:
    text = clean_text(" ".join(part for part in parts if part))
    tokens = []
    for chunk in re.split(r"[\s,，。！？!?:：;；、/|()\[\]【】《》<>“”\"'—\-]+", text):
        if not chunk:
            continue
        for token in re.findall(r"[\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z0-9\+\-]{1,24}", chunk):
            normalized = token.strip("-+").lower()
            if len(normalized) < 2:
                continue
            if normalized in DYNAMIC_TOKEN_STOPWORDS:
                continue
            if normalized.isdigit():
                continue
            if re.fullmatch(r"[\u4e00-\u9fff]+", normalized) and len(normalized) > 8:
                continue
            if re.fullmatch(r"[a-z0-9\+\-]+", normalized) and len(normalized) > 18:
                continue
            tokens.append(normalized)
    return tokens


def extract_signal_terms(*parts: str) -> list[str]:
    text = normalize_text(*parts)
    hits: list[str] = []
    for keywords in SIGNAL_KEYWORDS.values():
        for keyword in keywords:
            if contains_keyword(text, keyword):
                hits.append(keyword.lower())
    return hits


def extract_signal_families(*parts: str) -> list[str]:
    text = normalize_text(*parts)
    families: list[str] = []
    for family, keywords in SIGNAL_KEYWORDS.items():
        if any(contains_keyword(text, keyword) for keyword in keywords):
            families.append(family)
    return families


def extract_actions(*parts: str) -> list[str]:
    text = normalize_text(*parts)
    return [action for action in EVENT_ACTIONS if action.lower() in text]


def source_weight(source: str, mapping: dict[str, float], fallback: float = 1.0) -> float:
    for key, value in mapping.items():
        if source.startswith(key):
            return value
    return fallback


def pick_editor_labels(*parts: str) -> list[str]:
    text = normalize_text(*parts)
    labels = [label for label, keys in EDITOR_TOPIC_RULES if any(contains_keyword(text, key) for key in keys)]
    return labels or ["其他观察"]


def entity_count_payload(entities: dict[str, list[str]]) -> list[str]:
    flat = []
    for category in ["people", "orgs", "countries", "commodities", "sectors", "policies"]:
        flat.extend(entities.get(category, []))
    return flat


def prioritized_entity_terms(entities: dict[str, list[str]]) -> list[str]:
    ordered: list[str] = []
    for category in ["countries", "commodities", "orgs", "people", "sectors", "policies"]:
        for value in entities.get(category, []):
            lowered = str(value).lower()
            if lowered not in ordered:
                ordered.append(lowered)
    return ordered


def summarize_dynamic_signature(
    title: str,
    summary: str,
    author: str,
    source: str,
    entities: dict[str, list[str]],
    editor_labels: list[str],
) -> dict[str, Any]:
    token_counter: Counter[str] = Counter()
    title_tokens = extract_dynamic_tokens(title)
    summary_tokens = extract_dynamic_tokens(summary)
    author_tokens = extract_dynamic_tokens(author)
    signal_terms = extract_signal_terms(title, summary, author)
    for token in title_tokens:
        token_counter[token] += 3
    for token in summary_tokens:
        token_counter[token] += 2
    for token in author_tokens:
        token_counter[token] += 1
    for token in signal_terms:
        token_counter[token] += 4
    for entity in entity_count_payload(entities):
        token_counter[str(entity).lower()] += 4
    for action in extract_actions(title, summary):
        token_counter[action.lower()] += 3
    for label in editor_labels:
        if label != "其他观察":
            token_counter[label.lower()] += 1

    dominant_tokens = [token for token, _ in token_counter.most_common(8)]
    dominant_actions = extract_actions(title, summary)[:3]
    dominant_entities = entity_count_payload(entities)[:6]
    entity_terms = prioritized_entity_terms(entities)[:2]
    action_terms = [action.lower() for action in dominant_actions[:1]]
    signal_families = extract_signal_families(title, summary, author)[:2]
    label_terms = [normalize_slug(label) for label in editor_labels if label != "其他观察"][:1]
    semantic_terms = entity_terms + signal_families + action_terms + label_terms
    fallback_terms = [
        token for token in dominant_tokens
        if token not in set(semantic_terms)
    ][:2]
    core_terms = semantic_terms[:4]
    if len(core_terms) < 2:
        core_terms = (semantic_terms + fallback_terms)[:4]
    if not core_terms:
        core_terms = label_terms + title_tokens[:2] or ["观察"]

    cluster_key = normalize_slug("-".join(core_terms[:4]))
    return {
        "dynamic_cluster_key": cluster_key,
        "dominant_tokens": dominant_tokens,
        "dominant_actions": dominant_actions,
        "dominant_entities": dominant_entities,
    }


def detect_noise_tags(text: str) -> list[str]:
    lowered = clean_text(text).lower()
    tags = []
    for tag, keywords in NOISE_PATTERNS.items():
        if any(keyword.lower() in lowered for keyword in keywords):
            tags.append(tag)
    if len(lowered) < 18:
        tags.append("low_info_density")
    return sorted(set(tags))


def canonical_channel(source: str) -> str:
    if source.startswith("5173/"):
        return source.split("/", 1)[1]
    if source.startswith("8000/wechat_") or source.startswith("8001/wechat_"):
        return "wechat"
    if source.startswith("reports/"):
        return "reports"
    return "other"


def channel_label(channel: str) -> str:
    return CHANNEL_DISPLAY_NAMES.get(channel, channel)


def build_wechat_issue_summary(curated_articles: dict[str, dict[str, Any]]) -> list[str]:
    issues: list[str] = []
    curated_count = sum(len(payload.get("data", {}).get("list", [])) for payload in curated_articles.values())
    if curated_count < WECHAT_MIN_VALID_ITEMS:
        issues.append(f"定向公众号样本不足：当前 {curated_count} 条，阈值 {WECHAT_MIN_VALID_ITEMS} 条。")
    missing_titles = 0
    for payload in curated_articles.values():
        for item in payload.get("data", {}).get("list", []):
            if not clean_text(str(item.get("title") or "")):
                missing_titles += 1
    if missing_titles:
        issues.append(f"公众号标题缺失 {missing_titles} 条。")
    return issues


def build_dedupe_group_id(title: str, summary: str, url: str, cluster_key: str, entities: dict[str, list[str]], tokens: list[str]) -> str:
    normalized = normalize_url(url)
    if normalized:
        parsed = urlparse(normalized)
        if parsed.netloc:
            return f"url-{sha1_text(f'{parsed.netloc}{parsed.path}')[:16]}"
    meaningful = entity_count_payload(entities)[:2] + tokens[:4]
    if not meaningful:
        meaningful = extract_dynamic_tokens(title, summary)[:4]
    return f"grp-{normalize_slug('-'.join([cluster_key, *meaningful[:4]]))[:48]}"


def truncate_title(title: str, limit: int = 56) -> str:
    title = clean_text(title)
    if len(title) <= limit:
        return title
    return f"{title[: limit - 1]}…"


def compute_excerpt(title: str, summary: str, limit: int = 70) -> str:
    text = clean_text(summary or title)
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1]}…"


TOPIC_TRANSLATION_CACHE: dict[str, str] = {}
TOPIC_FRAGMENT_TRANSLATIONS = {
    "ai": "人工智能",
    "ai工具/工作流": "人工智能工具与工作流",
    "ai工具": "人工智能工具",
    "ai agent": "人工智能代理",
    "ai agents": "人工智能代理",
    "agent": "智能代理",
    "agents": "智能代理",
    "market": "市场",
    "markets": "市场",
    "tech": "科技",
    "technology": "科技",
    "workflow": "工作流",
    "workflows": "工作流",
}
LOW_SIGNAL_ENGLISH_TOPIC_TOKENS = {
    "i",
    "me",
    "my",
    "our",
    "this",
    "that",
    "these",
    "those",
    "visit",
    "visiting",
    "visited",
    "sub",
    "subreddit",
    "thread",
}


def has_chinese_text(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in str(text or ""))


def needs_chinese_topic_translation(text: str) -> bool:
    raw = clean_text(text)
    if not raw:
        return False
    chinese_count = sum(1 for char in raw if "\u4e00" <= char <= "\u9fff")
    latin_count = sum(1 for char in raw if "a" <= char.lower() <= "z")
    return chinese_count == 0 or latin_count > chinese_count


def is_low_signal_english_topic(text: str) -> bool:
    tokens = re.findall(r"[A-Za-z]+", clean_text(text).lower())
    return bool(tokens) and len(tokens) <= 5 and all(token in LOW_SIGNAL_ENGLISH_TOPIC_TOKENS for token in tokens)


def translate_english_to_chinese(text: str) -> str:
    raw = clean_text(text)
    if not raw or not needs_chinese_topic_translation(raw):
        return raw
    cached = TOPIC_TRANSLATION_CACHE.get(raw.lower())
    if cached:
        return cached
    try:
        response = requests.get(
            "https://translate.googleapis.com/translate_a/single",
            params={"client": "gtx", "sl": "en", "tl": "zh-CN", "dt": "t", "q": raw[:240]},
            timeout=4,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        response.raise_for_status()
        payload = response.json()
        translated = "".join(part[0] for part in (payload[0] or []) if part and part[0]).strip()
        if translated and has_chinese_text(translated):
            TOPIC_TRANSLATION_CACHE[raw.lower()] = translated
            return translated
    except Exception:
        pass
    return f"海外市场：{raw}"


def polish_chinese_topic_title(title: str) -> str:
    raw = clean_text(title)
    if not raw:
        return raw

    def normalize_fragment(fragment: str) -> str:
        cleaned = clean_text(fragment)
        translated = TOPIC_FRAGMENT_TRANSLATIONS.get(cleaned.lower(), cleaned)
        translated = re.sub(r"(?<![A-Za-z])AI(?![A-Za-z])", "人工智能", translated)
        translated = re.sub(r"^AI(?=[\u4e00-\u9fff])", "人工智能", translated)
        return translated.replace("AI工具/工作流", "人工智能工具与工作流")

    if "/" not in raw and "|" not in raw:
        return normalize_fragment(raw)

    protected = raw.replace("AI工具/工作流", "AI工具∕工作流").replace("ai工具/工作流", "ai工具∕工作流")
    fragments = [
        normalize_fragment(part.replace("∕", "/"))
        for part in re.split(r"\s*[/|]\s*", protected)
        if clean_text(part)
    ]
    deduped: list[str] = []
    for fragment in fragments:
        if not fragment or fragment in deduped:
            continue
        if any(fragment in existing and len(fragment) <= 4 for existing in fragments if existing != fragment):
            continue
        deduped.append(fragment)
    if deduped and all(not needs_chinese_topic_translation(fragment) for fragment in deduped):
        separator = "、" if all(has_chinese_text(fragment) for fragment in deduped) else " / "
        return truncate_title(separator.join(deduped), 64)
    return truncate_title(" / ".join(deduped or fragments), 64)


def ensure_chinese_topic_title(title_candidate: str, representative_titles: list[str]) -> tuple[str, str]:
    original = clean_text(title_candidate)
    if not needs_chinese_topic_translation(original):
        return polish_chinese_topic_title(original), original
    for title in representative_titles:
        cleaned = clean_text(title)
        if has_chinese_text(cleaned) and not needs_chinese_topic_translation(cleaned):
            return polish_chinese_topic_title(truncate_title(cleaned, 64)), original
    source_text = clean_text(representative_titles[0] if representative_titles else original)
    if is_low_signal_english_topic(source_text or original):
        return "海外社区零散讨论", original
    translated = translate_english_to_chinese(source_text or original)
    return polish_chinese_topic_title(truncate_title(translated, 64)), original


def normalize_hotspot_radar(raw_payload: dict[str, Any]) -> dict[str, Any]:
    radar = raw_payload.get("radar") if isinstance(raw_payload, dict) else {}
    if not isinstance(radar, dict):
        return {}
    try:
        macro_policy_score = float(radar.get("macro_policy_score") or 0.0)
    except (TypeError, ValueError):
        macro_policy_score = 0.0
    return {
        "capture_role": str(radar.get("capture_role") or ""),
        "source_role": str(radar.get("source_role") or ""),
        "macro_policy_score": round(max(0.0, min(macro_policy_score, 1.0)), 4),
        "kept_by": str(radar.get("kept_by") or ""),
    }


def editor_label_names() -> set[str]:
    return {label for label, _ in EDITOR_TOPIC_RULES}


def cluster_title_is_generic(title: str) -> bool:
    cleaned = clean_text(title)
    if not cleaned:
        return True
    normalized = normalize_slug(cleaned)
    labels = editor_label_names()
    normalized_labels = {normalize_slug(label) for label in labels}
    if (
        cleaned in GENERIC_CLUSTER_TITLE_NORMALIZED
        or normalized in GENERIC_CLUSTER_TITLE_NORMALIZED
        or cleaned in labels
        or cleaned in EVENT_ACTIONS
        or normalized in normalized_labels
    ):
        return True
    fragments = [clean_text(part) for part in re.split(r"[/|]+", cleaned) if clean_text(part)]
    if fragments and all(
        fragment in GENERIC_CLUSTER_LABELS
        or fragment in labels
        or normalize_slug(fragment) in GENERIC_CLUSTER_TITLE_NORMALIZED
        or normalize_slug(fragment) in normalized_labels
        for fragment in fragments
    ):
        return True
    tokens = extract_dynamic_tokens(cleaned)
    informative_tokens = [
        token
        for token in tokens
        if token not in CLUSTER_TITLE_NOISE_TOKENS and token not in DYNAMIC_TOKEN_STOPWORDS
    ]
    return len(informative_tokens) <= 1 and any(label in cleaned for label in GENERIC_CLUSTER_LABELS)


def compact_cluster_source_title(title: str, limit: int = 48) -> str:
    cleaned = clean_text(title)
    cleaned = re.sub(r"https?://\S+", "", cleaned)
    cleaned = re.sub(r"[🔥⭐🌈✅❌]+", "", cleaned)
    cleaned = re.sub(r"[（(]20\d{2}年[^）)]*[）)]", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ，,；;。")
    if len(cleaned) <= limit:
        return cleaned
    clauses = [clean_text(part) for part in re.split(r"[。；;！!?]", cleaned) if clean_text(part)]
    if clauses:
        clauses.sort(
            key=lambda part: (
                len(extract_signal_terms(part)),
                len(entity_count_payload(extract_entities(part))),
                -abs(len(part) - 34),
            ),
            reverse=True,
        )
        best = clauses[0]
        if len(best) <= limit + 12:
            cleaned = best
    return truncate_title(cleaned, limit)


def representative_title_quality(title: str, label: str) -> float:
    cleaned = clean_text(title)
    if not cleaned:
        return -999.0
    score = 0.0
    if has_chinese_text(cleaned):
        score += 1.2
    score += min(len(cleaned) / 24.0, 2.2)
    score += min(len(extract_signal_terms(cleaned)), 4) * 0.75
    score += min(len(entity_count_payload(extract_entities(cleaned))), 4) * 0.55
    if label and label != "其他观察" and label not in cleaned:
        score += 0.25
    if any(keyword in cleaned for keyword in ("报名", "欢迎参会", "腾讯会议", "会议号", "直播", "加群")):
        score -= 2.2
    if detect_noise_tags(cleaned):
        score -= 1.4
    if cluster_title_is_generic(cleaned):
        score -= 2.0
    return round(score, 4)


def best_representative_cluster_title(representative_titles: list[str], label: str) -> str:
    candidates = [clean_text(title) for title in representative_titles if clean_text(title)]
    if not candidates:
        return ""
    candidates.sort(key=lambda title: representative_title_quality(title, label), reverse=True)
    return candidates[0]


def build_cluster_title_candidate(
    label: str,
    dominant_entities: list[str],
    dominant_actions: list[str],
    dominant_tokens: list[str],
    representative_titles: list[str],
) -> tuple[str, str]:
    normalized_entities = {item.lower() for item in dominant_entities}
    filtered_tokens = [
        token for token in dominant_tokens
        if token not in normalized_entities
        and token not in CLUSTER_TITLE_NOISE_TOKENS
        and token not in DYNAMIC_TOKEN_STOPWORDS
        and not token.isdigit()
        and len(token) >= 2
    ]
    title_terms: list[str] = []
    title_terms.extend(dominant_entities[:2])
    if label != "其他观察" and label not in GENERIC_CLUSTER_LABELS:
        title_terms.append(label)
    if dominant_actions:
        title_terms.extend(dominant_actions[:1])
    if len(title_terms) < 2:
        title_terms.extend(filtered_tokens[: max(0, 2 - len(title_terms))])

    deduped_title_terms: list[str] = []
    seen_title_terms: set[str] = set()
    for term in title_terms:
        norm = normalize_slug(term)
        if not norm or norm in seen_title_terms:
            continue
        seen_title_terms.add(norm)
        deduped_title_terms.append(term)
    title_candidate = " / ".join(deduped_title_terms[:4]) if deduped_title_terms else label
    representative = best_representative_cluster_title(representative_titles, label)
    if representative and (
        cluster_title_is_generic(title_candidate)
        or representative_title_quality(representative, label) >= representative_title_quality(title_candidate, label) + 1.4
    ):
        title_candidate = compact_cluster_source_title(representative)
    return ensure_chinese_topic_title(title_candidate, representative_titles)


def editorial_relevance_score(item: "SelectedItem") -> float:
    text = normalize_text(item.title, item.summary, item.author, " ".join(item.dynamic_tokens), " ".join(entity_count_payload(item.entities)))
    signal_hits = len(set(extract_signal_terms(item.title, item.summary, item.author)))
    entity_hits = len(entity_count_payload(item.entities))
    label_bonus = 2.2 if any(label != "其他观察" for label in item.editor_labels) else 0.0
    source_bonus = 0.0
    if item.channel == "content_research":
        source_bonus += 2.5
    elif item.channel == "ai_hot":
        source_bonus += 3.2
    elif item.channel == "reports":
        source_bonus += 1.8
    if item.source in {"8000/wechat_curated", "8001/wechat_curated"}:
        source_bonus += 1.6
    elif item.channel == "wechat":
        source_bonus += 0.4
    if item.source_tier in {"official", "mainstream_media"}:
        source_bonus += 0.8
    keyword_bonus = 0.0
    for keywords in SIGNAL_KEYWORDS.values():
        if any(contains_keyword(text, keyword) for keyword in keywords):
            keyword_bonus += 0.65
    radar_score = float((item.hotspot_radar or {}).get("macro_policy_score") or 0.0)
    radar_bonus = min(radar_score, 1.0) * 1.8
    action_bonus = min(len(item.dominant_actions), 2) * 0.35
    noise_penalty = len(item.noise_tags) * 1.35
    generic_penalty = 0.9 if item.topic == "其他观察" and signal_hits == 0 and entity_hits == 0 else 0.0
    score = label_bonus + min(signal_hits, 4) * 0.9 + min(entity_hits, 4) * 0.55 + min(keyword_bonus, 2.6) + radar_bonus + action_bonus + source_bonus - noise_penalty - generic_penalty
    return round(score, 3)


def pick_analysis_items(selected: list["SelectedItem"]) -> list["SelectedItem"]:
    relevant = []
    for item in selected:
        relevance = float(item.raw_heat_signals.get("editorial_relevance") or 0.0)
        cross_channel_hits = int(item.raw_heat_signals.get("cross_channel_hits") or 0)
        cross_source_hits = int(item.raw_heat_signals.get("cross_source_hits") or 0)
        if item.channel == "ai_hot":
            relevant.append(item)
            continue
        if item.heat_score >= 58 and (cross_channel_hits >= 2 or cross_source_hits >= 2):
            relevant.append(item)
            continue
        if item.heat_score >= 62 and item.channel in {"public_news", "local_news", "reports"}:
            relevant.append(item)
            continue
        if relevance >= 2.2:
            relevant.append(item)
            continue
        if item.trendradar_signal and relevance >= 1.4:
            relevant.append(item)
            continue
        if item.source in {"8000/wechat_curated", "8001/wechat_curated"} and relevance >= 1.4:
            relevant.append(item)
            continue
        if item.channel == "content_research" and relevance >= 1.4:
            relevant.append(item)
            continue
    return relevant or selected


@dataclass
class SelectedItem:
    source: str
    channel: str
    title: str
    url: str
    author: str
    published_at: str
    summary: str
    decision: str
    topic: str
    editor_labels: list[str]
    raw_payload: dict[str, Any]
    source_tier: str
    entities: dict[str, list[str]]
    noise_tags: list[str]
    cluster_key: str
    dynamic_tokens: list[str]
    dominant_actions: list[str]
    trendradar_signal: bool
    source_freshness_weight: float
    source_timeliness_weight: float
    source_authority_weight: float
    fetch_status: str = "ok"
    heat_score: float = 0.0
    heat_level: str = "D"
    dedupe_group_id: str = ""
    raw_heat_signals: dict[str, Any] = field(default_factory=dict)
    hotspot_radar: dict[str, Any] = field(default_factory=dict)
    capture_quality: dict[str, Any] = field(default_factory=dict)

    def to_record(self, run_id: str, index: int, generated_at: str) -> dict[str, Any]:
        digest = sha1_text(f"{self.source}|{self.title}|{self.url}")
        engagement_score = (
            self.raw_payload.get("liked_count")
            or self.raw_payload.get("score")
            or self.raw_payload.get("view_count")
            or self.raw_payload.get("read_num")
            or None
        )
        return {
            "meta": {
                "id": f"intake-{run_id.replace('-', '').replace('_', '')}-{index:03d}",
                "object_type": "intake_record",
                "run_id": run_id,
                "version": "4.0.0",
                "status": "ready",
                "generated_by": "run_stage1_intake.py",
                "input_digest": digest,
                "upstream_ids": [],
                "doc_refs": [{"kind": "url", "token": self.source, "url": self.url, "title": self.title}],
                "created_at": generated_at,
                "updated_at": generated_at,
            },
            "record_id": f"intake-{run_id.replace('-', '').replace('_', '')}-{index:03d}",
            "channel": self.channel,
            "source": self.source,
            "url": self.url,
            "publish_time": self.published_at,
            "author_or_account": self.author,
            "source_item_id": digest,
            "source_quality_tier": self.source_tier,
            "title": self.title,
            "summary": self.summary,
            "normalized_text": f"{self.source} | {self.topic} | {self.title} | {self.summary}",
            "dedupe_group_id": self.dedupe_group_id,
            "dedupe_fingerprint": sha1_text(f"{self.cluster_key}|{self.dedupe_group_id}|{self.title[:42]}"),
            "freshness_score": round((self.source_freshness_weight + self.source_timeliness_weight) / 2, 3),
            "engagement_score": engagement_score,
            "raw_heat_signals": self.raw_heat_signals,
            "capture_quality": self.capture_quality,
            "radar": self.hotspot_radar,
            "heat_score": self.heat_score,
            "heat_level": self.heat_level,
            "is_trendradar_source": self.trendradar_signal,
            "fetch_status": self.fetch_status,
            "tags": [self.topic, *self.editor_labels[:3], *entity_count_payload(self.entities)[:4]],
            "noise_tags": self.noise_tags,
            "event_key": self.cluster_key,
            "dynamic_cluster_key": self.cluster_key,
            "editor_labels": self.editor_labels,
            "entities": self.entities,
            "dynamic_tokens": self.dynamic_tokens[:8],
            "dominant_actions": self.dominant_actions[:4],
            "trendradar_signal": self.trendradar_signal,
            "source_freshness_weight": self.source_freshness_weight,
            "source_timeliness_weight": self.source_timeliness_weight,
            "source_authority_weight": self.source_authority_weight,
            "raw_payload": self.raw_payload,
        }


def source_capture_mode(source: str, channel: str) -> str:
    source_value = str(source or "").lower()
    channel_value = str(channel or "").lower()
    if source_value.startswith("local_chat/") or channel_value == "local_chat":
        return "local_chat"
    if source_value.startswith("local_news/") or channel_value == "local_news":
        return "local_news"
    if source_value.startswith("local_mp/"):
        return "local_mp_articles"
    if source_value.startswith("local_media/"):
        return "local_self_media"
    if source_value.startswith("public_news/") or channel_value == "public_news":
        return "public_news"
    if channel_value == "news":
        return "merged_news"
    if source_value.startswith("public/") or channel_value == "public_hot":
        return "public_hot"
    if source_value.startswith("ai_hot/") or channel_value == "ai_hot":
        return "ai_hot"
    if source_value.startswith("reports/"):
        return "legacy_reports"
    if source_value.startswith("5173/"):
        return "legacy_5173"
    if source_value.startswith("8000/"):
        return "legacy_8000"
    if channel_value == "wechat":
        return "wechat_articles"
    if channel_value == "content_research":
        return "self_media"
    return channel_value or "unknown"


def build_capture_quality(
    *,
    source: str,
    channel: str,
    title: str,
    url: str,
    summary: str,
    raw_payload: dict[str, Any],
    fetch_status: str,
) -> dict[str, Any]:
    title_value = clean_text(title)
    url_value = clean_text(url)
    text_for_length = clean_text(f"{title_value} {summary}")
    is_http_url = url_value.startswith(("http://", "https://"))
    is_local_anchor = url_value.startswith("dasheng-local://")
    is_synthetic = url_value.startswith(("dasheng-public-news://", "https://example.invalid/"))
    title_real = bool(title_value) and not title_value.startswith(("http://", "https://", "dasheng-")) and len(title_value) >= 4
    raw_quality = raw_payload.get("capture_quality") if isinstance(raw_payload.get("capture_quality"), dict) else {}
    debug_snapshot_path = (
        raw_quality.get("debug_snapshot_path")
        or raw_payload.get("debug_snapshot_path")
        or raw_payload.get("debug_path")
        or raw_payload.get("snapshot_path")
        or ""
    )
    source_health = "ok" if title_real and (is_http_url or is_local_anchor or not is_synthetic) and fetch_status in {"ok", "ready"} else "weak"
    return {
        "title_real": title_real,
        "content_length": len(text_for_length),
        "has_original_url": is_http_url,
        "has_traceable_anchor": is_http_url or is_local_anchor,
        "source_health": source_health,
        "capture_mode": raw_quality.get("capture_mode") or source_capture_mode(source, channel),
        "fetch_status": fetch_status,
        "debug_snapshot_path": str(debug_snapshot_path),
    }


def build_item(
    *,
    source: str,
    channel: str,
    title: str,
    url: str,
    author: str,
    published_at: str,
    summary: str,
    decision: str,
    raw_payload: dict[str, Any],
    fetch_status: str = "ok",
) -> SelectedItem | None:
    title = clean_text(title)
    url = normalize_url(url)
    if not title or not url:
        return None
    entity_payload = extract_entities(
        " ".join(
            [
                title,
                summary,
                author,
                str(raw_payload.get("author_name") or ""),
                str(raw_payload.get("platform") or ""),
                str(raw_payload.get("mp_name") or ""),
                str(raw_payload.get("channel_name") or ""),
            ]
        )
    )
    editor_labels = pick_editor_labels(title, summary, author)
    noise_tags = detect_noise_tags(f"{title} {summary} {author}")
    tier = classify_source_tier(source, title, raw_payload)
    signature = summarize_dynamic_signature(title, summary, author, source, entity_payload, editor_labels)
    cluster = signature["dynamic_cluster_key"]
    trendradar_signal = source.startswith("reports/")
    hotspot_radar = normalize_hotspot_radar(raw_payload)
    dynamic_tokens = signature["dominant_tokens"]
    dedupe_group_id = build_dedupe_group_id(title, summary, url, cluster, entity_payload, dynamic_tokens)
    raw_heat_signals = {
        "engagement": raw_payload.get("liked_count") or raw_payload.get("score") or raw_payload.get("view_count") or raw_payload.get("read_num") or 0,
        "source_authority_weight": SOURCE_AUTHORITY_WEIGHTS.get(tier, 1.0),
        "source_timeliness_weight": source_weight(source, SOURCE_TIMELINESS_WEIGHTS),
        "source_freshness_weight": source_weight(source, SOURCE_FRESHNESS_WEIGHTS),
        "trendradar_signal": trendradar_signal,
        "hotspot_macro_policy_score": hotspot_radar.get("macro_policy_score", 0.0),
        "hotspot_source_role": hotspot_radar.get("source_role", ""),
    }
    capture_quality = build_capture_quality(
        source=source,
        channel=channel,
        title=title,
        url=url,
        summary=summary,
        raw_payload=raw_payload,
        fetch_status=fetch_status,
    )
    return SelectedItem(
        source=source,
        channel=channel,
        title=title,
        url=url,
        author=author,
        published_at=published_at,
        summary=summary,
        decision=decision,
        topic=editor_labels[0],
        editor_labels=editor_labels,
        raw_payload=raw_payload,
        source_tier=tier,
        entities=entity_payload,
        noise_tags=noise_tags,
        cluster_key=cluster,
        dynamic_tokens=dynamic_tokens,
        dominant_actions=signature["dominant_actions"],
        trendradar_signal=trendradar_signal,
        source_freshness_weight=source_weight(source, SOURCE_FRESHNESS_WEIGHTS),
        source_timeliness_weight=source_weight(source, SOURCE_TIMELINESS_WEIGHTS),
        source_authority_weight=SOURCE_AUTHORITY_WEIGHTS.get(tier, 1.0),
        fetch_status=fetch_status,
        dedupe_group_id=dedupe_group_id,
        raw_heat_signals=raw_heat_signals,
        hotspot_radar=hotspot_radar,
        capture_quality=capture_quality,
    )


def fetch_platform_task(platform: str, limit: int, raw_dir: Path) -> ChannelTaskResult:
    task = ChannelTaskResult(channel=platform, source=f"5173/{platform}", label=channel_label(platform))
    try:
        payload = get_json(f"{PORT_5173}/api/data/latest?platform={platform}&limit={limit}")
        items = payload.get("items", []) or []
        # 强制截断：API可能返回全量数据，这里强制限制数量
        task.items = items[:limit]
        task.total = len(task.items)
        task.status = "ok"
        # 保存截断后的数据
        dump_json(raw_dir / f"mediacrawler_latest_{platform}.json", {"items": task.items, "total": task.total, "original_total": payload.get("total", 0)})
    except Exception as exc:
        task.status = "error"
        task.issues.append(str(exc))
        dump_json(raw_dir / f"mediacrawler_latest_{platform}.json", {"items": [], "total": 0, "error": str(exc)})
    return task


def fetch_content_research_task(raw_dir: Path) -> ChannelTaskResult:
    task = ChannelTaskResult(channel="content_research", source="5173/content_research", label=channel_label("content_research"))
    try:
        # First try to load AI-enhanced topics if available
        ai_enhanced_file = raw_dir / "mediacrawler_topnotes_content_research_ai_enhanced.json"
        if ai_enhanced_file.exists():
            payload = get_json(str(ai_enhanced_file))
            task.items = payload.get("items", []) or []
            task.total = payload.get("total_candidates", 0) or len(task.items)
            task.status = "ok"
            task.meta = {"total_candidates": payload.get("total_candidates", 0), "source": "ai_enhanced"}
            dump_json(raw_dir / "mediacrawler_topnotes_content_research.json", payload)
        else:
            # Fallback to API call
            payload = get_json(f"{PORT_5173}/api/intelligence/top-notes?task_group=content_research&days=1&limit=20")
            task.items = payload.get("items", []) or []
            task.total = payload.get("total_candidates", 0) or len(task.items)
            task.status = "ok"
            task.meta = {"total_candidates": payload.get("total_candidates", 0), "source": "api"}
            dump_json(raw_dir / "mediacrawler_topnotes_content_research.json", payload)
    except Exception as exc:
        task.status = "error"
        task.issues.append(str(exc))
        dump_json(raw_dir / "mediacrawler_topnotes_content_research.json", {"items": [], "total_candidates": 0, "error": str(exc)})
    return task


def fetch_reports_task(trendradar_base: str, raw_dir: Path) -> ChannelTaskResult:
    task = ChannelTaskResult(channel="reports", source="reports/news", label=channel_label("reports"))
    try:
        reports = get_json(f"{trendradar_base}/api/reports")
        # 强制限制reports数量为100条
        reports = reports[:100] if isinstance(reports, list) else reports
        latest_report_html = get_text(f"{trendradar_base}/output/index.html")
        report_links = extract_report_links(latest_report_html, limit=100)
        task.items = report_links
        task.total = len(report_links)
        task.status = "ok"
        task.meta = {"reports_count": len(reports), "html_available": bool(latest_report_html)}
        dump_json(raw_dir / "trendradar_reports.json", reports)
        dump_text(raw_dir / "trendradar_latest_report.html", latest_report_html)
        dump_json(raw_dir / "trendradar_top_links.json", report_links)
    except Exception as exc:
        task.status = "error"
        task.issues.append(str(exc))
        dump_json(raw_dir / "trendradar_reports.json", [])
        dump_text(raw_dir / "trendradar_latest_report.html", "")
        dump_json(raw_dir / "trendradar_top_links.json", [])
    return task


def fetch_wechat_public_channels(raw_dir: Path) -> dict[str, Any]:
    payload = get_json(f"{PORT_8000_API}/wx/public/channels?limit=200&offset=0")
    dump_json(raw_dir / "wemprss_public_channels.json", payload)
    return payload


def fetch_wechat_public_articles(channel_id: str, limit: int = 8, offset: int = 0) -> dict[str, Any]:
    return get_json(f"{PORT_8000_API}/wx/public/channels/{channel_id}/articles?limit={limit}&offset={offset}")


def fetch_wechat_public_article_detail(article_id: str) -> dict[str, Any]:
    return get_json(f"{PORT_8000_API}/wx/articles/{article_id}")


def fetch_ai_hot_task(platform_tasks: dict[str, ChannelTaskResult], content_task: ChannelTaskResult, raw_dir: Path) -> ChannelTaskResult:
    task = ChannelTaskResult(channel="ai_hot", source="ai_hot/aggregate", label=channel_label("ai_hot"))
    reddit_payload: dict[str, Any] = {}
    hn_payload: dict[str, Any] = {}
    candidates: list[dict[str, Any]] = []

    for subreddit, feed_url in AI_REDDIT_FEEDS.items():
        try:
            xml_text = get_text(feed_url, headers={"User-Agent": "Mozilla/5.0 NewmaIntake/1.0"})
            entries = extract_atom_entries(xml_text, limit=6)
            reddit_payload[subreddit] = {"status": "ok", "entries": entries}
            for index, entry in enumerate(entries):
                score_proxy = max(1, 7 - index) * 18
                candidates.append(
                    {
                        "provider": "reddit",
                        "source": "ai_hot/reddit",
                        "title": entry["title"],
                        "url": entry["url"],
                        "author_name": entry.get("author") or f"r/{subreddit}",
                        "created_at": entry.get("updated") or "",
                        "summary": f"Reddit r/{subreddit} 热门讨论",
                        "score": score_proxy,
                        "provider_meta": {"subreddit": subreddit, "rank": index + 1},
                    }
                )
        except Exception as exc:
            reddit_payload[subreddit] = {"status": "error", "error": str(exc), "entries": []}
            task.issues.append(f"reddit/{subreddit}: {exc}")

    for query in AI_HN_QUERIES:
        try:
            payload = get_json(
                f"https://hn.algolia.com/api/v1/search_by_date?query={requests.utils.quote(query)}&tags=story&hitsPerPage=8"
            )
            hits = payload.get("hits", []) or []
            hn_payload[query] = {"status": "ok", "hits": hits[:8]}
            for hit in hits[:8]:
                title = clean_text(str(hit.get("title") or hit.get("story_title") or ""))
                url = clean_text(str(hit.get("url") or hit.get("story_url") or ""))
                if not title or not url or not is_ai_topic(title, url):
                    continue
                points = float(hit.get("points") or 0)
                comments = float(hit.get("num_comments") or 0)
                candidates.append(
                    {
                        "provider": "hn",
                        "source": "ai_hot/hn",
                        "title": title,
                        "url": url,
                        "author_name": hit.get("author") or "Hacker News",
                        "created_at": hit.get("created_at") or "",
                        "summary": f"Hacker News 查询：{query}",
                        "score": round(points * 2.4 + comments * 1.8, 3),
                        "provider_meta": {
                            "query": query,
                            "points": points,
                            "num_comments": comments,
                        },
                    }
                )
        except Exception as exc:
            hn_payload[query] = {"status": "error", "error": str(exc), "hits": []}
            task.issues.append(f"hn/{query}: {exc}")

    for item in platform_tasks.get("bili", ChannelTaskResult(channel="bili", source="5173/bili", label=channel_label("bili"))).items:
        title = item.get("title", "")
        author = item.get("author_name") or "bili"
        if not is_ai_topic(title, author):
            continue
        candidates.append(
            {
                "provider": "bili",
                "source": "ai_hot/bili",
                "title": clean_text(title),
                "url": normalize_url(item.get("url", "")),
                "author_name": author,
                "created_at": to_dt_text(item.get("fetched_at") or item.get("created_at")),
                "summary": summarize_title(title, f"B站 AI 热门；score={item.get('score') or item.get('liked_count') or 0}"),
                "score": float(item.get("score") or item.get("liked_count") or item.get("view_count") or 0),
                "provider_meta": {"platform": "bili"},
            }
        )

    for item in content_task.items:
        title = item.get("title", "")
        if not is_ai_topic(title, item.get("platform") or ""):
            continue
        candidates.append(
            {
                "provider": "content_research",
                "source": "ai_hot/content_research",
                "title": clean_text(title),
                "url": normalize_url(item.get("url", "")),
                "author_name": item.get("platform") or "content_research",
                "created_at": to_dt_text(item.get("created_at")),
                "summary": summarize_title(title, f"content_research；score={item.get('score') or 0}"),
                "score": float(item.get("score") or 0),
                "provider_meta": {"platform": item.get("platform") or "content_research"},
            }
        )

    provider_bonus = {
        "hn": 6.0,
        "reddit": 4.8,
        "bili": 4.0,
        "content_research": 3.7,
    }
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    now_dt = now()
    for row in candidates:
        key = normalize_url(row.get("url", "")) or normalize_slug(row.get("title", ""))
        if not key or key in seen:
            continue
        seen.add(key)
        published_dt = parse_datetime_any(row.get("created_at"))
        if published_dt:
            age_hours = max((now_dt - published_dt).total_seconds() / 3600, 0.0)
            recency = max(0.0, 1.0 - age_hours / 168.0)
        else:
            recency = 0.4
        keyword_score = ai_keyword_hits(row.get("title", ""), row.get("summary", ""), row.get("author_name", ""))
        engagement = math.log1p(max(0.0, float(row.get("score") or 0.0)))
        row["rank_score"] = round(
            provider_bonus.get(row["provider"], 3.0)
            + keyword_score * 0.8
            + engagement * 0.75
            + recency * 3.0,
            4,
        )
        deduped.append(row)

    deduped.sort(key=lambda item: (item["rank_score"], item.get("score") or 0), reverse=True)
    selected_rows = deduped[:AI_HOT_LIMIT]
    task.items = selected_rows
    task.total = len(selected_rows)
    task.status = "ok" if selected_rows else "partial"
    task.meta = {
        "candidate_total": len(deduped),
        "providers": dict(Counter(row["provider"] for row in selected_rows)),
    }
    dump_json(raw_dir / "ai_hot_reddit.json", reddit_payload)
    dump_json(raw_dir / "ai_hot_hn.json", hn_payload)
    return task


def fetch_wechat_task(raw_dir: Path) -> tuple[ChannelTaskResult, dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]]:
    task = ChannelTaskResult(channel="wechat", source="8000/wechat_public", label=channel_label("wechat"))
    channels = {"data": {"total": 0, "list": []}}
    latest_articles = {"data": {"total": 0, "list": []}}
    curated_articles: dict[str, dict[str, Any]] = {}
    for attempt in range(1, WECHAT_FETCH_ROUNDS + 1):
        task.attempts = attempt
        try:
            channels = fetch_wechat_public_channels(raw_dir)
            all_channels = channels.get("data", {}).get("list", []) or []
            wechat_channels = [row for row in all_channels if clean_text(str(row.get("source_platform") or "")).lower() == "wechat"]
            channel_index = {row.get("id"): row for row in wechat_channels if row.get("id")}
            curated_articles = {}
            latest_candidates: list[dict[str, Any]] = []
            fetch_ids: list[str] = []
            fetch_ids.extend([mp_id for mp_id in CURATED_CHANNELS.values() if mp_id in channel_index])
            for row in wechat_channels:
                channel_id = row.get("id")
                if not channel_id or channel_id in fetch_ids:
                    continue
                fetch_ids.append(channel_id)
                if len(fetch_ids) >= 10:
                    break
            article_detail_cache: dict[str, dict[str, Any]] = {}
            for channel_id in fetch_ids:
                payload = fetch_wechat_public_articles(channel_id, limit=8, offset=0)
                channel_meta = payload.get("data", {}).get("channel", {}) or channel_index.get(channel_id, {})
                article_list = payload.get("data", {}).get("list", []) or []
                enriched_list = []
                for article in article_list:
                    article_id = article.get("id")
                    if article_id and article_id not in article_detail_cache:
                        try:
                            detail_payload = fetch_wechat_public_article_detail(article_id)
                            article_detail_cache[article_id] = detail_payload.get("data", {}) or {}
                        except Exception:
                            article_detail_cache[article_id] = {}
                    detail = article_detail_cache.get(article_id, {})
                    enriched = {
                        **article,
                        "url": detail.get("url") or article.get("url") or "",
                        "content": detail.get("content") or "",
                        "mp_name": article.get("mp_name") or channel_meta.get("name") or "",
                    }
                    if enriched.get("url"):
                        latest_candidates.append(enriched)
                    enriched_list.append(enriched)
                payload = {
                    **payload,
                    "data": {
                        **(payload.get("data", {}) or {}),
                        "channel": channel_meta,
                        "list": enriched_list,
                    },
                }
                channel_name = next((name for name, mp_id in CURATED_CHANNELS.items() if mp_id == channel_id), None)
                if channel_name:
                    curated_articles[channel_name] = payload
                slug_source = channel_name or channel_id
                slug = hashlib.md5(slug_source.encode("utf-8")).hexdigest()[:8]
                dump_json(raw_dir / f"wemprss_channel_{slug}.json", payload)
            latest_candidates.sort(key=lambda row: parse_datetime_any(row.get("publish_time")) or datetime(1970, 1, 1, tzinfo=timezone.utc), reverse=True)
            latest_articles = {
                "data": {
                    "total": len(latest_candidates),
                    "list": latest_candidates[:30],
                }
            }
            issues = build_wechat_issue_summary(curated_articles)
            task.items = list(latest_articles.get("data", {}).get("list", []) or [])
            task.total = (
                len(task.items)
                + sum(len(payload.get("data", {}).get("list", [])) for payload in curated_articles.values())
            )
            task.meta = {
                "channels_total": len(wechat_channels),
                "latest_articles_total": latest_articles.get("data", {}).get("total", 0),
                "curated_articles_total": sum(len(payload.get("data", {}).get("list", [])) for payload in curated_articles.values()),
            }
            if not issues:
                task.status = "ok"
                task.issues = []
                # 保存成功的缓存
                save_wechat_cache(channels, latest_articles, curated_articles, ROOT)
                break
            task.status = "partial"
            task.issues = issues

            # 如果WeChat结果不足，尝试用wechat-search补充
            if len(task.items) < WECHAT_MIN_VALID_ITEMS and attempt == WECHAT_FETCH_ROUNDS:
                try:
                    from skill_invoker import invoke_skill
                    # 从entity_rankings提取top 3实体作为搜索关键词
                    # 这里简化处理，实际应该从上游传入entity_rankings
                    search_keywords = ["AI", "科技", "金融"]  # 占位符，实际应从context获取
                    supplement_count = WECHAT_MIN_VALID_ITEMS - len(task.items) + 5

                    search_result = invoke_skill(
                        "wechat-search",
                        {
                            "query": " ".join(search_keywords[:3]),
                            "max_results": supplement_count,
                        }
                    )

                    if search_result.get("success") and search_result.get("articles"):
                        # 将搜索结果转换为标准格式并去重
                        supplemented = []
                        existing_urls = {item.get("url") for item in task.items}

                        for article in search_result.get("articles", []):
                            url = article.get("url", "")
                            if url and url not in existing_urls:
                                supplemented.append({
                                    "title": article.get("title", ""),
                                    "url": url,
                                    "mp_name": article.get("author", "公众号"),
                                    "publish_time": article.get("published_at", ""),
                                    "content": article.get("summary", ""),
                                })
                                existing_urls.add(url)

                        # 合并到task.items
                        task.items.extend(supplemented[:supplement_count])
                        task.meta["wechat_search_supplemented"] = len(supplemented)

                        if len(task.items) >= WECHAT_MIN_VALID_ITEMS:
                            task.status = "ok"
                            task.issues = []
                except Exception as search_exc:
                    # wechat-search失败不影响主流程
                    task.meta["wechat_search_error"] = str(search_exc)

            if attempt < WECHAT_FETCH_ROUNDS:
                time.sleep(WECHAT_WAIT_SECONDS)
                task.waited_seconds += WECHAT_WAIT_SECONDS
                continue
            break
        except Exception as exc:
            task.status = "error"
            task.issues = [str(exc)]
            if attempt < WECHAT_FETCH_ROUNDS:
                time.sleep(WECHAT_WAIT_SECONDS)
                task.waited_seconds += WECHAT_WAIT_SECONDS
                continue
    if task.status == "error" and not curated_articles:
        # 尝试使用缓存降级
        cached = load_wechat_cache(ROOT)
        if cached:
            channels, latest_articles, curated_articles = cached
            task.items = list(latest_articles.get("data", {}).get("list", []) or [])
            task.total = (
                len(task.items)
                + sum(len(payload.get("data", {}).get("list", [])) for payload in curated_articles.values())
            )
            task.status = "ok_from_cache"
            task.issues = ["使用缓存数据（采集失败）"]
            task.meta["cache_fallback"] = True
        else:
            curated_articles = {channel_name: {"data": {"list": []}, "error": "; ".join(task.issues)} for channel_name in CURATED_CHANNELS}
    elif task.status == "ok":
        # 成功采集，保存缓存
        save_wechat_cache(channels, latest_articles, curated_articles, ROOT)
    dump_json(raw_dir / "wemprss_public_channels.json", channels)
    dump_json(raw_dir / "wemprss_articles_latest.json", latest_articles)
    return task, channels, latest_articles, curated_articles


def build_selected_items(
    platform_tasks: dict[str, ChannelTaskResult],
    content_task: ChannelTaskResult,
    ai_hot_task: ChannelTaskResult,
    report_task: ChannelTaskResult,
    wechat_task: ChannelTaskResult,
    latest_articles: dict[str, Any],
    curated_articles: dict[str, dict[str, Any]],
    generic_tasks: dict[str, ChannelTaskResult] | None = None,
) -> list[SelectedItem]:
    selected: list[SelectedItem] = []
    for platform in ["x", "wb", "xhs", "douyin", "bili"]:
        task = platform_tasks[platform]
        for item in task.items:
            engagement = item.get("liked_count") or item.get("score") or item.get("view_count") or ""
            summary = summarize_title(item.get("title", ""), f"热度代理={engagement}")
            built = build_item(
                source=f"5173/{platform}",
                channel=platform,
                title=item.get("title", ""),
                url=item.get("url", ""),
                author=item.get("author_name") or "",
                published_at=to_dt_text(item.get("fetched_at") or item.get("created_at")),
                summary=summary,
                decision="待分流",
                raw_payload=item,
                fetch_status=task.status,
            )
            if built:
                selected.append(built)
    for item in content_task.items:
        summary = summarize_title(
            item.get("title", ""),
            item.get("summary") or f"score={item.get('score')}",
        )
        built = build_item(
            source=item.get("source") or content_task.source,
            channel=item.get("channel") or content_task.channel,
            title=item.get("title", ""),
            url=item.get("url", ""),
            author=item.get("author_name") or item.get("author") or item.get("platform") or "自媒体",
            published_at=to_dt_text(item.get("created_at") or item.get("time") or item.get("publish_time")),
            summary=summary,
            decision="待分流",
            raw_payload=item,
            fetch_status=content_task.status,
        )
        if built:
            selected.append(built)
    for item in ai_hot_task.items:
        built = build_item(
            source=item.get("source", "ai_hot/aggregate"),
            channel="ai_hot",
            title=item.get("title", ""),
            url=item.get("url", ""),
            author=item.get("author_name") or item.get("provider") or "ai_hot",
            published_at=to_dt_text(item.get("created_at")),
            summary=summarize_title(item.get("title", ""), item.get("summary", "AI 热点汇总")),
            decision="待分流",
            raw_payload=item,
            fetch_status=ai_hot_task.status,
        )
        if built:
            selected.append(built)
    for item in report_task.items:
        built = build_item(
            source="reports/news",
            channel="reports",
            title=item["title"],
            url=item["url"],
            author="TrendRadar聚合",
            published_at="",
            summary=summarize_title(item["title"], "来自 reports 最新外链"),
            decision="待分流",
            raw_payload=item,
            fetch_status=report_task.status,
        )
        if built:
            selected.append(built)
    for item in latest_articles.get("data", {}).get("list", []) or []:
        built = build_item(
            source=item.get("source") or "8000/wechat_latest",
            channel=item.get("channel") or "wechat",
            title=item.get("title", ""),
            url=item.get("url", ""),
            author=item.get("author_name") or item.get("mp_name") or item.get("channel_name") or "公众号",
            published_at=to_dt_text(item.get("created_at") or item.get("publish_time")),
            summary=summarize_title(item.get("title", ""), item.get("summary") or "公众号最新文章"),
            decision="待分流",
            raw_payload=item,
            fetch_status=wechat_task.status,
        )
        if built:
            selected.append(built)
    for channel_name, payload in curated_articles.items():
        for item in payload.get("data", {}).get("list", []) or []:
            built = build_item(
                source="8000/wechat_curated",
                channel="wechat",
                title=item.get("title", ""),
                url=item.get("url", ""),
                author=channel_name,
                published_at=to_dt_text(item.get("publish_time")),
                summary=summarize_title(item.get("title", ""), f"{channel_name} 定向样本"),
                decision="待分流",
                raw_payload={**item, "channel_name": channel_name},
                fetch_status=wechat_task.status,
            )
            if built:
                selected.append(built)
    for task in (generic_tasks or {}).values():
        for item in task.items:
            source = item.get("source") or task.source
            channel = item.get("channel") or task.channel
            built = build_item(
                source=source,
                channel=channel,
                title=item.get("title", ""),
                url=item.get("url", ""),
                author=item.get("author_name") or item.get("provider") or task.label,
                published_at=to_dt_text(item.get("created_at") or item.get("published_at")),
                summary=summarize_title(item.get("title", ""), item.get("summary", task.label)),
                decision="待分流",
                raw_payload=item,
                fetch_status=task.status,
            )
            if built:
                selected.append(built)
    return selected


def score_selected_items(selected: list[SelectedItem], run_started: datetime) -> None:
    dedupe_counter = Counter(item.dedupe_group_id for item in selected)
    cluster_sources: dict[str, set[str]] = defaultdict(set)
    cluster_channels: dict[str, set[str]] = defaultdict(set)
    cluster_dedupe_groups: dict[str, set[str]] = defaultdict(set)
    by_channel: dict[str, list[SelectedItem]] = defaultdict(list)
    for item in selected:
        by_channel[item.channel].append(item)
        cluster_sources[item.cluster_key].add(item.source)
        cluster_channels[item.cluster_key].add(item.channel)
        cluster_dedupe_groups[item.cluster_key].add(item.dedupe_group_id)

    for channel_items in by_channel.values():
        engagement_values = []
        freshness_values = []
        authority_values = []
        duplicate_values = []
        cross_source_values = []
        for item in channel_items:
            engagement_raw = float(item.raw_heat_signals.get("engagement") or 0)
            engagement_values.append(math.log1p(max(0.0, engagement_raw)))
            published_dt = parse_datetime_any(item.published_at)
            if published_dt:
                age_hours = max((run_started - published_dt).total_seconds() / 3600, 0.0)
                freshness = max(0.0, 1.0 - age_hours / 72.0)
            else:
                freshness = min(item.source_timeliness_weight / 1.4, 1.0)
            freshness_values.append(freshness)
            authority_values.append(item.source_authority_weight)
            duplicate_values.append(dedupe_counter[item.dedupe_group_id])
            source_hits = len(cluster_sources.get(item.cluster_key, set()))
            channel_hits = len(cluster_channels.get(item.cluster_key, set()))
            cluster_group_hits = len(cluster_dedupe_groups.get(item.cluster_key, set()))
            cross_source_values.append(
                max(source_hits - 1, 0) * 0.65
                + max(channel_hits - 1, 0) * 1.0
                + max(cluster_group_hits - 1, 0) * 0.3
            )

        def normalize(values: list[float], target: float) -> float:
            if not values:
                return 0.0
            min_value = min(values)
            max_value = max(values)
            if math.isclose(max_value, min_value):
                return 1.0 if target > 0 else 0.0
            return (target - min_value) / (max_value - min_value)

        for item in channel_items:
            engagement_raw = float(item.raw_heat_signals.get("engagement") or 0)
            logged_engagement = math.log1p(max(0.0, engagement_raw))
            published_dt = parse_datetime_any(item.published_at)
            if published_dt:
                age_hours = max((run_started - published_dt).total_seconds() / 3600, 0.0)
                freshness = max(0.0, 1.0 - age_hours / 72.0)
            else:
                freshness = min(item.source_timeliness_weight / 1.4, 1.0)
            duplicate_hits = float(dedupe_counter[item.dedupe_group_id])
            source_hits = len(cluster_sources.get(item.cluster_key, set()))
            channel_hits = len(cluster_channels.get(item.cluster_key, set()))
            cluster_group_hits = len(cluster_dedupe_groups.get(item.cluster_key, set()))
            cross_source_raw = (
                max(source_hits - 1, 0) * 0.65
                + max(channel_hits - 1, 0) * 1.0
                + max(cluster_group_hits - 1, 0) * 0.3
            )
            engagement_norm = normalize(engagement_values, logged_engagement)
            freshness_norm = normalize(freshness_values, freshness)
            authority_norm = normalize(authority_values, item.source_authority_weight)
            duplicate_norm = normalize(duplicate_values, duplicate_hits)
            cross_source_norm = normalize(cross_source_values, cross_source_raw)
            trend_bonus = 1.0 if item.trendradar_signal else 0.0
            heat_score = round(
                100
                * (
                    engagement_norm * 0.24
                    + freshness_norm * 0.24
                    + duplicate_norm * 0.12
                    + authority_norm * 0.12
                    + cross_source_norm * 0.20
                    + trend_bonus * 0.08
                ),
                2,
            )
            item.raw_heat_signals.update(
                {
                    "engagement_log": round(logged_engagement, 4),
                    "freshness_norm": round(freshness_norm, 4),
                    "engagement_norm": round(engagement_norm, 4),
                    "duplicate_hits": int(duplicate_hits),
                    "duplicate_norm": round(duplicate_norm, 4),
                    "authority_norm": round(authority_norm, 4),
                    "cross_source_hits": source_hits,
                    "cross_channel_hits": channel_hits,
                    "cross_cluster_group_hits": cluster_group_hits,
                    "cross_source_norm": round(cross_source_norm, 4),
                }
            )
            item.raw_heat_signals["editorial_relevance"] = editorial_relevance_score(item)
            item.heat_score = heat_score
            if heat_score >= 85:
                item.heat_level = "S"
            elif heat_score >= 70:
                item.heat_level = "A"
            elif heat_score >= 55:
                item.heat_level = "B"
            elif heat_score >= 40:
                item.heat_level = "C"
            else:
                item.heat_level = "D"


def build_entity_rankings(selected: list[SelectedItem], generated_at: str, run_id: str) -> dict[str, Any]:
    rankings: dict[str, Counter[str]] = defaultdict(Counter)
    for item in selected:
        for category, values in item.entities.items():
            rankings[category].update(values)
        rankings["dynamic_tokens"].update(item.dynamic_tokens[:6])
    return {
        "run_id": run_id,
        "generated_at": generated_at,
        "categories": {
            category: [{"name": name, "count": count} for name, count in counter.most_common(15)]
            for category, counter in rankings.items()
        },
    }


def build_event_clusters(selected: list[SelectedItem], generated_at: str, run_id: str) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    dedupe_counter = Counter(item.dedupe_group_id for item in selected)
    for item in selected:
        bucket = buckets.setdefault(
            item.cluster_key,
            {
                "cluster_id": item.cluster_key,
                "count": 0,
                "source_tiers": Counter(),
                "sources": Counter(),
                "channels": Counter(),
                "editor_labels": Counter(),
                "titles": [],
                "links": [],
                "entities": Counter(),
                "actions": Counter(),
                "dynamic_tokens": Counter(),
                "noise_tags": Counter(),
                "trendradar_count": 0,
                "hotspot_macro_policy_score_sum": 0.0,
                "hotspot_source_roles": Counter(),
                "freshness_weight_sum": 0.0,
                "timeliness_weight_sum": 0.0,
                "authority_weight_sum": 0.0,
                "heat_score_sum": 0.0,
                "dedupe_groups": set(),
            },
        )
        bucket["count"] += 1
        bucket["source_tiers"][item.source_tier] += 1
        bucket["sources"][item.source] += 1
        bucket["channels"][item.channel] += 1
        bucket["editor_labels"].update(item.editor_labels)
        if len(bucket["titles"]) < 6:
            bucket["titles"].append(item.title)
        if item.url and len(bucket["links"]) < 6:
            bucket["links"].append(item.url)
        bucket["entities"].update(entity_count_payload(item.entities))
        bucket["actions"].update(item.dominant_actions)
        bucket["dynamic_tokens"].update(item.dynamic_tokens)
        bucket["noise_tags"].update(item.noise_tags)
        bucket["trendradar_count"] += int(item.trendradar_signal)
        radar_score = float((item.hotspot_radar or {}).get("macro_policy_score") or 0.0)
        bucket["hotspot_macro_policy_score_sum"] += radar_score
        radar_role = str((item.hotspot_radar or {}).get("source_role") or "")
        if radar_role:
            bucket["hotspot_source_roles"][radar_role] += 1
        bucket["freshness_weight_sum"] += item.source_freshness_weight
        bucket["timeliness_weight_sum"] += item.source_timeliness_weight
        bucket["authority_weight_sum"] += item.source_authority_weight
        bucket["heat_score_sum"] += item.heat_score
        bucket["dedupe_groups"].add(item.dedupe_group_id)
    clusters = []
    for bucket in buckets.values():
        dominant_entities = [name for name, _ in bucket["entities"].most_common(6)]
        dominant_actions = [name for name, _ in bucket["actions"].most_common(4)]
        dominant_tokens = [name for name, _ in bucket["dynamic_tokens"].most_common(8)]
        label = bucket["editor_labels"].most_common(1)[0][0] if bucket["editor_labels"] else "其他观察"
        title_candidate_cn, title_candidate_original = build_cluster_title_candidate(
            label,
            dominant_entities,
            dominant_actions,
            dominant_tokens,
            bucket["titles"],
        )
        freshness_score = round(bucket["freshness_weight_sum"] / max(bucket["count"], 1), 3)
        timeliness_score = round(bucket["timeliness_weight_sum"] / max(bucket["count"], 1), 3)
        authority_score = round(bucket["authority_weight_sum"] / max(bucket["count"], 1), 3)
        noise_ratio = round(sum(bucket["noise_tags"].values()) / max(bucket["count"], 1), 4)
        avg_heat_score = round(bucket["heat_score_sum"] / max(bucket["count"], 1), 2)
        avg_macro_policy_score = round(bucket["hotspot_macro_policy_score_sum"] / max(bucket["count"], 1), 4)
        source_diversity = len(bucket["channels"])
        dedupe_depth = len(bucket["dedupe_groups"])
        priority_score = round(
            bucket["count"] * 3.2
            + source_diversity * 3.6
            + dedupe_depth * 1.4
            + avg_heat_score * 0.22
            + timeliness_score * 5.0
            + authority_score * 3.5
            + avg_macro_policy_score * 4.0
            + round(bucket["trendradar_count"] / max(bucket["count"], 1), 4) * 2.0
            - noise_ratio * 8.0
            - (6.0 if bucket["count"] == 1 else 0.0),
            3,
        )
        clusters.append(
            {
                "cluster_id": bucket["cluster_id"],
                "topic": label,
                "cluster_title_candidate": title_candidate_cn,
                "cluster_title_original": title_candidate_original,
                "cluster_summary": f"围绕 {title_candidate_cn} 的高频讨论，当前样本 {bucket['count']} 条，涉及 {len(bucket['channels'])} 个渠道、{len(bucket['dedupe_groups'])} 个去重组。",
                "count": bucket["count"],
                "primary_source_tier": bucket["source_tiers"].most_common(1)[0][0] if bucket["source_tiers"] else "unknown",
                "source_tiers": dict(bucket["source_tiers"]),
                "source_mix": dict(bucket["channels"]),
                "sources": dict(bucket["sources"]),
                "editor_labels": dict(bucket["editor_labels"]),
                "representative_titles": bucket["titles"],
                "representative_links": bucket["links"],
                "top_entities": dominant_entities[:8],
                "dominant_entities": dominant_entities[:6],
                "dominant_actions": dominant_actions,
                "dynamic_tokens": dominant_tokens,
                "noise_tags": dict(bucket["noise_tags"]),
                "trendradar_coverage": round(bucket["trendradar_count"] / max(bucket["count"], 1), 4),
                "hotspot_macro_policy_score": avg_macro_policy_score,
                "hotspot_source_roles": dict(bucket["hotspot_source_roles"]),
                "freshness_score": freshness_score,
                "timeliness_score": timeliness_score,
                "authority_score": authority_score,
                "noise_ratio": noise_ratio,
                "avg_heat_score": avg_heat_score,
                "source_diversity": source_diversity,
                "dedupe_depth": dedupe_depth,
                "priority_score": priority_score,
            }
        )
    clusters.sort(key=lambda item: item["priority_score"], reverse=True)
    return clusters


def build_source_quality_report(selected: list[SelectedItem], generated_at: str, run_id: str) -> dict[str, Any]:
    tier_counter = Counter(item.source_tier for item in selected)
    source_counter = Counter(item.source for item in selected)
    noisy_count = sum(1 for item in selected if item.noise_tags)
    trendradar_count = sum(1 for item in selected if item.trendradar_signal)
    channel_counter = Counter(item.channel for item in selected)
    heat_levels = Counter(item.heat_level for item in selected)
    return {
        "run_id": run_id,
        "generated_at": generated_at,
        "tier_distribution": dict(tier_counter),
        "top_sources": [{"source": name, "count": count} for name, count in source_counter.most_common(20)],
        "channel_distribution": dict(channel_counter),
        "heat_level_distribution": dict(heat_levels),
        "noise_sample_ratio": round(noisy_count / max(len(selected), 1), 4),
        "trendradar_ratio": round(trendradar_count / max(len(selected), 1), 4),
        "tier_notes": {
            "official": "官方与监管/机构源，可优先用于证据链。",
            "mainstream_media": "主流媒体与权威财经媒体。",
            "platform_hotspot": "平台热度源，适合发现话题，不适合直接下结论。",
            "self_media": "垂类公众号/自媒体，适合视角参考。",
            "personal_opinion": "个人表达，应谨慎入正文。",
        },
    }


def build_analysis_report(selected: list[SelectedItem], analysis_selected: list[SelectedItem]) -> dict[str, Any]:
    labels = Counter()
    channels = Counter()
    tiers = Counter()
    for item in analysis_selected:
        labels.update(label for label in item.editor_labels if label != "其他观察")
        channels[item.channel] += 1
        tiers[item.source_tier] += 1
    return {
        "selected_records": len(selected),
        "analysis_records": len(analysis_selected),
        "analysis_ratio": round(len(analysis_selected) / max(len(selected), 1), 4),
        "analysis_channels": dict(channels),
        "analysis_tiers": dict(tiers),
        "analysis_labels": dict(labels.most_common(12)),
    }


def build_channel_top10(selected: list[SelectedItem]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[SelectedItem]] = defaultdict(list)
    for item in selected:
        grouped[item.channel].append(item)

    result: dict[str, list[dict[str, Any]]] = {}
    for channel in CHANNEL_ORDER:
        items = grouped.get(channel, [])
        if not items:
            continue
        seen_groups: set[str] = set()
        seen_urls: set[str] = set()
        cluster_slots: Counter[str] = Counter()
        picked: list[dict[str, Any]] = []
        items_sorted = sorted(
            items,
            key=lambda item: (
                item.heat_score,
                item.source_authority_weight,
                item.source_timeliness_weight,
                0 if item.noise_tags else 1,
            ),
            reverse=True,
        )
        for item in items_sorted:
            if item.dedupe_group_id in seen_groups:
                continue
            if item.url in seen_urls:
                continue
            if channel != "ai_hot" and cluster_slots[item.cluster_key] >= 2:
                continue
            note_parts = [
                f"账号：{item.author or '未知'}",
                f"时间：{item.published_at or '未知'}",
                f"摘要：{compute_excerpt(item.title, item.summary)}",
            ]
            if item.noise_tags:
                note_parts.append(f"噪音标签：{', '.join(item.noise_tags)}")
            picked.append(
                {
                    "channel": channel,
                    "channel_label": channel_label(channel),
                    "source": item.source,
                    "heat_level": item.heat_level,
                    "heat_score": item.heat_score,
                    "title": item.title,
                    "url": item.url,
                    "author_or_account": item.author,
                    "publish_time": item.published_at,
                    "excerpt": compute_excerpt(item.title, item.summary),
                    "noise_tags": item.noise_tags,
                    "trendradar_signal": item.trendradar_signal,
                    "capture_quality": item.capture_quality,
                    "dedupe_group_id": item.dedupe_group_id,
                    "event_key": item.cluster_key,
                    "note": "；".join(note_parts),
                }
            )
            seen_groups.add(item.dedupe_group_id)
            seen_urls.add(item.url)
            cluster_slots[item.cluster_key] += 1
            if len(picked) >= 10:
                break
        result[channel] = picked
    return result


def brief_cluster_priority_score(item: dict[str, Any]) -> float:
    return round(
        float(item.get("priority_score") or 0.0) * 0.15
        + float(item.get("hotspot_macro_policy_score") or 0.0) * 90.0
        + float(item.get("authority_score") or 0.0) * 9.0
        + float(item.get("timeliness_score") or 0.0) * 4.0
        + float(item.get("source_diversity") or 0.0) * 2.0
        - float(item.get("noise_ratio") or 0.0) * 8.0,
        3,
    )


def cluster_role_keys(item: dict[str, Any]) -> list[str]:
    roles = [str(role) for role in (item.get("hotspot_source_roles") or {}).keys() if str(role).strip()]
    if roles:
        return sorted(roles)
    source_mix = item.get("source_mix") or {}
    channels = [str(channel) for channel in source_mix.keys() if str(channel).strip()]
    return sorted(channels) or ["unknown"]


def order_brief_clusters_for_handoff(event_clusters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    remaining = list(event_clusters)
    ordered: list[dict[str, Any]] = []
    role_counts: Counter[str] = Counter()
    while remaining:
        best_index = 0
        best_score = float("-inf")
        for index, item in enumerate(remaining):
            roles = cluster_role_keys(item)
            role_penalty = max(role_counts[role] for role in roles) * 18.0
            diversity_bonus = max(len(item.get("source_mix") or {}) - 1, 0) * 2.5
            adjusted = brief_cluster_priority_score(item) + diversity_bonus - role_penalty
            if adjusted > best_score:
                best_score = adjusted
                best_index = index
        selected = remaining.pop(best_index)
        ordered.append(selected)
        for role in cluster_role_keys(selected):
            role_counts[role] += 1
    return ordered


def build_brief_input(run_id: str, generated_at: str, event_clusters: list[dict[str, Any]], channel_top10: dict[str, list[dict[str, Any]]], entity_rankings: dict[str, Any]) -> dict[str, Any]:
    preferred_clusters = [
        item for item in event_clusters
        if item["count"] >= 2
        or item["source_diversity"] >= 2
        or item["dedupe_depth"] >= 2
        or item["trendradar_coverage"] > 0
        or item["authority_score"] >= 1.0
    ]
    cluster_pool = order_brief_clusters_for_handoff(sorted(preferred_clusters or event_clusters, key=brief_cluster_priority_score, reverse=True))
    event_candidates = []
    for item in cluster_pool[:15]:
        event_candidates.append(
            {
                "cluster_id": item["cluster_id"],
                "cluster_title_candidate": item["cluster_title_candidate"],
                "cluster_title_original": item.get("cluster_title_original", item["cluster_title_candidate"]),
                "cluster_summary": item["cluster_summary"],
                "count": item["count"],
                "source_mix": item["source_mix"],
                "source_diversity": item["source_diversity"],
                "dedupe_depth": item["dedupe_depth"],
                "priority_score": item["priority_score"],
                "brief_priority_score": brief_cluster_priority_score(item),
                "dominant_entities": item["dominant_entities"],
                "dominant_actions": item["dominant_actions"],
                "trendradar_coverage": item["trendradar_coverage"],
                "hotspot_macro_policy_score": item.get("hotspot_macro_policy_score", 0.0),
                "hotspot_source_roles": item.get("hotspot_source_roles", {}),
                "freshness_score": item["freshness_score"],
                "authority_score": item["authority_score"],
                "noise_ratio": item["noise_ratio"],
                "representative_titles": item["representative_titles"][:3],
                "representative_links": item["representative_links"][:3],
            }
        )
    trendradar_candidates = []
    for row in channel_top10.get("reports", [])[:10]:
        trendradar_candidates.append(
            {
                "title": row["title"],
                "url": row["url"],
                "heat_level": row["heat_level"],
                "heat_score": row["heat_score"],
                "event_key": row.get("event_key"),
            }
        )
    ai_hot_candidates = []
    for row in channel_top10.get("ai_hot", [])[:10]:
        ai_hot_candidates.append(
            {
                "title": row["title"],
                "url": row["url"],
                "heat_level": row["heat_level"],
                "heat_score": row["heat_score"],
                "event_key": row.get("event_key"),
                "excerpt": row.get("excerpt") or "",
            }
        )
    return {
        "run_id": run_id,
        "generated_at": generated_at,
        "channel_top10": channel_top10,
        "event_candidates": event_candidates,
        "top_entities": {
            category: values[:10]
            for category, values in (entity_rankings.get("categories") or {}).items()
        },
        "ai_hot_candidates": ai_hot_candidates,
        "trendradar_candidates": trendradar_candidates,
        "cross_channel_events": [
            {
                "cluster_id": item["cluster_id"],
                "cluster_title_candidate": item["cluster_title_candidate"],
                "cluster_title_original": item.get("cluster_title_original", item["cluster_title_candidate"]),
                "source_mix": item["source_mix"],
                "hotspot_macro_policy_score": item.get("hotspot_macro_policy_score", 0.0),
            }
            for item in event_clusters
            if len(item.get("source_mix", {})) >= 2
        ][:8],
        "manual_additions": [],
        "editor_note": "",
        "notes": [
            "intake 阶段只提供真实样本、渠道热度和候选事件簇，不替 brief 做观点判断。",
            "若人工指定题目，应补到 manual_additions 并保留真实标题、原始链接与原因。",
        ],
    }


def build_intake_gate(run_id: str, generated_at: str, selected: list[SelectedItem]) -> dict[str, Any]:
    noisy = [
        {
            "title": item.title,
            "url": item.url,
            "noise_tags": item.noise_tags,
            "source": item.source,
            "channel": item.channel,
            "heat_level": item.heat_level,
        }
        for item in selected
        if item.noise_tags
    ][:30]
    return {
        "run_id": run_id,
        "gate": "Intake Gate",
        "status": "pending_review",
        "generated_at": generated_at,
        "instructions": [
            "删除明显广告、生活方式、低信息密度、重复搬运样本。",
            "保留能形成事件线索、人物线索、议题线索的样本。",
            "如需补链，直接在 additions 中新增。",
            "若人工指定必须进入 brief 的样本，请追加到 must_include_urls。",
        ],
        "noise_candidates": noisy,
        "remove_ids": [],
        "keep_ids": [],
        "additions": [],
        "must_include_urls": [],
        "editor_note": "",
    }


def top_entities_text(entity_rankings: dict[str, Any], category: str, limit: int = 6) -> str:
    return ", ".join(item["name"] for item in entity_rankings.get("categories", {}).get(category, [])[:limit]) or "无"


def build_cross_channel_signals(selected: list[SelectedItem]) -> tuple[list[str], list[str], list[str]]:
    group_channels: dict[str, set[str]] = defaultdict(set)
    group_titles: dict[str, list[str]] = defaultdict(list)
    for item in selected:
        group_channels[item.cluster_key].add(item.channel)
        if len(group_titles[item.cluster_key]) < 3:
            group_titles[item.cluster_key].append(item.title)
    cross_platform = []
    channel_only = []
    noisy_hot = []
    for group_id, channels in sorted(group_channels.items(), key=lambda kv: len(kv[1]), reverse=True):
        title = truncate_title(group_titles[group_id][0]) if group_titles[group_id] else group_id
        if len(channels) >= 2 and len(cross_platform) < 6:
            cross_platform.append(f"- 跨平台共振：{title}｜覆盖 {', '.join(channel_label(channel) for channel in sorted(channels))}")
    for channel in sorted({item.channel for item in selected}):
        channel_items = [item for item in selected if item.channel == channel]
        by_group = Counter(item.cluster_key for item in channel_items)
        exclusive = [
            item for item in sorted(channel_items, key=lambda entry: entry.heat_score, reverse=True)
            if len(group_channels[item.cluster_key]) == 1 and by_group[item.cluster_key] >= 1
        ]
        if exclusive:
            top = exclusive[0]
            channel_only.append(f"- {channel_label(channel)}独热：{truncate_title(top.title)}｜热度 {top.heat_level}/{top.heat_score}")
        if len(channel_only) >= 6:
            break
    for item in sorted(selected, key=lambda entry: entry.heat_score, reverse=True):
        if item.noise_tags and len(noisy_hot) < 5:
            noisy_hot.append(f"- 噪音高但传播高：{truncate_title(item.title)}｜{channel_label(item.channel)}｜热度 {item.heat_level}/{item.heat_score}｜标签 {', '.join(item.noise_tags)}")
    return cross_platform, channel_only, noisy_hot


def build_noise_pool(selected: list[SelectedItem]) -> list[SelectedItem]:
    return sorted(
        [item for item in selected if item.noise_tags or item.fetch_status != "ok"],
        key=lambda item: (item.heat_score, item.fetch_status == "ok"),
        reverse=True,
    )[:40]


def build_markdown(
    run_label: str,
    counts: dict[str, Any],
    selected: list[SelectedItem],
    analysis_report: dict[str, Any],
    entity_rankings: dict[str, Any],
    event_clusters: list[dict[str, Any]],
    source_quality_report: dict[str, Any],
    channel_top10: dict[str, list[dict[str, Any]]],
    wechat_task: ChannelTaskResult,
) -> tuple[str, str]:
    top_people = top_entities_text(entity_rankings, "people")
    top_orgs = top_entities_text(entity_rankings, "orgs")
    top_countries = top_entities_text(entity_rankings, "countries")
    top_commodities = top_entities_text(entity_rankings, "commodities")
    top_sectors = top_entities_text(entity_rankings, "sectors")
    top_dynamic_tokens = top_entities_text(entity_rankings, "dynamic_tokens", 10)
    analysis_selected = pick_analysis_items(selected)
    cross_platform, channel_only, noisy_hot = build_cross_channel_signals(analysis_selected)

    def render_channel_top10() -> list[str]:
        lines: list[str] = []
        for channel in CHANNEL_ORDER:
            items = channel_top10.get(channel, [])
            if not items:
                continue
            lines.append(f"### {channel_label(channel)} Top{len(items)}")
            for item in items:
                lines.append(
                    f"- {item['heat_level']}｜{md_link(item['title'], item['url'])}｜{item.get('note') or item.get('excerpt') or '-'}"
                )
            lines.append("")
        return lines

    table_lines = [
        "| 来源平台 | 热度等级 | 标题/主题 | 原始链接 | 作者/账号 | 发布时间 | 一句话摘要 | 去留建议 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in sorted(selected, key=lambda entry: (CHANNEL_ORDER.index(entry.channel) if entry.channel in CHANNEL_ORDER else 99, -entry.heat_score, entry.title)):
        table_lines.append(
            f"| {md_cell(channel_label(item.channel))} | {item.heat_level} | {md_cell(item.title)} | {item.url} | {md_cell(item.author or '-')} | {md_cell(item.published_at or '-')} | {md_cell(compute_excerpt(item.title, item.summary))} | {md_cell(item.decision)} |"
        )

    duplicate_counter = Counter(item.dedupe_group_id for item in selected)
    duplicate_lines = []
    seen_duplicates: set[str] = set()
    for item in sorted(selected, key=lambda entry: duplicate_counter[entry.dedupe_group_id], reverse=True):
        if duplicate_counter[item.dedupe_group_id] < 2 or item.dedupe_group_id in seen_duplicates:
            continue
        seen_duplicates.add(item.dedupe_group_id)
        duplicate_lines.append(
            f"- {md_link(item.title, item.url)}｜{channel_label(item.channel)}｜重复 {duplicate_counter[item.dedupe_group_id]} 次"
        )
        if len(duplicate_lines) >= 20:
            break
    if not duplicate_lines:
        duplicate_lines = ["- 暂无显著重复样本。"]

    noise_lines = [
        f"- {channel_label(item.channel)}｜{md_link(item.title, item.url)}｜热度 {item.heat_level}/{item.heat_score}｜标签 {', '.join(item.noise_tags or ['fetch_issue'])}"
        for item in build_noise_pool(selected)
    ] or ["- 暂无明显噪音或抓取异常样本。"]

    trendradar_lines = []
    for row in channel_top10.get("reports", [])[:10]:
        trendradar_lines.append(
            f"- {row['heat_level']}｜{md_link(row['title'], row['url'])}｜{row.get('excerpt') or '-'}"
        )
    if not trendradar_lines:
        trendradar_lines = ["- 今日无 TrendRadar 高优先样本。"]

    brief_cluster_lines = []
    for item in event_clusters[:10]:
        brief_cluster_lines.append(
            f"- {item['cluster_title_candidate']}｜样本 {item['count']} 条｜覆盖 {len(item['source_mix'])} 个渠道｜TrendRadar {item['trendradar_coverage']:.0%}"
        )
    if not brief_cluster_lines:
        brief_cluster_lines = ["- 暂无可交给 brief 的事件簇。"]

    wechat_issue_lines = [f"- {issue}" for issue in wechat_task.issues] or ["- 本轮公众号抓取无异常。"]

    report = "\n".join(
        [
            f"# 第一环节采集报告（{run_label}）",
            "",
            "## 1. 本轮采集概览",
            f"- 0913 本地源：微信聊天={counts.get('wechat_chat_records_total', counts.get('local_chat_total', 0))}，公众号文章={counts.get('local_mp_articles_total', 0)}，自媒体文章={counts.get('local_media_articles_total', 0)}。",
            f"- 合并新闻源：本地新闻原始={counts.get('local_news_total', 0)}，公开新闻原始={counts.get('public_news_total', 0)}，合并去重后={counts.get('news_total', 0)}，删除重复={counts.get('news_deduplicated_total', 0)}。",
            f"- 公开补充源：公开热榜={counts.get('public_hot_total', 0)}，AI热点汇总={counts.get('ai_hot_total', 0)}，legacy 公众号定向样本={counts['curated_articles']}。",
            f"- 旧远程平台量：X={counts['x_total']}，微博={counts['wb_total']}，小红书={counts['xhs_total']}，抖音={counts['douyin_total']}，B站={counts['bili_total']}。",
            f"- 入库总量：`{counts['selected_records']}` 条；有效链接样本：`{counts['valid_linked_records']}` 条。",
            f"- 进入分析池：`{analysis_report['analysis_records']}` 条，占比 `{analysis_report['analysis_ratio']:.2%}`；该池仅用于事件簇、Brief 交接和热点横截面。",
            f"- 公众号等待轮次：`{wechat_task.attempts}`；累计等待：`{wechat_task.waited_seconds}` 秒；状态：`{wechat_task.status}`。",
            "",
            "## 2. 各渠道 Top10",
            *render_channel_top10(),
            "## 3. 全局热点横截面",
            f"- 高频人物：{top_people}",
            f"- 高频国家/地区：{top_countries}",
            f"- 高频机构：{top_orgs}",
            f"- 高频商品：{top_commodities}",
            f"- 高频行业：{top_sectors}",
            f"- 高频动态词：{top_dynamic_tokens}",
            f"- TrendRadar 命中占比：{source_quality_report['trendradar_ratio']:.2%}",
            f"- 分析池主标签：{', '.join(analysis_report['analysis_labels'].keys()) or '无'}",
            "",
            "## 4. 渠道差异提醒",
            "### 跨平台共振事件",
            *(cross_platform or ["- 暂无明显跨平台共振事件。"]),
            "",
            "### 单渠道独热提醒",
            *(channel_only or ["- 暂无明显单渠道独热样本。"]),
            "",
            "### 噪音高但传播高",
            *(noisy_hot or ["- 暂无明显噪音高传播样本。"]),
            "",
            "## 5. 交给 Brief 的输入建议",
            "- 这里只保留可继续深挖的热点簇，不在本阶段生成观点或选题判断。",
            *brief_cluster_lines,
            "",
            "### TrendRadar 补充池",
            *trendradar_lines,
            "",
            "### 公众号慢源说明",
            *wechat_issue_lines,
            "",
        ]
    )

    draft = "\n".join(
        [
            f"# 第一环节内容采集底稿（{run_label}）",
            "",
            "## 一、采集概览",
            f"- 今日共标准化沉淀 `{counts['selected_records']}` 条真实样本，全部保留真实标题与真实链接。",
            f"- 渠道覆盖：{', '.join(channel_label(channel) for channel in CHANNEL_ORDER if channel in channel_top10)}。",
            f"- AI 热点汇总单列沉淀 `{counts.get('ai_hot_total', 0)}` 条，并在分析池和 Brief handoff 中使用更高权重。",
            f"- 其中进入分析池 `{analysis_report['analysis_records']}` 条，仅用于事件簇与 brief 输入，不影响原始采集底稿留存。",
            f"- 公众号抓取状态：`{wechat_task.status}`，轮次 `{wechat_task.attempts}`，累计等待 `{wechat_task.waited_seconds}` 秒。",
            "",
            "## 二、各渠道 Top10（真实标题 + 真实链接）",
            *render_channel_top10(),
            "## 三、标准化来源清单",
            *table_lines,
            "",
            "## 四、重复与噪音池",
            "### 重复项",
            *duplicate_lines,
            "",
            "### 噪音项",
            *noise_lines,
            "",
            "## 五、趋势雷达补充池",
            *trendradar_lines,
            "",
            "## 六、给下一阶段的原始输入",
            *brief_cluster_lines,
            "",
            "## 七、人工干预位",
            "- 建议人工删除的条目：优先删广告、搬运、低信息密度样本。",
            "- 建议人工追加的条目：如需追加，请补真实标题、原始链接和追加原因。",
            "- 建议人工指定必须进入 brief 的样本：写入 `intake_review.json.must_include_urls`。",
            "",
        ]
    )
    return report, draft


def make_empty_task(channel: str, source: str, label: str, reason: str = "simple intake mode") -> ChannelTaskResult:
    return ChannelTaskResult(
        channel=channel,
        source=source,
        label=label,
        status="skipped",
        issues=[reason],
    )


def task_from_collected(name: str, source: str, channel: str, label: str, simple_run: Any) -> ChannelTaskResult:
    raw_items = simple_run.tasks.get(name, [])
    items = [
        item.to_payload() if hasattr(item, "to_payload") else dict(item)
        for item in raw_items
    ]
    status_payload = simple_run.status.get(name, {})
    status = str(status_payload.get("status") or ("ready" if items else "empty"))
    issues: list[str] = []
    if status_payload.get("error"):
        issues.append(str(status_payload["error"]))
    return ChannelTaskResult(
        channel=channel,
        source=source,
        label=label,
        items=items,
        total=len(items),
        status=status,
        issues=issues,
        meta={key: value for key, value in status_payload.items() if key not in {"status", "error", "total"}},
    )


def build_simple_intake_tasks(raw_dir: Path) -> tuple[
    dict[str, ChannelTaskResult],
    ChannelTaskResult,
    ChannelTaskResult,
    ChannelTaskResult,
    ChannelTaskResult,
    dict[str, Any],
    dict[str, Any],
    dict[str, dict[str, Any]],
    dict[str, ChannelTaskResult],
    dict[str, dict[str, Any]],
    list[str],
]:
    simple_run = collect_simple_intake(raw_dir)
    platform_tasks = {
        platform: make_empty_task(platform, f"legacy/{platform}", channel_label(platform))
        for platform in PLATFORM_FETCH_LIMITS
    }
    content_task = task_from_collected(
        "content_research",
        "local_media/8001",
        "content_research",
        channel_label("content_research"),
        simple_run,
    )
    report_task = make_empty_task("reports", "legacy/reports", channel_label("reports"))
    wechat_task = task_from_collected(
        "wechat",
        "local_mp/8001",
        "wechat",
        channel_label("wechat"),
        simple_run,
    )
    local_chat_task = task_from_collected("local_chat", "local_chat/messages", "local_chat", channel_label("local_chat"), simple_run)
    local_news_items = list(simple_run.tasks.get("local_news", []))
    public_news_items = list(simple_run.tasks.get("public_news", []))
    merged_news_items = merge_news_items(local_news_items, public_news_items)
    local_news_status = simple_run.status.get("local_news", {})
    public_news_status = simple_run.status.get("public_news", {})
    news_input_total = len(local_news_items) + len(public_news_items)
    news_task = ChannelTaskResult(
        channel="news",
        source="merged_news/local_and_public",
        label=channel_label("news"),
        items=[item.to_payload() for item in merged_news_items],
        total=len(merged_news_items),
        status="ready" if merged_news_items else "empty",
        meta={
            "input_total": news_input_total,
            "deduplicated": max(0, news_input_total - len(merged_news_items)),
            "source_totals": {
                "local_news": len(local_news_items),
                "public_news": len(public_news_items),
            },
            "source_status": {
                "local_news": local_news_status,
                "public_news": public_news_status,
            },
            "dedupe_rules": ["source_id+item_id", "canonical_url", "normalized_title", "near_title>=0.93"],
        },
    )
    dump_json(
        raw_dir / "merged_news_items.json",
        {
            "generated_at": iso(now()),
            "input_total": news_input_total,
            "deduplicated": news_task.meta["deduplicated"],
            "items": news_task.items,
        },
    )
    public_hot_task = task_from_collected("public_hot", "public/aggregate", "public_hot", channel_label("public_hot"), simple_run)

    ai_hot_items = [
        item
        for item in [
            *local_chat_task.items,
            *news_task.items,
            *content_task.items,
            *wechat_task.items,
            *public_hot_task.items,
        ]
        if is_ai_topic(item.get("title", ""), item.get("summary", ""), item.get("author_name", ""))
    ][:AI_HOT_LIMIT]
    ai_hot_task = ChannelTaskResult(
        channel="ai_hot",
        source="simple/ai_hot",
        label=channel_label("ai_hot"),
        items=[
            {**item, "source": item.get("source") or "simple/ai_hot", "channel": "ai_hot"}
            for item in ai_hot_items
        ],
        total=len(ai_hot_items),
        status="ready" if ai_hot_items else "empty",
        meta={
            "derived_from": [
                "local_chat",
                "news",
                "content_research",
                "wechat",
                "public_hot",
            ]
        },
    )

    generic_tasks = {
        "local_chat": local_chat_task,
        "news": news_task,
        "public_hot": public_hot_task,
    }
    ports_status = {
        "simple_intake": {
            "status": "ready",
            "mode": "simple",
            "sources": simple_run.status,
        }
    }
    wechat_accounts = sorted(
        {
            str(item.get("author_name") or item.get("channel_name") or "").strip()
            for item in wechat_task.items
            if str(item.get("author_name") or item.get("channel_name") or "").strip()
        }
    )
    channels = {
        "data": {
            "total": len(wechat_accounts),
            "list": [{"name": account} for account in wechat_accounts],
        }
    }
    latest_articles = {
        "data": {
            "total": wechat_task.total,
            "list": wechat_task.items,
        }
    }
    curated_articles: dict[str, dict[str, Any]] = {}
    return (
        platform_tasks,
        content_task,
        ai_hot_task,
        report_task,
        wechat_task,
        channels,
        latest_articles,
        curated_articles,
        generic_tasks,
        ports_status,
        [*simple_run.artifacts, "raw/merged_news_items.json"],
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Intake stage and write its canonical manifest.")
    parser.add_argument("--run-id", help="Stable run identifier shared by all mainline stages.")
    args = parser.parse_args(argv)
    if args.run_id and RUN_ID_PATTERN.fullmatch(args.run_id) is None:
        parser.error("--run-id must contain only letters, digits, dots, underscores, and hyphens")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    started = now()
    run_id = args.run_id or started.strftime(TIME_FMT)
    run_label = started.strftime("%Y-%m-%d %H:%M:%S")
    generated_at = iso(started)
    base = get_stage_dir("intake", run_id)
    raw_dir = base / "raw"
    notes_dir = base / "notes"
    raw_dir.mkdir(parents=True, exist_ok=True)
    notes_dir.mkdir(parents=True, exist_ok=True)

    generic_tasks: dict[str, ChannelTaskResult] = {}
    extra_artifacts: list[str] = []
    if INTAKE_MODE == "legacy":
        ports_status: dict[str, dict[str, Any]] = {}
        try:
            trendradar_base = resolve_trendradar_base()
            ports_status["reports"] = {"status": "ok", "base": trendradar_base}
        except Exception as exc:
            trendradar_base = PORT_REPORTS
            ports_status["reports"] = {"status": "error", "base": trendradar_base, "error": str(exc)}

        platform_tasks: dict[str, ChannelTaskResult] = {}
        for platform, limit in PLATFORM_FETCH_LIMITS.items():
            task = fetch_platform_task(platform, limit, raw_dir)
            platform_tasks[platform] = task
            ports_status.setdefault("5173", {"status": "ok", "base": PORT_5173})
            if task.status == "error":
                ports_status["5173"] = {"status": "error", "base": PORT_5173, "error": "; ".join(task.issues)}

        content_task = fetch_content_research_task(raw_dir)
        if content_task.status == "error":
            ports_status["5173"] = {"status": "error", "base": PORT_5173, "error": "; ".join(content_task.issues)}

        report_task = fetch_reports_task(trendradar_base, raw_dir)
        if report_task.status == "error":
            ports_status["reports"] = {"status": "error", "base": trendradar_base, "error": "; ".join(report_task.issues)}

        ai_hot_task = fetch_ai_hot_task(platform_tasks, content_task, raw_dir)

        wechat_task, channels, latest_articles, curated_articles = fetch_wechat_task(raw_dir)
        ports_status["8000"] = {
            "status": wechat_task.status,
            "base": PORT_8000_API,
            "issues": wechat_task.issues,
            "attempts": wechat_task.attempts,
            "waited_seconds": wechat_task.waited_seconds,
        }
    else:
        (
            platform_tasks,
            content_task,
            ai_hot_task,
            report_task,
            wechat_task,
            channels,
            latest_articles,
            curated_articles,
            generic_tasks,
            ports_status,
            extra_artifacts,
        ) = build_simple_intake_tasks(raw_dir)

    selected = build_selected_items(
        platform_tasks,
        content_task,
        ai_hot_task,
        report_task,
        wechat_task,
        latest_articles,
        curated_articles,
        generic_tasks,
    )
    score_selected_items(selected, started)
    analysis_selected = pick_analysis_items(selected)
    intake_records = [item.to_record(run_id, index + 1, generated_at) for index, item in enumerate(selected)]
    dump_json(raw_dir / "intake_records.json", intake_records)

    entity_rankings = build_entity_rankings(analysis_selected, generated_at, run_id)
    event_clusters = build_event_clusters(analysis_selected, generated_at, run_id)
    source_quality_report = build_source_quality_report(selected, generated_at, run_id)
    analysis_report = build_analysis_report(selected, analysis_selected)
    channel_top10 = build_channel_top10(selected)
    brief_input = build_brief_input(run_id, generated_at, event_clusters, channel_top10, entity_rankings)
    intake_gate = build_intake_gate(run_id, generated_at, selected)
    dump_json(base / "ai_hot_topics.json", {"run_id": run_id, "generated_at": generated_at, "items": ai_hot_task.items, "meta": ai_hot_task.meta})
    dump_json(base / "entity_rankings.json", entity_rankings)
    dump_json(base / "event_clusters.json", event_clusters)
    dump_json(base / "source_quality_report.json", source_quality_report)
    dump_json(base / "channel_top10.json", channel_top10)
    dump_json(base / "brief_input.json", brief_input)
    dump_json(base / "intake_review.json", intake_gate)
    all_channel_tasks = {
        **generic_tasks,
        **platform_tasks,
        "content_research": content_task,
        "ai_hot": ai_hot_task,
        "reports": report_task,
        "wechat": wechat_task,
    }
    dump_json(base / "channel_tasks.json", {name: asdict(task) for name, task in all_channel_tasks.items()})

    counts = {
        **{f"{platform}_total": task.total for platform, task in platform_tasks.items()},
        **{f"{name}_total": task.total for name, task in generic_tasks.items()},
        "content_research_candidates": content_task.meta.get("total_candidates", content_task.total),
        "ai_hot_total": ai_hot_task.total,
        "trendradar_reports": report_task.meta.get("reports_count", 0),
        "trendradar_links": report_task.total,
        "wemprss_channels_total": channels.get("data", {}).get("total", 0),
        "wemprss_articles_total": latest_articles.get("data", {}).get("total", 0),
        "curated_articles": sum(len(payload.get("data", {}).get("list", [])) for payload in curated_articles.values()),
        "selected_records": len(intake_records),
        "channel_top10_total": sum(len(items) for items in channel_top10.values()),
        "valid_linked_records": sum(1 for item in selected if item.title and item.url),
        "wechat_chat_records_total": generic_tasks["local_chat"].total if "local_chat" in generic_tasks else 0,
        "local_mp_articles_total": wechat_task.total,
        "local_media_articles_total": content_task.total,
    }
    simple_sources = ports_status.get("simple_intake", {}).get("sources", {})
    if INTAKE_MODE != "legacy":
        counts["local_news_total"] = int(simple_sources.get("local_news", {}).get("total") or 0)
        counts["public_news_total"] = int(simple_sources.get("public_news", {}).get("total") or 0)
        counts["news_total"] = generic_tasks["news"].total if "news" in generic_tasks else 0
        counts["news_deduplicated_total"] = int(
            (generic_tasks.get("news").meta if generic_tasks.get("news") else {}).get("deduplicated") or 0
        )

    report_md, draft_md = build_markdown(
        run_label,
        counts,
        selected,
        analysis_report,
        entity_rankings,
        event_clusters,
        source_quality_report,
        channel_top10,
        wechat_task,
    )
    dump_text(notes_dir / "01_内容采集_报告.md", report_md)
    dump_text(notes_dir / "01_内容采集_底稿.md", draft_md)

    manifest = {
        "run_id": run_id,
        "generated_at": generated_at,
        "stage": "intake",
        "object_type": "Run",
        "execution_model": "agent-driven",
        "run_dir": str(base),
        "intake_mode": INTAKE_MODE,
        "ports": ports_status,
        "ports_status": ports_status,
        "counts": counts,
        "analysis_pool": analysis_report,
        "channel_tasks": {name: {"status": task.status, "attempts": task.attempts, "waited_seconds": task.waited_seconds, "issues": task.issues, "total": task.total} for name, task in all_channel_tasks.items()},
        "artifacts": [
            *extra_artifacts,
            "raw/mediacrawler_latest_x.json",
            "raw/mediacrawler_latest_xhs.json",
            "raw/mediacrawler_latest_douyin.json",
            "raw/mediacrawler_latest_wb.json",
            "raw/mediacrawler_latest_bili.json",
            "raw/mediacrawler_topnotes_content_research.json",
            "raw/ai_hot_reddit.json",
            "raw/ai_hot_hn.json",
            "raw/trendradar_reports.json",
            "raw/trendradar_latest_report.html",
            "raw/trendradar_top_links.json",
            "raw/wemprss_public_channels.json",
            "raw/wemprss_articles_latest.json",
            "raw/intake_records.json",
            "ai_hot_topics.json",
            "entity_rankings.json",
            "event_clusters.json",
            "source_quality_report.json",
            "channel_top10.json",
            "brief_input.json",
            "channel_tasks.json",
            "intake_review.json",
            "notes/01_内容采集_报告.md",
            "notes/01_内容采集_底稿.md",
        ],
        "next_stage": "brief",
    }
    dump_json(base / "intake_manifest.json", manifest)

    print(
        json.dumps(
            {
                "run_id": run_id,
                "out_dir": str(base),
                "counts": counts,
                "top_event_cluster": event_clusters[0]["cluster_id"] if event_clusters else None,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
