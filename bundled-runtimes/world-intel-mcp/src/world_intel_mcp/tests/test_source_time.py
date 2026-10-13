import importlib
import time
from unittest.mock import AsyncMock

import feedparser
import pytest

from world_intel_mcp.source_time import parse_rss_time


@pytest.mark.parametrize("zone", ["UTC", "Asia/Shanghai", "America/New_York"])
@pytest.mark.parametrize("source", ["news", "health", "ai_watch", "service_status"])
def test_rss_dates_do_not_depend_on_server_timezone(zone, source, monkeypatch):
    entry = feedparser.parse("""<rss><channel><item><title>UTC example</title>
        <pubDate>Thu, 10 Sep 2026 08:00:00 GMT</pubDate></item></channel></rss>""").entries[0]
    parser = importlib.import_module(f"world_intel_mcp.sources.{source}")._parse_published
    try:
        with monkeypatch.context() as environment:
            environment.setenv("TZ", zone)
            time.tzset()
            assert parser(entry) == "2026-09-10T08:00:00Z"
    finally:
        time.tzset()


def test_atom_update_is_not_publication():
    entry = feedparser.parse("""<feed xmlns="http://www.w3.org/2005/Atom"><entry>
        <title>Updated notice</title><updated>2026-09-10T08:00:00Z</updated>
        </entry></feed>""").entries[0]
    assert parse_rss_time(entry) is None
    assert parse_rss_time(entry, "updated") == "2026-09-10T08:00:00Z"
    assert parse_rss_time({"published": "invalid"}) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("source, config, feeds, function, key", [
    ("news", "_RSS_FEEDS", {"test": [("Test", "https://example.com/feed")]}, "fetch_news_feed", "news:rss:test"),
    ("health", "_HEALTH_FEEDS", [("Test", "https://example.com/feed")], "fetch_disease_outbreaks", "health:rss:test"),
    ("ai_watch", "_AI_FEEDS", [("Test", "https://example.com/feed", "research")], "fetch_ai_watch", "ai_watch:rss:test"),
    ("service_status", "_STATUS_FEEDS", [{"provider": "Test", "url": "https://example.com/feed"}], "fetch_service_status", "status:rss:test"),
])
async def test_each_feed_keeps_its_successful_collection_time(fetcher, monkeypatch, source, config, feeds, function, key):
    module = importlib.import_module(f"world_intel_mcp.sources.{source}")
    monkeypatch.setattr(module, config, feeds)
    xml = """<rss><channel><item><title>Outage warning</title><pubDate>Thu, 10 Sep 2026 08:00:00 GMT</pubDate></item>
        <item><title>Notice without date</title></item></channel></rss>"""
    fetcher.cache.set(key, xml, -1)
    # A newer unrelated feed must not make this cached feed look current.
    fetcher.cache.set("news:rss:another", xml, 600)
    fetcher.get_xml = AsyncMock(return_value=xml)
    first = await getattr(module, function)(fetcher)
    second = await getattr(module, function)(fetcher)
    records = first.get("items", first.get("incidents"))
    repeated = second.get("items", second.get("incidents"))
    assert len(records) == 2
    assert records[0]["published"] == "2026-09-10T08:00:00Z"
    assert records[1]["published"] is None
    assert records[0]["freshness"] == "stale"
    assert records[0]["collected_at"] == repeated[0]["collected_at"]
    assert records[0]["collected_at"] is not None


@pytest.mark.asyncio
async def test_earthquake_missing_event_time_and_unavailable_source(fetcher):
    from world_intel_mcp.sources.seismology import fetch_earthquakes
    data = {"features": [{"id": "q", "properties": {"mag": 6}, "geometry": {"coordinates": [60, 20, 10]}}]}
    fetcher.cache.set("seismology:quakes:4.5:24", data, -1)
    fetcher.get_json = AsyncMock(return_value=data)
    result = await fetch_earthquakes(fetcher)
    assert result["earthquakes"][0]["time"] is None
    assert result["freshness"] == "stale"
    assert result["timestamp"] == result["collected_at"]
    fetcher.get_json = AsyncMock(return_value=None)
    failed = await fetch_earthquakes(fetcher)
    assert failed["error"]
