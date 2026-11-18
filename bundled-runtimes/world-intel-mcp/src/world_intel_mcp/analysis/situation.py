"""AI-powered situational analysis for world-intel-mcp.

Generates a real-time intelligence brief from all dashboard data
using a local Ollama LLM.  Falls back to a structured metrics summary
when the LLM is unavailable.
"""

import logging
import math
import os
from datetime import datetime, timezone

import httpx

from ..sources.wildfire import current_regions

logger = logging.getLogger("world-intel-mcp.analysis.situation")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_METRIC_LABELS = {
    "earthquakes": "地震条数", "max_magnitude": "最高震级", "military_aircraft": "军事航空器",
    "conflicts": "冲突样本", "fire_clusters": "卫星热异常网格样本", "cyber_threats": "网络威胁样本",
    "posture_score": "模型综合评分", "alerts": "告警", "kp_index": "Kp指数",
    "outbreaks": "高关注疾病样本", "total_aircraft": "航空器", "avg_congestion": "拥堵度",
}


def _source(data: dict, key: str) -> dict:
    value = data.get(key)
    if (not isinstance(value, dict) or value.get("error") or value.get("_stale")
            or value.get("freshness") == "stale" or value.get("status") in {"unavailable", "error", "stale"}):
        return {}
    return value


def _number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def _extract_metrics(data: dict) -> dict:
    """Preserve valid zeros, but never convert missing/failed/stale inputs to zero."""
    fields = {
        "earthquakes": ("earthquakes", "count"), "military_aircraft": ("military_flights", "count"),
        "posture_score": ("strategic_posture", "composite_score"), "alerts": ("alert_digest", "alert_count"),
        "kp_index": ("space_weather", "current_kp"), "outbreaks": ("disease_outbreaks", "high_concern_count"),
        "total_aircraft": ("domestic_flights", "total_aircraft"), "avg_congestion": ("traffic_flow", "global_avg_congestion"),
    }
    metrics = {key: _number(_source(data, domain).get(field)) for key, (domain, field) in fields.items()}
    eq = _source(data, "earthquakes")
    events = eq.get("events", eq.get("earthquakes", []))
    magnitudes = [_number(e.get("magnitude")) for e in events if isinstance(e, dict)] if isinstance(events, list) else []
    metrics["max_magnitude"] = max((m for m in magnitudes if m is not None), default=None)
    # Do not replace a failed primary feed with a differently dated conflict series.
    conflict_key = next((key for key in ("acled_events", "conflict_zones", "ucdp_events") if key in data), "acled_events")
    metrics["conflicts"] = _number(_source(data, conflict_key).get("count"))
    fire_source = _source(data, "wildfires")
    regions = fire_source.get("fires_by_region")
    current_fire_regions = current_regions(fire_source)
    fire_coverage = fire_source.get("coverage")
    complete_fires = (fire_source.get("status") == "ok" and fire_source.get("freshness") == "fresh"
                      and isinstance(regions, dict) and bool(regions) and len(current_fire_regions) == len(regions)
                      and isinstance(fire_coverage, dict)
                      and fire_coverage.get("available") == fire_coverage.get("requested") == len(regions)
                      and all(r.get("status") == "ok" and not r.get("clusters_truncated") for r in current_fire_regions.values()))
    metrics["fire_clusters"] = sum(len(r["top_clusters"]) for r in current_fire_regions.values()) if complete_fires else None
    threats = _source(data, "cyber_threats").get("threats")
    metrics["cyber_threats"] = len(threats) if isinstance(threats, list) else None
    metrics["risk_level"] = _source(data, "strategic_posture").get("risk_level", "unknown") if metrics["posture_score"] is not None else "unknown"
    news = _source(data, "news_feed")
    items = news.get("items", news.get("articles", []))
    metrics["top_headlines"] = [item["title"] for item in items[:5] if isinstance(item, dict) and isinstance(item.get("title"), str)] if isinstance(items, list) else []
    return metrics


def _display(m: dict, key: str, unit: str = "") -> str:
    value = _number(m.get(key))
    return "未知（未取得有效观测）" if value is None else f"{value:g}{unit}"


def _build_prompt(m: dict) -> str:
    """Build an LLM prompt from extracted metrics."""
    headline_block = "\n".join(f"  - {h}" for h in m["top_headlines"]) if m["top_headlines"] else "  (no headlines available)"

    metric_block = "\n".join(f"{label}: {_display(m, key)}" for key, label in _METRIC_LABELS.items())
    return f"""你是一名高级情报分析师。请基于以下本次来源响应，生成简洁、专业的中文态势简报：

{metric_block}
综合风险标签: {m['risk_level']}

TOP HEADLINES:
{headline_block}

严格写成 3 个自然段：
1. 已知观测及数据缺口；缺失不代表零，也不代表低风险
2. 有证据支持的区域热点，不凭单次快照推断变化或趋势
3. 未来 12 小时需要持续监控的事项

只引用已提供的有效数字。卫星热异常不等同已核实山火；来源口径和窗口不同，样本计数不是全球总量；未知项明确待核验，不得填0或推测安全。不要写标题和前言。"""


def _fallback_brief(m: dict) -> str:
    """Generate a structured summary without LLM."""
    risk_label = {
        "LOW": "低风险",
        "GUARDED": "警戒",
        "ELEVATED": "风险升高",
        "HIGH": "高风险",
        "CRITICAL": "严重风险",
    }.get(str(m["risk_level"]).upper(), "未知，待核验")
    lines = [
        f"模型综合风险：{risk_label}；评分：{_display(m, 'posture_score', '/100')}；活跃告警：{_display(m, 'alerts', ' 条')}。军事航空器：{_display(m, 'military_aircraft', ' 架')}；冲突样本：{_display(m, 'conflicts', ' 条')}。",
        f"地震：{_display(m, 'earthquakes', ' 次')}；最高震级：{_display(m, 'max_magnitude')}；卫星热异常网格样本：{_display(m, 'fire_clusters')}；网络威胁样本：{_display(m, 'cyber_threats')}；高关注疾病样本：{_display(m, 'outbreaks')}。",
        f"空间天气 Kp：{_display(m, 'kp_index')}；航空器：{_display(m, 'total_aircraft', ' 架')}；城市平均拥堵度：{_display(m, 'avg_congestion', '%')}。下一步应优先核验缺失来源，再结合连续观测判断变化；本次快照不证明风险上升或下降。",
    ]
    return "\n\n".join(lines)


async def fetch_situation_brief(overview_data: dict, use_ai: bool = True) -> dict:
    """Generate an AI situational analysis brief from dashboard data.

    Uses local Ollama LLM to synthesize all intelligence domains into
    an actionable 3-paragraph brief.  Falls back to structured metrics
    summary when Ollama is unavailable.

    Args:
        overview_data: Full dashboard overview dict from _fetch_overview().

    Returns:
        Dict with brief text, generation metadata, and key metrics.
    """
    metrics = _extract_metrics(overview_data)
    missing = [key for key in _METRIC_LABELS if metrics[key] is None]
    available = len(_METRIC_LABELS) - len(missing)
    prompt = _build_prompt(metrics)

    ollama_url = os.environ.get("OLLAMA_API_URL", "http://mac-studio.local:11434")
    model = os.environ.get("OLLAMA_MODEL", "llama3.2")

    brief_text = ""
    ai_generated = False
    used_model = "fallback"

    if use_ai and available:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{ollama_url}/api/generate",
                    json={
                        "model": model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {"temperature": 0.3, "num_predict": 500},
                    },
                )
                resp.raise_for_status()
                result = resp.json()
                brief_text = result.get("response", "").strip()
                if brief_text:
                    ai_generated = True
                    used_model = model
        except Exception as exc:
            logger.debug("Ollama unavailable for situation brief: %s", exc)

    if not brief_text:
        brief_text = _fallback_brief(metrics)

    coverage_note = f"本次可用数字指标 {available}/{len(_METRIC_LABELS)}（不代表全源覆盖）。"
    if missing:
        coverage_note += "未取得有效观测：" + "、".join(_METRIC_LABELS[key] for key in missing) + "；来源缺失、失败或过期不代表零风险。"
    coverage_note += "各来源窗口和样本口径不同，不能当作全球总量；卫星热异常不等同已核实山火。"

    return {
        "brief": coverage_note + "\n\n" + brief_text,
        "status": "unavailable" if not available else "partial" if missing else "ok",
        "coverage": {"available": available, "expected": len(_METRIC_LABELS), "missing": missing},
        "ai_generated": ai_generated,
        "model": used_model,
        "metrics_snapshot": metrics,
        "source": "situation-brief",
        "timestamp": _utc_now_iso(),
    }
