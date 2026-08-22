from __future__ import annotations

import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from vibe_visualization_api.global_topics.store import GlobalTopicStore


TOPICS: dict[str, dict[str, Any]] = {
    "fed-rates": {
        "title": "联储加息",
        "subtitle": "利率路径与全球资产重定价",
        "question": "下一阶段更可能降息、维持还是加息？",
        "accent": "cyan",
        "metrics": [
            {"label": "政策利率", "value": "5.50%", "change": "目标区间上限"},
            {"label": "核心通胀", "value": "3.2%", "change": "同比参考"},
            {"label": "2Y-10Y", "value": "-18bp", "change": "曲线倒挂"},
            {"label": "市场定价", "value": "2 次", "change": "未来一年降息"},
        ],
        "factors": [
            {"id": "inflation", "label": "通胀压力", "min": 0, "max": 100, "value": 58, "direction": 1.0},
            {"id": "employment", "label": "就业韧性", "min": 0, "max": 100, "value": 62, "direction": 0.8},
            {"id": "financialStress", "label": "金融压力", "min": 0, "max": 100, "value": 34, "direction": -1.1},
        ],
        "outcomes": ["降息", "维持", "加息"],
        "baseScores": [0.25, 1.1, -0.25],
        "series": [
            {"id": "policy-rate", "label": "政策利率", "color": "#38bdf8"},
            {"id": "core-inflation", "label": "核心通胀", "color": "#f59e0b"},
        ],
        "transmission": ["通胀与就业", "联储表态", "利率路径", "美元与美债", "全球风险资产"],
        "sources": ["Federal Reserve / FOMC", "FRED", "美国劳工统计局", "CME FedWatch"],
    },
    "hormuz": {
        "title": "美伊战争",
        "subtitle": "霍尔木兹海峡与能源供应冲击",
        "question": "海峡风险将缓和、受控升级还是出现中断？",
        "accent": "amber",
        "metrics": [
            {"label": "全球原油通行", "value": "约 20%", "change": "经霍尔木兹海峡"},
            {"label": "通道风险", "value": "68/100", "change": "综合监测"},
            {"label": "油轮运价", "value": "+24%", "change": "冲突敏感指标"},
            {"label": "证据状态", "value": "多源", "change": "航行与官方信号"},
        ],
        "factors": [
            {"id": "military", "label": "军事活动", "min": 0, "max": 100, "value": 66, "direction": 1.2},
            {"id": "shipping", "label": "航运中断", "min": 0, "max": 100, "value": 43, "direction": 1.1},
            {"id": "diplomacy", "label": "外交缓和", "min": 0, "max": 100, "value": 38, "direction": -1.0},
        ],
        "outcomes": ["缓和", "受控升级", "通道中断"],
        "baseScores": [0.0, 1.0, -0.35],
        "series": [
            {"id": "risk-index", "label": "通道风险", "color": "#f59e0b"},
            {"id": "tanker-rate", "label": "油轮运价", "color": "#ef4444"},
        ],
        "transmission": ["军事与航行信号", "海峡可用性", "原油与LNG供给", "运价与保险", "通胀及行业利润"],
        "sources": ["EIA", "UKMTO", "NGA 航行警告", "IEA", "World Intelligence MCP"],
    },
    "us-china-trade": {
        "title": "中美贸易",
        "subtitle": "制裁、出口管制与产业链传导",
        "question": "制裁强度将缓和、维持还是扩大？",
        "accent": "red",
        "metrics": [
            {"label": "限制强度", "value": "72/100", "change": "规则与实体清单"},
            {"label": "重点行业", "value": "6", "change": "芯片、AI、能源等"},
            {"label": "政策事件", "value": "14", "change": "近 12 月"},
            {"label": "供应链压力", "value": "61/100", "change": "替代与库存周期"},
        ],
        "factors": [
            {"id": "controls", "label": "出口管制", "min": 0, "max": 100, "value": 72, "direction": 1.1},
            {"id": "retaliation", "label": "反制强度", "min": 0, "max": 100, "value": 54, "direction": 0.9},
            {"id": "negotiation", "label": "谈判进展", "min": 0, "max": 100, "value": 36, "direction": -1.0},
        ],
        "outcomes": ["缓和", "维持", "扩大"],
        "baseScores": [-0.1, 1.05, -0.1],
        "series": [
            {"id": "restriction-index", "label": "限制强度", "color": "#ef4444"},
            {"id": "supply-pressure", "label": "供应链压力", "color": "#a3e635"},
        ],
        "transmission": ["法案与清单", "技术与资本限制", "企业合规成本", "供应链替代", "行业盈利与估值"],
        "sources": ["美国商务部 BIS", "OFAC", "USTR", "中国商务部", "海关总署"],
    },
}


def _seed_observations() -> list[dict[str, Any]]:
    seeds = {
        "fed-rates": {"policy-rate": [1.0, 2.5, 4.5, 5.25, 5.5, 5.5, 5.5, 5.25], "core-inflation": [6.0, 5.5, 4.7, 4.1, 3.8, 3.6, 3.4, 3.2]},
        "hormuz": {"risk-index": [28, 34, 31, 46, 51, 63, 59, 68], "tanker-rate": [18, 21, 20, 27, 31, 38, 35, 42]},
        "us-china-trade": {"restriction-index": [38, 44, 51, 55, 61, 66, 69, 72], "supply-pressure": [42, 48, 54, 51, 58, 64, 59, 61]},
    }
    dates = ["2025-01", "2025-04", "2025-07", "2025-10", "2026-01", "2026-04", "2026-06", "2026-08"]
    rows: list[dict[str, Any]] = []
    for topic_id, series_map in seeds.items():
        for series_id, values in series_map.items():
            unit = "%" if topic_id == "fed-rates" else "index"
            source = "FRED / BLS" if topic_id == "fed-rates" else "Newma 多源标准化指数"
            rows.extend({"topicId": topic_id, "seriesId": series_id, "date": date, "value": value, "unit": unit, "source": source} for date, value in zip(dates, values))
    return rows


EVENTS = [
    {"id": "fed-2026-guidance", "topicId": "fed-rates", "date": "2026-07-29", "title": "FOMC 维持利率并调整前瞻指引", "summary": "利率决定需与通胀、就业数据共同验证。", "source": "Federal Reserve", "sourceUrl": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm", "impact": "high", "confidence": 0.96},
    {"id": "fed-2026-inflation", "topicId": "fed-rates", "date": "2026-08-12", "title": "核心通胀仍高于长期目标", "summary": "限制快速宽松的空间，市场继续交易数据依赖。", "source": "BLS", "sourceUrl": "https://www.bls.gov/cpi/", "impact": "medium", "confidence": 0.91},
    {"id": "hormuz-shipping", "topicId": "hormuz", "date": "2026-08-14", "title": "霍尔木兹周边航行风险上升", "summary": "需由航行警告、船舶轨迹与官方通报交叉确认。", "source": "UKMTO / NGA", "sourceUrl": "https://www.ukmto.org/", "impact": "high", "confidence": 0.82},
    {"id": "hormuz-energy", "topicId": "hormuz", "date": "2026-08-13", "title": "能源市场计入部分供应风险溢价", "summary": "油价、油轮运价和保险费率尚未形成极端中断定价。", "source": "EIA", "sourceUrl": "https://www.eia.gov/international/analysis/special-topics/World_Oil_Transit_Chokepoints", "impact": "medium", "confidence": 0.88},
    {"id": "trade-bis", "topicId": "us-china-trade", "date": "2026-08-10", "title": "出口管制清单与许可范围更新", "summary": "先进计算、半导体设备和关联实体是主要传导节点。", "source": "BIS", "sourceUrl": "https://www.bis.gov/", "impact": "high", "confidence": 0.94},
    {"id": "trade-response", "topicId": "us-china-trade", "date": "2026-08-08", "title": "中方重申出口管制与反制裁规则", "summary": "关键矿产、供应链本地化与企业合规成本需要联动观察。", "source": "中国商务部", "sourceUrl": "https://www.mofcom.gov.cn/", "impact": "high", "confidence": 0.92},
]


def forecast(topic_id: str, factors: dict[str, float]) -> dict[str, Any]:
    topic = TOPICS[topic_id]
    configured = topic["factors"]
    normalized = []
    for factor in configured:
        value = max(float(factor["min"]), min(float(factor["max"]), float(factors.get(factor["id"], factor["value"]))))
        normalized.append(((value - 50.0) / 50.0) * factor["direction"])
    pressure = sum(normalized) / len(normalized)
    scores = list(topic["baseScores"])
    scores[0] -= pressure * 1.2
    scores[2] += pressure * 1.2
    exponents = [math.exp(score - max(scores)) for score in scores]
    total = sum(exponents)
    probabilities = [round(value / total * 100) for value in exponents]
    probabilities[1] += 100 - sum(probabilities)
    return {
        "generatedAt": datetime.now(UTC).isoformat(),
        "probabilities": [
            {"label": label, "probability": probability}
            for label, probability in zip(topic["outcomes"], probabilities)
        ],
        "dominantScenario": topic["outcomes"][probabilities.index(max(probabilities))],
        "confidence": round(0.55 + min(abs(pressure), 0.5) * 0.3, 2),
        "method": "透明因子加权情景模型 v1",
        "disclaimer": "概率用于情景比较，不是确定性预测或投资建议。",
    }


def topic_snapshot(topic_id: str, database_path: Path) -> dict[str, Any]:
    topic = TOPICS[topic_id]
    store = GlobalTopicStore(database_path)
    store.seed(_seed_observations(), EVENTS)
    defaults = {factor["id"]: factor["value"] for factor in topic["factors"]}
    return {
        "schemaVersion": "newma-desk.global-topic.v1",
        "topicId": topic_id,
        **topic,
        "observations": store.observations(topic_id),
        "events": store.events(topic_id),
        "forecast": forecast(topic_id, defaults),
        "dataMode": "reference-baseline",
        "updatedAt": datetime.now(UTC).isoformat(),
    }
