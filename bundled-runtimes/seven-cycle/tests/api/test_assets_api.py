"""Contract tests for asset products queried from one live catalog."""

from fastapi.testclient import TestClient

from conftest import PublishedRun, assert_row_provenance


def test_assets_and_attribution_strictly_filter_horizon_and_model(
    client: TestClient,
    published_run: PublishedRun,
) -> None:
    attribution = client.get(
        "/v1/assets/asset-valid/attribution",
        params={"horizon": 12, "model_version": published_run.context.model_version},
    )
    unmatched = client.get(
        "/v1/assets/asset-valid/attribution?model_version=not-the-live-run"
    )

    assert attribution.status_code == 200
    assert [
        (row["asset_id"], row["horizon_months"]) for row in attribution.json()["data"]
    ] == [("asset-valid", 12)]
    assert_row_provenance(attribution, published_run)
    assert unmatched.status_code == 200
    assert unmatched.json()["data"] == []


def test_assets_are_sorted_paginated_and_reject_unsupported_filters(
    client: TestClient,
    published_run: PublishedRun,
) -> None:
    full = client.get("/v1/assets?limit=10")
    page = client.get("/v1/assets?limit=1&offset=0")
    unsupported = client.get("/v1/assets?asset_tier=core")

    assert full.status_code == 200
    assert [row["asset_id"] for row in full.json()["data"]] == [
        "asset-failed",
        "asset-valid",
    ]
    assert full.json()["pagination"] == {"limit": 10, "offset": 0, "total": 2}
    assert page.status_code == 200
    assert [row["asset_id"] for row in page.json()["data"]] == ["asset-failed"]
    assert page.json()["pagination"] == {"limit": 1, "offset": 0, "total": 2}
    assert_row_provenance(full, published_run)
    assert unsupported.status_code == 422
    assert unsupported.json()["caveats"] == [
        "request parameters are invalid or unavailable for this product"
    ]


def test_analogs_strictly_filter_live_metadata_and_paginate(
    client: TestClient,
    published_run: PublishedRun,
) -> None:
    response = client.get(
        "/v1/analogs",
        params={
            "as_of": published_run.context.as_of.isoformat(),
            "model_version": published_run.context.model_version,
            "limit": 1,
        },
    )
    unmatched = client.get("/v1/analogs?model_version=not-the-live-run")

    assert response.status_code == 200
    assert response.json()["pagination"] == {"limit": 1, "offset": 0, "total": 2}
    assert [
        (row["historical_date"], row["analog_rank"]) for row in response.json()["data"]
    ] == [("2025-01-31", 2)]
    assert_row_provenance(response, published_run)
    assert unmatched.status_code == 200
    assert unmatched.json()["data"] == []


def test_current_mapping_keeps_valid_and_failed_assets_with_objective_status(
    client: TestClient,
    published_run: PublishedRun,
) -> None:
    response = client.get(
        "/v1/assets/compare",
        params={"horizon": 12, "model_version": published_run.context.model_version},
    )

    assert response.status_code == 200
    assert {row["asset_id"] for row in response.json()["data"]} == {
        "asset-valid",
        "asset-failed",
    }
    failed = next(
        row for row in response.json()["data"] if row["asset_id"] == "asset-failed"
    )
    assert failed["mapping_status"] == "unavailable"
    assert failed["publication_status"] == "partial"
    assert failed["publication_reason_codes"] == "ASSET_SOURCE_FAILED"
    assert response.json()["usage_status"] == "partial"
    assert response.json()["freshness"] == "stale"
    assert_row_provenance(response, published_run)


def test_current_and_future_mappings_do_not_cross_scenarios_or_horizons(
    client: TestClient,
    published_run: PublishedRun,
) -> None:
    current = client.get("/v1/assets/asset-valid/mapping?horizon=3")
    future = client.get("/v1/assets/asset-valid/mapping?scenario=baseline&horizon=12")
    comparison = client.get("/v1/assets/compare?scenario=baseline&horizon=3")
    unmatched = client.get("/v1/assets/asset-valid/mapping?scenario=missing")

    assert [
        (row["asset_id"], row["horizon_months"]) for row in current.json()["data"]
    ] == [("asset-valid", 3)]
    assert [
        (row["scenario_id"], row["horizon_months"]) for row in future.json()["data"]
    ] == [("baseline", 12)]
    assert [
        (row["scenario_id"], row["horizon_months"]) for row in comparison.json()["data"]
    ] == [("baseline", 3)]
    assert unmatched.status_code == 200
    assert unmatched.json()["data"] == []
    assert_row_provenance(current, published_run)
    assert_row_provenance(future, published_run)


def test_scenarios_strictly_filter_the_live_scenario_and_model(
    client: TestClient,
    published_run: PublishedRun,
) -> None:
    response = client.get(
        "/v1/scenarios",
        params={
            "scenario": "baseline",
            "model_version": published_run.context.model_version,
        },
    )
    unmatched = client.get("/v1/scenarios?scenario=missing")

    assert response.status_code == 200
    assert {row["scenario_id"] for row in response.json()["data"]} == {"baseline"}
    assert_row_provenance(response, published_run)
    assert unmatched.status_code == 200
    assert unmatched.json()["data"] == []
