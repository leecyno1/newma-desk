from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
import re

from vibe_visualization_api.policy_analysis.collector import collect_policy_feeds
from vibe_visualization_api.policy_analysis.collector import classify_lifecycle, extract_policy_entities, is_policy_document
from vibe_visualization_api.policy_analysis.store import PolicyStore


OFFICIAL_SOURCES = [
    {"id": "gov", "name": "中国政府网", "url": "https://www.gov.cn/zhengce/", "categories": ["综合", "财政政策", "产业政策"], "rssHubPath": "/gov/zhengce/govall"},
    {"id": "pbc", "name": "中国人民银行", "url": "https://www.pbc.gov.cn/", "categories": ["货币政策", "金融监管"], "rssHubPath": "/gov/pbc/tradeAnnouncement"},
    {"id": "csrc", "name": "中国证监会", "url": "https://www.csrc.gov.cn/", "categories": ["资本市场", "金融监管"], "rssHubPath": "/gov/csrc/zfxxgk_zdgk/c101953"},
    {"id": "ndrc", "name": "国家发展改革委", "url": "https://www.ndrc.gov.cn/", "categories": ["产业政策", "宏观政策"], "rssHubPath": "/gov/ndrc/zfxxgk"},
    {"id": "mof", "name": "财政部", "url": "https://www.mof.gov.cn/", "categories": ["财政政策"], "rssHubPath": "/gov/mof/gss/zhengcefabu"},
    {"id": "nfra", "name": "国家金融监督管理总局", "url": "https://www.nfra.gov.cn/", "categories": ["金融监管"], "rssHubPath": "/gov/nfra/926"},
    {"id": "miit", "name": "工业和信息化部", "url": "https://www.miit.gov.cn/", "categories": ["产业政策"], "rssHubPath": "/gov/miit/zcjd"},
    {"id": "mofcom", "name": "商务部", "url": "https://www.mofcom.gov.cn/", "categories": ["对外经贸", "消费政策"], "rssHubPath": "/gov/mofcom/article/b"},
    {"id": "stats", "name": "国家统计局", "url": "https://www.stats.gov.cn/", "categories": ["宏观数据"], "rssHubPath": "/gov/stats/sj/sjjd"},
]
COMPARISON_TERMS = (
    "降准", "降息", "LPR", "流动性", "信贷", "财政", "税收", "专项债",
    "国债", "补贴", "准入", "监管", "处罚", "并购重组", "上市公司",
    "人工智能", "数字经济", "绿色低碳", "新能源", "制造业", "房地产",
)


def _event(
    event_id: str,
    title: str,
    event_date: date,
    institution: str,
    category: str,
    level: int,
    status: str,
    certainty: str,
    summary: str,
    rationale: list[str],
    source_url: str,
    *,
    market_scope: list[str],
    document_type: str = "formal-policy",
) -> dict:
    lifecycle_stage, series_key = classify_lifecycle(title, document_type, status)
    return {
        "id": event_id,
        "title": title,
        "date": event_date.isoformat(),
        "institution": institution,
        "category": category,
        "level": level,
        "status": status,
        "certainty": certainty,
        "summary": summary,
        "rationale": rationale,
        "sourceUrl": source_url,
        "marketScope": market_scope,
        "assessmentConfidence": 1,
        "assessmentStatus": "reviewed",
        "documentType": document_type,
        "lifecycleStage": lifecycle_stage, "policySeriesKey": series_key,
        "entities": extract_policy_entities(title, summary),
    }


def policy_events(today: date | None = None) -> list[dict]:
    current = today or date.today()
    year = current.year
    events = [
        _event("hist-20240924", "国新办金融支持经济高质量发展发布会", date(2024, 9, 24), "中国人民银行等", "货币政策", 3, "published", "official", "涉及降准、政策利率、存量房贷和资本市场支持工具的一揽子政策。", ["多部门联合发布", "改变流动性与风险偏好", "覆盖股票、债券与地产链"], "https://www.gov.cn/zhengce/202409/content_6976207.htm", market_scope=["A股", "债券", "地产"]),
        _event("hist-20241209", "中央政治局会议分析研究经济工作", date(2024, 12, 9), "中共中央政治局", "宏观政策", 3, "published", "official", "会议提出实施更加积极的财政政策和适度宽松的货币政策。", ["最高层级政策定调", "财政与货币政策框架变化", "影响全市场定价"], "https://www.gov.cn/yaowen/liebiao/202412/content_6991714.htm", market_scope=["全市场"]),
        _event("hist-20250305", "政府工作报告与年度目标发布", date(2025, 3, 5), "国务院", "宏观政策", 3, "published", "official", "公布年度增长、赤字、就业和重点产业政策目标。", ["年度顶层政策总纲", "包含量化宏观目标", "跨行业影响"], "https://www.gov.cn/yaowen/liebiao/202503/content_7011474.htm", market_scope=["全市场"]),
        _event(f"window-{year}-q3-mpr", "货币政策执行报告发布窗口", date(year, 8, 15), "中国人民银行", "货币政策", 2, "scheduled", "expected-window", "季度货币政策执行报告通常在季后发布，关注流动性、信贷和汇率表述变化。", ["央行季度核心报告", "影响利率与流动性预期", "日期为规律窗口，待官方确认"], "https://www.pbc.gov.cn/zhengcehuobisi/125207/125227/125957/index.html", market_scope=["A股", "债券", "人民币"]),
        _event(f"window-{year}-aug-lpr", "8 月贷款市场报价利率（LPR）", date(year, 8, 20), "中国人民银行授权全国银行间同业拆借中心", "货币政策", 2, "scheduled", "calendar-rule", "每月 20 日公布 LPR，遇节假日顺延。", ["固定月度政策利率日程", "直接影响信贷与地产预期", "最终日期以官方公告为准"], "https://www.pbc.gov.cn/zhengcehuobisi/125207/125213/125440/index.html", market_scope=["银行", "地产", "债券"]),
        _event(f"window-{year}-sep-pmi", "9 月制造业采购经理指数发布", date(year, 9, 30), "国家统计局", "宏观数据", 1, "scheduled", "calendar-rule", "月末宏观数据窗口，用于观察政策效果与经济景气变化。", ["高频宏观验证数据", "通常不直接改变制度规则", "日期为统计发布惯例"], "https://www.stats.gov.cn/sj/zxfb/", market_scope=["A股", "商品"]),
        _event(f"window-{year}-q3-politburo", "三季度经济形势分析会议窗口", date(year, 10, 28), "中共中央政治局", "宏观政策", 3, "scheduled", "expected-window", "关注稳增长、财政、地产和资本市场政策定调。", ["最高层级政策定调", "可能影响多部门后续政策", "日期为历史规律窗口，非官方预约"], "https://www.gov.cn/yaowen/", market_scope=["全市场"]),
        _event(f"window-{year}-cewc", "中央经济工作会议窗口", date(year, 12, 12), "中共中央、国务院", "宏观政策", 3, "scheduled", "expected-window", "年度政策主线和次年经济工作部署的重要观察窗口。", ["年度最高层级经济工作部署", "跨财政、货币与产业政策", "具体日期待官方确认"], "https://www.gov.cn/yaowen/", market_scope=["全市场"]),
    ]
    for event in events:
        event_date = date.fromisoformat(event["date"])
        if event["status"] == "scheduled" and event_date < current:
            event["status"] = "awaiting-verification"
            event["lifecycleStage"] = "scheduled"
    return sorted(events, key=lambda item: item["date"], reverse=True)


def _comparison_features(event: dict) -> set[str]:
    text = f"{event['title']} {event['summary']}"
    features = {term for term in COMPARISON_TERMS if term in text}
    features.update(re.findall(r"(?<!\d)\d+(?:\.\d+)?(?:%|亿元|万亿元|年|个月|日)?", text))
    return features


def compare_policy_events(current: dict, previous: dict) -> dict:
    current_features = _comparison_features(current)
    previous_features = _comparison_features(previous)
    return {
        "basePolicyId": previous["id"],
        "basis": "title-summary",
        "added": sorted(current_features - previous_features)[:12],
        "removed": sorted(previous_features - current_features)[:12],
        "shared": sorted(current_features & previous_features)[:12],
        "note": "基于标题与采集摘要的要素差异，不等同于政策全文逐条对比。",
    }


def build_policy_interpretation(event: dict, related: list[dict]) -> dict:
    """Build an auditable fallback when the model provider is unavailable."""
    ordered = sorted(related, key=lambda item: (item["date"], item["id"]))
    previous = ordered[-1] if ordered else None
    comparison = compare_policy_events(event, previous) if previous else None
    return {
        "policyId": event["id"],
        "title": event["title"],
        "sourceUrl": event["sourceUrl"],
        "mode": "rule-fallback",
        "impactAnalysis": {
            "facts": [event["summary"], *event.get("rationale", [])],
            "inferences": [
                f"重点观察：{scope}。" for scope in event.get("marketScope", [])
            ],
            "uncertainties": [
                "以上为基于公开摘要的研究框架，不等同于投资建议。",
                "执行细则与落地节奏仍需以官方后续文件为准。",
            ],
        },
        "historicalComparison": {
            "matchedPolicies": [
                {"id": item["id"], "title": item["title"], "date": item["date"]}
                for item in related
            ],
            "added": comparison["added"] if comparison else [],
            "removed": comparison["removed"] if comparison else [],
            "shared": comparison["shared"] if comparison else [],
            "note": "历史对比基于政策标题与采集摘要，不代表全文语义推演。",
        },
        "transcriptComparison": {
            "status": "unavailable",
            "basis": "summary",
            "note": "当前仅保存官方链接与采集摘要，尚未取得两份可比对的官方正文。",
        },
    }


async def policy_dashboard(
    today: date | None = None,
    *,
    database_path: Path,
    rsshub_base_url: str = "",
    timeout_seconds: float = 8.0,
    refresh: bool = False,
) -> dict:
    current = today or date.today()
    store = PolicyStore(database_path)
    baseline_events = policy_events(current)
    store.upsert_events(baseline_events)
    if refresh:
        live_events, collector_state = await collect_policy_feeds(
            OFFICIAL_SOURCES, rsshub_base_url, timeout_seconds
        )
        store.upsert_events(live_events)
        collected_at = collector_state.get("collectedAt")
        if collected_at:
            store.record_source_runs(collector_state.get("feeds", []), collected_at)
    else:
        collector_state = {
            "mode": "rsshub-cache" if rsshub_base_url else "official-source-registry",
            "status": "not-configured",
            "feeds": [],
        }
    stored_runs = store.source_runs()
    if not refresh and stored_runs:
        active_sources = [source for source in OFFICIAL_SOURCES if source["rssHubPath"]]
        feeds = [
            stored_runs.get(source["id"], {
                "sourceId": source["id"], "status": "pending", "items": 0,
            })
            for source in active_sources
        ]
        successful = sum(feed["status"] == "ok" for feed in feeds)
        collector_state = {
            "mode": "rsshub-cache",
            "status": "ready" if successful == len(feeds) else "degraded" if successful else "unavailable",
            "feeds": feeds,
            "collectedAt": max(
                (feed.get("lastAttemptAt", "") for feed in feeds), default=""
            ),
        }
    else:
        collector_state["feeds"] = [
            {**stored_runs.get(feed["sourceId"], {}), **feed}
            for feed in collector_state.get("feeds", [])
        ]
    events = [
        item for item in store.list_events()
        if item.get("discoveredBy") != "rsshub"
        or is_policy_document(
            item["title"], item["summary"],
            item["id"].split("-", 2)[1] if item["id"].startswith("feed-") else "",
        )
    ]
    for item in events:
        lifecycle_stage, series_key = classify_lifecycle(
            item["title"], item["documentType"], item["status"]
        )
        item["lifecycleStage"] = lifecycle_stage
        item["policySeriesKey"] = series_key
    series = {}
    for item in events:
        series.setdefault(item["policySeriesKey"], []).append(item)
    for item in events:
        related = series[item["policySeriesKey"]]
        item["relatedPolicyIds"] = [
            candidate["id"] for candidate in related if candidate["id"] != item["id"]
        ]
        ordered = sorted(related, key=lambda value: (value["date"], value["id"]))
        position = next((index for index, candidate in enumerate(ordered) if candidate["id"] == item["id"]), 0)
        previous = ordered[position - 1] if position > 0 else (ordered[1] if len(ordered) > 1 else None)
        item["comparison"] = compare_policy_events(item, previous) if previous else None
    future = [item for item in events if item["date"] >= current.isoformat() and item["status"] == "scheduled"]
    return {
        "schemaVersion": "newma-desk.policy-analysis.v1",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "today": current.isoformat(),
        "events": events,
        "sources": OFFICIAL_SOURCES,
        "summary": {
            "total": len(events),
            "level3": sum(1 for item in events if item["level"] == 3),
            "upcoming": len(future),
            "nextDate": min((item["date"] for item in future), default=None),
            "lifecycle": {stage: sum(1 for item in events if item["lifecycleStage"] == stage)
                for stage in ("scheduled", "solicitation", "published", "effective", "amended", "adjusted", "repealed", "expired")},
        },
        "assessment": [
            {"level": 3, "label": "战略级", "definition": "改变宏观政策框架、制度规则或全市场定价。"},
            {"level": 2, "label": "行业级", "definition": "显著影响一个或多个行业、资产或资金成本。"},
            {"level": 1, "label": "执行级", "definition": "局部规则、例行数据或执行口径调整。"},
        ],
        "collector": {
            "foundation": "DIYgod/RSSHub",
            "revision": "ddaa58f793eb5c5a8075ec507ce86dcd2e17cd95",
            **collector_state,
            "note": "公共 RSSHub 实例不作为生产依赖；本地采集器启用后可按 rssHubPath 增量接入。",
        },
    }
