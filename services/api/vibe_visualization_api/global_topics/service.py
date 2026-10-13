from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

TOPICS: dict[str, dict[str, Any]] = {
    "fed-rates": {
        "title": "联储加息",
        "subtitle": "利率路径与全球资产重定价",
        "question": "下一阶段更可能降息、维持还是加息？",
        "accent": "cyan",
        "factors": [
            {"id": "inflation", "label": "通胀压力", "min": 0, "max": 100, "value": 50, "direction": 1.0},
            {"id": "employment", "label": "就业韧性", "min": 0, "max": 100, "value": 50, "direction": 0.8},
            {"id": "financialStress", "label": "金融压力", "min": 0, "max": 100, "value": 50, "direction": -1.1},
        ],
        "outcomes": ["降息", "维持", "加息"],
        "baseScores": [0.25, 1.1, -0.25],
        "transmission": ["通胀与就业", "联储表态", "利率路径", "美元与美债", "全球风险资产"],
    },
    "hormuz": {
        "title": "美伊战争",
        "subtitle": "霍尔木兹海峡与能源供应冲击",
        "question": "海峡风险将缓和、受控升级还是出现中断？",
        "accent": "amber",
        "factors": [
            {"id": "military", "label": "军事活动", "min": 0, "max": 100, "value": 50, "direction": 1.2},
            {"id": "shipping", "label": "航运中断", "min": 0, "max": 100, "value": 50, "direction": 1.1},
            {"id": "diplomacy", "label": "外交缓和", "min": 0, "max": 100, "value": 50, "direction": -1.0},
        ],
        "outcomes": ["缓和", "受控升级", "通道中断"],
        "baseScores": [0.0, 1.0, -0.35],
        "transmission": ["军事与航行信号", "海峡可用性", "原油与LNG供给", "运价与保险", "通胀及行业利润"],
    },
    "us-china-trade": {
        "title": "中美贸易",
        "subtitle": "制裁、出口管制与产业链传导",
        "question": "制裁强度将缓和、维持还是扩大？",
        "accent": "red",
        "factors": [
            {"id": "controls", "label": "出口管制", "min": 0, "max": 100, "value": 50, "direction": 1.1},
            {"id": "retaliation", "label": "反制强度", "min": 0, "max": 100, "value": 50, "direction": 0.9},
            {"id": "negotiation", "label": "谈判进展", "min": 0, "max": 100, "value": 50, "direction": -1.0},
        ],
        "outcomes": ["缓和", "维持", "扩大"],
        "baseScores": [-0.1, 1.05, -0.1],
        "transmission": ["法案与清单", "技术与资本限制", "企业合规成本", "供应链替代", "行业盈利与估值"],
    },
}


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
        "disclaimer": "内置因子模型仅用于情景比较；权重与模型指标未经统计校准，不代表真实发生概率或投资建议。",
    }


def topic_snapshot(topic_id: str, evidence: dict[str, Any]) -> dict[str, Any]:
    topic = TOPICS[topic_id]
    defaults = {factor["id"]: factor["value"] for factor in topic["factors"]}
    generated_at = datetime.now(UTC).isoformat()
    return {
        "schemaVersion": "newma-desk.global-topic.v1",
        "topicId": topic_id,
        **topic,
        **evidence,
        "forecast": forecast(topic_id, defaults),
        "factorSource": "user-assumptions",
        "generatedAt": generated_at,
        "updatedAt": generated_at,  # Response generation, not collection time.
    }
