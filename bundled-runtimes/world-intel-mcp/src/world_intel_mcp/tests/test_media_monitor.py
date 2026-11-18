"""Tests for the lightweight media monitor."""

from datetime import datetime, timezone

from world_intel_mcp.analysis.media_monitor import analyze_media_monitor


def test_updated_only_reports_use_update_time_without_inventing_publication() -> None:
    result = analyze_media_monitor([
        {"title": "Shipping route correction after attack", "published": "invalid", "updated": "2026-10-27T11:00:00Z"},
        {"title": "Shipping route attack", "updated": "2026-10-27T03:00:00Z"},
    ], now=datetime(2026, 10, 27, 12, tzinfo=timezone.utc), window_hours=6)
    assert result["summary"]["current_mentions"] == result["summary"]["previous_mentions"] == 1
    assert result["summary"]["heat_velocity_pct"] == 0
    assert result["summary"]["time_coverage"]["updated"] == 2
    topic = result["topics"][0]
    assert topic["latest_at"] == "2026-10-27T11:00:00Z"
    assert topic["latest_at_basis"] == "updated"
    assert topic["items"][0]["published"] is None
    assert topic["items"][0]["timestamp_basis"] == "updated"
    assert topic["verification_timeline"][0]["timestamp_basis"] == "updated"


def test_missing_future_and_collection_dates_do_not_imply_flat_or_zero_heat() -> None:
    for fields, missing, future in [({}, 1, 0), ({"timestamp": "2026-10-27T11:00:00Z"}, 1, 0),
                                    ({"published": "2026-10-27T12:01:00Z"}, 0, 1)]:
        result = analyze_media_monitor([{"title": "Shipping route attack", **fields}],
            now=datetime(2026, 10, 27, 12, tzinfo=timezone.utc), window_hours=6)
        summary = result["summary"]
        assert summary["current_mentions"] is summary["previous_mentions"] is None
        assert summary["velocity_state"] == "unknown"
        assert summary["heat_velocity_pct"] is None
        assert summary["time_coverage"]["unknown"] == missing
        assert summary["time_coverage"]["future"] == future
        assert result["topics"][0]["heat_score"] is None
        assert result["topics"][0]["attention_score"] is None
        assert result["topics"][0]["latest_at"] is None


def test_partial_dates_keep_observed_counts_but_withhold_growth() -> None:
    result = analyze_media_monitor([
        {"title": "Shipping route attack", "published": "2026-10-27T11:00:00Z"},
        {"title": "Shipping route attack continues"},
    ], now=datetime(2026, 10, 27, 12, tzinfo=timezone.utc), window_hours=6)
    assert result["summary"]["current_mentions"] == 1
    assert result["summary"]["previous_mentions"] == 0
    assert result["summary"]["time_coverage"]["status"] == "partial"
    assert result["summary"]["velocity_state"] == "unknown"
    assert result["summary"]["heat_velocity_pct"] is None
    assert result["topics"][0]["heat_score"] is None


def test_published_takes_precedence_and_old_samples_do_not_imply_flat() -> None:
    result = analyze_media_monitor([
        {"title": "Shipping route attack", "published": "2026-10-25T12:00:00Z", "updated": "2026-10-27T11:00:00Z"},
    ], now=datetime(2026, 10, 27, 12, tzinfo=timezone.utc), window_hours=6)
    assert result["summary"]["current_mentions"] == result["summary"]["previous_mentions"] == 0
    assert result["summary"]["time_coverage"]["outside_window"] == 1
    assert result["summary"]["velocity_state"] == "unknown"
    assert result["topics"][0]["items"][0]["timestamp_basis"] == "published"


def test_unmatched_multilingual_reports_are_unassessed_not_neutral() -> None:
    reports = [
        ("de", "Die Regierung veröffentlicht den Haushaltsplan"),
        ("ru", "Правительство представило бюджет на следующий год"),
        ("ar", "الحكومة تعلن الموازنة للعام القادم"),
        ("en", "Parliament publishes the annual budget schedule"),
    ]
    result = analyze_media_monitor([
        {"title": title, "language": language, "feed_name": language, "source_tier": "wire"}
        for language, title in reports
    ])
    sentiment = result["summary"]["sentiment"]
    assert sentiment["neutral"] == 0
    assert sentiment["unknown"] == 4
    assert sentiment["assessed_items"] == 0
    assert sentiment["unknown_pct"] == 100
    assert sentiment["negative_pct"] is None
    assert sentiment["net_score"] is None
    assert all(item["sentiment"] == "unknown" and item["sentiment_score"] is None for item in result["annotations"])
    assert all(topic["attention_score"] is None for topic in result["topics"])
    assert result["media_frames"][0]["dominant_sentiment"] == "unknown"


def test_partial_lexicon_coverage_preserves_signals_without_inventing_overall_tone() -> None:
    result = analyze_media_monitor([
        {"title": "Shipping route attack", "feed_name": "Wire", "source_tier": "wire"},
        {"title": "Shipping route timetable", "feed_name": "Agency", "source_tier": "government"},
    ])
    sentiment = result["summary"]["sentiment"]
    assert sentiment["negative"] == sentiment["unknown"] == 1
    assert sentiment["negative_pct"] == sentiment["unknown_pct"] == 50
    assert sentiment["assessed_items"] == 1
    assert sentiment["net_score"] is None
    topic = result["topics"][0]
    assert topic["mention_count"] == 2
    assert topic["sentiment"] == "unknown"
    assert topic["sentiment_score"] is None
    assert topic["framing_divergence"] is None
    assert topic["framing_divergence_score"] is None
    assert topic["attention_score"] is None
    assert result["summary"]["attention_topic_count"] is None
    assert result["summary"]["divergent_topic_count"] is None
    assert result["annotations"][0]["sentiment"] == "negative"


def test_fully_matched_balanced_signals_preserve_real_zero() -> None:
    result = analyze_media_monitor([
        {"title": "Shipping route peace", "source_tier": "wire"},
        {"title": "Shipping route attack", "source_tier": "wire"},
    ])
    assert result["summary"]["sentiment"]["net_score"] == 0
    assert result["summary"]["sentiment"]["assessed_items"] == 2
    assert result["summary"]["sentiment"]["unknown"] == 0
    assert result["topics"][0]["sentiment_score"] == 0


def test_empty_sample_preserves_counts_without_assessing_sentiment_or_spread() -> None:
    result = analyze_media_monitor([], now=datetime(2026, 10, 27, 12, tzinfo=timezone.utc), window_hours=6)
    summary = result["summary"]
    for key in ("analyzed_items", "news_items", "social_items", "source_count", "language_count",
                "topic_count", "current_mentions", "previous_mentions", "flagged_topic_count",
                "cross_language_topic_count", "disputed_topic_count", "reversal_topic_count",
                "divergent_topic_count", "attention_topic_count"):
        assert summary[key] == 0
    assert summary["window_hours"] == 6
    assert summary["spread_score"] is None
    assert summary["heat_velocity_pct"] is None
    assert summary["velocity_state"] == "unknown"
    for sentiment in ("positive", "negative", "neutral", "mixed"):
        assert summary["sentiment"][sentiment] == 0
        assert summary["sentiment"][f"{sentiment}_pct"] is None
    assert summary["sentiment"]["net_score"] is None
    assert result["topics"] == result["annotations"] == result["media_frames"] == []
    assert result["timestamp"] == "2026-10-27T12:00:00Z"


def test_media_monitor_combines_languages_and_surfaces_verification_cues() -> None:
    result = analyze_media_monitor(
        [
            {
                "title": "Iran denies unverified claim about Strait of Hormuz closure",
                "summary": "Officials deny the report while shipping disruption continues.",
                "feed_name": "Reuters World",
                "source_tier": "wire",
                "published": "2026-08-12T11:00:00Z",
                "link": "https://example.com/en",
            },
            {
                "title": "Irán niega el rumor sobre el cierre de Ormuz",
                "summary": "El comercio marítimo sigue bajo presión.",
                "feed_name": "BBC Mundo",
                "source_tier": "major",
                "published": "2026-08-12T10:30:00Z",
                "link": "https://example.com/es",
            },
            {
                "title": "Correction: Iran did not close the Strait of Hormuz",
                "summary": "The earlier account was corrected.",
                "feed_name": "AP Top News",
                "source_tier": "wire",
                "published": "2026-08-12T10:00:00Z",
                "link": "https://example.com/correction",
            },
        ],
        [{
            "title": "Is the Hormuz closure report true?",
            "subreddit": "worldnews",
            "score": 4200,
            "num_comments": 900,
            "created": "2026-08-12T11:15:00Z",
            "url": "https://reddit.com/test",
        }],
        now=datetime(2026, 8, 12, 12, tzinfo=timezone.utc),
        window_hours=6,
    )

    topic = result["topics"][0]
    assert topic["mention_count"] == 4
    assert topic["cross_language"] is True
    assert topic["language_count"] >= 2
    assert topic["spread_score"] >= 55
    assert topic["verification_status"] == "出现纠正"
    assert result["summary"]["flagged_topic_count"] == 1
    assert result["summary"]["heat_velocity_pct"] is None
    assert result["summary"]["velocity_state"] == "new"
    statuses = [step["status"] for step in topic["verification_timeline"]]
    assert statuses[0] == "出现纠正"
    assert "待核实" in statuses
    assert statuses[-1] == "出现否认"


def test_media_topic_identity_survives_new_records_joining() -> None:
    base = [{
        "title": "Iran shipping disruption near Strait of Hormuz",
        "feed_name": "Reuters World",
        "source_tier": "wire",
        "published": "2026-08-12T10:00:00Z",
        "link": "https://example.com/one",
    }]
    later = [*base, {
        "title": "Iran reports more shipping disruption in Hormuz",
        "feed_name": "AP Top News",
        "source_tier": "wire",
        "published": "2026-08-12T11:00:00Z",
        "link": "https://example.com/two",
    }]

    first = analyze_media_monitor(base, now=datetime(2026, 8, 12, 12, tzinfo=timezone.utc))
    second = analyze_media_monitor(later, now=datetime(2026, 8, 12, 12, tzinfo=timezone.utc))

    assert first["topics"][0]["id"] == second["topics"][0]["id"]


def test_media_monitor_reports_sentiment_velocity_and_source_frames() -> None:
    result = analyze_media_monitor(
        [
            {
                "title": "Peace agreement restores shipping route",
                "feed_name": "UN News",
                "source_tier": "government",
                "published": "2026-08-12T11:00:00Z",
            },
            {
                "title": "Missile attack escalates regional crisis",
                "feed_name": "Defense One",
                "source_tier": "specialty",
                "published": "2026-08-12T10:00:00Z",
            },
            {
                "title": "Regional trade talks continue",
                "feed_name": "Reuters World",
                "source_tier": "wire",
                "published": "2026-08-12T03:00:00Z",
            },
        ],
        now=datetime(2026, 8, 12, 12, tzinfo=timezone.utc),
        window_hours=6,
    )

    summary = result["summary"]
    assert summary["sentiment"]["positive"] >= 1
    assert summary["sentiment"]["negative"] >= 1
    assert summary["current_mentions"] == 2
    assert summary["previous_mentions"] == 1
    assert summary["heat_velocity_pct"] == 100
    assert {frame["group"] for frame in result["media_frames"]} >= {
        "mainstream", "official", "specialist",
    }


def test_media_monitor_clusters_a_shared_product_launch_without_inventing_tone() -> None:
    result = analyze_media_monitor(
        [
            {
                "title": "Google unveils Pixel Watch 5 with advanced health monitoring",
                "feed_name": "TechCrunch",
                "source_tier": "specialty",
                "published": "2026-08-12T11:00:00Z",
            },
            {
                "title": "Google Pixel Watch 5 can detect breathing emergencies",
                "feed_name": "Wired",
                "source_tier": "major",
                "published": "2026-08-12T10:55:00Z",
            },
            {
                "title": "Google Pixel Watch 5 dives deeper into AI and health",
                "feed_name": "The Verge",
                "source_tier": "specialty",
                "published": "2026-08-12T10:50:00Z",
            },
        ],
        now=datetime(2026, 8, 12, 12, tzinfo=timezone.utc),
    )

    assert result["summary"]["topic_count"] == 1
    topic = result["topics"][0]
    assert topic["mention_count"] == 3
    assert topic["heat_score"] > 0
    assert topic["attention_score"] is None
    assert topic["sentiment_counts"]["unknown"] == 3
    assert "pixel" in topic["keywords"]


def test_media_monitor_flags_divergent_source_tone() -> None:
    result = analyze_media_monitor(
        [
            {
                "title": "Peace agreement restores shipping route",
                "feed_name": "UN News",
                "source_tier": "government",
                "published": "2026-08-12T11:00:00Z",
            },
            {
                "title": "Shipping route deal faces threat of renewed attack",
                "feed_name": "Defense One",
                "source_tier": "specialty",
                "published": "2026-08-12T10:50:00Z",
            },
        ],
        now=datetime(2026, 8, 12, 12, tzinfo=timezone.utc),
    )

    topic = result["topics"][0]
    assert topic["framing_divergence"] is True
    assert topic["framing_divergence_score"] > 0
    assert result["summary"]["divergent_topic_count"] == 1
