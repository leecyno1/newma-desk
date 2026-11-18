import time
from unittest.mock import AsyncMock

import pytest
from click.testing import CliRunner

from world_intel_mcp.analysis.exposure import fetch_population_exposure
from world_intel_mcp.analysis.situation import _extract_metrics, fetch_situation_brief
from world_intel_mcp.sources import wildfire


class MemoryCache:
    def __init__(self, stale=()):
        self.stale = set(stale)
        self.entries = {}

    def entry_timing(self, key):
        now = time.time()
        return {'created_at': now - 3600, 'expires_at': now - 1 if key in self.stale else now + 300}

    def set(self, key, value, ttl):
        self.entries[key] = value


class FakeFetcher:
    def __init__(self, payloads, stale=()):
        self.payloads = payloads
        self.cache = MemoryCache(stale)

    async def get_text(self, *, cache_key, **_):
        return self.payloads.get(cache_key.rsplit(':', 1)[-1])


HEADER = 'latitude,longitude,confidence,frp\n'
ONE = HEADER + '10,20,nominal,12\n'


@pytest.mark.asyncio
async def test_partial_regions_do_not_become_zero_or_a_complete_total(monkeypatch):
    monkeypatch.setattr(wildfire, 'REGIONS', {'one': '0,0,30,30', 'two': '0,0,30,30'})
    result = await wildfire.fetch_wildfires(FakeFetcher({'one': ONE, 'two': None}), api_key='synthetic')
    assert result['status'] == 'partial'
    assert result['total_fires'] is None
    assert result['sample_detections'] == 1
    assert result['coverage'] == {'available': 1, 'requested': 2}
    assert result['fires_by_region']['one']['count'] == 1
    assert result['fires_by_region']['two']['count'] is None
    assert _extract_metrics({'wildfires': result})['fire_clusters'] is None


@pytest.mark.asyncio
@pytest.mark.parametrize('body', ['<html>unauthorized</html>', '', 'longitude,confidence\n2,high\n', HEADER + 'not-a-latitude,20,high,1\n'])
async def test_invalid_source_is_not_an_observed_zero(monkeypatch, body):
    monkeypatch.setattr(wildfire, 'REGIONS', {'one': '0,0,30,30'})
    result = await wildfire.fetch_wildfires(FakeFetcher({'one': body}), api_key='synthetic')
    assert result['total_fires'] is None
    assert result['fires_by_region']['one']['count'] is None
    assert result['status'] in {'unavailable', 'partial'}


@pytest.mark.asyncio
async def test_valid_empty_csv_is_a_real_zero(monkeypatch):
    monkeypatch.setattr(wildfire, 'REGIONS', {'one': '0,0,30,30'})
    result = await wildfire.fetch_wildfires(FakeFetcher({'one': HEADER}), api_key='synthetic')
    assert result['status'] == 'ok'
    assert result['total_fires'] == 0
    assert result['fires_by_region']['one']['count'] == 0
    assert _extract_metrics({'wildfires': result})['fire_clusters'] == 0
    brief = await fetch_situation_brief({'wildfires': result}, use_ai=False)
    assert '卫星热异常网格样本' in brief['brief']
    assert '不等同已核实山火' in brief['brief']
    monkeypatch.setattr(wildfire, 'fetch_wildfires', AsyncMock(return_value=result))
    exposure = await fetch_population_exposure(object(), event_types=['wildfire'])
    assert exposure['status'] == 'ok'
    assert exposure['events_analyzed'] == 0


@pytest.mark.asyncio
async def test_stale_region_is_not_included_in_current_exposure(monkeypatch):
    monkeypatch.setattr(wildfire, 'REGIONS', {'one': '0,0,30,30', 'two': '0,0,30,30'})
    result = await wildfire.fetch_wildfires(FakeFetcher({'one': ONE, 'two': ONE}, stale={'wildfire:csv:two'}), api_key='synthetic')
    assert result['status'] == 'partial'
    assert result['total_fires'] is None
    assert result['fires_by_region']['two']['status'] == 'stale'
    monkeypatch.setattr(wildfire, 'fetch_wildfires', AsyncMock(return_value=result))
    exposure = await fetch_population_exposure(object(), event_types=['wildfire'])
    assert exposure['status'] == 'partial'
    assert exposure['coverage']['sources']['wildfire'] == 'partial'
    assert exposure['events_analyzed'] == 1


def test_cli_explains_partial_coverage_and_missing_frp(monkeypatch):
    from world_intel_mcp import cli
    data = {'status': 'partial', 'total_fires': None, 'sample_detections': 1, 'coverage': {'available': 1, 'requested': 2},
        'fires_by_region': {'one': {'status': 'ok', 'count': 1, 'top_clusters': [{'lat': 10, 'lon': 20, 'fire_count': 1, 'max_frp': None}]},
                            'two': {'status': 'unavailable', 'count': None, 'top_clusters': []}}}
    monkeypatch.setattr(cli, '_get_fetcher', lambda: object())
    monkeypatch.setattr(wildfire, 'fetch_wildfires', AsyncMock(return_value=data))
    result = CliRunner().invoke(cli.main, ['fires'])
    assert result.exit_code == 0
    assert '1/2' in result.output
    assert 'unknown' in result.output.lower()
    assert 'high-confidence fires detected' not in result.output


@pytest.mark.asyncio
@pytest.mark.parametrize('source', [
    {'fires_by_region': {'old': {'top_clusters': [{'lat': 10, 'lon': 20, 'fire_count': 1}]}}},
    {'status': 'ok', 'freshness': 'fresh', 'fires_by_region': {'old': {'top_clusters': []}}},
    {'status': 'ok', 'freshness': 'fresh', 'fires_by_region': {'old': {'status': 'ok', 'freshness': 'stale', 'top_clusters': []}}},
    {'status': 'ok', 'freshness': 'fresh', 'fires_by_region': {'old': {'status': 'ok', 'freshness': 'fresh', 'collected_at': '2000-01-01T00:00:00Z', 'cache_expires_at': '2000-01-02T00:00:00Z', 'top_clusters': []}}},
    {'status': 'ok', 'freshness': 'fresh', 'fires_by_region': {'old': {'status': 'ok', 'freshness': 'fresh', 'collected_at': '2099-01-01T00:00:00Z', 'cache_expires_at': '2100-01-01T00:00:00Z', 'top_clusters': []}}},
    {'status': 'ok', 'freshness': 'fresh', 'fires_by_region': {'old': {'status': 'ok', 'freshness': 'fresh', 'top_clusters': []}}},
    {'status': 'ok', 'freshness': 'fresh', 'fires_by_region': {}},
])
async def test_unverified_legacy_regions_do_not_become_current_exposure_or_zero(monkeypatch, source):
    assert _extract_metrics({'wildfires': source})['fire_clusters'] is None
    monkeypatch.setattr(wildfire, 'fetch_wildfires', AsyncMock(return_value=source))
    result = await fetch_population_exposure(object(), event_types=['wildfire'])
    assert result['coverage']['sources']['wildfire'] == 'unavailable'
    assert result['events_analyzed'] is None
    assert result['total_exposed_population'] is None


@pytest.mark.asyncio
async def test_partial_current_region_retains_its_observations_without_claiming_fires(monkeypatch):
    source = {'status': 'partial', 'freshness': 'unknown', 'fires_by_region': {
        'fresh': {'status': 'partial', 'freshness': 'fresh', 'collected_at': '2020-01-01T00:00:00Z', 'cache_expires_at': '2099-01-01T00:00:00Z', 'top_clusters': [{'lat': 10, 'lon': 20, 'fire_count': 1, 'max_frp': None}]},
        'unverified': {'top_clusters': [{'lat': 10, 'lon': 20, 'fire_count': 2}]},
    }}
    monkeypatch.setattr(wildfire, 'fetch_wildfires', AsyncMock(return_value=source))
    result = await fetch_population_exposure(object(), event_types=['wildfire'])
    assert result['coverage']['sources']['wildfire'] == 'partial'
    assert result['events_analyzed'] == 1
    assert '卫星' in result['note'] and '不等同' in result['note']
