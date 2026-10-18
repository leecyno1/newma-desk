import pytest

from vibe_visualization_api.capital_flow.sentiment import sentiment_snapshot
from vibe_visualization_api.capital_flow.turnover import SOURCE, NOTE, turnover_snapshot


def source():
    snapshot = turnover_snapshot([
        {"ts_code": f"{i:06}.SZ", "trade_date": "20261015", "close": 10, "amount": amount, "pct_chg": pct}
        for i, (amount, pct) in enumerate([(100, 1), (100, -2), (100, 0), (0, 0), (100, None)], 1)
    ], [], "2026-10-15")
    return {**snapshot, "source": SOURCE, "note": NOTE, "asOf": "2026-10-15", "expectedDate": "2026-10-15",
            "status": "ready", "current": True, "calendarStatus": "ready", "generatedAt": "2026-10-16T00:00:00Z"}


def test_daily_sample_preserves_exclusions_and_never_infers_limit_counts():
    data = sentiment_snapshot(source())
    assert data["sentiment"]["up"] == data["sentiment"]["down"] == data["sentiment"]["flat"] == 1
    assert data["sentiment"]["zt"] is None and data["sentiment"]["dt"] is None
    assert data["sample"]["inactiveCount"] == data["sample"]["missingPctCount"] == 1
    assert data["sample"]["validCount"] == 3
    assert sum(row["count"] for row in data["sample"]["buckets"]) == 3
    assert data["coverage"]["universeVerified"] is False
    assert data["session"]["current"]


def test_failed_refresh_with_saved_snapshot_withdraws_counts():
    prior = source()
    prior.update(status="upstream-error", usingSaved=True, current=False, reason="日线请求失败")
    data = sentiment_snapshot(prior)
    assert data["sentiment"]["up"] is None
    assert data["sentiment"]["date"] is None
    assert data["sample"] is None
    assert not data["session"]["current"]
    assert data["sources"]["sentiment"]["reason"] == "日线请求失败"


def test_empty_sample_does_not_claim_zero_market():
    prior = source()
    prior["breadth"].update(validCount=0, up=0, down=0, flat=0)
    assert sentiment_snapshot(prior)["sentiment"]["up"] is None


def test_unverified_calendar_keeps_date_but_not_current_claim():
    prior = source()
    prior.update(calendarStatus="upstream-error", current=False, reason="交易日历未确认")
    data = sentiment_snapshot(prior)
    assert data["sentiment"]["date"] == "2026-10-15"
    assert not data["session"]["current"]


@pytest.mark.asyncio
async def test_route_reuses_turnover_service(tmp_path, monkeypatch):
    from vibe_visualization_api.capital_flow.routes import get_market_sentiment, TurnoverResearchService
    from vibe_visualization_api.config import Settings
    calls = []
    async def research(self, *, refresh=False):
        calls.append(refresh)
        return source()
    monkeypatch.setattr(TurnoverResearchService, "research", research)
    result = await get_market_sentiment(refresh=True, settings=Settings(database_path=tmp_path / "test.db"))
    assert calls == [True]
    assert result["data"]["sample"]["validCount"] == 3
