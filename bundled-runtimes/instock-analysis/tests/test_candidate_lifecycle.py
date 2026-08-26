from instock.core.selection.candidate_lifecycle import enrich_candidate_lifecycle


def _payload(as_of, rows):
    return {
        "as_of": as_of,
        "candidates": [
            {"symbol": symbol, "rank": rank, "score": score}
            for symbol, rank, score in rows
        ],
    }


def test_candidate_lifecycle_tracks_continuing_returned_and_new_candidates():
    history = [
        {"as_of": "2026-08-15", "payload": _payload(
            "2026-08-15", [("000001", 1, 70), ("000003", 2, 60)]
        )},
        {"as_of": "2026-08-14", "payload": _payload(
            "2026-08-14", [("000001", 2, 65), ("000002", 1, 72)]
        )},
    ]
    current = _payload(
        "2026-08-16",
        [("000001", 2, 68), ("000002", 1, 75), ("000004", 3, 58)],
    )

    result = enrich_candidate_lifecycle(current, history)
    rows = {item["symbol"]: item["lifecycle"] for item in result["candidates"]}

    assert result["candidate_lifecycle"] == {
        "schema_version": "2.0",
        "comparison_scope": "same_candidate_configuration",
        "semantics": "observed_candidate_history_not_return_backtest",
        "observation_count": 3,
        "first_as_of": "2026-08-14",
        "latest_as_of": "2026-08-16",
        "previous_as_of": "2026-08-15",
        "summary": {"new": 1, "continuing": 1, "returned": 1},
    }
    assert rows["000001"]["state"] == "continuing"
    assert rows["000001"]["observed_periods"] == 3
    assert rows["000001"]["consecutive_observations"] == 3
    assert rows["000001"]["rank_change"] == -1
    assert rows["000001"]["score_change"] == -2
    assert rows["000002"]["state"] == "returned"
    assert rows["000002"]["first_seen_as_of"] == "2026-08-14"
    assert rows["000002"]["previous_rank"] is None
    assert rows["000004"]["state"] == "new"


def test_candidate_lifecycle_replaces_same_day_history_with_current_result():
    history = [{
        "as_of": "2026-08-16",
        "payload": _payload("2026-08-16", [("000001", 3, 50)]),
    }]
    current = _payload("2026-08-16", [("000001", 1, 80)])

    result = enrich_candidate_lifecycle(current, history)

    assert result["candidate_lifecycle"]["observation_count"] == 1
    assert result["candidates"][0]["lifecycle"]["state"] == "new"
    assert result["candidates"][0]["lifecycle"]["previous_score"] is None


def test_candidate_lifecycle_only_compares_same_candidate_configuration():
    parameters = {
        "market": "CN",
        "universeMode": "quick",
        "universeSize": 30,
        "outputSize": 10,
        "bars": 120,
        "profile": "balanced",
        "filters": {"industries": []},
    }
    history = [
        {
            "parameters": parameters,
            "payload": _payload("2026-08-15", [("000001", 2, 65)]),
        },
        {
            "parameters": {**parameters, "profile": "trend"},
            "payload": _payload("2026-08-14", [("000002", 1, 75)]),
        },
        {
            "parameters": {},
            "payload": _payload("2026-08-13", [("000003", 1, 80)]),
        },
    ]

    result = enrich_candidate_lifecycle(
        _payload("2026-08-16", [("000001", 1, 70)]),
        history,
        parameters=parameters,
    )

    assert result["candidate_lifecycle"]["observation_count"] == 2
    assert result["candidate_lifecycle"]["first_as_of"] == "2026-08-15"
    assert result["candidates"][0]["lifecycle"]["state"] == "continuing"
