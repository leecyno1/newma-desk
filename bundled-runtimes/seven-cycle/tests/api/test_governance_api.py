"""Governance evidence and audit API contracts."""

from fastapi.testclient import TestClient
import pytest

from seven_cycle_platform.api.app import create_app
from seven_cycle_platform.api.repository import QueryResult
from seven_cycle_platform.api.routes import governance as governance_routes


def test_cycle_evidence_endpoint_filters_cycle(client: TestClient) -> None:
    response = client.get("/v1/governance/evidence?cycle_ids=C4")

    assert response.status_code == 200
    rows = response.json()["data"]
    assert [(row["cycle_id"], row["evidence_status"]) for row in rows] == [
        ("C4", "supported")
    ]
    assert rows[0]["family_centers_json"] == "[40.0,42.2]"
    assert rows[0]["family_centers"] == [40.0, 42.2]
    assert rows[0]["reason_codes_json"] == '["cross_family_consensus"]'
    assert rows[0]["reason_codes"] == ["cross_family_consensus"]


def test_cycle_evidence_filter_is_parameter_bound(client: TestClient) -> None:
    response = client.get(
        "/v1/governance/evidence",
        params={"cycle_ids": "C4' OR 1=1 --"},
    )

    assert response.status_code == 200
    assert response.json()["data"] == []
    assert response.json()["pagination"]["total"] == 0


def test_publication_endpoint_exposes_block_reason(client: TestClient) -> None:
    response = client.get("/v1/governance/publication?cycle_ids=C5")

    assert response.status_code == 200
    body = response.json()
    rows = body["data"]
    assert [row["layer"] for row in rows] == [
        "historical",
        "realtime",
        "forecast",
        "asset_statistics",
    ]
    assert {row["status"] for row in rows} == {"blocked"}
    assert all("period_unidentified" in row["reason_codes_json"] for row in rows)
    assert all(row["reason_codes"] == ["period_unidentified"] for row in rows)
    assert body["caveats"] == ["period_unidentified"]


def test_publication_endpoint_paginates_workflow_order(client: TestClient) -> None:
    response = client.get("/v1/governance/publication?cycle_ids=C5&limit=2&offset=1")

    assert response.status_code == 200
    body = response.json()
    assert [row["layer"] for row in body["data"]] == ["realtime", "forecast"]
    assert body["pagination"] == {"limit": 2, "offset": 1, "total": 4}


def test_data_identity_endpoint_reports_stale_sources(client: TestClient) -> None:
    response = client.get("/v1/governance/data-identity")

    assert response.status_code == 200
    assert any(row["freshness_status"] == "stale" for row in response.json()["data"])


def test_calibrations_endpoint_uses_standard_pagination(client: TestClient) -> None:
    response = client.get("/v1/governance/calibrations?limit=1&offset=0")

    assert response.status_code == 200
    body = response.json()
    assert [(row["subject_id"], row["version"]) for row in body["data"]] == [
        ("C4", "v4")
    ]
    assert body["pagination"] == {"limit": 1, "offset": 0, "total": 1}


@pytest.mark.parametrize(
    ("path", "expected_parameters"),
    [
        (
            "/v1/governance/evidence",
            {"as_of", "model_version", "cycle_ids", "limit", "offset"},
        ),
        (
            "/v1/governance/publication",
            {"as_of", "model_version", "cycle_ids", "limit", "offset"},
        ),
        (
            "/v1/governance/data-identity",
            {"as_of", "model_version", "limit", "offset"},
        ),
        (
            "/v1/governance/calibrations",
            {"as_of", "model_version", "limit", "offset"},
        ),
    ],
)
def test_governance_openapi_exposes_only_supported_filters(
    path: str, expected_parameters: set[str]
) -> None:
    parameters = create_app().openapi()["paths"][path]["get"]["parameters"]

    assert {parameter["name"] for parameter in parameters} == expected_parameters


@pytest.mark.parametrize(
    "path",
    [
        "/v1/governance/evidence?horizon=12",
        "/v1/governance/publication?scenario=stress",
        "/v1/governance/data-identity?cycle_ids=C4",
        "/v1/governance/calibrations?benchmark=CSI300",
    ],
)
def test_governance_endpoints_reject_unsupported_filters(
    client: TestClient, path: str
) -> None:
    response = client.get(path)

    assert response.status_code == 422
    assert response.json()["caveats"] == [
        "request parameters are invalid or unavailable for this product"
    ]


def test_malformed_governance_json_returns_catalog_error(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def malformed_result(*args, **kwargs) -> QueryResult:
        return QueryResult(
            rows=[
                {
                    "cycle_id": "C4",
                    "reason_codes_json": "not-json",
                    "family_centers_json": "[]",
                }
            ],
            total=1,
            available=True,
            view="cycle_evidence",
            primary_usage_statuses=(),
        )

    monkeypatch.setattr(governance_routes, "query_view", malformed_result)

    response = client.get("/v1/governance/evidence")

    assert response.status_code == 503
    assert response.json()["caveats"] == ["published data is temporarily unavailable"]
