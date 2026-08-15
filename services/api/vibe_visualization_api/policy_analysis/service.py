from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from vibe_visualization_api.policy_analysis.collector import collect_policy_feeds


OFFICIAL_SOURCES = [
    {"id": "gov", "name": "中国政府网", "url": "https://www.gov.cn/zhengce/", "categories": ["综合", "财政政策", "产业政策"], "rssHubPath": "/gov/zhengce/zuixin"},
    {"id": "pbc", "name": "中国人民银行", "url": "https://www.pbc.gov.cn/", "categories": ["货币政策", "金融监管"], "rssHubPath": "/gov/pbc/goutongjiaoliu"},
    {"id": "csrc", "name": "中国证监会", "url": "https://www.csrc.gov.cn/", "categories": ["资本市场", "金融监管"], "rssHubPath": "/gov/csrc/zfxxgk_zdgk/c101953"},
    {"id": "ndrc", "name": "国家发展改革委", "url": "https://www.ndrc.gov.cn/", "categories": ["产业政策", "宏观政策"], "rssHubPath": "/gov/ndrc/zfxxgk"},
    {"id": "mof", "name": "财政部", "url": "https://www.mof.gov.cn/", "categories": ["财政政策"], "rssHubPath": "/gov/mof/bond"},
    {"id": "nfra", "name": "国家金融监督管理总局", "url": "https://www.nfra.gov.cn/", "categories": ["金融监管"], "rssHubPath": "/gov/nfra/926"},
    {"id": "miit", "name": "工业和信息化部", "url": "https://www.miit.gov.cn/", "categories": ["产业政策"], "rssHubPath": "/gov/miit/zcwj"},
    {"id": "mofcom", "name": "商务部", "url": "https://www.mofcom.gov.cn/", "categories": ["对外经贸", "消费政策"], "rssHubPath": "/gov/mofcom/article/b"},
    {"id": "stats", "name": "国家统计局", "url": "https://www.stats.gov.cn/", "categories": ["宏观数据"], "rssHubPath": None},
]


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
) -> dict:
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
    return sorted(events, key=lambda item: item["date"], reverse=True)


async def policy_dashboard(
    today: date | None = None,
    *,
    rsshub_base_url: str = "",
    timeout_seconds: float = 8.0,
) -> dict:
    current = today or date.today()
    baseline_events = policy_events(current)
    live_events, collector_state = await collect_policy_feeds(OFFICIAL_SOURCES, rsshub_base_url, timeout_seconds)
    events_by_id = {item["id"]: item for item in baseline_events}
    known_urls = {item["sourceUrl"] for item in baseline_events}
    for event in live_events:
        if event["sourceUrl"] not in known_urls:
            events_by_id[event["id"]] = event
            known_urls.add(event["sourceUrl"])
    events = sorted(events_by_id.values(), key=lambda item: item["date"], reverse=True)
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
            "nextDate": future[-1]["date"] if future else None,
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
