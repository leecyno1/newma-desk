import subprocess
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from scripts import newma_release_check as release_check

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "newma_release_check.py"
WORKFLOW = ROOT / ".github" / "workflows" / "newma-mod-release.yml"


def test_offline_release_plan_contains_no_docker_commands():
    checks = release_check._process_checks(ROOT, str(ROOT / ".venv" / "bin" / "python"))
    commands = [" ".join(check.command).lower() for check in checks]

    assert {check.name for check in checks} == {
        "python-tests", "python-dependencies", "python-compile",
        "python-native-runtime", "bridge-javascript", "git-diff",
    }
    assert not any("docker" in command for command in commands)


def test_live_local_http_probes_bypass_system_proxy_settings(monkeypatch):
    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            body = json.dumps({"ok": True}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):  # noqa: A002
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:1")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    try:
        status, payload = release_check._request_json(
            f"http://127.0.0.1:{server.server_port}/health", timeout=5
        )
        assert status == 200
        assert payload["ok"] is True
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_newma_release_plan_uses_native_compiler_and_certification():
    newma = ROOT.parent / "newma-desk"
    checks = release_check._newma_checks(ROOT, newma)
    by_name = {check.name: check for check in checks}

    assert "loadModStore" in " ".join(by_name["newma-suite-compiler"].command)
    assert "checkModManifest" in " ".join(by_name["newma-suite-compiler"].command)
    assert "DataServiceDescriptor.model_validate" in " ".join(
        by_name["newma-data-service-descriptor"].command
    )
    descriptor_contract = " ".join(by_name["newma-data-service-descriptor"].command)
    assert "descriptor.model_dump_json" not in descriptor_contract
    assert "'capabilities': sorted(descriptor.capabilities)" in descriptor_contract
    runtime_contract = " ".join(by_name["newma-data-service-runtime-contracts"].command)
    assert "DataServiceClient" in runtime_contract
    for capability_id in (
        "analysis.czsc", "analysis.czsc.scan", "analysis.rotation",
        "analysis.rotation.experiment", "analysis.industry-chain",
        "analysis.stock-candidates", "analysis.stock-research",
        "analysis.strategy-validation",
        "analysis.event-flow",
        "analysis.research-book",
        "analysis.market-workbench",
        "analysis.market-map",
        "analysis.technical-signals",
    ):
        assert capability_id in runtime_contract
    assert "mods:theme:check" in " ".join(by_name["newma-theme"].command)
    stack_status = by_name["newma-core-stack-status"]
    assert stack_status.command == ("npm", "run", "dev:status")
    assert stack_status.warn_on_miss is True
    assert "instock-czsc,instock-rotation" in by_name["newma-level-two-certification"].command
    assert not any("docker" in " ".join(check.command).lower() for check in checks)


def test_optional_newma_runtime_miss_is_reported_without_blocking_release(monkeypatch, tmp_path):
    def completed(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout=(
                "OK   Newma-Desk http://127.0.0.1:5888/\n"
                "MISS Deepsee http://127.0.0.1:8001/api/health · timeout\n"
                "Newma-Desk 核心可用；部分可选或外部 Mod 当前处于降级状态。"
            ),
        )

    monkeypatch.setattr(release_check.subprocess, "run", completed)
    result = release_check._run_process(release_check.ProcessCheck(
        "newma-core-stack-status",
        ("npm", "run", "dev:status"),
        tmp_path,
        warn_on_miss=True,
    ))

    assert result.status == "passed"
    assert result.warnings == [
        "MISS Deepsee http://127.0.0.1:8001/api/health · timeout"
    ]


def test_optional_frontend_miss_can_return_nonzero_without_blocking_release(monkeypatch, tmp_path):
    def completed(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=1,
            stdout=(
                "OK   Newma-Desk API http://127.0.0.1:8911/api/health\n"
                "OK   InStock Analysis http://127.0.0.1:9988/api/v1/health\n"
                "MISS Newma-Desk http://127.0.0.1:5888/ · fetch failed"
            ),
        )

    monkeypatch.setattr(release_check.subprocess, "run", completed)
    result = release_check._run_process(release_check.ProcessCheck(
        "newma-core-stack-status", ("npm", "run", "dev:status"), tmp_path,
        warn_on_miss=True,
    ))

    assert result.status == "passed"
    assert result.warnings == [
        "MISS Newma-Desk http://127.0.0.1:5888/ · fetch failed"
    ]


def test_market_breadth_normalization_is_kept_out_of_release_failure_logic():
    # Live market breadth and industry snapshots can be temporarily unavailable;
    # the release checker treats that condition as a warning after core routes,
    # provenance and candidate extraction have passed.
    source = SCRIPT.read_text("utf-8")

    assert 'warnings.append("Desk aggregate market breadth is currently unavailable")' in source
    assert 'errors.append("rotation returned no successful ETF candidates")' in source
    assert 'attached runtime leaked /instock/data' in source


def test_stock_candidate_release_gate_requires_financial_coverage_and_factors():
    source = SCRIPT.read_text("utf-8")

    assert 'errors.append("stock-candidates live analysis returned partial data")' in source
    assert 'errors.append("stock-candidates returned no available Desk financial snapshot")' in source
    assert 'if not {"quality", "growth"}.issubset(candidate_factors):' in source
    assert 'errors.append("stock-candidates factor model omitted quality or growth")' in source


def test_live_health_contract_requires_certified_analysis_dependencies():
    ready_dependencies = {
        package: {
            "required_version": version,
            "installed_version": version,
            "status": "ready",
        }
        for package, version in release_check.EXPECTED_HEALTH_DEPENDENCIES.items()
    }
    payload = {
        "ok": True,
        "data": {
            "status": "ok",
            "runtime": {
                "mode": "newma-desk-attached",
                "instance": {"id": "a" * 32, "started_at": "2026-08-05T10:00:00+08:00"},
                "state": {
                    "cleared_on_restart": False,
                    "volatile_state_cleared_on_restart": True,
                    "analysis_snapshots": {"volatile": True},
                    "analysis_history": {
                        "storage": "sqlite",
                        "volatile": False,
                        "cleared_on_restart": False,
                    },
                    "sector_fund_flow_history": {
                        "storage": "sqlite",
                        "volatile": False,
                        "cleared_on_restart": False,
                    },
                    "czsc_scans": {"volatile": True},
                    "rotation_snapshots": {"volatile": True},
                    "rotation_experiments": {"volatile": True},
                    "api_requests": {
                        "volatile": True,
                        "route_labels": "fixed_templates",
                        "totals": {"requests": 0},
                        "routes": {},
                    },
                },
            },
            "readiness": {
                "status": "ready",
                "analysis_dependencies": True,
                "market_data": True,
                "distribution_metadata": True,
                "native_runtime": {"status": "ready", "isolation": "subprocess"},
            },
            "market_data": {"status": "ready", "provider": "newma-desk"},
            "dependencies": ready_dependencies,
        },
    }

    assert release_check._health_contract_errors(200, payload) == []

    payload["data"]["dependencies"]["czsc"] = {
        "required_version": "0.10.12",
        "installed_version": "0.10.11",
        "status": "version_mismatch",
    }
    errors = release_check._health_contract_errors(200, payload)
    assert "health dependency czsc is not ready" in errors
    assert any("runtime=0.10.11, certified=0.10.12" in error for error in errors)


def test_live_health_contract_requires_ready_desk_market_data():
    payload = {
        "ok": True,
        "data": {
            "status": "ok",
            "runtime": {
                "mode": "newma-desk-attached",
                "instance": {"id": "a" * 32, "started_at": "2026-08-05T10:00:00+08:00"},
                "state": {
                    "cleared_on_restart": False,
                        "volatile_state_cleared_on_restart": True,
                    "analysis_snapshots": {"volatile": True},
                    "analysis_history": {"storage": "sqlite", "volatile": False, "cleared_on_restart": False},
                    "sector_fund_flow_history": {"storage": "sqlite", "volatile": False, "cleared_on_restart": False},
                    "czsc_scans": {"volatile": True},
                    "rotation_snapshots": {"volatile": True},
                    "rotation_experiments": {"volatile": True},
                    "api_requests": {
                        "volatile": True,
                        "route_labels": "fixed_templates",
                        "totals": {"requests": 0},
                        "routes": {},
                    },
                },
            },
            "readiness": {
                "status": "ready",
                "analysis_dependencies": True,
                "market_data": False,
                "distribution_metadata": True,
                "native_runtime": {"status": "ready", "isolation": "subprocess"},
            },
            "market_data": {"status": "unavailable", "provider": "newma-desk"},
            "dependencies": {
                package: {"installed_version": version, "status": "ready"}
                for package, version in release_check.EXPECTED_HEALTH_DEPENDENCIES.items()
            },
        },
    }

    errors = release_check._health_contract_errors(200, payload)
    assert "health Desk market data is not ready" in errors
    assert "health Desk market data probe is unavailable" in errors


def test_live_health_contract_rejects_high_cardinality_metric_labels():
    payload = {
        "ok": True,
        "data": {
            "status": "ok",
            "runtime": {
                "mode": "newma-desk-attached",
                "instance": {"id": "a" * 32, "started_at": "2026-08-05T10:00:00+08:00"},
                "state": {
                    "cleared_on_restart": False,
                    "volatile_state_cleared_on_restart": True,
                    "analysis_snapshots": {"volatile": True},
                    "analysis_history": {"storage": "sqlite", "volatile": False, "cleared_on_restart": False},
                    "sector_fund_flow_history": {"storage": "sqlite", "volatile": False, "cleared_on_restart": False},
                    "czsc_scans": {"volatile": True},
                    "rotation_snapshots": {"volatile": True},
                    "rotation_experiments": {"volatile": True},
                    "api_requests": {
                        "volatile": True,
                        "route_labels": "fixed_templates",
                        "totals": {"requests": 1},
                        "routes": {
                            "GET /api/v1/czsc/scans/private-id": {
                                "latency_ms": {"sample_size": 1}
                            }
                        },
                    },
                },
            },
            "readiness": {
                "status": "ready",
                "analysis_dependencies": True,
                "market_data": True,
                "distribution_metadata": True,
                "native_runtime": {"status": "ready", "isolation": "subprocess"},
            },
            "market_data": {"status": "ready", "provider": "newma-desk"},
            "dependencies": {
                package: {
                    "installed_version": version,
                    "status": "ready",
                }
                for package, version in release_check.EXPECTED_HEALTH_DEPENDENCIES.items()
            },
        },
    }

    errors = release_check._health_contract_errors(200, payload)
    assert any("not a fixed template" in error for error in errors)


def test_live_health_contract_accepts_industry_chain_and_legacy_metric_routes():
    assert "/api/v1/industry-chain/research" in (
        release_check.EXPECTED_API_METRIC_ROUTES
    )
    assert "/api/v1/rotations/supply-chain-research" in (
        release_check.EXPECTED_API_METRIC_ROUTES
    )
    assert "/api/v1/stock-candidates/snapshots" in (
        release_check.EXPECTED_API_METRIC_ROUTES
    )
    assert "/api/v1/stock-research/dossiers" in (
        release_check.EXPECTED_API_METRIC_ROUTES
    )
    assert "/api/v1/strategy-validations" in (
        release_check.EXPECTED_API_METRIC_ROUTES
    )
    assert "/api/v1/event-flows" in release_check.EXPECTED_API_METRIC_ROUTES
    assert "/api/v1/research-books" in release_check.EXPECTED_API_METRIC_ROUTES
    assert "/api/v1/market-workbench/snapshots" in release_check.EXPECTED_API_METRIC_ROUTES
    assert "/api/v1/market-maps/snapshots" in release_check.EXPECTED_API_METRIC_ROUTES
    assert "/api/v1/technical-signals/snapshots" in release_check.EXPECTED_API_METRIC_ROUTES
    assert "/api/v1/analysis-history" in release_check.EXPECTED_API_METRIC_ROUTES
    assert "/api/v1/analysis-history/{history_id}" in release_check.EXPECTED_API_METRIC_ROUTES


def test_live_contract_reports_non_object_suite_discovery_without_crashing(monkeypatch):
    responses = iter([
        (200, {
            "ok": True,
            "data": {
                "status": "ok",
                "runtime": {
                    "mode": "newma-desk-attached",
                    "instance": {"id": "a" * 32, "started_at": "2026-08-05T10:00:00+08:00"},
                    "state": {
                        "cleared_on_restart": False,
                    "volatile_state_cleared_on_restart": True,
                        "analysis_snapshots": {"volatile": True},
                        "analysis_history": {"storage": "sqlite", "volatile": False, "cleared_on_restart": False},
                        "sector_fund_flow_history": {"storage": "sqlite", "volatile": False, "cleared_on_restart": False},
                        "czsc_scans": {"volatile": True},
                        "rotation_snapshots": {"volatile": True},
                        "rotation_experiments": {"volatile": True},
                        "api_requests": {
                            "volatile": True, "route_labels": "fixed_templates",
                            "totals": {"requests": 0}, "routes": {},
                        },
                    },
                },
                "readiness": {
                    "status": "ready", "analysis_dependencies": True,
                    "market_data": True,
                    "distribution_metadata": True,
                    "native_runtime": {"status": "ready", "isolation": "subprocess"},
                },
                "market_data": {"status": "ready", "provider": "newma-desk"},
                "dependencies": {
                    package: {"installed_version": version, "status": "ready"}
                    for package, version in release_check.EXPECTED_HEALTH_DEPENDENCIES.items()
                },
            },
        }),
        (200, "temporary upstream response"),
        (200, {"ok": True, "data": {"snapshot": {"provenance": {
            "provider": "newma-desk", "adjust": "qfq", "upstream_source": "fixture",
        }}}}),
        (200, {"ok": True, "data": {
            "successful_count": 1, "market_breadth": {"state": "available"},
        }}),
        (200, {"ok": True, "data": {
            "engine": {"name": "instock-market-workbench"},
            "coverage": {"successful_boards": 5},
        }}),
        (200, {"ok": True, "data": {
            "engine": {"name": "instock-market-map"},
            "coverage": {"displayed_securities": 100},
        }}),
        (200, {"ok": True, "data": {
            "engine": {"name": "instock-stock-candidate-engine"},
            "coverage": {"analyzed_count": 1},
        }}),
        (200, {"ok": True, "data": {
            "engine": {"name": "instock-technical-signal-center"},
            "data_state": "complete",
            "coverage": {
                "eligible_count": 1,
                "analyzed_count": 1,
                "failed_count": 0,
                "short_history_watch_count": 0,
            },
            "short_history_watchlist": [],
            "catalog": {"strategies": [{}] * 10},
        }}),
        (200, {"ok": True, "data": {
            "engine": {"name": "instock-stock-research-dossier"},
            "identity": {"symbol": "300502"},
            "snapshot": {"snapshot_id": "instock-stock-research-dossier:fixture"},
        }}),
    ])
    monkeypatch.setattr(release_check, "_request_json", lambda *args, **kwargs: next(responses))
    monkeypatch.setattr(release_check, "_request_status", lambda *args, **kwargs: 200)
    monkeypatch.setattr(release_check, "_request_json_post", lambda *args, **kwargs: (
        200, {"ok": True, "data": {"engine": {"name": "instock-industry-chain-research"}, "summary": {"chain_node_count": 1}}},
    ))

    result = release_check._live_contract_check("http://127.0.0.1:9988")

    assert result.status == "failed"
    assert "suite discovery returned a non-object payload" in result.detail


def test_release_report_records_source_provenance(tmp_path):
    target = tmp_path / "release.json"

    release_check._write_report(target, [release_check.CheckResult(
        name="fixture", status="passed", duration_seconds=0.01,
    )])
    payload = json.loads(target.read_text("utf-8"))

    assert payload["suite_version"] == "0.17.0"
    assert payload["generated_at"].endswith("+00:00")
    assert payload["source"]["repository"] == "https://github.com/myhhub/stock.git"
    assert len(payload["source"]["head"]) == 40
    assert len(payload["source"]["upstream_head"]) == 40
    expected_dirty = bool(subprocess.run(
        ("git", "status", "--porcelain"),
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        check=True,
    ).stdout.strip())
    assert payload["source"]["worktree_dirty"] is expected_dirty
    assert payload["source"]["untracked_delivery_files"] == (
        release_check._untracked_delivery_files(ROOT)
    )


def test_untracked_delivery_parser_ignores_runtime_artifacts(monkeypatch):
    monkeypatch.setattr(
        release_check,
        "_git_output",
        lambda *args: (
            "?? instock/core/new_feature.py\n"
            "?? tests/test_new_feature.py\n"
            "?? output/playwright/review.png\n"
            "?? .playwright-cli/page.yml\n"
        ),
    )

    assert release_check._untracked_delivery_files(ROOT) == [
        "instock/core/new_feature.py",
        "tests/test_new_feature.py",
    ]


def test_mod_release_workflow_is_native_and_uses_the_offline_gate():
    source = WORKFLOW.read_text("utf-8")

    assert "python scripts/newma_release_check.py" in source
    assert "requirements-dev.txt" in source
    assert "requirements-attached.txt" in source
    assert "requirements-attached.constraints.txt" in source
    assert "docker" not in source.lower()
    assert "--live" not in source
