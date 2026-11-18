from datetime import UTC, datetime

import pytest

from vibe_visualization_api.crucix.adapter import normalize_snapshot

NOW = datetime(2026, 11, 14, 12, tzinfo=UTC)
STAMP = "2026-11-14T11:00:00Z"
WINDOW = {"start": "2026-10-15T10:00:00Z", "end": "2026-11-14T10:00:00Z", "days": 30}


def payload(status="ok", count=20):
    return {"meta": {"timestamp": "2026-11-14T11:30:00Z"},
        "whoMeta": {"status": status, "count": count, "collectedAt": STAMP, "window": WINDOW,
                    "gaps": {"pagination": "source may have more records"} if status == "partial" else {}},
        "who": [] if count == 0 or status == "error" else [{"title": "A report", "date": "2026-11-10T01:00:00Z"}]}


@pytest.mark.parametrize("status,count", [("ok", 20), ("ok", 0), ("partial", 3), ("error", None)])
def test_who_retains_window_count_limit_and_original_collection_not_display_or_batch(status, count):
    raw = payload(status, count)
    result = normalize_snapshot(raw, now=NOW)["global"]["who"]
    assert result["status"] == status and result["reportCount"] == count
    assert result["window"] == WINDOW
    assert result["displayed"] == len(raw["who"]) and result["sourceDisplayLimit"] == 15 and result["queryLimit"] == 100
    assert result["collectedAt"] == (STAMP if status != "error" else None)
    assert result["checkedAt"] == STAMP and result["freshness"]["status"] == ("fresh" if status != "error" else "unknown")
    assert result["complete"] is (status == "ok")
    assert "不是感染人数" in result["note"] and "非疫情发生时间" in result["note"]
    assert bool(result["gaps"]) is (status == "partial")


@pytest.mark.parametrize("patch", [{"window": None}, {"count": -1}, {"count": True}, {"count": 1.5},
    {"window": {**WINDOW, "end": "2026-11-15T10:00:00Z"}},
    {"window": {**WINDOW, "start": "2026-11-14T10:00:00Z"}},
    {"window": {**WINDOW, "days": 1}}, {"gaps": {"pagination": "More pages"}}])
def test_unverified_scope_or_count_does_not_become_complete_empty(patch):
    raw = payload(count=0)
    raw["whoMeta"].update(patch)
    result = normalize_snapshot(raw, now=NOW)["global"]["who"]
    assert result["complete"] is False and result["status"] != "ok"
    if "gaps" not in patch:
        assert result["reportCount"] is None


def test_who_legacy_missing_and_old_are_not_recent_complete_coverage():
    assert normalize_snapshot({"who": []}, now=NOW)["global"]["who"] is None
    result = normalize_snapshot(payload(), now=datetime(2026, 11, 20, tzinfo=UTC))["global"]["who"]
    assert result["reportCount"] == 20 and result["freshness"]["status"] == "stale"
    assert result["collectedAt"] == STAMP


def test_official_news_uses_original_who_collection_not_enrichment_batch():
    raw = payload()
    raw["newsFeed"] = [{"source": "WHO", "type": "who", "headline": "A report", "timestamp": "2026-11-10T01:00:00Z",
                        "timestampBasis": "published", "url": "https://www.who.int/example"}]
    result = normalize_snapshot(raw, now=NOW)["news"][0]
    assert result["publishedAt"] == "2026-11-10T01:00:00Z"
    assert result["collectedAt"] == STAMP and result["collectionFreshness"]["status"] == "fresh"
    raw["whoMeta"]["status"] = "error"
    result = normalize_snapshot(raw, now=NOW)["news"][0]
    assert result["collectedAt"] is None and result["collectionFreshness"]["status"] == "unknown"


def test_full_page_retains_known_sample_without_claiming_complete_window():
    result = normalize_snapshot(payload(count=100), now=NOW)["global"]["who"]
    assert result["reportCount"] == 100 and result["status"] == "partial"
    assert result["complete"] is False and result["gaps"]["pagination"]


def test_window_cannot_finish_after_collection_even_by_a_fraction_of_a_second():
    raw = payload()
    raw["whoMeta"].update(collectedAt="2026-11-14T10:00:00Z", window={
        "start": "2026-10-15T10:00:00.100Z", "end": "2026-11-14T10:00:00.100Z", "days": 30})
    result = normalize_snapshot(raw, now=NOW)["global"]["who"]
    assert result["reportCount"] is None and result["complete"] is False


def test_nonempty_display_does_not_certify_an_empty_query_count():
    raw = payload(count=0)
    raw["who"] = [{"title": "A report"}]
    result = normalize_snapshot(raw, now=NOW)["global"]["who"]
    assert result["reportCount"] is None and result["complete"] is False


def test_who_bulletins_survive_a_full_general_news_feed_without_duplicate_truncated_titles():
    raw = payload(count=20)
    title = "A WHO bulletin " * 12
    raw["who"] = [{"title": title, "date": "2026-11-10T01:00:00Z", "url": "https://www.who.int/bulletin"}]
    raw["newsFeed"] = [{"headline": f"RSS story {index}", "source": "RSS", "type": "rss"} for index in range(120)]
    result = normalize_snapshot(raw, now=NOW)
    assert len(result["news"]) == 80
    official = [row for row in result["news"] if row["type"] == "who"]
    assert len(official) == 1 and official[0]["title"] == title.strip()
    raw["newsFeed"].insert(0, {"headline": title[:100], "source": "WHO", "type": "who",
                             "timestamp": "2026-11-10T01:00:00Z", "url": "https://www.who.int/bulletin"})
    result = normalize_snapshot(raw, now=NOW)
    assert len([row for row in result["news"] if row["type"] == "who"]) == 1
