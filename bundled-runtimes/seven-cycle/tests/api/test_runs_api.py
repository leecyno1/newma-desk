"""Contracts for the immutable published-run endpoint and public OpenAPI."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from conftest import PublishedRun, assert_row_provenance
from seven_cycle_platform.api.app import create_app


APPROVED_ENDPOINTS = (
    "/v1/runs",
    "/v1/cycles/current",
    "/v1/cycles/history",
    "/v1/cycles/forecast",
    "/v1/assets",
    "/v1/assets/compare",
    "/v1/assets/asset-valid/attribution",
    "/v1/assets/asset-valid/mapping",
    "/v1/surfaces/cycle-asset?asset_id=asset-valid&cycle_x=C1&cycle_y=C2&horizon=12",
    "/v1/analogs",
    "/v1/scenarios",
    "/v1/governance/evidence",
    "/v1/governance/publication",
    "/v1/governance/data-identity",
    "/v1/governance/calibrations",
)
OPENAPI_ENDPOINTS = (
    "/v1/runs",
    "/v1/cycles/current",
    "/v1/cycles/history",
    "/v1/cycles/forecast",
    "/v1/assets",
    "/v1/assets/compare",
    "/v1/assets/{asset_id}/attribution",
    "/v1/assets/{asset_id}/mapping",
    "/v1/surfaces/cycle-asset",
    "/v1/analogs",
    "/v1/scenarios",
    "/v1/governance/evidence",
    "/v1/governance/publication",
    "/v1/governance/data-identity",
    "/v1/governance/calibrations",
)
CHECKSUM_HEADERS = {
    "ETag",
    "Cache-Control",
    "X-Catalog-Checksum",
    "X-Manifest-Checksum",
    "X-Config-Hash",
}
CHECKSUM_HEADER_NAMES = {header.casefold() for header in CHECKSUM_HEADERS}
SNAPSHOT_PATH = Path(__file__).parent / "snapshots" / "openapi-v1.json"


def _stable_openapi() -> str:
    return (
        json.dumps(
            create_app().openapi(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def test_runs_returns_only_live_run_with_consistent_provenance(
    client: TestClient,
    published_run: PublishedRun,
) -> None:
    response = client.get("/v1/runs?limit=1&offset=0")

    assert response.status_code == 200
    assert response.json()["pagination"] == {"limit": 1, "offset": 0, "total": 1}
    assert_row_provenance(response, published_run)


def test_runs_filters_objective_live_run_metadata(
    client: TestClient,
    published_run: PublishedRun,
) -> None:
    matched = client.get(
        "/v1/runs",
        params={
            "as_of": published_run.context.as_of.isoformat(),
            "model_version": published_run.context.model_version,
        },
    )
    unmatched = client.get("/v1/runs?model_version=not-the-live-run")

    assert matched.status_code == 200
    assert [row["run_id"] for row in matched.json()["data"]] == [
        published_run.context.run_id
    ]
    assert unmatched.status_code == 200
    assert unmatched.json()["data"] == []
    assert unmatched.json()["caveats"] == ["no rows matched the requested filters"]


@pytest.mark.parametrize("path", APPROVED_ENDPOINTS)
def test_every_approved_endpoint_has_200_304_and_checksum_headers(
    client: TestClient,
    published_run: PublishedRun,
    path: str,
) -> None:
    response = client.get(path)
    not_modified = client.get(path, headers={"If-None-Match": response.headers["etag"]})

    assert response.status_code == 200
    assert CHECKSUM_HEADER_NAMES <= {header.casefold() for header in response.headers}
    assert not_modified.status_code == 304
    assert CHECKSUM_HEADER_NAMES <= {
        header.casefold() for header in not_modified.headers
    }
    assert_row_provenance(response, published_run)


def test_openapi_snapshot_and_declared_error_envelopes() -> None:
    openapi = create_app().openapi()

    assert SNAPSHOT_PATH.read_text() == _stable_openapi()
    for endpoint in OPENAPI_ENDPOINTS:
        responses = openapi["paths"][endpoint]["get"]["responses"]
        assert responses["200"]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/ResponseEnvelope"
        }
        for status_code in ("200", "304"):
            assert set(responses[status_code]["headers"]) == CHECKSUM_HEADERS
        for status_code in ("404", "422", "503"):
            assert responses[status_code]["content"]["application/json"]["schema"] == {
                "$ref": "#/components/schemas/ResponseEnvelope"
            }


@pytest.mark.parametrize(
    ("path", "status_code", "caveat"),
    [
        ("/v1/not-a-route", 404, "requested endpoint was not found"),
        (
            "/v1/cycles/history?limit=501",
            422,
            "request parameters are invalid or unavailable for this product",
        ),
    ],
)
def test_controlled_client_errors_keep_the_redacted_envelope(
    client: TestClient,
    path: str,
    status_code: int,
    caveat: str,
) -> None:
    response = client.get(path)

    assert response.status_code == status_code
    assert response.json() == {
        "data": [],
        "provenance": {},
        "freshness": "unavailable",
        "usage_status": "unavailable",
        "caveats": [caveat],
    }


def test_unavailable_publication_uses_redacted_503_envelope(tmp_path: Path) -> None:
    with TestClient(
        create_app(product_root=tmp_path / "missing")
    ) as unavailable_client:
        response = unavailable_client.get("/v1/runs")

    assert response.status_code == 503
    assert response.json() == {
        "data": [],
        "provenance": {},
        "freshness": "unavailable",
        "usage_status": "unavailable",
        "caveats": ["published data is temporarily unavailable"],
    }
