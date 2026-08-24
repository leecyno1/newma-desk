from datetime import UTC, datetime

from vibe_visualization_api.crucix.adapter import (
    normalize_health,
    normalize_snapshot,
)


def test_snapshot_keeps_titled_evidence_and_strips_external_markup() -> None:
    payload = {
        "meta": {
            "timestamp": "2026-08-24T00:00:00Z",
            "sourcesQueried": 3,
            "sourcesOk": 2,
            "sourcesFailed": 1,
        },
        "health": [
            {"n": "GDELT", "err": False, "stale": False},
            {"n": "GSCPI", "err": False, "stale": True},
            {"n": "Telegram", "err": True, "stale": False},
        ],
        "newsFeed": [
            {
                "headline": "<b>Shipping risk rises</b>",
                "source": "GDELT",
                "type": "gdelt",
                "timestamp": "2026-08-24T00:10:00Z",
                "region": "Global",
                "url": "https://example.com/story",
            },
            {"headline": "", "source": "Category only"},
            {
                "headline": "Unsafe link",
                "source": "Telegram",
                "url": "javascript:alert(1)",
            },
        ],
        "fred": [
            {
                "id": "CPIAUCSL",
                "label": "US CPI",
                "value": 315.2,
                "date": "2026-07-01",
                "momChangePct": 0.2,
            }
        ],
        "gscpi": {
            "value": 1.25,
            "date": "2026-08-01",
            "interpretation": "Above normal pressure",
        },
        "defense": [
            {
                "recipient": "Example Corp",
                "amount": 1200000,
                "desc": "<i>Radar systems</i>",
            }
        ],
    }

    result = normalize_snapshot(
        payload,
        now=datetime(2026, 8, 24, 0, 30, tzinfo=UTC),
    )

    assert result["contract"] == "newma-desk.crucix-intelligence.v1"
    assert result["freshness"]["status"] == "fresh"
    assert result["sourceHealth"] == {
        "queried": 3,
        "ok": 2,
        "failed": 1,
        "items": [
            {"source": "GDELT", "status": "ok"},
            {"source": "GSCPI", "status": "stale"},
            {"source": "Telegram", "status": "error"},
        ],
    }
    assert [item["title"] for item in result["news"]] == [
        "Shipping risk rises",
        "Unsafe link",
    ]
    assert result["news"][0]["url"] == "https://example.com/story"
    assert "url" not in result["news"][1]
    assert result["macro"]["gscpi"]["value"] == 1.25
    assert result["global"]["defenseContracts"][0]["description"] == "Radar systems"
    assert "ideas" not in result


def test_health_marks_old_or_partial_sweep_as_degraded() -> None:
    result = normalize_health(
        {
            "status": "ok",
            "lastSweep": "2026-08-23T20:00:00Z",
            "nextSweep": "2026-08-23T21:00:00Z",
            "sourcesOk": 28,
            "sourcesFailed": 1,
            "refreshIntervalMinutes": 60,
            "sweepInProgress": False,
        },
        now=datetime(2026, 8, 24, 0, 30, tzinfo=UTC),
    )

    assert result["status"] == "degraded"
    assert result["freshness"]["status"] == "stale"
    assert result["sourceHealth"] == {"ok": 28, "failed": 1}
