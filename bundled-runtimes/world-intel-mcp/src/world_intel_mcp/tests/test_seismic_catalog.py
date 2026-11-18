import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import httpx
import respx
import pytest

from world_intel_mcp.analysis.inputs import AnalysisInputs
from world_intel_mcp.analysis.exposure import fetch_population_exposure
from world_intel_mcp.sources import seismology, nuclear, intelligence, conflict, wildfire


def feature(identity='q', hours=1, mag=5, lon=44, lat=33):
    return {'type': 'Feature', 'id': identity, 'properties': {
        'mag': mag, 'time': (datetime.now(timezone.utc).timestamp() - hours * 3600) * 1000,
        'place': 'Test', 'type': 'earthquake'},
        'geometry': {'type': 'Point', 'coordinates': [lon, lat, 10]}}


def catalogue(rows):
    return {'type': 'FeatureCollection', 'metadata': {
        'count': len(rows), 'generated': datetime.now(timezone.utc).timestamp() * 1000}, 'features': rows}


@respx.mock
async def test_four_cycle_consumers_share_one_catalogue_and_keep_distinct_windows(fetcher, monkeypatch):
    route = respx.get(seismology._USGS_MONTH).mock(return_value=httpx.Response(200, json=catalogue([
        feature('recent'), feature('older', hours=36), feature('month', hours=400, mag=3),
        feature('site', mag=2, lon=129.08, lat=41.30), feature('future', hours=-1),
    ])))
    monkeypatch.setattr(conflict, 'fetch_acled_events', AsyncMock(return_value={'error': 'no credentials'}))
    monkeypatch.setattr(wildfire, 'fetch_wildfires', AsyncMock(return_value={'error': 'no credentials'}))
    inputs = AnalysisInputs(fetcher)
    try:
        quakes, regions, sites, exposure = await asyncio.gather(*(inputs.get(name) for name in (
            'earthquakes', 'signal_convergence', 'nuclear_monitor', 'population_exposure')))
        assert route.call_count == 1
        assert quakes['count'] == 1
        assert quakes['earthquakes'][0]['id'] == 'recent'
        assert next(r for r in regions['hotspots'] if r['name'] == 'middle_east')['signals']['earthquakes'] == 3
        assert sum(s['events_detected'] for s in sites['sites']) == 1
        assert exposure['events_analyzed'] == 2
        assert exposure['status'] == 'partial'
        assert exposure['coverage']['available'] == 1
        assert quakes['source_updated_at'] == sites['source_updated_at'] == regions['source_updated_at']
    finally:
        await inputs.close()
    assert all(task.done() for task in inputs.tasks.values())


async def test_missing_catalogue_is_not_zero_or_static_risk(fetcher):
    missing = {'error': 'timeout', 'status': 'unavailable'}
    quakes = await seismology.fetch_earthquakes(fetcher, catalog=missing)
    regions = await intelligence.fetch_signal_convergence(fetcher, catalog=missing)
    sites = await nuclear.fetch_nuclear_monitor(fetcher, catalog=missing)
    assert quakes['count'] is None
    assert all(r['signals']['earthquakes'] is None and r['convergence_score'] is None for r in regions['hotspots'])
    assert sites['total_flagged_events'] is sites['critical_flags'] is None
    assert all(site['events_detected'] is None for site in sites['sites'])


@respx.mock
async def test_empty_malformed_and_stale_catalogues_are_different(fetcher):
    route = respx.get(seismology._USGS_MONTH)
    for raw, count, status in [(catalogue([]), 0, 'ok'), ({'features': []}, None, 'unavailable')]:
        fetcher.cache.delete(seismology._CATALOG_KEY)
        route.mock(return_value=httpx.Response(200, json=raw))
        result = await seismology.fetch_earthquakes(fetcher)
        assert result['count'] == count and result['status'] == status
    old = catalogue([feature()])
    old['metadata']['generated'] -= 3600 * 1000
    fetcher.cache.set(seismology._CATALOG_KEY, old, 300)
    result = await seismology.fetch_earthquakes(fetcher)
    assert result['count'] == 1 and result['status'] == 'stale'
    assert result['source_updated_at'] != result['collected_at']


@respx.mock
async def test_filter_keeps_zero_coordinates_and_discloses_limit(fetcher):
    rows = [feature('zero', lon=0, lat=0), feature('older', hours=2, lon=0, lat=0)]
    respx.get(seismology._USGS_MONTH).mock(return_value=httpx.Response(200, json=catalogue(rows)))
    small = await seismology.fetch_earthquakes(fetcher, limit=1)
    large = await seismology.fetch_earthquakes(fetcher, limit=2)
    assert small['count'] == 1 and small['truncated'] is True
    assert large['count'] == 2 and large['truncated'] is False
    assert small['earthquakes'][0]['longitude'] == small['earthquakes'][0]['latitude'] == 0


@respx.mock
async def test_custom_range_retains_fdsn_query_and_cache_identity(fetcher):
    route = respx.get(seismology._USGS_ENDPOINT).mock(return_value=httpx.Response(200, json=catalogue([feature(mag=.5)])))
    await seismology.fetch_earthquakes(fetcher, min_magnitude=0, hours=1000, limit=1)
    result = await seismology.fetch_earthquakes(fetcher, min_magnitude=0, hours=1000, limit=2)
    assert route.call_count == 2
    assert result['query']['hours'] == 1000 and result['query']['limit'] == 2
    assert result['count'] == 1


async def test_exposure_missing_sources_stays_unknown(fetcher, monkeypatch):
    monkeypatch.setattr(conflict, 'fetch_acled_events', AsyncMock(return_value={'error': 'missing'}))
    monkeypatch.setattr(wildfire, 'fetch_wildfires', AsyncMock(return_value={'error': 'missing'}))
    result = await fetch_population_exposure(fetcher, catalog={'error': 'unavailable'})
    assert result['total_exposed_population'] is result['exposed_city_count'] is None
    assert result['status'] == 'unavailable'


@respx.mock
async def test_unknown_depth_never_generates_a_concern_score(fetcher):
    rows = [feature(str(i), lon=129.08, lat=41.30) for i in range(3)]
    for row, depth in zip(rows, [None, True, float('nan')]):
        row['geometry']['coordinates'][2] = depth
    # Cache can contain malformed legacy values, not just strict JSON responses.
    fetcher.cache.set(seismology._CATALOG_KEY, catalogue(rows), 300)
    data = await nuclear.fetch_nuclear_monitor(fetcher)
    assert data['total_flagged_events'] == 3
    assert data['critical_flags'] is None
    assert all(e['depth_km'] is e['concern_score'] is None for e in data['flagged_events'])


@respx.mock
async def test_missing_catalogue_metadata_is_partial_and_invalid_limits_rejected(fetcher):
    raw = catalogue([feature()])
    raw['metadata'] = ['bad schema']
    respx.get(seismology._USGS_MONTH).mock(return_value=httpx.Response(200, json=raw))
    data = await seismology.fetch_earthquakes(fetcher)
    assert data['status'] == 'partial' and data['source_updated_at'] is None
    for kwargs in ({'hours': 0}, {'limit': -1}, {'limit': True}, {'min_magnitude': float('nan')}):
        with pytest.raises(ValueError):
            await seismology.fetch_earthquakes(fetcher, **kwargs)


async def test_exposure_starts_other_sources_while_shared_catalogue_is_pending(fetcher, monkeypatch):
    started = asyncio.Event()
    async def fires(*args, **kwargs):
        started.set()
        return {'error': 'missing'}
    async def catalog():
        await asyncio.wait_for(started.wait(), .5)
        return {'error': 'unavailable'}
    monkeypatch.setattr(wildfire, 'fetch_wildfires', fires)
    monkeypatch.setattr(conflict, 'fetch_acled_events', AsyncMock(return_value={'error': 'missing'}))
    inputs = AnalysisInputs(fetcher)
    inputs.factories['seismic_catalog'] = catalog
    try:
        data = await inputs.get('population_exposure')
        assert started.is_set()
        assert 'source_times' in data and data['status'] == 'unavailable'
    finally:
        await inputs.close()


def test_cli_keeps_missing_counts_and_depth_unknown(monkeypatch):
    from click.testing import CliRunner
    from world_intel_mcp.cli import main
    monkeypatch.setattr('world_intel_mcp.cli._get_fetcher', lambda: None)
    data = {'status': 'unavailable', 'count': None, 'error': 'source missing',
            'total_flagged_events': None, 'sites': [{'name': 'Test', 'events_detected': None}]}
    monkeypatch.setattr('world_intel_mcp.cli._run', lambda coro: (coro.close(), data)[1])
    for command in ('earthquakes', 'nuclear'):
        result = CliRunner().invoke(main, [command])
        assert result.exit_code == 0
        assert 'unknown' in result.output and 'source missing' in result.output
        assert '0 events' not in result.output
    data.update(status='ok', count=1, error=None, earthquakes=[{'magnitude': 5, 'depth_km': None, 'time': '', 'place': 'Zero depth unknown'}])
    result = CliRunner().invoke(main, ['earthquakes'])
    assert result.exit_code == 0 and 'unknown' in result.output
