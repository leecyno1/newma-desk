"""A missing observation is not a zero-risk observation."""
import pytest

from world_intel_mcp.analysis.situation import _extract_metrics, _build_prompt, fetch_situation_brief


@pytest.mark.asyncio
async def test_failed_domains_do_not_become_zero_in_brief():
    data = {name: {"error": "source unavailable", "count": 0} for name in (
        "strategic_posture", "alert_digest", "military_flights", "acled_events", "wildfires", "traffic_flow",
    )}
    data["earthquakes"] = {"count": 2, "earthquakes": [{"magnitude": 5.8}, {"magnitude": 3.2}]}
    # A historical secondary series must not fill a failed primary source.
    data["ucdp_events"] = {"count": 100}
    result = await fetch_situation_brief(data, use_ai=False)
    assert result["metrics_snapshot"]["earthquakes"] == 2
    assert result["metrics_snapshot"]["max_magnitude"] == 5.8
    for key in ("posture_score", "alerts", "military_aircraft", "conflicts", "fire_clusters", "avg_congestion"):
        assert result["metrics_snapshot"][key] is None
    assert "0/100" not in result["brief"]
    assert "未知" in result["brief"] and "0 起冲突" not in result["brief"]
    assert result["status"] == "partial"
    assert "conflicts" in result["coverage"]["missing"]
    assert result["ai_generated"] is False


@pytest.mark.asyncio
async def test_valid_empty_results_remain_zero_without_zero_magnitude():
    result = await fetch_situation_brief({
        "earthquakes": {"count": 0, "earthquakes": []},
        "acled_events": {"count": 0}, "cyber_threats": {"threats": []},
        "traffic_flow": {"global_avg_congestion": 0},
        "strategic_posture": {"composite_score": 0, "risk_level": "LOW"},
    }, use_ai=False)
    metrics = result["metrics_snapshot"]
    assert metrics["earthquakes"] == metrics["conflicts"] == metrics["cyber_threats"] == metrics["avg_congestion"] == 0
    assert metrics["max_magnitude"] is None
    assert metrics["posture_score"] == 0 and "0/100" in result["brief"]


@pytest.mark.parametrize("state", [{"_stale": True}, {"freshness": "stale"}, {"status": "unavailable"}, {"error": "timeout"}])
def test_stale_or_failed_values_are_not_current(state):
    metrics = _extract_metrics({"strategic_posture": {"composite_score": 80, "risk_level": "HIGH", **state}})
    assert metrics["posture_score"] is None and metrics["risk_level"] == "unknown"


@pytest.mark.asyncio
async def test_null_metrics_do_not_crash_and_prompt_explains_unknowns():
    result = await fetch_situation_brief({"space_weather": {"current_kp": None},
        "strategic_posture": {"composite_score": None, "risk_level": "LOW"},
        "earthquakes": {"count": 1, "earthquakes": [{"magnitude": None}]}}, use_ai=False)
    assert result["metrics_snapshot"]["max_magnitude"] is None
    assert result["metrics_snapshot"]["risk_level"] == "unknown"
    prompt = _build_prompt(result["metrics_snapshot"])
    assert "未知" in prompt and "缺失不代表零" in prompt
    assert "None" not in result["brief"] and "None" not in prompt
