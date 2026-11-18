import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from world_intel_mcp.analysis.inputs import AnalysisInputs
from world_intel_mcp.analysis.alerts import build_alert_digest
from world_intel_mcp.analysis.posture import build_strategic_posture
from world_intel_mcp.sources import infrastructure, maritime


async def test_same_cycle_reuses_navigation_request_for_cables(fetcher, monkeypatch):
    fetcher.get_json = AsyncMock(return_value={'broadcast-warn': []})
    reader = AsyncMock(return_value={'status': 'ok', 'freshness': 'fresh', 'warnings': [], 'count': 0})
    monkeypatch.setattr(maritime, 'fetch_nav_warnings', reader)
    inputs = AnalysisInputs(fetcher)
    try:
        nav, cable = await asyncio.gather(inputs.get('nav_warnings'), inputs.get('cable_health'))
        reader.assert_awaited_once_with(fetcher)
        assert cable['warnings_total'] == nav['count'] == 0
        assert all(c['status_score'] is None for c in cable['corridors'].values())
        assert cable['corridors']['red_sea']['status_label'] == 'no_matching_warnings'
    finally:
        await inputs.close()


async def test_duplicate_coordinates_overlap_cancelled_and_unlocated(fetcher):
    rows = [
        {'msgYear': 2026, 'msgNumber': 1, 'navArea': 'P', 'text': 'CABLE WORKS 20-00N/040-00E 21-00N 041-00E', 'status': 'A'},
        {'msgYear': 2026, 'msgNumber': 1, 'navArea': 'P', 'text': 'CABLE WORKS 20-00N/040-00E', 'status': 'A'},
        {'msgYear': 2026, 'msgNumber': 1, 'navArea': 'A', 'text': 'CABLE WORKS 20.5N 40.5E', 'status': 'A'},
        {'msgYear': 2026, 'msgNumber': 2, 'text': 'CABLE WORKS 20-00N 040-00E', 'status': 'C'},
        {'msgYear': 2026, 'msgNumber': 3, 'text': 'CABLE OPERATIONS NO COORDINATES', 'status': 'A'},
    ]
    payload = {'broadcast-warn': rows}
    fetcher.cache.set('maritime:warnings:all', payload, 3600)
    fetcher.get_json = AsyncMock(return_value=payload)
    result = await infrastructure.fetch_cable_health(fetcher)
    assert result['warnings_total'] == 3
    assert result['unlocated_warnings'] == 1
    for name in ('red_sea', 'asia_europe'):
        item = result['corridors'][name]
        assert item['warning_count'] == 2
        assert item['status_score'] is None
        assert item['status_label'] == 'warnings_observed'
        assert item['relevant_warnings'][0]['issue_date'] is None
    assert result['health_assessment'] == 'not_assessed'


async def test_old_cache_keeps_source_date_and_does_not_score(fetcher):
    with patch('world_intel_mcp.cache.time.time', return_value=1786543311):
        fetcher.cache.set('maritime:warnings:all', {'broadcast-warn': []}, 3600)
    fetcher.get_json = AsyncMock(side_effect=TimeoutError)
    result = await infrastructure.fetch_cable_health(fetcher)
    assert result['timestamp'] == result['collected_at'] == '2026-08-12T14:01:51Z'
    assert result['freshness'] == 'stale'
    assert result['status'] == 'partial'
    assert result['health_assessment'] == 'not_assessed'


async def test_failure_does_not_refetch_or_claim_empty_cables(fetcher):
    fetcher.get_json = AsyncMock()
    result = await infrastructure.fetch_cable_health(fetcher, nav_data={'error': 'unavailable', 'warnings': [], 'count': None})
    fetcher.get_json.assert_not_called()
    assert result['warnings_total'] is None
    assert result['timestamp'] is None
    assert all(c['warning_count'] is None for c in result['corridors'].values())


def test_old_proxy_scores_no_longer_trigger_damage_alerts():
    inputs = {'cable_health': {'status': 'ok', 'corridors': {'red_sea': {'status_score': 3}}},
              'internet_outages': {'status': 'ok', 'ongoing_count': 6}}
    alerts = build_alert_digest(inputs)
    assert len(alerts['alerts']) == 1
    assert 'internet outages' in alerts['alerts'][0]['message']
    assert 'cable_health' not in alerts['domains_checked']
    assert build_strategic_posture(inputs)['domain_scores']['infrastructure']['score'] is None


@pytest.mark.parametrize('text, points', [
    ('40-30.5N/030-15.2E', [{'lat': 40.5083, 'lon': 30.2533}]),
    ('20.5n 40.5e', [{'lat': 20.5, 'lon': 40.5}]),
    ('99-99N/200-90E', []),
])
def test_shared_coordinate_parser(text, points):
    assert maritime._all_coords(text) == points
