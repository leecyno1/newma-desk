"""Policy-rate semantics: exact series, missing newest value, stale evidence."""
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from click.testing import CliRunner

from world_intel_mcp.sources.central_banks import _latest_observation, fetch_central_bank_rates


@pytest.mark.parametrize("body,expected", [
    ("observation_date,DFEDTARU\n2026-10-25,4\n2026-10-26,.\n", (None, "2026-10-26")),
    ("observation_date,DFF\n2026-10-26,4\n", (None, None)),
    ("<html>provider unavailable</html>", (None, None)),
    ("observation_date,DFEDTARU\n2026-10-28,5\n2026-10-26,0\n", (0, "2026-10-26")),
    ("observation_date,DFEDTARU\n2026-10-26,-0.25\n", (-0.25, "2026-10-26")),
    ("observation_date,DFEDTARU\n2026-10-26,4\n2026-10-26,5\n", (None, "2026-10-26")),
    ("observation_date,DFEDTARU\n2026-10-26,Infinity\n", (None, "2026-10-26")),
    ("observation_date,DFEDTARU\n2025-10-26,4\n", (None, None)),
])
def test_latest_observation(body, expected):
    assert _latest_observation(body, "DFEDTARU", date(2026, 10, 27)) == expected


@pytest.mark.asyncio
async def test_cached_observation_keeps_original_time_and_no_key_claim(fetcher, monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "test-only-not-used")
    today = datetime.now(timezone.utc).date()
    key = "central_banks:public-v1:DFEDTARU"
    body = f"observation_date,DFEDTARU\n{today.isoformat()},4\n"
    fetcher.cache.set(key, body, -60)
    timing = fetcher.cache.entry_timing(key)
    async def cached(url, **kwargs):
        return fetcher.cache.get_stale(kwargs["cache_key"])
    monkeypatch.setattr(fetcher, "get_text", cached)
    result = await fetch_central_bank_rates(fetcher)
    fed = next(r for r in result["rates"] if r["country"] == "USA")
    assert fed["status"] == "stale" and fed["rate"] == 4
    assert fed["as_of"] == today.isoformat()
    assert fed["collected_at"] == datetime.fromtimestamp(timing["created_at"], timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert result["coverage"]["stale"] == 1
    assert result["coverage"]["failed"] == 2
    assert result["fred_available"] is False


@pytest.mark.asyncio
async def test_newly_collected_old_observation_is_not_current(fetcher, monkeypatch):
    today = datetime.now(timezone.utc).date()
    body = f"observation_date,DFEDTARU\n{(today - timedelta(days=8)).isoformat()},4\n"
    async def response(url, **kwargs):
        fetcher.cache.set(kwargs["cache_key"], body, 3600)
        return body
    monkeypatch.setattr(fetcher, "get_text", response)
    result = await fetch_central_bank_rates(fetcher)
    fed = next(r for r in result["rates"] if r["country"] == "USA")
    assert fed["freshness"] == "fresh" and fed["status"] == "stale"
    assert result["fred_available"] is False


def test_cli_missing_rate_and_separate_reference(monkeypatch):
    import world_intel_mcp.cli as cli
    monkeypatch.setattr(cli, "_get_fetcher", lambda: None)
    monkeypatch.setattr(cli, "fetch_central_bank_rates", AsyncMock(return_value={
        "count": 1, "coverage": {"available": 0}, "rates": [
            {"bank": "Test", "rate": None, "as_of": None, "status": "unavailable",
             "reference": {"rate": 4.5, "as_of": "2025-01-29"}},
        ],
    }))
    result = CliRunner().invoke(cli.main, ["central-banks"], terminal_width=180)
    assert result.exit_code == 0, result.output
    assert "N/A" in result.output and "4.50%" in result.output
    assert "0 available observations" in result.output
