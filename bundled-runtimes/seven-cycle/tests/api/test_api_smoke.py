from datetime import date, datetime, timezone
import hashlib
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from seven_cycle_platform.catalog import build_catalog, open_catalog
from seven_cycle_platform.contracts.arrow import (
    ASSET_ATTRIBUTION_SCHEMA,
    CYCLE_PHASE_VINTAGE_SCHEMA,
)
from seven_cycle_platform.products.asset_mapping_current import (
    ASSET_MAPPING_CURRENT_SCHEMA,
)
from seven_cycle_platform.products.asset_mapping_future import (
    ASSET_MAPPING_FUTURE_SCHEMA,
)
from seven_cycle_platform.products.cycle_forecast import CYCLE_FORECAST_SCHEMA
from seven_cycle_platform.products.cycle_asset_surface import CYCLE_ASSET_SURFACE_SCHEMA
from seven_cycle_platform.storage import RunContext, publish_run


APPROVED_ENDPOINTS = (
    "/v1/runs",
    "/v1/cycles/current",
    "/v1/cycles/history",
    "/v1/cycles/forecast",
    "/v1/assets",
    "/v1/assets/compare",
    "/v1/assets/asset-a/attribution",
    "/v1/assets/asset-a/mapping",
    "/v1/surfaces/cycle-asset?asset_id=asset-a&cycle_x=C1&cycle_y=C2&horizon=12",
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


def _table(schema: pa.Schema, values: dict[str, list[object]]) -> pa.Table:
    row_count = len(next(iter(values.values())))
    return pa.Table.from_arrays(
        [
            pa.array(
                values.get(field.name, [None] * row_count),
                type=field.type,
                from_pandas=True,
            )
            for field in schema
        ],
        schema=schema,
    )


def _published_catalog(tmp_path: Path):
    context = RunContext.create(
        as_of=date(2026, 6, 30),
        data_vintage=date(2026, 6, 30),
        model_version="api-smoke-v1",
        config={"api": "smoke"},
        input_checksums={"inputs/source": hashlib.sha256(b"source").hexdigest()},
        quality_summary={"checks": {"failed": 0, "passed": 4}},
        created_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
    )
    product_root = tmp_path / "products"
    catalog_root = product_root / "catalogs"

    tables = {
        "cycle_phase_vintage.parquet": _table(
            CYCLE_PHASE_VINTAGE_SCHEMA,
            {
                "date": [date(2026, 6, 30), date(2026, 6, 30)],
                "cycle_id": ["C1", "C2"],
                "vintage": ["realtime", "realtime"],
                "phase": ["expansion", "contraction"],
                "run_id": [context.run_id, context.run_id],
                "as_of": [context.as_of, context.as_of],
                "data_vintage": [context.data_vintage, context.data_vintage],
                "model_version": [context.model_version, context.model_version],
                "config_hash": [context.config_hash, context.config_hash],
                "created_at": [context.created_at, context.created_at],
            },
        ),
        "asset_attribution.parquet": _table(
            ASSET_ATTRIBUTION_SCHEMA,
            {
                "asset_id": ["asset-a", "asset-b"],
                "horizon_months": [12, 12],
                "status": ["available", "unavailable"],
                "evidence_level": ["formal", "retrospective_only"],
                "run_id": [context.run_id, context.run_id],
                "as_of": [context.as_of, context.as_of],
                "data_vintage": [context.data_vintage, context.data_vintage],
                "model_version": [context.model_version, context.model_version],
                "config_hash": [context.config_hash, context.config_hash],
                "created_at": [context.created_at, context.created_at],
            },
        ),
        "asset_mapping_current.parquet": _table(
            ASSET_MAPPING_CURRENT_SCHEMA,
            {
                "asset_id": ["asset-a", "asset-b"],
                "horizon_months": [12, 12],
                "mapping_status": ["available", "unavailable"],
                "freshness_status": ["fresh", "stale"],
                "publication_status": ["partial", "live"],
                "evidence_level": ["formal", "retrospective_only"],
                "run_id": [context.run_id, context.run_id],
                "as_of": [context.as_of, context.as_of],
                "data_vintage": [context.data_vintage, context.data_vintage],
                "model_version": [context.model_version, context.model_version],
                "created_at": [context.created_at, context.created_at],
            },
        ),
        "cycle_forecast.parquet": _table(
            CYCLE_FORECAST_SCHEMA,
            {
                "cycle_id": ["C1", "C2"],
                "horizon_months": [12, 12],
                "status": ["unavailable", "available"],
                "turning_status": ["available", "unavailable"],
                "run_id": [context.run_id, context.run_id],
                "as_of": [context.as_of, context.as_of],
                "data_vintage": [context.data_vintage, context.data_vintage],
                "model_version": [context.model_version, context.model_version],
                "config_hash": [context.config_hash, context.config_hash],
                "created_at": [context.created_at, context.created_at],
            },
        ),
        "asset_mapping_future.parquet": _table(
            ASSET_MAPPING_FUTURE_SCHEMA,
            {
                "asset_id": ["asset-a", "asset-b"],
                "horizon_months": [12, 12],
                "scenario_id": ["baseline", "stress"],
                "mapping_status": ["conditional", "available"],
                "status": ["available", "unavailable"],
                "scenario_version": ["v1", "v1"],
                "catalog_version": ["v1", "v1"],
                "scenario_config_hash": ["a" * 64, "a" * 64],
                "run_id": [context.run_id, context.run_id],
                "as_of": [context.as_of, context.as_of],
                "data_vintage": [context.data_vintage, context.data_vintage],
                "model_version": [context.model_version, context.model_version],
                "config_hash": [context.config_hash, context.config_hash],
                "created_at": [context.created_at, context.created_at],
            },
        ),
        "cycle_asset_surface.parquet": _table(
            CYCLE_ASSET_SURFACE_SCHEMA,
            {
                "asset_id": ["asset-a"],
                "asset_label": ["资产A"],
                "cycle_x": ["C1"],
                "cycle_y": ["C2"],
                "metric": ["observed_return"],
                "horizon_months": [12],
                "scenario_id": ["baseline"],
                "window_months": [60],
                "grid_size": [19],
                "status": ["not_identifiable"],
                "estimator_version": ["circular-kernel-loocv-v1"],
                "sample_count": [0],
                "identifiable": [False],
                "reason": ["样本不足"],
                "observations_json": ["[]"],
                "grid_json": ["[]"],
                "future_path_json": ['[{"label":"baseline","x":1,"y":2,"z":0.03}]'],
                "run_id": [context.run_id],
                "as_of": [context.as_of],
                "data_vintage": [context.data_vintage],
                "model_version": [context.model_version],
                "config_hash": [context.config_hash],
                "created_at": [context.created_at],
            },
        ),
    }

    def write_staging(staging_dir: Path) -> None:
        for filename, table in tables.items():
            pq.write_table(table, staging_dir / filename)

    manifest = publish_run(product_root, context, write_staging=write_staging)
    run_dir = product_root / "runs" / manifest.run_id
    catalog_root.mkdir()
    build_catalog(
        run_dir,
        catalog_root / f"{manifest.run_id}.duckdb",
        expected_manifest=manifest,
    )
    return product_root, catalog_root, manifest


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    from seven_cycle_platform.api.app import create_app

    product_root, catalog_root, _ = _published_catalog(tmp_path)
    return TestClient(create_app(product_root=product_root, catalog_root=catalog_root))


def test_health_and_spa_share_the_verified_release(tmp_path: Path) -> None:
    from seven_cycle_platform.api.app import create_app

    product_root, catalog_root, manifest = _published_catalog(tmp_path)
    web_root = tmp_path / "web"
    data_root = web_root / "data"
    data_root.mkdir(parents=True)
    (web_root / "index.html").write_text(
        "<!doctype html><title>Circle</title><div id='root'></div>",
        encoding="utf-8",
    )
    (data_root / "release.json").write_text(
        '{"status":"ready"}\n',
        encoding="utf-8",
    )

    client = TestClient(
        create_app(
            product_root=product_root,
            catalog_root=catalog_root,
            web_root=web_root,
        )
    )

    health = client.get("/healthz")
    assert health.status_code == 200
    assert health.json() == {
        "catalog": "available",
        "deployment": "disabled",
        "run_id": manifest.run_id,
        "service": "seven-cycle-platform",
        "status": "ok",
        "web": "available",
    }
    assert "Circle" in client.get("/cycles").text
    assert client.get("/data/release.json").json() == {"status": "ready"}
    missing_api = client.get("/v1/missing")
    assert missing_api.status_code == 404
    assert missing_api.json()["usage_status"] == "unavailable"


def test_health_release_verification_is_cached_and_single_flight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Lock
    from time import sleep
    from types import SimpleNamespace

    from seven_cycle_platform.api import dependencies
    from seven_cycle_platform.api.app import create_app

    product_root, catalog_root, manifest = _published_catalog(tmp_path)
    app = create_app(product_root=product_root, catalog_root=catalog_root)
    request = SimpleNamespace(app=app)
    original = dependencies._open_request_context
    calls = 0
    calls_lock = Lock()

    def counted_open(current_request):
        nonlocal calls
        with calls_lock:
            calls += 1
        sleep(0.05)
        return original(current_request)

    monkeypatch.setattr(dependencies, "_open_request_context", counted_open)
    with ThreadPoolExecutor(max_workers=8) as executor:
        contexts = list(
            executor.map(
                lambda _: dependencies.get_health_context(request),
                range(8),
            )
        )

    assert calls == 1
    assert {context.manifest.run_id for context in contexts} == {manifest.run_id}


def test_health_verifies_product_identity_and_reports_web_copy_scope(
    tmp_path: Path,
) -> None:
    from seven_cycle_platform.api.app import create_app
    from seven_cycle_platform.deployment import write_deployment_manifest

    product_root, catalog_root, manifest = _published_catalog(tmp_path)
    catalog_path = catalog_root / f"{manifest.run_id}.duckdb"
    with open_catalog(
        catalog_path,
        run_dir=product_root / "runs" / manifest.run_id,
        expected_manifest=manifest,
    ) as connection:
        catalog_checksum = connection.execute(
            "SELECT catalog_checksum FROM runs"
        ).fetchone()[0]
    web_root = tmp_path / "health-web"
    (web_root / "data").mkdir(parents=True)
    (web_root / "index.html").write_text("<title>Circle</title>", encoding="utf-8")
    _, deployment_id = write_deployment_manifest(
        product_root=product_root,
        catalog_checksum=catalog_checksum,
        run_id=manifest.run_id,
        deployment_as_of=manifest.as_of,
        web_root=web_root,
    )
    client = TestClient(
        create_app(
            product_root=product_root,
            catalog_root=catalog_root,
            web_root=web_root,
        )
    )

    healthy = client.get("/healthz").json()
    assert healthy["status"] == "ok"
    assert healthy["service"] == "seven-cycle-platform"
    assert healthy["deployment_id"] == deployment_id

    product_deployment = product_root / "deployment.json"
    web_deployment = web_root / "data" / "deployment.json"
    product_content = product_deployment.read_bytes()
    web_content = web_deployment.read_bytes()
    web_deployment.unlink()
    missing_web = client.get("/healthz").json()
    assert missing_web["status"] == "ok"
    assert missing_web["deployment"] == "available"
    assert missing_web["deployment_verification"] == "product-only"
    web_deployment.write_bytes(web_content)

    product_deployment.unlink()
    missing_product = client.get("/healthz").json()
    assert missing_product["status"] == "degraded"
    assert missing_product["deployment"] == "inconsistent"
    product_deployment.write_bytes(product_content)

    web_deployment.write_text("{}\n", encoding="utf-8")
    corrupt_web = client.get("/healthz").json()
    assert corrupt_web["status"] == "degraded"
    assert corrupt_web["deployment"] == "inconsistent"
    web_deployment.write_bytes(web_content)

    write_deployment_manifest(
        product_root=product_root,
        catalog_checksum="f" * 64,
        run_id=manifest.run_id,
        deployment_as_of=manifest.as_of,
        web_root=web_root,
    )
    assert client.get("/healthz").json()["status"] == "degraded"


@pytest.mark.parametrize(
    "path",
    APPROVED_ENDPOINTS,
)
def test_all_approved_endpoints_return_envelopes(client: TestClient, path: str) -> None:
    response = client.get(path)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, max-age=0, must-revalidate"
    assert response.headers["etag"]
    assert response.headers["x-catalog-checksum"]
    assert response.headers["x-manifest-checksum"]
    assert response.headers["x-config-hash"]
    body = response.json()
    assert {"data", "provenance", "freshness", "usage_status", "caveats"} <= body.keys()
    assert body["provenance"]["run_id"]
    assert {
        "config_hash",
        "manifest_checksum",
        "catalog_checksum",
        "quality_summary",
        "data_quality",
    } <= body["provenance"].keys()
    assert body["provenance"]["quality_summary"] == {
        "checks": {"failed": 0, "passed": 4}
    }
    assert (
        response.headers["x-catalog-checksum"] == body["provenance"]["catalog_checksum"]
    )
    assert (
        response.headers["x-manifest-checksum"]
        == body["provenance"]["manifest_checksum"]
    )
    assert response.headers["x-config-hash"] == body["provenance"]["config_hash"]


def test_filters_pagination_and_single_run_binding(client: TestClient) -> None:
    response = client.get("/v1/cycles/history?cycle_ids=C1&limit=1&offset=0")

    assert response.status_code == 200
    body = response.json()
    assert body["pagination"] == {"limit": 1, "offset": 0, "total": 1}
    assert [row["cycle_id"] for row in body["data"]] == ["C1"]
    assert {row["run_id"] for row in body["data"]} == {body["provenance"]["run_id"]}

    filtered = client.get("/v1/scenarios?scenario=baseline")
    assert filtered.status_code == 200
    assert [row["scenario_id"] for row in filtered.json()["data"]] == ["baseline"]

    forecast = client.get("/v1/cycles/forecast?horizon=12")
    assert forecast.status_code == 200
    assert [row["horizon_months"] for row in forecast.json()["data"]] == [12, 12]


def test_mapping_view_selection_and_current_partial_status(client: TestClient) -> None:
    current = client.get("/v1/assets/asset-a/mapping")
    comparison = client.get("/v1/assets/compare?limit=10")
    future_mapping = client.get("/v1/assets/asset-a/mapping?scenario=baseline")
    future_comparison = client.get("/v1/assets/compare?scenario=baseline")

    assert current.status_code == 200
    assert "scenario_id" not in current.json()["data"][0]
    assert current.json()["usage_status"] == "available"
    assert comparison.json()["pagination"] == {"limit": 10, "offset": 0, "total": 2}
    assert {row["asset_id"] for row in comparison.json()["data"]} == {
        "asset-a",
        "asset-b",
    }
    assert all(
        "current" not in row and "future" not in row
        for row in comparison.json()["data"]
    )
    assert comparison.json()["usage_status"] == "partial"

    assert future_mapping.status_code == 200
    assert [row["scenario_id"] for row in future_mapping.json()["data"]] == ["baseline"]
    assert future_mapping.json()["usage_status"] == "conditional"
    assert future_comparison.status_code == 200
    assert [row["scenario_id"] for row in future_comparison.json()["data"]] == [
        "baseline"
    ]


def test_cycle_asset_surface_returns_evidence_gated_research_product(
    client: TestClient,
) -> None:
    response = client.get(
        "/v1/surfaces/cycle-asset",
        params={
            "asset_id": "asset-a",
            "cycle_x": "C1",
            "cycle_y": "C2",
            "horizon": 12,
            "window_months": 60,
            "grid_size": 19,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body.get("pagination") is None
    assert len(body["data"]) == 1
    surface = body["data"][0]
    assert surface["asset_id"] == "asset-a"
    assert surface["cycle_x"] == "C1"
    assert surface["cycle_y"] == "C2"
    assert surface["status"] == "not_identifiable"
    assert surface["grid"] == []
    assert surface["evidence"]["identifiable"] is False
    assert surface["estimator_version"] == "circular-kernel-loocv-v1"
    assert surface["source_kind"] == "published_product"
    assert body["usage_status"] == "partial"


def test_published_historical_surface_falls_back_to_baseline_scenario(
    client: TestClient,
) -> None:
    response = client.get(
        "/v1/surfaces/cycle-asset",
        params={
            "asset_id": "asset-a",
            "cycle_x": "C1",
            "cycle_y": "C2",
            "horizon": 12,
            "scenario": "growth",
            "window_months": 60,
            "grid_size": 19,
        },
    )

    assert response.status_code == 200
    surface = response.json()["data"][0]
    assert surface["scenario_id"] == "baseline"
    assert surface["requested_scenario_id"] == "growth"
    assert surface["scenario_fallback"] is True
    assert surface["future_path"] == []
    assert surface["source_kind"] == "published_product"


def test_authoritative_status_columns_ignore_secondary_statuses(
    client: TestClient,
) -> None:
    unavailable_forecast = client.get("/v1/cycles/forecast?cycle_ids=C1")
    unavailable_future = client.get("/v1/assets/compare?scenario=stress")

    assert unavailable_forecast.status_code == 200
    assert unavailable_forecast.json()["usage_status"] == "unavailable"
    assert unavailable_future.status_code == 200
    assert unavailable_future.json()["usage_status"] == "unavailable"


def test_available_view_without_matches_is_not_unavailable(client: TestClient) -> None:
    response = client.get("/v1/assets/not-a-published-asset/mapping")

    assert response.status_code == 200
    assert response.json()["data"] == []
    assert response.json()["usage_status"] == "available"
    assert response.json()["freshness"] == "unknown"
    assert response.json()["caveats"] == ["no rows matched the requested filters"]


def test_etag_conditional_get_and_optional_product_degrade(client: TestClient) -> None:
    response = client.get("/v1/analogs")

    assert response.status_code == 200
    assert response.json()["data"] == []
    assert response.json()["usage_status"] == "unavailable"
    conditional = client.get(
        "/v1/analogs", headers={"If-None-Match": response.headers["etag"]}
    )
    assert conditional.status_code == 304
    assert (
        conditional.headers["x-catalog-checksum"]
        == response.headers["x-catalog-checksum"]
    )
    assert (
        conditional.headers["x-manifest-checksum"]
        == response.headers["x-manifest-checksum"]
    )
    assert conditional.headers["x-config-hash"] == response.headers["x-config-hash"]
    assert (
        client.get(
            "/v1/analogs",
            headers={"If-None-Match": f'"bogus", {response.headers["etag"]}'},
        ).status_code
        == 304
    )


@pytest.mark.parametrize(
    "path",
    [
        "/v1/cycles/forecast?horizon=0",
        "/v1/assets?limit=501",
        "/v1/cycles/history?offset=-1",
        "/v1/cycles/history?cycle_ids=C1,C2,C3,C4,C5,C6,C7,C8",
        "/v1/assets?asset_tier=core",
        "/v1/assets?benchmark=CSI300",
    ],
)
def test_invalid_or_unsupported_parameters_are_controlled(
    client: TestClient,
    path: str,
) -> None:
    response = client.get(path)

    assert response.status_code == 422
    assert {"data", "provenance", "freshness", "usage_status", "caveats"} <= set(
        response.json()
    )
    assert response.headers["etag"]


def test_openapi_declares_response_envelopes_for_all_approved_endpoints() -> None:
    from seven_cycle_platform.api.app import create_app

    openapi = create_app().openapi()
    for endpoint in OPENAPI_ENDPOINTS:
        responses = openapi["paths"][endpoint]["get"]["responses"]
        schema = responses["200"]["content"]["application/json"]["schema"]
        assert schema == {"$ref": "#/components/schemas/ResponseEnvelope"}
        for status_code in ("200", "304"):
            assert set(responses[status_code]["headers"]) == {
                "ETag",
                "Cache-Control",
                "X-Catalog-Checksum",
                "X-Manifest-Checksum",
                "X-Config-Hash",
            }
        for status_code in ("404", "422", "503"):
            error_schema = responses[status_code]["content"]["application/json"][
                "schema"
            ]
            assert error_schema == {"$ref": "#/components/schemas/ResponseEnvelope"}


def test_not_found_keeps_http_status_and_uses_redacted_envelope(
    client: TestClient,
) -> None:
    response = client.get("/v1/not-a-route")

    assert response.status_code == 404
    assert response.json()["caveats"] == ["requested endpoint was not found"]


class _CloseSpyConnection:
    def __init__(self, connection: object) -> None:
        self._connection = connection
        self.close_count = 0

    def close(self) -> None:
        self.close_count += 1
        self._connection.close()

    def __getattr__(self, name: str) -> object:
        return getattr(self._connection, name)


def test_request_connection_closes_for_normal_304_and_route_error(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from seven_cycle_platform.api import dependencies
    from seven_cycle_platform.api.routes import runs

    original_open_catalog = dependencies.open_catalog
    connections: list[_CloseSpyConnection] = []

    def spy_open_catalog(*args: object, **kwargs: object) -> _CloseSpyConnection:
        connection = _CloseSpyConnection(original_open_catalog(*args, **kwargs))
        connections.append(connection)
        return connection

    monkeypatch.setattr(dependencies, "open_catalog", spy_open_catalog)
    normal = client.get("/v1/runs")
    not_modified = client.get(
        "/v1/runs", headers={"If-None-Match": normal.headers["etag"]}
    )
    monkeypatch.setattr(
        runs,
        "query_view",
        lambda *args, **kwargs: (_ for _ in ()).throw(HTTPException(status_code=422)),
    )
    failed = client.get("/v1/runs")

    assert normal.status_code == 200
    assert not_modified.status_code == 304
    assert failed.status_code == 422
    assert [connection.close_count for connection in connections] == [1, 1, 1]


def test_metadata_failure_closes_open_connection_before_yield(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from seven_cycle_platform.api import dependencies

    class BadMetadataConnection:
        def close(self) -> None:
            pass

        def execute(self, query: str) -> "BadMetadataConnection":
            return self

        def fetchall(self) -> list[tuple[str]]:
            return [("only_catalog_checksum",)]

    connection = _CloseSpyConnection(BadMetadataConnection())
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                product_root=tmp_path / "products",
                catalog_root=tmp_path / "catalogs",
            )
        )
    )
    monkeypatch.setattr(dependencies, "_require_real_directory", lambda path: None)
    monkeypatch.setattr(dependencies, "_require_regular_file", lambda path: None)
    monkeypatch.setattr(dependencies, "_read_latest_run_id", lambda root: "run-id")
    monkeypatch.setattr(dependencies, "load_manifest", lambda path: object())
    monkeypatch.setattr(
        dependencies, "verify_manifest", lambda path, expected: expected
    )
    monkeypatch.setattr(
        dependencies, "open_catalog", lambda *args, **kwargs: connection
    )

    generator = dependencies.get_request_context(request)
    with pytest.raises(HTTPException):
        next(generator)
    assert connection.close_count == 1


def test_cli_serve_parser_defaults_and_paths() -> None:
    from seven_cycle_platform.cli import handle_serve, parse_args

    defaults = parse_args(["serve"])
    explicit = parse_args(
        [
            "serve",
            "--host",
            "127.0.0.2",
            "--port",
            "9010",
            "--product-root",
            "local/products",
            "--catalog-root",
            "local/catalogs",
        ]
    )

    assert defaults.host == "127.0.0.1"
    assert defaults.port == 8008
    assert defaults.handler is handle_serve
    assert explicit.host == "127.0.0.2"
    assert explicit.port == 9010
    assert explicit.product_root == Path("local/products")
    assert explicit.catalog_root == Path("local/catalogs")


@pytest.mark.parametrize("port", [1, 65535])
def test_cli_serve_accepts_port_boundaries(port: int) -> None:
    from seven_cycle_platform.cli import parse_args

    assert parse_args(["serve", "--port", str(port)]).port == port


@pytest.mark.parametrize("port", ["0", "65536", "not-a-number"])
def test_cli_serve_rejects_invalid_ports(port: str) -> None:
    from seven_cycle_platform.cli import parse_args

    with pytest.raises(SystemExit) as error_info:
        parse_args(["serve", "--port", port])

    assert error_info.value.code == 2


def test_cli_serve_help_keeps_port_usage_compact(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from seven_cycle_platform.cli import parse_args

    with pytest.raises(SystemExit) as error_info:
        parse_args(["serve", "--help"])

    help_text = capsys.readouterr().out
    assert error_info.value.code == 0
    assert "--port PORT" in help_text
    assert len(help_text) < 2_000
    assert "{1,2,3" not in help_text


def test_cli_serve_wraps_regular_startup_exceptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import uvicorn

    from seven_cycle_platform import cli

    monkeypatch.setattr(
        uvicorn,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("startup failed")),
    )

    with pytest.raises(cli.CLIError, match="local API could not start"):
        cli.handle_serve(cli.parse_args(["serve"]))
