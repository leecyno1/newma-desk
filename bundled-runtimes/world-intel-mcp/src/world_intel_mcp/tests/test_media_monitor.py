"""Tests for the lightweight media monitor."""

from datetime import datetime, timezone

from world_intel_mcp.analysis.media_monitor import analyze_media_monitor


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


def test_media_monitor_clusters_a_shared_product_launch_and_scores_attention() -> None:
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
    assert topic["attention_score"] >= 25
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
