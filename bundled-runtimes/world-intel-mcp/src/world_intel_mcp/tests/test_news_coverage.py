"""RSS failure, empty feeds, and cached articles are different evidence."""

import asyncio
from unittest.mock import patch

import pytest
import httpx
import respx

from world_intel_mcp.sources import news


EMPTY = '<rss version="2.0"><channel><title>Empty</title></channel></rss>'
STORY = '<rss version="2.0"><channel><item><title>Retained report</title><pubDate>Mon, 26 Oct 2026 01:00:00 GMT</pubDate></item></channel></rss>'


@pytest.mark.asyncio
async def test_news_receipts_keep_empty_failure_and_old_cache_distinct(fetcher):
    feeds = [(name, f"https://example.com/{name}") for name in ("Empty", "HTML", "Failed", "Old", "Broken")]
    fetcher.cache.set("news:rss:old", STORY, ttl_seconds=-1)

    async def get_xml(url, **kwargs):
        name = url.rsplit("/", 1)[-1]
        if name == "Old":
            raise asyncio.TimeoutError
        if name == "Broken":
            raise ValueError("parser/transport failed")
        content = {"Empty": EMPTY, "HTML": "<html><body>Blocked</body></html>", "Failed": None}[name]
        if content:
            fetcher.cache.set(kwargs["cache_key"], content, ttl_seconds=300)
        return content

    with patch.object(news, "_RSS_FEEDS", {"test": feeds}), patch.object(fetcher, "get_xml", side_effect=get_xml):
        result = await news.fetch_news_feed(fetcher)
    assert result["status"] == "partial"
    assert result["coverage"] == {"expected": 5, "available": 2, "complete": 1, "stale": 1, "partial": 0, "failed": 3}
    rows = {row["source"]: row for row in result["source_results"]}
    assert rows["Empty"]["status"] == "ok"
    assert rows["Empty"]["count"] == 0
    assert rows["HTML"]["reason_code"] == "invalid_feed"
    assert rows["HTML"]["count"] is None
    assert rows["Failed"]["count"] is None
    assert rows["Broken"]["status"] == "unavailable"
    assert rows["Old"]["status"] == "stale"
    assert rows["Old"]["reason_code"] == "timeout"
    assert rows["Old"]["collected_at"] == result["items"][0]["collected_at"]
    assert result["items"][0]["published"] == "2026-10-26T01:00:00Z"
    assert result["count"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("body,expected_status,expected_count", [(None, "unavailable", None), (EMPTY, "ok", 0)])
async def test_news_bundle_does_not_turn_failed_input_into_zero_analysis(fetcher, body, expected_status, expected_count):
    async def get_xml(url, **kwargs):
        if body:
            fetcher.cache.set(kwargs["cache_key"], body, ttl_seconds=300)
        return body

    with patch.object(news, "_RSS_FEEDS", {"test": [("Test", "https://example.com/rss")]}), patch.object(fetcher, "get_xml", side_effect=get_xml):
        result = await news.fetch_news_bundle(fetcher)
        trends = await news.fetch_trending_keywords(fetcher)
    for key in ("news_feed", "trending_keywords", "media_monitor"):
        assert result[key]["status"] == expected_status
    assert result["news_feed"]["count"] == expected_count
    assert result["trending_keywords"]["total_items_analyzed"] == expected_count
    assert trends["status"] == expected_status
    assert trends["total_items_analyzed"] == expected_count
    if body is None:
        assert result["media_monitor"]["summary"] == {}
        assert result["media_monitor"]["error"]


@pytest.mark.asyncio
async def test_partial_feed_keeps_recovered_articles_but_never_claims_complete(fetcher):
    malformed = '<rss version="2.0"><channel><item><title>Recovered item</title></item>'
    fetcher.cache.set("news:rss:test", malformed, ttl_seconds=300)
    with patch.object(news, "_RSS_FEEDS", {"test": [("Test", "https://example.com/rss")]}), patch.object(fetcher, "get_xml", return_value=malformed):
        result = await news.fetch_news_bundle(fetcher)
    assert result["news_feed"]["count"] == 1
    assert result["news_feed"]["source_results"][0]["status"] == "partial"
    assert result["trending_keywords"]["status"] == "partial"
    assert result["media_monitor"]["status"] == "partial"


def test_media_rebuild_preserves_news_failure_and_marks_social_only_sample():
    feed = {"status": "unavailable", "error": "RSS unavailable", "items": [], "coverage": {"expected": 2, "available": 0}}
    assert news.build_media_monitor(feed)["summary"] == {}
    social = news.build_media_monitor(feed, [{"title": "Trade policy announcement", "source": "Test social"}])
    assert social["status"] == "partial"
    assert social["sample_basis"] == "social_sample_news_unavailable"
    assert social["news_error"] == "RSS unavailable"
    assert social["coverage"]["available"] == 0


@respx.mock
@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["DW News", "DW Deutsch", "DW Europe", "DW Español", "VOA News", "Radio Free Europe", "Scroll India", "Lloyd's List", "Maritime Executive"])
async def test_replaced_endpoint_does_not_reuse_old_url_cache(fetcher, name):
    url = dict(feed for feeds in news._RSS_FEEDS.values() for feed in feeds)[name]
    old_key = "news:rss:" + name.lower().replace(" ", "_")
    fetcher.cache.set(old_key, STORY, ttl_seconds=300)
    route = respx.get(url).mock(return_value=httpx.Response(200, text=EMPTY))
    with patch.object(news, "_RSS_FEEDS", {"test": [(name, url)]}):
        result = await news.fetch_news_feed(fetcher)
    assert route.called
    assert result["status"] == "ok"
    assert result["count"] == 0
    assert result["source_results"][0]["configured_url"] == url
    assert fetcher.cache.get(old_key) == STORY


@respx.mock
@pytest.mark.asyncio
async def test_maritime_atom_keeps_source_category_links_and_dates(fetcher):
    url = dict(news._RSS_FEEDS["maritime"])["Maritime Executive"]
    assert url == "https://maritime-executive.com/articles.rss"
    atom = '''<feed xmlns="http://www.w3.org/2005/Atom">
      <title>Maritime Executive</title><updated>2026-10-27T08:00:00Z</updated>
      <entry><id>https://maritime-executive.com/article/sample</id>
        <title>Shipping route observation</title>
        <link href="https://maritime-executive.com/article/sample"/>
        <published>2026-10-26T20:00:00-04:00</published><updated>2026-10-27T08:00:00Z</updated>
        <summary type="html">&lt;p&gt;Report summary&lt;/p&gt;</summary>
      </entry></feed>'''
    respx.get(url).mock(return_value=httpx.Response(200, text=atom))
    with patch.object(news, "_RSS_FEEDS", {"maritime": [("Maritime Executive", url)]}):
        result = await news.fetch_news_bundle(fetcher)
    feed = result["news_feed"]
    assert feed["status"] == "ok" and feed["count"] == 1
    item = feed["items"][0]
    assert item["feed_name"] == "Maritime Executive" and item["category"] == "maritime"
    assert item["source_tier"] == "specialty"
    assert item["link"] == "https://maritime-executive.com/article/sample"
    assert item["published"] == "2026-10-27T00:00:00Z"
    assert item["updated"] == "2026-10-27T08:00:00Z"
    assert item["summary"] == "Report summary"
    receipt = feed["source_results"][0]
    assert receipt["configured_url"] == url and receipt["count"] == 1
    assert receipt["collected_at"] == item["collected_at"]
    assert result["media_monitor"]["coverage"] == feed["coverage"]


@respx.mock
@pytest.mark.asyncio
async def test_invalid_http_response_does_not_destroy_last_valid_feed(fetcher):
    url = "https://example.com/alternating-feed"
    route = respx.get(url).mock(return_value=httpx.Response(200, text=STORY))
    with patch.object(news, "_RSS_FEEDS", {"test": [("Test", url)]}):
        good = await news.fetch_news_feed(fetcher)
        collected = good["items"][0]["collected_at"]
        expires = fetcher.cache.entry_timing("news:rss:test")["expires_at"]
        with patch("world_intel_mcp.cache.time.time", return_value=expires + 1):
            fetcher.cache.evict_expired()
        assert fetcher.cache.get_stale("news:rss:test") is None
        assert fetcher.cache.get_stale("news:rss:test:last-valid")
        route.mock(return_value=httpx.Response(200, text="<html>Unavailable</html>"))
        for _ in range(2):
            failed = await news.fetch_news_feed(fetcher)
            assert failed["status"] == "partial"
            assert failed["count"] == 1
            assert failed["items"][0]["collected_at"] == collected
            assert failed["items"][0]["freshness"] == "stale"
            row = failed["source_results"][0]
            assert row["reason_code"] == "invalid_feed"
            assert row["status"] == "stale"
            assert "上次有效" in row["reason"]

        # A real empty feed supersedes the old story; a later outage retains zero
        # only as a dated historical count, not a successful current query.
        fetcher.cache.delete("news:rss:test")
        route.mock(return_value=httpx.Response(200, text=EMPTY))
        empty = await news.fetch_news_feed(fetcher)
        assert empty["status"] == "ok" and empty["count"] == 0
        fetcher.cache.delete("news:rss:test")
        route.mock(return_value=httpx.Response(200, text="invalid"))
        old_empty = await news.fetch_news_feed(fetcher)
        assert old_empty["status"] == "partial" and old_empty["count"] == 0
        assert old_empty["source_results"][0]["status"] == "stale"
        assert not old_empty["items"]
