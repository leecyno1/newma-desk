from datetime import datetime, timezone
from unittest.mock import patch

import httpx
import pytest
import respx

from world_intel_mcp.sources import aviation

URL = 'https://nasstatus.faa.gov/api/airport-status-information'


def feed(body=''):
    now = datetime.now(timezone.utc).strftime('%a %b %d %H:%M:%S %Y GMT')
    return f'<AIRPORT_STATUS_INFORMATION><Update_Time>{now}</Update_Time>{body}</AIRPORT_STATUS_INFORMATION>'


@pytest.mark.asyncio
@respx.mock
async def test_faa_official_xml_keeps_all_advisories_and_deduplicates_airports(fetcher):
    xml = feed('''<Delay_type><Name>Ground Stop Programs</Name><Ground_Stop_List>
      <Program><ARPT>DEN</ARPT><Reason>low visibility</Reason><End_Time>9:15 am MDT</End_Time></Program>
      </Ground_Stop_List></Delay_type>
      <Delay_type><Name>General Arrival/Departure Delay Info</Name><Arrival_Departure_Delay_List>
      <Delay><ARPT>DEN</ARPT><Reason>Construction</Reason><Arrival_Departure Type="Departure"><Min>16 minutes</Min><Max>30 minutes</Max><Trend>Increasing</Trend></Arrival_Departure></Delay>
      </Arrival_Departure_Delay_List></Delay_type>
      <Delay_type><Name>Airport Closures</Name><Airport_Closure_List>
      <Airport><ARPT>LAX</ARPT><Reason>CLSD TO NON SKED TRANSIENT GA ACFT EXC PPR</Reason><Start>May 27</Start><Reopen>May 28</Reopen></Airport>
      </Airport_Closure_List></Delay_type>''')
    route = respx.get(URL).mock(return_value=httpx.Response(200, text=xml))
    result = await aviation.fetch_airport_delays(fetcher)
    assert route.call_count == 1
    assert result['status'] == 'ok'
    assert result['reported_airport_count'] == result['delayed_count'] == 2
    assert result['advisory_count'] == 3
    assert result['total_checked'] is None
    assert result['updated_at'] and result['collected_at']
    assert len(result['delayed'][0]['status']) == 2
    assert result['delayed'][0]['status'][1]['direction'] == 'Departure'
    assert result['delayed'][0]['status'][1]['min_delay'] == '16 minutes'
    assert result['delayed'][1]['status'][0]['reason'] == 'CLSD TO NON SKED TRANSIENT GA ACFT EXC PPR'


@pytest.mark.asyncio
@respx.mock
async def test_faa_failure_is_unknown_not_zero_and_cli_does_not_claim_clear(fetcher):
    from click.testing import CliRunner
    from world_intel_mcp.cli import main
    respx.get(URL).mock(return_value=httpx.Response(403, text='denied'))
    result = await aviation.fetch_airport_delays(fetcher)
    assert result['status'] == 'unavailable'
    assert result['delayed_count'] is result['reported_airport_count'] is None
    assert result['errors'] == 1
    with patch('world_intel_mcp.cli._get_fetcher', return_value=fetcher), patch('world_intel_mcp.cli._run', side_effect=lambda coro: (coro.close(), result)[1]):
        output = CliRunner().invoke(main, ['delays'])
    assert output.exit_code == 0
    assert 'unknown' in output.output.lower()
    assert 'No major airport delays' not in output.output


@pytest.mark.asyncio
@respx.mock
async def test_faa_valid_empty_feed_differs_from_html_and_malformed_xml(fetcher):
    for raw, expected in [('<html>maintenance</html>', None), ('<AIRPORT_STATUS_INFORMATION>', None), (feed(), 0)]:
        fetcher.cache.delete('aviation:faa:nas-status:v1')
        respx.get(URL).mock(return_value=httpx.Response(200, text=raw))
        result = await aviation.fetch_airport_delays(fetcher)
        assert result['reported_airport_count'] == expected
        assert result['status'] == ('ok' if expected == 0 else 'unavailable')


@pytest.mark.asyncio
@respx.mock
async def test_faa_unknown_structure_and_missing_dates_are_partial(fetcher):
    raw = '<AIRPORT_STATUS_INFORMATION><Delay_type><Name>New schema</Name><New_List><ARPT>DEN</ARPT></New_List></Delay_type></AIRPORT_STATUS_INFORMATION>'
    respx.get(URL).mock(return_value=httpx.Response(200, text=raw))
    result = await aviation.fetch_airport_delays(fetcher)
    assert result['status'] == 'partial'
    assert result['reported_airport_count'] is None
    assert result['invalid_records'] > 0
    assert result['updated_at'] is None
    assert result['freshness'] == 'unknown'


@pytest.mark.asyncio
@respx.mock
async def test_faa_stale_cache_keeps_original_source_date(fetcher):
    xml = '<AIRPORT_STATUS_INFORMATION><Update_Time>Tue Oct 27 12:00:00 2020 GMT</Update_Time></AIRPORT_STATUS_INFORMATION>'
    fetcher.cache.set('aviation:faa:nas-status:v1', xml, ttl_seconds=600)
    result = await aviation.fetch_airport_delays(fetcher)
    assert result['status'] == result['freshness'] == 'stale'
    assert result['updated_at'] == '2020-10-27T12:00:00Z'
    assert result['timestamp'] == result['updated_at']


@pytest.mark.asyncio
@respx.mock
async def test_faa_network_failure_keeps_expired_snapshot_as_history(fetcher):
    xml = feed('<Delay_type><Ground_Stop_List><Program><ARPT>DEN</ARPT><Reason>Weather</Reason></Program></Ground_Stop_List></Delay_type>')
    fetcher.cache.set(aviation._FAA_CACHE_KEY, xml, ttl_seconds=-1)
    collected = fetcher.cache.entry_timing(aviation._FAA_CACHE_KEY)['created_at']
    respx.get(URL).mock(return_value=httpx.Response(503))
    result = await aviation.fetch_airport_delays(fetcher)
    assert result['status'] == result['freshness'] == 'stale'
    assert result['reported_airport_count'] == 1
    assert result['updated_at'] == aviation._parse_faa_status(xml)[1]
    assert result['collected_at'] == datetime.fromtimestamp(collected, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


@pytest.mark.asyncio
@respx.mock
async def test_faa_future_source_date_cannot_be_current_evidence(fetcher):
    xml = '<AIRPORT_STATUS_INFORMATION><Update_Time>Tue Oct 27 12:00:00 2099 GMT</Update_Time></AIRPORT_STATUS_INFORMATION>'
    respx.get(URL).mock(return_value=httpx.Response(200, text=xml))
    result = await aviation.fetch_airport_delays(fetcher)
    assert result['status'] == 'partial'
    assert result['freshness'] == 'unknown'
