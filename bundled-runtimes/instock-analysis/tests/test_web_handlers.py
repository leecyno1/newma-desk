import asyncio
import json
import os
import sys
import time
from datetime import datetime, timedelta
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import tornado.web
from tornado.testing import AsyncHTTPTestCase, gen_test

import instock.web.rotation_handler as rotation_handler
import instock.web.czsc_chart_handler as czsc_chart_handler
import instock.web.czsc_scan_handler as czsc_scan_handler
import instock.web.integration_api as integration_api
from instock.web.runtime_metrics import get_api_metrics_registry
from instock.core.analysis_snapshot import get_analysis_snapshot_registry
from instock.core.analysis_history import get_analysis_history_registry
from instock.core.rotation.sector_fund_flow_history import get_sector_fund_flow_history
from instock.web.analysis_history_handler import (
    AnalysisHistoryCollectionHandler,
    AnalysisHistoryResourceHandler,
)
from instock.web.analysis_snapshot_handler import AnalysisSnapshotResourceHandler
from instock.web.czsc_chart_handler import CZSCAnalysisHandler
from instock.web.czsc_scan_handler import CZSCScanCollectionHandler, CZSCScanResourceHandler
from instock.web.integration_api import (
    IntegrationCapabilitiesHandler,
    IntegrationHealthHandler,
    NewmaDeskSuiteHandler,
)


def test_native_runtime_probe_returns_sanitized_failure():
    integration_api._native_analysis_runtime_readiness.cache_clear()
    completed = SimpleNamespace(returncode=7, stderr="loader failed at /private/runtime")
    try:
        with patch.object(integration_api.subprocess, "run", return_value=completed):
            readiness = integration_api._native_analysis_runtime_readiness()
    finally:
        integration_api._native_analysis_runtime_readiness.cache_clear()

    assert readiness == {
        "status": "not_ready",
        "reason": "native_import_failed",
        "exit_code": 7,
        "isolation": "subprocess",
    }
    assert "/private/runtime" not in json.dumps(readiness)


def test_native_runtime_probe_times_out_without_blocking_readiness():
    integration_api._native_analysis_runtime_readiness.cache_clear()
    try:
        with patch.object(
            integration_api.subprocess,
            "run",
            side_effect=integration_api.subprocess.TimeoutExpired("python", 10),
        ):
            readiness = integration_api._native_analysis_runtime_readiness()
    finally:
        integration_api._native_analysis_runtime_readiness.cache_clear()

    assert readiness == {
        "status": "not_ready",
        "reason": "probe_timeout",
        "exit_code": None,
        "isolation": "subprocess",
    }


class CountingRotationEngine:
    calls = 0
    shadow_inputs = []

    def __init__(self, provider):
        self.provider = provider

    def analyze(
        self,
        window,
        benchmark,
        as_of=None,
        fund_flow_history=None,
        shadow_state=None,
    ):
        type(self).calls += 1
        type(self).shadow_inputs.append(shadow_state)
        time.sleep(0.08)
        shadow_payload = {
            "schema_version": "instock.rotation.shadow.v1",
            "strategy_id": "rotation-stateful-ensemble-v1",
            "as_of": "2026-07-24",
            "lifecycle_state": "historical_disabled" if as_of else "bootstrap",
            "signal_id": "" if as_of else "rotation-stateful-ensemble-v1:2026-07-24",
            "models": [{
                "id": "balanced-w60",
                "selected_code": "510300",
                "code": "510300",
            }],
        }
        return {
            "engine": {"name": "instock-rotation", "version": "fixture"},
            "as_of": "2026-07-24",
            "requested_as_of": as_of,
            "window": window,
            "benchmark": {"code": benchmark},
            "etfs": [],
            "failures": [],
            "warnings": [],
            "parameter_consensus": {"shadow_state": shadow_payload},
            "snapshot": {
                "schema_version": "1.0",
                "snapshot_id": "instock-rotation:000000000000000000000001",
                "analysis": {"name": "instock-rotation", "version": "fixture"},
            },
        }


class MemoryRotationShadowLedger:
    def __init__(self):
        self.states = {}
        self.latest_calls = 0
        self.record_calls = 0

    def latest(self, benchmark):
        self.latest_calls += 1
        return self.states.get(benchmark)

    def record(self, benchmark, state):
        self.record_calls += 1
        if benchmark in self.states:
            return False
        self.states[benchmark] = dict(state)
        return True

    def stats(self):
        return {
            "storage": "sqlite",
            "volatile": False,
            "cleared_on_restart": False,
            "entries": len(self.states),
            "benchmarks": len(self.states),
            "signal_entries": len(self.states),
            "latest_as_of": "2026-07-24" if self.states else "",
        }


class CountingRotationExperiment:
    calls = 0
    supported_rebalances = (5, 10, 20)
    supported_cost_bps = (10, 25, 50)

    def __init__(self, provider):
        self.provider = provider

    def run(self, *, benchmark, rebalance_days, cost_bps, as_of=None):
        type(self).calls += 1
        time.sleep(0.05)
        return {
            "as_of": "2026-07-24",
            "requested_as_of": as_of,
            "data_source": "fixture",
            "rules": {"holding_period_sessions": rebalance_days, "cost_bps_per_side": cost_bps},
            "data_quality": {"state": "complete"},
            "selected_variant": {"id": "balanced-w60", "out_of_sample": {"trades": 12}},
            "parameter_surface": [],
            "stress_tests": [],
            "equity_curve": [],
            "summary": {"selected_variant_id": "balanced-w60", "oos_excess_return_pct": 1.2},
            "verdict": {"state": "insufficient_evidence", "label": "证据不足", "reasons": []},
            "failures": [],
            "limitations": [],
            "snapshot": {
                "schema_version": "1.0",
                "snapshot_id": "instock-rotation-experiment:000000000000000000000001",
                "analysis": {"name": "instock-rotation-experiment", "version": "1.0.0"},
            },
        }


class FixtureCZSCProvider:
    name = "fixture"

    def get_kline(self, symbol, period="daily", limit=480, as_of=None):
        rows = []
        for index in range(max(limit, 120)):
            close = 20 + (index % 17) * 0.12 + index * 0.01
            rows.append({
                "date": datetime(2025, 1, 1) + timedelta(days=index),
                "open": close - 0.1,
                "high": close + 0.3,
                "low": close - 0.3,
                "close": close,
                "volume": 100000 + index,
                "amount": (100000 + index) * close,
            })
        frame = pd.DataFrame(rows).tail(limit).reset_index(drop=True)
        frame.attrs.update({"data_source": self.name, "adjust": "qfq"})
        return frame


class BlockingCZSCBatchScanner:
    started = Event()

    def __init__(self, provider, max_workers=4):
        self.max_workers = max_workers

    def scan(self, symbols, *, period, bars, as_of, cancel_event, on_progress):
        ordered = list(symbols)
        type(self).started.set()
        on_progress({
            "total": len(ordered),
            "completed": 0,
            "succeeded": 0,
            "failed": 0,
            "current_symbol": None,
            "cancel_requested": False,
        })
        cancel_event.wait(timeout=2)
        progress = {
            "total": len(ordered),
            "completed": 0,
            "succeeded": 0,
            "failed": 0,
            "cancel_requested": cancel_event.is_set(),
        }
        return {
            "status": "cancelled" if cancel_event.is_set() else "completed",
            "parameters": {
                "symbols": ordered,
                "period": period,
                "bars": bars,
                "asOf": as_of,
                "max_workers": self.max_workers,
            },
            "progress": progress,
            "summary": {"bullish": 0, "neutral": 0, "bearish": 0, "partial_input": 0},
            "candidates": [],
            "failures": [],
            "ranking_method": "instock-czsc-candidate-score-v1",
        }


class AnalysisHandlerTest(AsyncHTTPTestCase):
    def setUp(self):
        self.cors_patch = patch.dict(
            os.environ,
            {"INSTOCK_CORS_ORIGIN": "", "INSTOCK_CORS_ORIGINS": ""},
        )
        self.provider_patch = patch.object(
            rotation_handler,
            "get_market_data_provider",
            return_value=SimpleNamespace(name="fixture"),
        )
        self.engine_patch = patch.object(
            rotation_handler, "RotationEngine", CountingRotationEngine
        )
        self.experiment_patch = patch.object(
            rotation_handler, "RotationExperiment", CountingRotationExperiment
        )
        self.scan_provider_patch = patch.object(
            czsc_scan_handler,
            "get_market_data_provider",
            return_value=FixtureCZSCProvider(),
        )
        self.native_runtime_patch = patch.object(
            integration_api,
            "_native_analysis_runtime_readiness",
            return_value={
                "status": "ready",
                "reason": None,
                "exit_code": 0,
                "isolation": "subprocess",
            },
        )
        self.market_data_patch = patch.object(
            integration_api,
            "_market_data_readiness",
            return_value={
                "status": "ready",
                "provider": "newma-desk",
                "reason": None,
                "checked_at": "2026-08-13T10:00:00+08:00",
                "cache_ttl_seconds": 15.0,
            },
        )
        self.shadow_ledger = MemoryRotationShadowLedger()
        self.shadow_ledger_patch = patch.object(
            rotation_handler,
            "get_rotation_shadow_state",
            return_value=self.shadow_ledger,
        )
        self.cors_patch.start()
        self.provider_patch.start()
        self.engine_patch.start()
        self.experiment_patch.start()
        self.scan_provider_patch.start()
        self.native_runtime_patch.start()
        self.market_data_patch.start()
        self.shadow_ledger_patch.start()
        CountingRotationEngine.calls = 0
        CountingRotationEngine.shadow_inputs = []
        CountingRotationExperiment.calls = 0
        rotation_handler._SNAPSHOT_CACHE.clear()
        rotation_handler._SNAPSHOT_INFLIGHT.clear()
        rotation_handler._EXPERIMENT_CACHE.clear()
        rotation_handler._EXPERIMENT_INFLIGHT.clear()
        czsc_chart_handler._RESULT_CACHE.clear()
        czsc_chart_handler._INFLIGHT.clear()
        get_analysis_snapshot_registry().clear()
        get_analysis_history_registry().clear()
        get_sector_fund_flow_history().clear()
        czsc_scan_handler.get_czsc_scan_registry().clear()
        get_api_metrics_registry().clear()
        super().setUp()

    def tearDown(self):
        super().tearDown()
        rotation_handler._SNAPSHOT_CACHE.clear()
        rotation_handler._SNAPSHOT_INFLIGHT.clear()
        rotation_handler._EXPERIMENT_CACHE.clear()
        rotation_handler._EXPERIMENT_INFLIGHT.clear()
        czsc_chart_handler._RESULT_CACHE.clear()
        czsc_chart_handler._INFLIGHT.clear()
        get_analysis_snapshot_registry().clear()
        get_analysis_history_registry().clear()
        get_sector_fund_flow_history().clear()
        czsc_scan_handler.get_czsc_scan_registry().clear()
        get_api_metrics_registry().clear()
        self.shadow_ledger_patch.stop()
        self.market_data_patch.stop()
        self.native_runtime_patch.stop()
        self.scan_provider_patch.stop()
        self.experiment_patch.stop()
        self.engine_patch.stop()
        self.provider_patch.stop()
        self.cors_patch.stop()

    def get_app(self):
        return tornado.web.Application([
            (r"/api/czsc/analysis", CZSCAnalysisHandler),
            (r"/api/v1/czsc/analyses", CZSCAnalysisHandler),
            (r"/api/v1/czsc/scans", CZSCScanCollectionHandler),
            (r"/api/v1/czsc/scans/([^/]+)", CZSCScanResourceHandler),
            (r"/api/rotation/snapshot", rotation_handler.RotationSnapshotHandler),
            (r"/api/v1/rotations/snapshots", rotation_handler.RotationSnapshotHandler),
            (r"/api/v1/rotations/experiments", rotation_handler.RotationExperimentHandler),
            (r"/api/v1/analysis-snapshots/([^/]+)", AnalysisSnapshotResourceHandler),
            (r"/api/v1/analysis-history", AnalysisHistoryCollectionHandler),
            (r"/api/v1/analysis-history/([^/]+)", AnalysisHistoryResourceHandler),
            (r"/api/v1/health", IntegrationHealthHandler),
            (r"/api/v1/capabilities", IntegrationCapabilitiesHandler),
            (r"/\.well-known/newma-desk-suite\.json", NewmaDeskSuiteHandler),
        ])

    @gen_test
    async def test_rotation_concurrent_refreshes_share_one_analysis(self):
        url = self.get_url("/api/rotation/snapshot?window=60&benchmark=510300&refresh=1")
        responses = await asyncio.gather(
            self.http_client.fetch(url),
            self.http_client.fetch(url),
        )

        assert all(response.code == 200 for response in responses)
        assert all(json.loads(response.body)["data"]["cache_hit"] is False for response in responses)

        cached = await self.http_client.fetch(
            self.get_url("/api/rotation/snapshot?window=60&benchmark=510300")
        )
        assert json.loads(cached.body)["data"]["cache_hit"] is True
        assert CountingRotationEngine.calls == 1
        assert CountingRotationEngine.shadow_inputs == [None]
        assert len(self.shadow_ledger.states) == 1

    @gen_test
    async def test_rotation_refresh_reuses_previous_shadow_state(self):
        url = self.get_url(
            "/api/v1/rotations/snapshots?window=60&benchmark=510300&refresh=1"
        )
        await self.http_client.fetch(url)
        second = json.loads((await self.http_client.fetch(url)).body)["data"]

        assert CountingRotationEngine.calls == 2
        assert CountingRotationEngine.shadow_inputs[0] is None
        assert CountingRotationEngine.shadow_inputs[1]["as_of"] == "2026-07-24"
        assert self.shadow_ledger.record_calls == 2
        assert second["shadow_ledger"]["state"] == "unchanged"

    @gen_test
    async def test_historical_rotation_does_not_touch_shadow_ledger(self):
        response = await self.http_client.fetch(self.get_url(
            "/api/v1/rotations/snapshots?window=60&benchmark=510300"
            "&asOf=2026-07-01&refresh=1"
        ))
        payload = json.loads(response.body)["data"]

        assert self.shadow_ledger.latest_calls == 0
        assert self.shadow_ledger.record_calls == 0
        assert payload["shadow_ledger"]["state"] == "historical_disabled"

    @gen_test
    async def test_czsc_analysis_cache_refresh_and_history_are_consistent(self):
        calls = 0

        def fake_analysis(provider, *, symbol, period, bars, as_of=None, include_chart=True):
            nonlocal calls
            calls += 1
            return {
                "symbol": symbol,
                "period": period,
                "end_date": "2026-08-12",
                "engine": {"name": "czsc", "version": "fixture"},
                "summary": {},
                "evidence": {},
                "structure": {},
                "chart": {},
                "data_source": "fixture",
                "snapshot": {
                    "schema_version": "1.0",
                    "snapshot_id": f"czsc:fixture-{calls}",
                    "analysis": {"name": "czsc", "version": "fixture"},
                    "parameters": {},
                    "data_window": {},
                    "provenance": {},
                    "freshness": {},
                    "input": {},
                    "result": {},
                },
            }

        url = self.get_url("/api/v1/czsc/analyses?code=300502&period=daily&bars=120")
        with (
            patch.object(czsc_chart_handler, "get_market_data_provider", return_value=SimpleNamespace(name="fixture")),
            patch.object(czsc_chart_handler, "run_czsc_analysis", side_effect=fake_analysis),
        ):
            first = json.loads((await self.http_client.fetch(url)).body)
            second = json.loads((await self.http_client.fetch(url)).body)
            refreshed = json.loads((await self.http_client.fetch(url + "&refresh=1")).body)

        assert first["data"]["cache_hit"] is False
        assert second["data"]["cache_hit"] is True
        assert refreshed["data"]["cache_hit"] is False
        assert calls == 2
        history = get_analysis_history_registry().list("czsc")
        assert len(history) == 2
        assert first["meta"]["history"]["history_id"] != refreshed["meta"]["history"]["history_id"]
        assert "history" not in second["meta"]

    @gen_test
    async def test_refresh_versions_remain_browsable(self):
        url = self.get_url("/api/v1/rotations/snapshots?window=60&benchmark=510300&refresh=1")
        await self.http_client.fetch(url)
        await self.http_client.fetch(url)

        history = await self.http_client.fetch(
            self.get_url("/api/v1/analysis-history?moduleId=rotation")
        )
        records = json.loads(history.body)["data"]
        assert len(records) == 2
        assert records[0]["history_id"] != records[1]["history_id"]

        restored = await self.http_client.fetch(
            self.get_url(f"/api/v1/analysis-history/{records[1]['history_id']}")
        )
        record = json.loads(restored.body)["data"]
        assert record["module_id"] == "rotation"
        assert record["payload"]["benchmark"] == {"code": "510300"}

    @gen_test
    async def test_rotation_experiment_is_cached_and_validates_friction_inputs(self):
        url = self.get_url(
            "/api/v1/rotations/experiments?benchmark=510300&rebalanceDays=10&costBps=25"
        )
        first = await self.http_client.fetch(url)
        second = await self.http_client.fetch(url)
        first_payload = json.loads(first.body)["data"]
        second_payload = json.loads(second.body)["data"]

        assert first_payload["cache_hit"] is False
        assert second_payload["cache_hit"] is True
        assert CountingRotationExperiment.calls == 1
        assert first_payload["rules"]["holding_period_sessions"] == 10

        invalid = await self.http_client.fetch(
            self.get_url("/api/v1/rotations/experiments?rebalanceDays=7&costBps=25"),
            raise_error=False,
        )
        assert invalid.code == 400
        assert json.loads(invalid.body)["error"]["code"] == "invalid_rebalance_days"

    @gen_test
    async def test_api_cors_is_off_by_default_and_explicit_when_configured(self):
        url = self.get_url("/api/rotation/snapshot?window=60&benchmark=510300")
        response = await self.http_client.fetch(url)
        assert response.headers.get("Access-Control-Allow-Origin") is None

        os.environ["INSTOCK_CORS_ORIGIN"] = "http://127.0.0.1:5173"
        response = await self.http_client.fetch(url)
        assert response.headers["Access-Control-Allow-Origin"] == "http://127.0.0.1:5173"
        assert response.headers["Vary"] == "Origin"

        preflight = await self.http_client.fetch(
            self.get_url("/api/v1/czsc/scans"),
            method="OPTIONS",
            headers={"Origin": "http://127.0.0.1:5173"},
        )
        assert preflight.code == 204
        assert preflight.headers["Access-Control-Allow-Methods"] == "GET, POST, DELETE, OPTIONS"

    @gen_test
    async def test_czsc_handler_rejects_invalid_symbol_before_data_fetch(self):
        response = await self.http_client.fetch(
            self.get_url("/api/czsc/analysis?code=bad-code&period=daily&bars=480"),
            raise_error=False,
        )
        payload = json.loads(response.body)

        assert response.code == 400
        assert payload["ok"] is False
        assert "股票代码" in payload["error"]

    @gen_test
    async def test_v1_error_contract_is_structured(self):
        response = await self.http_client.fetch(
            self.get_url("/api/v1/czsc/analyses?code=bad-code&period=daily&bars=480"),
            raise_error=False,
        )
        payload = json.loads(response.body)

        assert response.code == 400
        assert payload["error"]["code"] == "invalid_symbol"
        assert "股票代码" in payload["error"]["message"]
        assert payload["meta"]["api_version"] == "1.0"
        assert response.headers["X-Request-Id"] == payload["meta"]["request_id"]

        health_response = await self.http_client.fetch(self.get_url("/api/v1/health"))
        metrics = json.loads(health_response.body)["data"]["runtime"]["state"]["api_requests"]
        invalid_route = metrics["routes"]["GET /api/v1/czsc/analyses"]
        assert invalid_route["requests"] == 1
        assert invalid_route["errors"] == 1
        assert invalid_route["server_errors"] == 0
        assert invalid_route["status_classes"] == {"4xx": 1}

    @gen_test
    async def test_v1_rejects_invalid_historical_as_of(self):
        response = await self.http_client.fetch(
            self.get_url(
                "/api/v1/rotations/snapshots?window=60&benchmark=510300&asOf=not-a-date"
            ),
            raise_error=False,
        )
        payload = json.loads(response.body)

        assert response.code == 400
        assert payload["error"]["code"] == "invalid_as_of"

        loose_format = await self.http_client.fetch(
            self.get_url(
                "/api/v1/rotations/snapshots?window=60&benchmark=510300&asOf=2026-7-1"
            ),
            raise_error=False,
        )
        assert loose_format.code == 400

    @gen_test
    async def test_health_and_capabilities_report_analysis_and_market_data_separately(self):
        analysis_modules_before = {
            name for name in sys.modules
            if name == "czsc" or name.startswith("czsc.") or name == "talib" or name.startswith("talib.")
        }
        health_response = await self.http_client.fetch(self.get_url("/api/v1/health"))
        health = json.loads(health_response.body)["data"]
        assert health["status"] == "ok"
        assert health["database_required"] is False
        assert health["runtime"] == {
            "mode": "newma-desk-attached",
            "lifecycle_owner": "newma-desk",
            "standalone_deployment": False,
            "instance": health["runtime"]["instance"],
            "state": health["runtime"]["state"],
        }
        instance = health["runtime"]["instance"]
        assert len(instance["id"]) == 32
        assert instance["started_at"]
        assert instance["uptime_seconds"] >= 0
        runtime_state = health["runtime"]["state"]
        assert runtime_state["storage"] == "mixed"
        assert runtime_state["volatile"] is True
        assert runtime_state["cleared_on_restart"] is False
        assert runtime_state["volatile_state_cleared_on_restart"] is True
        assert runtime_state["persistent_state"] == [
            "analysis_history", "sector_fund_flow_history", "rotation_shadow_state"
        ]
        assert runtime_state["analysis_history"]["storage"] == "sqlite"
        assert runtime_state["analysis_history"]["volatile"] is False
        assert runtime_state["sector_fund_flow_history"]["storage"] == "sqlite"
        assert runtime_state["sector_fund_flow_history"]["volatile"] is False
        assert runtime_state["rotation_shadow_state"]["storage"] == "sqlite"
        assert runtime_state["rotation_shadow_state"]["volatile"] is False
        assert runtime_state["analysis_snapshots"]["entries"] == 0
        assert runtime_state["czsc_analyses"]["max_entries"] == 64
        assert runtime_state["czsc_scans"]["active"] == 0
        assert runtime_state["market_map_results"]["max_entries"] == 4
        assert runtime_state["market_workbench_results"]["max_entries"] == 8
        assert runtime_state["stock_candidate_results"]["max_entries"] == 32
        assert runtime_state["technical_signal_results"]["max_entries"] == 16
        assert runtime_state["stock_research_results"]["max_entries"] == 64
        assert runtime_state["rotation_snapshots"]["max_entries"] == 64
        assert runtime_state["rotation_experiments"]["max_entries"] == 32
        api_requests = runtime_state["api_requests"]
        assert api_requests["route_labels"] == "fixed_templates"
        assert api_requests["latency_sample_max_per_route"] == 256
        assert api_requests["totals"]["requests"] == 0
        assert api_requests["observation_scope"] == (
            "completed_requests_before_current_health_response"
        )
        assert health["readiness"] == {
            "status": "ready",
            "analysis_dependencies": True,
            "market_data": True,
            "distribution_metadata": True,
            "native_runtime": {
                "status": "ready",
                "reason": None,
                "exit_code": 0,
                "isolation": "subprocess",
            },
            "check_mode": "distribution_metadata_and_isolated_import",
        }
        assert health["market_data"] == {
            "provider": "newma-desk",
            "configured": True,
            "configured_as": "newma-desk",
            "status": "ready",
            "reason": None,
            "checked_at": "2026-08-13T10:00:00+08:00",
            "cache_ttl_seconds": 15.0,
        }
        assert {
            package: dependency["installed_version"]
            for package, dependency in health["dependencies"].items()
        } == integration_api.REQUIRED_ANALYSIS_DEPENDENCIES
        analysis_modules_after = {
            name for name in sys.modules
            if name == "czsc" or name.startswith("czsc.") or name == "talib" or name.startswith("talib.")
        }
        assert analysis_modules_after == analysis_modules_before

        second_health = json.loads((await self.http_client.fetch(
            self.get_url("/api/v1/health")
        )).body)["data"]
        assert second_health["runtime"]["instance"]["id"] == instance["id"]
        assert second_health["runtime"]["instance"]["uptime_seconds"] >= instance["uptime_seconds"]
        completed_metrics = second_health["runtime"]["state"]["api_requests"]
        assert completed_metrics["totals"]["requests"] == 1
        assert completed_metrics["routes"]["GET /api/v1/health"]["status_classes"] == {
            "2xx": 1
        }

        capabilities_response = await self.http_client.fetch(
            self.get_url("/api/v1/capabilities")
        )
        capabilities = json.loads(capabilities_response.body)["data"]
        assert capabilities["runtime"]["workspace_runtime_id"] == "instock"
        assert capabilities["runtime"]["standalone_deployment"] is False
        assert capabilities["compatibility"]["level"] == 2
        assert capabilities["compatibility"]["connected_actions"] is True
        assert capabilities["discovery"]["suite"] == "/.well-known/newma-desk-suite.json"
        assert {page["mod_id"] for page in capabilities["pages"]} == {
            "instock-czsc", "instock-rotation", "instock-industry-chain",
            "instock-stock-candidates", "instock-stock-research",
            "instock-strategy-validation",
            "instock-event-flow",
            "instock-research-book",
            "instock-market-workbench",
            "instock-market-map",
            "instock-technical-signals",
        }
        assert {item["id"] for item in capabilities["apis"]} == {
            "analysis.czsc", "analysis.czsc.scan", "analysis.rotation",
            "analysis.rotation.experiment", "analysis.industry-chain",
            "analysis.rotation.supply-chain",
            "analysis.stock-candidates", "analysis.stock-research",
            "analysis.strategy-validation",
            "analysis.event-flow",
            "analysis.research-book",
            "analysis.market-workbench",
            "analysis.market-map",
            "analysis.technical-signals",
            "analysis.snapshot",
        }
        assert capabilities["data_boundary"]["stock_candidates"]["fundamental_batch_size"] == 4
        assert capabilities["data_boundary"]["stock_candidates"]["fundamental_batch_workers"] == 3
        assert capabilities["data_boundary"]["technical_signals"]["fundamental_batch_size"] == 8
        assert capabilities["data_boundary"]["technical_signals"]["fundamental_batch_workers"] == 2

        suite_response = await self.http_client.fetch(
            self.get_url("/.well-known/newma-desk-suite.json")
        )
        suite = json.loads(suite_response.body)
        assert suite["id"] == "instock-suite"
        assert suite["runtime"]["defaultBaseUrl"] == self.get_url("").rstrip("/")
        assert {page["id"] for page in suite["pages"]} == {
            "instock-czsc", "instock-rotation", "instock-industry-chain",
            "instock-stock-candidates", "instock-stock-research",
            "instock-strategy-validation",
            "instock-event-flow",
            "instock-research-book",
            "instock-market-workbench",
            "instock-market-map",
            "instock-technical-signals",
        }

    @gen_test
    async def test_health_returns_503_when_analysis_dependency_is_missing(self):
        real_version = integration_api.distribution_version

        def missing_czsc(package):
            if package == "czsc":
                raise integration_api.PackageNotFoundError(package)
            return real_version(package)

        with patch.object(integration_api, "distribution_version", side_effect=missing_czsc):
            response = await self.http_client.fetch(
                self.get_url("/api/v1/health"), raise_error=False
            )

        payload = json.loads(response.body)
        details = payload["error"]["details"]
        assert response.code == 503
        assert payload["error"]["code"] == "analysis_dependencies_not_ready"
        assert details["readiness"]["status"] == "not_ready"
        assert details["readiness"]["native_runtime"]["status"] == "not_checked"
        assert details["dependencies"]["czsc"] == {
            "required_version": "0.10.12",
            "installed_version": None,
            "status": "missing",
        }

    @gen_test
    async def test_health_returns_503_when_analysis_dependency_version_drifts(self):
        real_version = integration_api.distribution_version

        def drifted_version(package):
            if package == "rs-czsc":
                return "0.1.25"
            return real_version(package)

        with patch.object(integration_api, "distribution_version", side_effect=drifted_version):
            response = await self.http_client.fetch(
                self.get_url("/api/v1/health"), raise_error=False
            )

        payload = json.loads(response.body)
        details = payload["error"]["details"]
        assert response.code == 503
        assert details["readiness"]["analysis_dependencies"] is False
        assert details["dependencies"]["rs-czsc"] == {
            "required_version": "0.1.26.post260402",
            "installed_version": "0.1.25",
            "status": "version_mismatch",
        }

    @gen_test
    async def test_health_returns_503_when_native_runtime_probe_fails(self):
        native_failure = {
            "status": "not_ready",
            "reason": "native_import_failed",
            "exit_code": 1,
            "isolation": "subprocess",
        }
        with patch.object(
            integration_api,
            "_native_analysis_runtime_readiness",
            return_value=native_failure,
        ):
            response = await self.http_client.fetch(
                self.get_url("/api/v1/health"), raise_error=False
            )

        payload = json.loads(response.body)
        details = payload["error"]["details"]
        assert response.code == 503
        assert payload["error"]["code"] == "analysis_dependencies_not_ready"
        assert details["readiness"]["distribution_metadata"] is True
        assert details["readiness"]["native_runtime"] == native_failure

    @gen_test
    async def test_health_stays_available_but_reports_desk_data_degradation(self):
        with patch.object(
            integration_api,
            "_market_data_readiness",
            return_value={
                "status": "unavailable",
                "provider": "newma-desk",
                "reason": "desk_health_unreachable",
                "checked_at": "2026-08-13T10:00:00+08:00",
                "cache_ttl_seconds": 15.0,
            },
        ):
            response = await self.http_client.fetch(self.get_url("/api/v1/health"))

        health = json.loads(response.body)["data"]
        assert response.code == 200
        assert health["status"] == "ok"
        assert health["readiness"]["status"] == "ready"
        assert health["readiness"]["analysis_dependencies"] is True
        assert health["readiness"]["market_data"] is False
        assert health["market_data"]["status"] == "unavailable"

    @gen_test
    async def test_snapshot_resource_is_queryable_and_returns_standard_404(self):
        snapshot = {
            "schema_version": "1.0",
            "snapshot_id": "czsc:000000000000000000000001",
            "analysis": {"name": "czsc", "version": "0.10.12"},
        }
        get_analysis_snapshot_registry().register(snapshot)

        response = await self.http_client.fetch(
            self.get_url(f"/api/v1/analysis-snapshots/{snapshot['snapshot_id']}")
        )
        payload = json.loads(response.body)
        assert payload["data"] == snapshot
        assert payload["meta"]["registry"]["volatile"] is True

        missing = await self.http_client.fetch(
            self.get_url("/api/v1/analysis-snapshots/czsc:ffffffffffffffffffffffff"),
            raise_error=False,
        )
        missing_payload = json.loads(missing.body)
        assert missing.code == 404
        assert missing_payload["error"]["code"] == "analysis_snapshot_not_found"

    @gen_test
    async def test_czsc_batch_scan_task_completes_and_is_queryable(self):
        response = await self.http_client.fetch(
            self.get_url("/api/v1/czsc/scans"),
            method="POST",
            headers={"Content-Type": "application/json"},
            body=json.dumps({
                "symbols": ["300502", "512800"],
                "period": "daily",
                "bars": 120,
                "maxWorkers": 2,
            }),
        )
        created = json.loads(response.body)
        assert response.code == 202
        assert response.headers["Location"].endswith(created["data"]["scan_id"])

        record = created["data"]
        for _ in range(200):
            status_response = await self.http_client.fetch(
                self.get_url(f"/api/v1/czsc/scans/{record['scan_id']}")
            )
            record = json.loads(status_response.body)["data"]
            if record["status"] in {"completed", "cancelled", "failed"}:
                break
            await asyncio.sleep(0.02)

        assert record["status"] == "completed"
        assert record["result"]["progress"]["succeeded"] == 2
        assert len(record["result"]["candidates"]) == 2
        assert all(row["snapshot_id"].startswith("czsc:") for row in record["result"]["candidates"])

    @gen_test
    async def test_czsc_batch_scan_rejects_invalid_or_oversized_symbol_lists(self):
        invalid = await self.http_client.fetch(
            self.get_url("/api/v1/czsc/scans"),
            method="POST",
            headers={"Content-Type": "application/json"},
            body=json.dumps({"symbols": ["bad-code"]}),
            raise_error=False,
        )
        assert invalid.code == 400
        assert json.loads(invalid.body)["error"]["code"] == "invalid_symbols"

        oversized = await self.http_client.fetch(
            self.get_url("/api/v1/czsc/scans"),
            method="POST",
            headers={"Content-Type": "application/json"},
            body=json.dumps({"symbols": [f"{index:06d}" for index in range(21)]}),
            raise_error=False,
        )
        assert oversized.code == 400

    @gen_test
    async def test_czsc_batch_scan_delete_requests_real_cancellation(self):
        BlockingCZSCBatchScanner.started.clear()
        with patch.object(czsc_scan_handler, "CZSCBatchScanner", BlockingCZSCBatchScanner):
            response = await self.http_client.fetch(
                self.get_url("/api/v1/czsc/scans"),
                method="POST",
                headers={"Content-Type": "application/json"},
                body=json.dumps({"symbols": ["300502", "512800"], "bars": 120}),
            )
            record = json.loads(response.body)["data"]
            assert await asyncio.to_thread(BlockingCZSCBatchScanner.started.wait, 1)

            active_health = json.loads((await self.http_client.fetch(
                self.get_url("/api/v1/health")
            )).body)["data"]
            active_stats = active_health["runtime"]["state"]["czsc_scans"]
            assert active_stats["active"] == 1
            assert active_stats["status_counts"] == {"running": 1}

            cancelled = await self.http_client.fetch(
                self.get_url(f"/api/v1/czsc/scans/{record['scan_id']}"),
                method="DELETE",
            )
            cancelling_record = json.loads(cancelled.body)["data"]
            assert cancelled.code == 202
            assert cancelling_record["status"] == "cancelling"
            assert cancelling_record["progress"]["cancel_requested"] is True

            for _ in range(100):
                status_response = await self.http_client.fetch(
                    self.get_url(f"/api/v1/czsc/scans/{record['scan_id']}")
                )
                record = json.loads(status_response.body)["data"]
                if record["status"] == "cancelled":
                    break
                await asyncio.sleep(0.01)

            assert record["status"] == "cancelled"
            assert record["result"]["progress"]["cancel_requested"] is True

            terminal_health = json.loads((await self.http_client.fetch(
                self.get_url("/api/v1/health")
            )).body)["data"]
            terminal_stats = terminal_health["runtime"]["state"]["czsc_scans"]
            assert terminal_stats["active"] == 0
            assert terminal_stats["terminal"] == 1
            assert terminal_stats["status_counts"] == {"cancelled": 1}
