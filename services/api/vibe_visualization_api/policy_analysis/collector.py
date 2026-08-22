from __future__ import annotations

import hashlib
import asyncio
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
import re
from xml.etree import ElementTree
from urllib.parse import urlsplit

import httpx


STRATEGIC_AUTHORITY_TERMS = ("中共中央", "中央政治局", "国务院", "全国人民代表大会")
MARKET_WIDE_TOOL_TERMS = (
    "降准", "降低存款准备金率", "降息", "政策利率", "印花税",
    "赤字率", "特别国债", "资本市场支持工具",
)
SYSTEMIC_CHANGE_TERMS = ("总体方案", "纲要", "条例", "促进法", "五年规划")
SECTOR_RULE_TERMS = (
    "办法", "规定", "通知", "指导意见", "实施方案", "行动方案",
    "规划", "准入", "补贴", "税率", "关税", "修改", "废止",
)
DOCUMENT_TYPE_RULES = [
    ("policy-interpretation", ("政策解读", "一图读懂", "图解", "答记者问", "问答", "解读")),
    ("macro-data", ("数据报告", "统计公报", "采购经理指数", "CPI", "PPI", "金融统计数据")),
    ("meeting-speech", ("会议", "讲话", "出席", "调研", "座谈会", "发表重要文章", "主场活动")),
    ("implementation-update", ("推进", "进展", "成效", "动态", "多措并举", "截至", "前7月", "前8月", "前9月")),
]
LIFECYCLE_RULES = [
    ("repealed", ("废止", "停止执行", "取消")),
    ("expired", ("失效", "到期", "终止")),
    ("solicitation", ("征求意见", "意见稿", "公开征集", "征求稿")),
    ("amended", ("修订", "修改", "修正")),
    ("adjusted", ("调整",)),
    ("effective", ("生效", "施行", "正式实施")),
]
LIFECYCLE_LABELS = {
    "scheduled": "待发布", "solicitation": "征求意见",
    "published": "正式发布", "effective": "已生效",
    "amended": "修订", "adjusted": "调整",
    "repealed": "废止", "expired": "失效",
}
ENTITY_RULES = [
    ("industry", "银行", ("银行", "信贷", "存款")),
    ("industry", "证券", ("证券", "券商", "IPO", "并购重组")),
    ("industry", "保险", ("保险",)),
    ("industry", "房地产", ("房地产", "房贷", "住房")),
    ("industry", "汽车", ("汽车", "新能源车")),
    ("industry", "医药生物", ("医药", "医疗", "药品")),
    ("industry", "电子", ("半导体", "集成电路", "芯片")),
    ("industry", "计算机", ("人工智能", "数字经济", "软件")),
    ("industry", "电力设备", ("光伏", "储能", "电池", "新能源")),
    ("concept", "低空经济", ("低空经济",)),
    ("concept", "新质生产力", ("新质生产力",)),
    ("concept", "国企改革", ("国企改革", "国有企业改革")),
    ("concept", "数据要素", ("数据要素",)),
    ("concept", "绿色低碳", ("绿色低碳", "碳达峰", "碳中和")),
]
TRADED_ENTITY_RULES = [
    ("etf", "沪深300ETF", "510300", ("沪深300ETF", "沪深300")),
    ("etf", "上证50ETF", "510050", ("上证50ETF", "上证50")),
    ("etf", "创业板ETF", "159915", ("创业板ETF", "创业板")),
    ("etf", "科创50ETF", "588000", ("科创50ETF", "科创50")),
    ("etf", "医药ETF", "512010", ("医药ETF",)),
]
POLICY_DOCUMENT_TERMS = (
    "通知", "公告", "决定", "意见", "办法", "规定", "条例", "规划",
    "方案", "指南", "细则", "目录", "清单", "政策解读", "答记者问",
    "征求意见", "工作报告", "执行报告", "统计公报", "金融统计数据",
    "采购经理指数", "CPI", "PPI", "LPR", "公开市场业务交易公告",
    "中央政治局会议", "国务院常务会议", "发布会",
)
POLICY_SPECIALIST_SOURCES = {"pbc", "csrc", "ndrc", "mof", "nfra", "miit", "stats"}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def clean_policy_text(value: str, limit: int = 280) -> str:
    if not value:
        return ""
    parser = _TextExtractor()
    parser.feed(value)
    text = unescape(" ".join(parser.parts))
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _text(node: ElementTree.Element, *names: str) -> str:
    for name in names:
        child = node.find(name)
        if child is not None and child.text:
            return child.text.strip()
    return ""


def _published_date(value: str) -> date | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).date()
    except (TypeError, ValueError, OverflowError):
        pass
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def classify_document_type(title: str, summary: str = "") -> str:
    del summary
    for document_type, terms in DOCUMENT_TYPE_RULES:
        if any(term in title for term in terms):
            return document_type
    return "formal-policy"


def is_policy_document(title: str, summary: str, source_id: str) -> bool:
    """Exclude ordinary government news from the policy evidence store."""
    if source_id in POLICY_SPECIALIST_SOURCES:
        return True
    del summary
    return bool(re.search(r"《[^》]{3,120}》", title)) or any(
        term in title for term in POLICY_DOCUMENT_TERMS
    )


def classify_lifecycle(title: str, document_type: str, status: str = "published") -> tuple[str, str]:
    """Return the policy lifecycle stage and a stable series key."""
    if status in {"scheduled", "awaiting-verification"}:
        stage = "scheduled"
    else:
        text = title
        stage = "published"
        for candidate, terms in LIFECYCLE_RULES:
            if any(term in text for term in terms):
                stage = candidate
                break
    quoted = re.findall(r"《([^》]{4,120})》", title)
    series_key = quoted[0] if quoted else re.sub(
        r"政策解读|一图读懂|图解|关于|发布|通知|公告|决定|实施|办法|规划", "", title
    )
    series_key = re.sub(r"[^一-龥A-Za-z0-9]+", "", series_key).lower()[:120]
    return stage, series_key or title[:80]


def assess_policy(
    title: str, summary: str = "", document_type: str = "formal-policy"
) -> tuple[int, float, list[str]]:
    text = f"{title} {summary}"
    score = 0
    rationale: list[str] = []
    if any(term in text for term in STRATEGIC_AUTHORITY_TERMS):
        score += 4
        rationale.append("发布或决策层级属于中央战略层")
    if any(term in text for term in MARKET_WIDE_TOOL_TERMS):
        score += 4
        rationale.append("涉及利率、准备金或全市场定价工具")
    if any(term in text for term in SYSTEMIC_CHANGE_TERMS):
        score += 2
        rationale.append("涉及中长期制度或政策框架")
    if any(term in text for term in SECTOR_RULE_TERMS):
        score += 2
        rationale.append("涉及行业规则、执行方案或政策工具调整")

    if score >= 4:
        level = 3
    elif score >= 2:
        level = 2
    else:
        level = 1
        rationale.append("暂未发现跨行业或制度级影响信号")
    if document_type in {"policy-interpretation", "meeting-speech", "implementation-update", "macro-data"} and level == 3:
        level = 2
        rationale.append("当前为解读、会议、执行动态或数据发布，不直接视为战略级正式政策")
    rationale.append("量级为规则初筛，需研究员结合正文复核")
    confidence = min(0.9, 0.56 + max(1, len(rationale) - 1) * 0.09)
    return level, confidence, rationale


def classify_policy(title: str, summary: str, source: dict) -> tuple[str, list[str]]:
    if source.get("id") == "stats":
        return "宏观数据", ["A股", "债券", "商品"]
    text = f"{title} {summary}"
    rules = [
        ("货币政策", ("降准", "降息", "LPR", "公开市场", "货币政策", "存款准备金"), ["A股", "债券", "人民币"]),
        ("财政政策", ("财政", "预算", "专项债", "国债", "税收", "政府采购"), ["A股", "债券"]),
        ("资本市场", ("证券", "期货", "上市公司", "基金", "IPO", "并购重组"), ["A股", "券商", "基金"]),
        ("金融监管", ("银行", "保险", "信托", "金融监管", "反洗钱"), ["银行", "保险", "债券"]),
        ("对外经贸", ("关税", "进出口", "外资", "外贸", "贸易", "制裁"), ["出口链", "人民币"]),
        ("产业政策", ("产业", "能源", "制造", "科技", "数字经济", "消费", "生态"), ["行业主题", "相关ETF"]),
    ]
    for category, terms, scope in rules:
        if any(term in text for term in terms):
            return category, scope
    return source["categories"][0], ["待研判"]


def extract_policy_entities(title: str, summary: str) -> list[dict]:
    text = f"{title} {summary}"
    entities: list[dict] = []
    for entity_type, name, terms in ENTITY_RULES:
        matched = next((term for term in terms if term in text), None)
        if matched:
            slug = hashlib.sha1(name.encode()).hexdigest()[:12]
            entities.append({
                "type": entity_type, "canonicalId": f"{entity_type}:cn:{slug}",
                "displayName": name, "confidence": 0.76,
                "evidence": matched, "source": "rule",
            })
    for entity_type, name, symbol, terms in TRADED_ENTITY_RULES:
        matched = next((term for term in terms if term in text), None)
        if matched:
            entities.append({
                "type": entity_type, "canonicalId": f"{entity_type}:CN:{symbol}",
                "displayName": name, "market": "CN", "symbol": symbol,
                "assetType": "etf", "confidence": 0.9,
                "evidence": matched, "source": "rule",
            })
    explicit_codes = re.findall(
        r"(?:代码|证券代码|股票代码|基金代码|ETF代码)\s*[:：]?\s*([036][0-9]{5})(?!\d)",
        text,
    )
    for symbol in sorted(set(explicit_codes)):
        if any(item.get("symbol") == symbol for item in entities):
            continue
        entities.append({
            "type": "security", "canonicalId": f"security:CN:{symbol}",
            "displayName": symbol, "market": "CN", "symbol": symbol,
            "assetType": "stock", "confidence": 0.88,
            "evidence": symbol, "source": "rule",
        })
    return entities[:20]


def _is_official_link(link: str, source_url: str) -> bool:
    link_host = (urlsplit(link).hostname or "").removeprefix("www.")
    source_host = (urlsplit(source_url).hostname or "").removeprefix("www.")
    return bool(link_host and source_host and (link_host == source_host or link_host.endswith(f".{source_host}")))


def parse_policy_feed(xml: str, source: dict) -> list[dict]:
    root = ElementTree.fromstring(xml)
    entries = root.findall(".//item")
    atom = False
    if not entries:
        entries = root.findall(".//{http://www.w3.org/2005/Atom}entry")
        atom = True

    events = []
    for entry in entries:
        if atom:
            title = _text(entry, "{http://www.w3.org/2005/Atom}title")
            published = _text(entry, "{http://www.w3.org/2005/Atom}published", "{http://www.w3.org/2005/Atom}updated")
            link_node = entry.find("{http://www.w3.org/2005/Atom}link")
            link = link_node.get("href", "").strip() if link_node is not None else ""
            summary = _text(entry, "{http://www.w3.org/2005/Atom}summary", "{http://www.w3.org/2005/Atom}content")
        else:
            title = _text(entry, "title")
            published = _text(entry, "pubDate", "date")
            link = _text(entry, "link", "guid")
            summary = _text(entry, "description")
        event_date = _published_date(published)
        if not title or not _is_official_link(link, source["url"]) or event_date is None:
            continue
        summary = clean_policy_text(summary)
        if not is_policy_document(title, summary, source["id"]):
            continue
        document_type = classify_document_type(title, summary)
        lifecycle_stage, series_key = classify_lifecycle(title, document_type)
        level, confidence, rationale = assess_policy(title, summary, document_type)
        category, market_scope = classify_policy(title, summary, source)
        entities = extract_policy_entities(title, summary)
        digest = hashlib.sha1(f"{source['id']}:{link}".encode()).hexdigest()[:16]
        content_hash = hashlib.sha256(f"{title}:{event_date}:{summary}".encode()).hexdigest()
        events.append({
            "id": f"feed-{source['id']}-{digest}", "title": title,
            "date": event_date.isoformat(), "institution": source["name"],
            "category": category, "level": level,
            "status": "published", "certainty": "official",
            "summary": summary or "由官方渠道采集，详情以原文为准。",
            "rationale": rationale, "sourceUrl": link,
            "marketScope": market_scope, "discoveredBy": "rsshub",
            "assessmentConfidence": confidence, "assessmentStatus": "machine",
            "documentType": document_type,
            "lifecycleStage": lifecycle_stage, "policySeriesKey": series_key,
            "entities": entities,
            "contentHash": content_hash,
        })
    return events


async def collect_policy_feeds(
    sources: list[dict], base_url: str, timeout_seconds: float,
    client: httpx.AsyncClient | None = None,
) -> tuple[list[dict], dict]:
    if not base_url:
        return [], {"mode": "official-source-registry", "status": "not-configured", "feeds": []}

    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True)
    async def collect_source(source: dict) -> tuple[list[dict], dict] | None:
        path = source.get("rssHubPath")
        if not path:
            return None
        url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
        try:
            response = await http_client.get(url, headers={"Accept": "application/rss+xml, application/atom+xml, application/xml"})
            response.raise_for_status()
            parsed = parse_policy_feed(response.text, source)
            return parsed, {"sourceId": source["id"], "status": "ok", "items": len(parsed)}
        except (httpx.HTTPError, ElementTree.ParseError, ValueError) as error:
            return [], {"sourceId": source["id"], "status": "failed", "items": 0, "reason": str(error)[:160]}

    try:
        results = [result for result in await asyncio.gather(*(collect_source(source) for source in sources)) if result is not None]
    finally:
        if owns_client:
            await http_client.aclose()

    events = [event for source_events, _ in results for event in source_events]
    feed_status = [status for _, status in results]
    successful = sum(item["status"] == "ok" for item in feed_status)
    status = "ready" if successful == len(feed_status) else "degraded"
    if not successful:
        status = "unavailable"
    return events, {"mode": "rsshub-live", "status": status, "feeds": feed_status, "collectedAt": datetime.now(timezone.utc).isoformat()}
