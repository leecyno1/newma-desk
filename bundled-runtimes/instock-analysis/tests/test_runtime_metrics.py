from instock.web.runtime_metrics import ApiMetricsRegistry, metric_route


def test_metric_route_replaces_resource_ids_and_drops_query_data():
    assert metric_route("/api/v1/czsc/scans/private-scan-id") == (
        "/api/v1/czsc/scans/{scan_id}"
    )
    assert metric_route("/api/v1/analysis-snapshots/czsc:private-id") == (
        "/api/v1/analysis-snapshots/{snapshot_id}"
    )
    assert metric_route("/api/v1/analysis-history") == "/api/v1/analysis-history"
    assert metric_route("/api/v1/analysis-history/private-id") == (
        "/api/v1/analysis-history/{history_id}"
    )
    assert metric_route("/api/v1/rotations/supply-chain-research") == (
        "/api/v1/rotations/supply-chain-research"
    )
    assert metric_route("/api/v1/industry-chain/research") == (
        "/api/v1/industry-chain/research"
    )
    assert metric_route("/api/v1/market-workbench/snapshots") == (
        "/api/v1/market-workbench/snapshots"
    )
    assert metric_route("/api/v1/market-maps/snapshots") == (
        "/api/v1/market-maps/snapshots"
    )
    assert metric_route("/api/v1/technical-signals/snapshots") == (
        "/api/v1/technical-signals/snapshots"
    )
    assert metric_route("/api/v1/not-declared/300502") == "/api/v1/unmatched"


def test_api_metrics_are_bounded_aggregate_and_report_latency_percentiles():
    now = [10.0]
    registry = ApiMetricsRegistry(latency_sample_max=16, clock=lambda: now[0])

    for index, status in enumerate((200, 200, 404, 503)):
        started_at = now[0]
        now[0] += (index + 1) / 1000
        registry.record("GET", "/api/v1/czsc/scans/private-id", status, started_at)

    route = registry.stats()["routes"]["GET /api/v1/czsc/scans/{scan_id}"]
    assert route == {
        "requests": 4,
        "errors": 2,
        "server_errors": 1,
        "error_rate": 0.5,
        "status_classes": {"2xx": 2, "4xx": 1, "5xx": 1},
        "latency_ms": {"sample_size": 4, "p50": 2.0, "p95": 4.0, "max": 4.0},
    }
    assert "private-id" not in str(registry.stats())


def test_latency_samples_are_bounded_while_request_totals_are_cumulative():
    now = [0.0]
    registry = ApiMetricsRegistry(latency_sample_max=16, clock=lambda: now[0])
    for _ in range(20):
        started_at = now[0]
        now[0] += 0.001
        registry.record("GET", "/api/v1/health", 200, started_at)

    stats = registry.stats()
    route = stats["routes"]["GET /api/v1/health"]
    assert route["requests"] == 20
    assert route["latency_ms"]["sample_size"] == 16
    assert stats["latency_sample_max_per_route"] == 16
