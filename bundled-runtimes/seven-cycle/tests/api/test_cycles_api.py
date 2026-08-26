"""Contract tests for cycle products queried from one live catalog."""

from fastapi.testclient import TestClient

from conftest import PublishedRun, assert_row_provenance


def test_current_and_history_strictly_filter_cycle_vintage_and_model(
    client: TestClient,
    published_run: PublishedRun,
) -> None:
    parameters = {
        "cycle_ids": "C1",
        "vintage": "realtime",
        "as_of": published_run.context.as_of.isoformat(),
        "model_version": published_run.context.model_version,
    }
    current = client.get("/v1/cycles/current", params=parameters)
    history = client.get("/v1/cycles/history", params=parameters)
    unmatched = client.get("/v1/cycles/history?cycle_ids=C9")

    for response in (current, history):
        assert response.status_code == 200
        assert [
            (row["cycle_id"], row["vintage"]) for row in response.json()["data"]
        ] == [("C1", "realtime")]
        assert_row_provenance(response, published_run)
    assert unmatched.status_code == 200
    assert unmatched.json()["data"] == []


def test_forecast_strictly_filters_cycle_horizon_and_model(
    client: TestClient,
    published_run: PublishedRun,
) -> None:
    response = client.get(
        "/v1/cycles/forecast",
        params={
            "cycle_ids": "C1",
            "horizon": 12,
            "model_version": published_run.context.model_version,
        },
    )
    unmatched = client.get("/v1/cycles/forecast?horizon=24")

    assert response.status_code == 200
    assert [
        (row["cycle_id"], row["horizon_months"]) for row in response.json()["data"]
    ] == [("C1", 12)]
    assert_row_provenance(response, published_run)
    assert unmatched.status_code == 200
    assert unmatched.json()["data"] == []
