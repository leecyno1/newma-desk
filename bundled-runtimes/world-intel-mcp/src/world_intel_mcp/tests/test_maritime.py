from unittest.mock import AsyncMock, patch

import pytest

from world_intel_mcp.sources.maritime import _parse_warning, fetch_nav_warnings


@pytest.mark.parametrize("raw, expected", [
    ("081653Z MAY 2024", "2024-05-08T16:53:00Z"),
    ("2026-09-10T08:30:00Z", "2026-09-10T08:30:00Z"),
    ("292359Z FEB 2024", "2024-02-29T23:59:00Z"),
    ("310830Z FEB 2026", None),
    ("unknown", None),
    (None, None),
])
def test_warning_preserves_publication_date(raw, expected):
    warning = _parse_warning({"msgYear": 2024, "msgNumber": 517, "issueDate": raw})
    assert warning["issue_date"] == expected
    assert warning["issue_date_raw"] == raw
    assert warning["status"] == "active"


@pytest.mark.asyncio
async def test_stale_warning_keeps_successful_collection_time(fetcher):
    payload = {"broadcast-warn": [
        {"msgYear": 2024, "msgNumber": 517, "issueDate": "081653Z MAY 2024"},
        {"msgYear": 2026, "msgNumber": 9, "issueDate": "011200Z SEP 2026"},
    ]}
    with patch("world_intel_mcp.cache.time.time", return_value=1786543311):
        fetcher.cache.set("maritime:warnings:all", payload, 3600)
    fetcher.get_json = AsyncMock(return_value=payload)
    first = await fetch_nav_warnings(fetcher)
    second = await fetch_nav_warnings(fetcher)
    assert first["collected_at"] == second["collected_at"] == "2026-08-12T14:01:51Z"
    assert first["timestamp"] == first["collected_at"]
    assert first["freshness"] == "stale"
    assert first["warnings"][0]["issue_date"] == "2026-09-01T12:00:00Z"
    assert first["warnings"][1]["issue_date"] == "2024-05-08T16:53:00Z"


@pytest.mark.asyncio
async def test_unavailable_warnings_are_not_a_confirmed_empty_result(fetcher):
    fetcher.get_json = AsyncMock(return_value=None)
    result = await fetch_nav_warnings(fetcher)
    assert result["error"]
    assert result["timestamp"] is None
    assert result["freshness"] == "unknown"


@pytest.mark.asyncio
async def test_successful_empty_feed_is_distinct_from_failure(fetcher):
    payload = {"broadcast-warn": []}
    fetcher.cache.set("maritime:warnings:all", payload, 3600)
    fetcher.get_json = AsyncMock(return_value=payload)
    result = await fetch_nav_warnings(fetcher)
    assert result["count"] == 0
    assert result["freshness"] == "fresh"
    assert result["collected_at"]
    assert "error" not in result


@pytest.mark.asyncio
async def test_full_text_all_coordinates_relayed_navarea_and_cancelled_status(fetcher):
    text = "OFFSHORE WORKS. " * 40 + "20-00N 060-00E, 26-30N 056-20E. STRAIT OF HORMUZ."
    payload = {"broadcast-warn": [
        {"msgYear": 2024, "msgNumber": 1, "navArea": "P", "authority": "NAVAREA IX 1/24", "text": text, "status": "A"},
        {"msgYear": 2024, "msgNumber": 2, "navArea": "9", "text": "REGIONAL WARNING", "status": "A"},
        {"msgYear": 2024, "msgNumber": 3, "navArea": "IX", "text": "CANCELLED", "status": "C"},
        {"msgYear": 2024, "msgNumber": 4, "navArea": "4", "text": "UNRELATED"},
    ]}
    fetcher.cache.set("maritime:warnings:all", payload, 3600)
    fetcher.get_json = AsyncMock(return_value=payload)
    result = await fetch_nav_warnings(fetcher, "IX")
    numeric = await fetch_nav_warnings(fetcher, "9")
    assert result["warnings"] == numeric["warnings"]
    assert result["count"] == 2
    relayed = result["warnings"][0]
    assert relayed["navarea"] == "P" and relayed["broadcast_label"] == "HYDROPAC"
    assert relayed["origin_navarea"] == "IX"
    assert relayed["text"] == text
    assert len(relayed["coordinates"]) == 2
    assert relayed["coordinates"][1] == {"lat": 26.5, "lon": 56.3333}
    assert fetcher.get_json.call_args.kwargs["cache_key"] == "maritime:warnings:all"


@pytest.mark.asyncio
async def test_invalid_feed_is_not_a_successful_empty_result(fetcher):
    fetcher.get_json = AsyncMock(return_value={"error": "upstream unavailable"})
    assert (await fetch_nav_warnings(fetcher))["error"]


@pytest.mark.asyncio
async def test_slow_source_uses_expired_cache_without_refreshing_its_date(fetcher):
    with patch("world_intel_mcp.cache.time.time", return_value=1786543311):
        fetcher.cache.set("maritime:warnings:all", {"broadcast-warn": []}, 3600)
    fetcher.get_json = AsyncMock(side_effect=TimeoutError)
    result = await fetch_nav_warnings(fetcher)
    assert result["collected_at"] == "2026-08-12T14:01:51Z"
    assert result["freshness"] == "stale"


@pytest.mark.asyncio
async def test_targeted_http_endpoint_does_not_scan_other_domains(fetcher):
    import httpx
    from world_intel_mcp.dashboard.app import app

    with patch("world_intel_mcp.dashboard.app._ensure_fetcher", return_value=fetcher), \
         patch("world_intel_mcp.dashboard.app._fetch_overview", new_callable=AsyncMock) as overview, \
         patch("world_intel_mcp.dashboard.app.maritime.fetch_nav_warnings", new_callable=AsyncMock, return_value={"warnings": [], "count": 0}) as read:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
            response = await client.get("/api/maritime/warnings?navarea=IX")
        assert response.status_code == 200
        assert response.json()["count"] == 0
        read.assert_awaited_once_with(fetcher, "IX")
        overview.assert_not_awaited()
