from datetime import UTC, datetime

import pytest

from vibe_visualization_api.crucix.adapter import normalize_snapshot


@pytest.mark.parametrize("code,http", [("RSS_TIMEOUT", None), ("RSS_CONNECTION_REFUSED", None),
    ("RSS_DNS_ERROR", None), ("RSS_TLS_ERROR", None), ("RSS_NETWORK_ERROR", None),
    ("RSS_INVALID_FEED", None), ("RSS_HTTP_ERROR", 403)])
def test_rss_failure_evidence_reaches_api_without_changing_old_article_time(code, http):
    row = {"source": "Synthetic", "url": "https://example.org/feed", "status": "error", "count": None,
           "errorCode": code, "httpStatus": http, "asOf": "2026-11-14T11:00:00Z",
           "cached": True, "dataAsOf": "2026-11-13T11:00:00Z", "availableCount": 1}
    coverage = normalize_snapshot({"newsMeta": {"items": [row]}}, now=datetime(2026, 11, 14, 12, tzinfo=UTC))["newsCoverage"]
    result = coverage["items"][0]
    assert result["errorCode"] == code and result["httpStatus"] == http
    assert result["sourceUrl"] == row["url"]
    assert result["status"] == "error" and result["count"] is None
    assert result["dataAsOf"] == row["dataAsOf"] and result["dataFreshness"]["status"] == "stale"
    assert coverage["status"] == "partial" and coverage["cachedSources"] == 1


def test_rss_unknown_error_detail_and_invalid_http_are_not_exported_as_diagnostics():
    row = {"source": "Synthetic", "url": "javascript:alert(1)", "status": "error", "errorCode": "private-error-detail", "httpStatus": 403.5}
    result = normalize_snapshot({"newsMeta": {"items": [row]}})["newsCoverage"]["items"][0]
    assert result["sourceUrl"] is None and result["errorCode"] is None and result["httpStatus"] is None


def test_rss_news_distinct_urls_keep_their_identity_even_with_identical_titles_and_dates():
    rows = [{"source": "Synthetic", "type": "rss", "headline": "Same title", "timestamp": "2026-11-14T11:00:00Z",
             "url": "https://example.org/" + url} for url in ("report-a", "report-b", "report-a")]
    result = normalize_snapshot({"newsFeed": rows})["news"]
    assert [row["url"] for row in result] == ["https://example.org/report-a", "https://example.org/report-b"]
