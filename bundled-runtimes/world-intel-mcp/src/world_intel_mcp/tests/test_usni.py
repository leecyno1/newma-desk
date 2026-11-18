from unittest.mock import AsyncMock, patch

import pytest

from world_intel_mcp.sources.usni_fleet import _extract_fleet_data, fetch_usni_fleet


def test_cutter_hulls_keep_numbers_and_deduplicate_same_ship():
    result = _extract_fleet_data('USCGC Alpha (WMSL-750). USCGC Beta (WMSL-751). USCGC Alpha (WMSL-750).')
    assert {ship['hull_number'] for ship in result['ships']} == {'WMSL-750', 'WMSL-751'}
    assert result['ship_count'] == 2
    assert result['region_basis'] == 'article_context_heuristic'


@pytest.mark.asyncio
@pytest.mark.parametrize('body', [None, '<html>access denied</html>', '<rss><channel/></rss>'])
async def test_unavailable_feed_is_unknown_not_zero(fetcher, body):
    fetcher.get_text = AsyncMock(return_value=body)
    result = await fetch_usni_fleet(fetcher)
    assert result['status'] == 'unavailable'
    assert result['ship_count'] is None
    assert result['timestamp'] is None
    assert result['error']


@pytest.mark.asyncio
async def test_latest_tracker_not_first_entry_and_keep_source_time(fetcher):
    xml = '''<rss><channel>
      <item><title>Other navy news</title><pubDate>Tue, 27 Oct 2026 12:00:00 GMT</pubDate></item>
      <item><title>USNI Fleet and Marine Tracker: Old</title><pubDate>Mon, 05 Oct 2026 12:00:00 GMT</pubDate></item>
      <item><title>USNI Fleet and Marine Tracker: Latest</title><pubDate>Mon, 19 Oct 2026 12:00:00 GMT</pubDate>
        <description><![CDATA[<p>USS <em>John C. Stennis</em> (CVN&nbsp;74) in the Pacific.</p>]]></description></item>
    </channel></rss>'''
    with patch('world_intel_mcp.cache.time.time', return_value=1792411200):
        fetcher.cache.set('usni:fleet_tracker_rss', xml, 3600)
    fetcher.get_text = AsyncMock(return_value=xml)
    first = await fetch_usni_fleet(fetcher)
    second = await fetch_usni_fleet(fetcher)
    assert first['report_title'].endswith('Latest')
    assert first['report_date'] == '2026-10-19T12:00:00Z'
    assert first['timestamp'] == second['timestamp'] == first['collected_at']
    assert first['freshness'] == 'stale'
    assert first['ships'][0]['hull_number'] == 'CVN-74'
    assert first['status'] == 'partial'


@pytest.mark.asyncio
async def test_summary_without_ships_does_not_mean_zero_fleet(fetcher):
    fetcher.get_text = AsyncMock(return_value='''<rss><channel><item>
      <title>USNI Fleet and Marine Tracker</title><description>Read the full report.</description>
    </item></channel></rss>''')
    result = await fetch_usni_fleet(fetcher)
    assert result['status'] == 'partial'
    assert result['ship_count'] is None
    assert result['report_date'] is None
    assert result['content_basis'] == 'summary'
    assert result['coverage_note']
