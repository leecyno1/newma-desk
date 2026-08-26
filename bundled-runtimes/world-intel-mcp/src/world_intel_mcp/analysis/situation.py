"""AI-powered situational analysis for world-intel-mcp.

Generates a real-time intelligence brief from all dashboard data
using a local Ollama LLM.  Falls back to a structured metrics summary
when the LLM is unavailable.
"""

import logging
import os
from datetime import datetime, timezone

import httpx

logger = logging.getLogger("world-intel-mcp.analysis.situation")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_metrics(data: dict) -> dict:
    """Pull key numbers from the full overview data."""
    eq = data.get("earthquakes", {})
    quakes = eq.get("count", 0) if isinstance(eq, dict) else 0
    eq_events = (eq.get("events") or eq.get("earthquakes") or []) if isinstance(eq, dict) else []
    max_mag = max((e.get("magnitude", 0) for e in eq_events), default=0) if eq_events else 0

    mil = data.get("military_flights", {})
    mil_count = mil.get("count", 0) if isinstance(mil, dict) else 0

    conflict_src = data.get("acled_events") or data.get("conflict_zones") or data.get("ucdp_events") or {}
    conflict_count = conflict_src.get("count", 0) if isinstance(conflict_src, dict) else 0

    fires = data.get("wildfires", {})
    fire_regions = fires.get("fires_by_region", {}) if isinstance(fires, dict) else {}
    fire_clusters = sum(
        len(r.get("top_clusters", [])) for r in fire_regions.values() if isinstance(r, dict)
    )

    cyber = data.get("cyber_threats", {})
    cyber_count = len(cyber.get("threats", [])) if isinstance(cyber, dict) else 0

    posture = data.get("strategic_posture", {})
    posture_score = posture.get("composite_score", 0) if isinstance(posture, dict) else 0
    risk_level = posture.get("risk_level", "unknown") if isinstance(posture, dict) else "unknown"

    alerts = data.get("alert_digest", {})
    alert_count = alerts.get("alert_count", 0) if isinstance(alerts, dict) else 0

    space = data.get("space_weather", {})
    kp = space.get("current_kp", 0) if isinstance(space, dict) else 0

    health = data.get("disease_outbreaks", {})
    outbreaks = health.get("high_concern_count", 0) if isinstance(health, dict) else 0

    news = data.get("news_feed", {})
    headlines = []
    if isinstance(news, dict):
        for item in (news.get("items") or news.get("articles") or [])[:5]:
            if isinstance(item, dict):
                headlines.append(item.get("title", ""))

    domestic = data.get("domestic_flights", {})
    total_aircraft = domestic.get("total_aircraft", 0) if isinstance(domestic, dict) else 0

    traffic = data.get("traffic_flow", {})
    avg_congestion = traffic.get("global_avg_congestion", 0) if isinstance(traffic, dict) else 0

    return {
        "earthquakes": quakes,
        "max_magnitude": round(max_mag, 1),
        "military_aircraft": mil_count,
        "conflicts": conflict_count,
        "fire_clusters": fire_clusters,
        "cyber_threats": cyber_count,
        "posture_score": round(posture_score),
        "risk_level": risk_level,
        "alerts": alert_count,
        "kp_index": round(kp, 1),
        "outbreaks": outbreaks,
        "total_aircraft": total_aircraft,
        "avg_congestion": avg_congestion,
        "top_headlines": headlines,
    }


def _build_prompt(m: dict) -> str:
    """Build an LLM prompt from extracted metrics."""
    headline_block = "\n".join(f"  - {h}" for h in m["top_headlines"]) if m["top_headlines"] else "  (no headlines available)"

    return f"""你是一名高级情报分析师。请基于以下实时指标，生成简洁、专业的中文态势简报：

THREAT POSTURE: Score {m['posture_score']}/100 ({m['risk_level']}), {m['alerts']} active alerts
MILITARY: {m['military_aircraft']} tracked aircraft
CONFLICT: {m['conflicts']} active events
SEISMIC: {m['earthquakes']} earthquakes (max M{m['max_magnitude']})
FIRES: {m['fire_clusters']} active fire clusters
CYBER: {m['cyber_threats']} tracked IOCs
SPACE WEATHER: Kp {m['kp_index']}
HEALTH: {m['outbreaks']} high-concern outbreaks
AIR TRAFFIC: {m['total_aircraft']} aircraft airborne
TRAFFIC: {m['avg_congestion']}% avg city congestion

TOP HEADLINES:
{headline_block}

严格写成 3 个自然段：
1. 总体威胁评估与最重要变化
2. 区域热点与正在形成的模式
3. 未来 12 小时需要持续监控的事项

必须引用具体数字，不要写标题和前言。"""


def _fallback_brief(m: dict) -> str:
    """Generate a structured summary without LLM."""
    risk_label = {
        "LOW": "低风险",
        "GUARDED": "警戒",
        "ELEVATED": "风险升高",
        "HIGH": "高风险",
        "CRITICAL": "严重风险",
    }.get(str(m["risk_level"]).upper(), "监测中")
    lines = [
        f"当前综合风险为 {risk_label}，评分 {m['posture_score']}/100，共有 {m['alerts']} 条活跃告警。正在跟踪 {m['military_aircraft']} 架军事相关航空器和 {m['conflicts']} 起冲突事件。",
        f"自然与公共安全方面共监测到 {m['earthquakes']} 次地震，最高震级 M{m['max_magnitude']}，以及 {m['fire_clusters']} 个火点集群；网络侧发现 {m['cyber_threats']} 个威胁指标，高关注疾病事件 {m['outbreaks']} 起。",
        f"未来 12 小时重点关注冲突与军事活动变化、强震和山火扩散、网络基础设施异常。当前空间天气 Kp 指数为 {m['kp_index']}，空中航空器 {m['total_aircraft']} 架，城市平均拥堵度 {m['avg_congestion']}%。",
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
    prompt = _build_prompt(metrics)

    ollama_url = os.environ.get("OLLAMA_API_URL", "http://mac-studio.local:11434")
    model = os.environ.get("OLLAMA_MODEL", "llama3.2")

    brief_text = ""
    ai_generated = False
    used_model = "fallback"

    if use_ai:
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

    return {
        "brief": brief_text,
        "ai_generated": ai_generated,
        "model": used_model,
        "metrics_snapshot": metrics,
        "source": "situation-brief",
        "timestamp": _utc_now_iso(),
    }
