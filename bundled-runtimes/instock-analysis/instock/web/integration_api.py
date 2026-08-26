#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Discovery endpoints for external Web and Newma-Desk integration."""

from __future__ import annotations

import copy
import json
import logging
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version as distribution_version
from pathlib import Path

from instock.web.api_contract import (
    API_VERSION,
    BRIDGE_PROTOCOL,
    AnalysisApiHandler,
    exact_http_origin,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
NEWMA_SUITE_PATH = (
    PROJECT_ROOT / "integrations" / "newma-desk" / "instock-suite" / "suite.json"
)
REQUIRED_ANALYSIS_DEPENDENCIES = {
    "czsc": "0.10.12",
    "TA-Lib": "0.6.8",
    "rs-czsc": "0.1.26.post260402",
}
_PROCESS_INSTANCE_ID = uuid.uuid4().hex
_PROCESS_STARTED_AT = datetime.now().astimezone().isoformat(timespec="seconds")
_PROCESS_STARTED_MONOTONIC = time.monotonic()
_NATIVE_RUNTIME_PROBE_SOURCE = """
import numpy as np
import czsc
import rs_czsc
import talib

assert hasattr(czsc, "CZSC")
assert hasattr(rs_czsc, "CZSC")
assert callable(talib.SMA)
values = talib.SMA(np.array([1.0, 2.0, 3.0]), timeperiod=2)
assert float(values[-1]) == 2.5
""".strip()


@lru_cache(maxsize=1)
def _newma_suite_descriptor() -> dict:
    return json.loads(NEWMA_SUITE_PATH.read_text("utf-8"))


def _analysis_dependency_readiness() -> tuple[bool, dict[str, dict[str, str | None]]]:
    """Check installed distribution metadata without importing analysis engines."""

    dependencies = {}
    ready = True
    for package, required_version in REQUIRED_ANALYSIS_DEPENDENCIES.items():
        try:
            installed_version = distribution_version(package)
        except PackageNotFoundError:
            installed_version = None

        if installed_version is None:
            status = "missing"
        elif installed_version != required_version:
            status = "version_mismatch"
        else:
            status = "ready"
        if status != "ready":
            ready = False
        dependencies[package] = {
            "required_version": required_version,
            "installed_version": installed_version,
            "status": status,
        }
    return ready, dependencies


@lru_cache(maxsize=1)
def _native_analysis_runtime_readiness() -> dict[str, str | int | None]:
    """Load native analysis extensions in a disposable isolated interpreter."""

    try:
        completed = subprocess.run(
            [sys.executable, "-I", "-c", _NATIVE_RUNTIME_PROBE_SOURCE],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            check=False,
        )
    except subprocess.TimeoutExpired:
        logging.error("CZSC native runtime readiness probe timed out")
        return {
            "status": "not_ready",
            "reason": "probe_timeout",
            "exit_code": None,
            "isolation": "subprocess",
        }
    except OSError as exc:
        logging.error("CZSC native runtime readiness probe could not start: %s", exc)
        return {
            "status": "not_ready",
            "reason": "probe_launch_failed",
            "exit_code": None,
            "isolation": "subprocess",
        }

    if completed.returncode != 0:
        diagnostic = completed.stderr.strip().replace("\n", " ")[-1000:]
        logging.error(
            "CZSC native runtime readiness probe failed: exit=%s detail=%s",
            completed.returncode,
            diagnostic,
        )
        return {
            "status": "not_ready",
            "reason": "native_import_failed",
            "exit_code": completed.returncode,
            "isolation": "subprocess",
        }
    return {
        "status": "ready",
        "reason": None,
        "exit_code": 0,
        "isolation": "subprocess",
    }


def warm_analysis_runtime_readiness() -> None:
    """Populate readiness caches before the attached HTTP socket is exposed."""

    metadata_ready, _ = _analysis_dependency_readiness()
    if metadata_ready:
        _native_analysis_runtime_readiness()


_MARKET_DATA_HEALTH_TTL_SECONDS = 15.0
_MARKET_DATA_HEALTH_CACHE: tuple[float, dict] | None = None


def _market_data_readiness() -> dict:
    """Probe the configured Desk data boundary with a short process-local cache."""

    global _MARKET_DATA_HEALTH_CACHE
    now = time.monotonic()
    if (
        _MARKET_DATA_HEALTH_CACHE is not None
        and now - _MARKET_DATA_HEALTH_CACHE[0] < _MARKET_DATA_HEALTH_TTL_SECONDS
    ):
        return copy.deepcopy(_MARKET_DATA_HEALTH_CACHE[1])

    from instock.core.market_data_provider import MarketDataError, get_market_data_provider

    try:
        result = get_market_data_provider().health()
        if not isinstance(result, dict):
            result = {
                "status": "unavailable",
                "provider": "unknown",
                "reason": "invalid_health_payload",
            }
    except (MarketDataError, OSError, TypeError, ValueError) as exc:
        result = {
            "status": "unavailable",
            "provider": "unknown",
            "reason": "provider_initialization_failed",
            "detail": str(exc),
        }
    result = copy.deepcopy(result)
    result["checked_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    result["cache_ttl_seconds"] = _MARKET_DATA_HEALTH_TTL_SECONDS
    _MARKET_DATA_HEALTH_CACHE = (now, result)
    return copy.deepcopy(result)


def _volatile_runtime_state() -> dict:
    """Describe bounded runtime state without exposing task or analysis data."""

    from instock.core.analysis_history import get_analysis_history_registry
    from instock.core.analysis_snapshot import get_analysis_snapshot_registry
    from instock.core.rotation.rotation_shadow_state import get_rotation_shadow_state
    from instock.core.rotation.sector_fund_flow_history import get_sector_fund_flow_history
    from instock.web.czsc_chart_handler import czsc_analysis_runtime_stats
    from instock.web.czsc_scan_handler import get_czsc_scan_registry
    from instock.web.market_map_handler import market_map_runtime_stats
    from instock.web.market_workbench_handler import market_workbench_runtime_stats
    from instock.web.rotation_handler import rotation_runtime_stats
    from instock.web.runtime_metrics import get_api_metrics_registry
    from instock.web.stock_candidates_handler import stock_candidate_runtime_stats
    from instock.web.stock_research_handler import stock_research_runtime_stats
    from instock.web.technical_signal_handler import technical_signal_runtime_stats

    rotation = rotation_runtime_stats()
    history = get_analysis_history_registry().stats()
    return {
        "storage": "mixed",
        "volatile": True,
        "cleared_on_restart": False,
        "volatile_state_cleared_on_restart": True,
        "persistent_state": [
            "analysis_history", "sector_fund_flow_history", "rotation_shadow_state"
        ],
        "analysis_snapshots": get_analysis_snapshot_registry().stats(),
        "analysis_history": history,
        "sector_fund_flow_history": get_sector_fund_flow_history().stats(),
        "rotation_shadow_state": get_rotation_shadow_state().stats(),
        "czsc_analyses": czsc_analysis_runtime_stats(),
        "czsc_scans": get_czsc_scan_registry().stats(),
        "market_map_results": market_map_runtime_stats(),
        "market_workbench_results": market_workbench_runtime_stats(),
        "stock_candidate_results": stock_candidate_runtime_stats(),
        "technical_signal_results": technical_signal_runtime_stats(),
        "stock_research_results": stock_research_runtime_stats(),
        "rotation_snapshots": rotation["snapshots"],
        "rotation_experiments": rotation["experiments"],
        "api_requests": get_api_metrics_registry().stats(),
    }


class NewmaDeskSuiteHandler(AnalysisApiHandler):
    """Serve the canonical HTTP Suite Descriptor used by Newma-Desk discovery."""

    def get(self) -> None:
        descriptor = copy.deepcopy(_newma_suite_descriptor())
        configured = (
            os.environ.get("NEWMA_DESK_INSTOCK_WEB_URL")
            or os.environ.get("INSTOCK_ANALYSIS_WEB_URL")
            or ""
        )
        request_origin = f"{self.request.protocol}://{self.request.host}"
        public_origin = exact_http_origin(configured) or exact_http_origin(request_origin)
        if public_origin:
            descriptor["runtime"]["defaultBaseUrl"] = public_origin
        self.write(descriptor)


class IntegrationHealthHandler(AnalysisApiHandler):
    def get(self) -> None:
        configured_provider = os.environ.get(
            "INSTOCK_MARKET_DATA_PROVIDER", "newma-desk"
        ).strip().lower()
        provider = (
            "newma-desk"
            if configured_provider in {"newma-desk", "newma", "vibedesk"}
            else configured_provider
        )
        metadata_ready, dependencies = _analysis_dependency_readiness()
        if metadata_ready:
            native_runtime = _native_analysis_runtime_readiness()
        else:
            native_runtime = {
                "status": "not_checked",
                "reason": "distribution_metadata_not_ready",
                "exit_code": None,
                "isolation": "subprocess",
            }
        dependencies_ready = metadata_ready and native_runtime["status"] == "ready"
        market_data = _market_data_readiness()
        market_data_ready = market_data.get("status") == "ready"
        health = {
            "status": "ok" if dependencies_ready else "unavailable",
            "service": "instock-analysis",
            "api_version": API_VERSION,
            "bridge_protocol": BRIDGE_PROTOCOL,
            "time": datetime.now().astimezone().isoformat(timespec="seconds"),
            "database_required": False,
            "runtime": {
                "mode": "newma-desk-attached",
                "lifecycle_owner": "newma-desk",
                "standalone_deployment": False,
                "instance": {
                    "id": _PROCESS_INSTANCE_ID,
                    "started_at": _PROCESS_STARTED_AT,
                    "uptime_seconds": round(
                        max(time.monotonic() - _PROCESS_STARTED_MONOTONIC, 0.0), 3
                    ),
                },
                "state": _volatile_runtime_state(),
            },
            "market_data": {
                "provider": provider,
                "configured": configured_provider in {
                    "newma-desk", "newma", "vibedesk", "instock"
                },
                "configured_as": configured_provider,
                **market_data,
            },
            "readiness": {
                "status": "ready" if dependencies_ready else "not_ready",
                "analysis_dependencies": dependencies_ready,
                "market_data": market_data_ready,
                "distribution_metadata": metadata_ready,
                "native_runtime": native_runtime,
                "check_mode": "distribution_metadata_and_isolated_import",
            },
            "dependencies": dependencies,
        }
        if not dependencies_ready:
            self.write_error(
                503,
                "analysis_dependencies_not_ready",
                "CZSC analysis runtime dependencies are missing or incompatible",
                details=health,
            )
            return
        self.write_success(health)


class IntegrationCapabilitiesHandler(AnalysisApiHandler):
    def get(self) -> None:
        self.write_success({
            "service": "instock-analysis",
            "runtime": {
                "mode": "newma-desk-attached",
                "lifecycle_owner": "newma-desk",
                "workspace_runtime_id": "instock",
                "standalone_deployment": False,
            },
            "compatibility": {
                "level": 2,
                "name": "Connected Mod",
                "bridge_protocol": BRIDGE_PROTOCOL,
                "connected_actions": True,
            },
            "discovery": {
                "suite": "/.well-known/newma-desk-suite.json",
                "legacy_suite_paths": [
                    "/.well-known/newma-dock-suite.json",
                    "/.well-known/vibedesk-suite.json",
                ],
            },
            "pages": [
                {
                    "id": "market-workbench",
                    "mod_id": "instock-market-workbench",
                    "path": "/mods/market-workbench",
                    "minimum_width": 320,
                },
                {
                    "id": "market-map",
                    "mod_id": "instock-market-map",
                    "path": "/mods/market-map",
                    "minimum_width": 320,
                },
                {
                    "id": "czsc-analysis",
                    "mod_id": "instock-czsc",
                    "path": "/mods/czsc",
                    "minimum_width": 320,
                },
                {
                    "id": "sector-etf-rotation",
                    "mod_id": "instock-rotation",
                    "path": "/mods/rotation",
                    "minimum_width": 320,
                },
                {
                    "id": "industry-chain-research",
                    "mod_id": "instock-industry-chain",
                    "path": "/mods/industry-chain",
                    "minimum_width": 320,
                },
                {
                    "id": "stock-candidates",
                    "mod_id": "instock-stock-candidates",
                    "path": "/mods/stock-candidates",
                    "minimum_width": 320,
                },
                {
                    "id": "technical-signals",
                    "mod_id": "instock-technical-signals",
                    "path": "/mods/technical-signals",
                    "minimum_width": 320,
                },
                {
                    "id": "stock-research",
                    "mod_id": "instock-stock-research",
                    "path": "/mods/stock-research",
                    "minimum_width": 320,
                },
                {
                    "id": "strategy-validation",
                    "mod_id": "instock-strategy-validation",
                    "path": "/mods/strategy-validation",
                    "minimum_width": 320,
                },
                {
                    "id": "event-flow",
                    "mod_id": "instock-event-flow",
                    "path": "/mods/event-flow",
                    "minimum_width": 320,
                },
                {
                    "id": "research-book",
                    "mod_id": "instock-research-book",
                    "path": "/mods/research-book",
                    "minimum_width": 320,
                },
            ],
            "apis": [
                {
                    "id": "analysis.market-workbench",
                    "method": "GET",
                    "path": "/api/v1/market-workbench/snapshots",
                    "parameters": {"scanLimit": [50, 100, 200]},
                    "refresh": "0|1",
                    "data_access": "Desk market.overview, market.emotion and market.scan only",
                    "calibration": "latest cross-sectional market tape; not trade signal",
                },
                {
                    "id": "analysis.market-map",
                    "method": "GET",
                    "path": "/api/v1/market-maps/snapshots",
                    "parameters": {"capacity": [100, 500]},
                    "refresh": "0|1",
                    "data_access": "Desk market.scan ranked results only",
                    "calibration": "Top100 is market-cap ranked; Top500 is a deduplicated multi-ranking coverage pool, not full-market or market-cap Top500",
                },
                {
                    "id": "analysis.czsc",
                    "method": "GET",
                    "path": "/api/v1/czsc/analyses",
                    "parameters": {
                        "code": "symbol",
                        "period": "daily|weekly|monthly",
                        "bars": [120, 240, 480, 800],
                        "asOf": "YYYY-MM-DD (optional)",
                        "refresh": "0|1",
                    },
                },
                {
                    "id": "analysis.czsc.scan",
                    "method": "POST",
                    "path": "/api/v1/czsc/scans",
                    "resource_path": "/api/v1/czsc/scans/{scan_id}",
                    "cancel_method": "DELETE",
                    "parameters": {
                        "symbols": "1..20 unique CN symbols",
                        "period": "daily|weekly|monthly",
                        "bars": [120, 240, 480, 800],
                        "maxWorkers": "1..4",
                        "asOf": "YYYY-MM-DD (optional)",
                    },
                    "lifecycle": "process-memory; bounded; cancellable; cleared on restart",
                },
                {
                    "id": "analysis.rotation",
                    "method": "GET",
                    "path": "/api/v1/rotations/snapshots",
                    "parameters": {
                        "window": [40, 60, 120],
                        "benchmark": "symbol",
                        "refresh": "0|1",
                        "asOf": "YYYY-MM-DD (optional)",
                    },
                },
                {
                    "id": "analysis.rotation.experiment",
                    "method": "GET",
                    "path": "/api/v1/rotations/experiments",
                    "parameters": {
                        "benchmark": "symbol",
                        "rebalanceDays": [5, 10, 20],
                        "costBps": [10, 25, 50],
                        "refresh": "0|1",
                        "asOf": "YYYY-MM-DD (optional)",
                    },
                    "validation": "65% chronological training / 35% out-of-sample holdout",
                },
                {
                    "id": "analysis.industry-chain",
                    "method": "POST",
                    "path": "/api/v1/industry-chain/research",
                    "parameters": {
                        "schema_version": "2.0",
                        "theme": "research theme",
                        "market": "CN|HK|US|TW|JP|KR|EU|GLOBAL",
                        "as_of": "YYYY-MM-DD",
                        "evidence": "1..300 host-supplied evidence records",
                        "chain": "1..60 nodes and 0..120 relationships",
                        "layers": "1..20 scarce-layer assessments",
                        "candidates": "1..100 public-company assessments",
                    },
                    "data_access": "host-supplied packet only; no project-side browsing",
                    "calibration": "research-priority heuristic; not return forecast",
                },
                {
                    "id": "analysis.stock-candidates",
                    "method": "GET",
                    "path": "/api/v1/stock-candidates/snapshots",
                    "parameters": {
                        "market": ["CN", "HK", "CN_HK"],
                        "universeMode": ["broad", "quick"],
                        "universeSize": [30, 50, 100, 200],
                        "outputSize": [10, 20, 30],
                        "bars": [120, 240],
                        "advancedFilters": "market, technical and Desk fundamental constraints",
                        "refresh": "0|1",
                    },
                    "data_access": "Desk market.scan, market.quotes, market.ohlcv, research.equity-comparison and research.equity-snapshot fallback",
                    "calibration": "two-stage research ranking; not trade signal",
                },
                {
                    "id": "analysis.technical-signals",
                    "method": "GET",
                    "path": "/api/v1/technical-signals/snapshots",
                    "parameters": {
                        "market": ["CN", "HK", "CN_HK"],
                        "universeMode": ["broad", "quick"],
                        "universeSize": [30, 50, 100, 200],
                        "bars": [120, 260],
                        "filters": "industry, liquidity, valuation, ROE, growth, direction, pattern and classic strategy hard rules",
                        "maxWorkers": "1..8",
                        "refresh": "0|1",
                    },
                    "data_access": "Desk multi-axis market.scan, CN/HK market.ohlcv, research.equity-comparison and bounded research.equity-snapshot fallback",
                    "calibration": "hard-rule stock screening with indicator, candlestick and deterministic strategy evidence; not trade advice",
                },
                {
                    "id": "analysis.stock-research",
                    "method": "GET",
                    "path": "/api/v1/stock-research/dossiers",
                    "parameters": {
                        "symbol": "CN symbol",
                        "period": "daily|weekly|monthly",
                        "bars": [120, 240, 480, 800],
                        "asOf": "YYYY-MM-DD (optional)",
                        "industryChainSnapshotId": "optional analysis snapshot reference",
                        "refresh": "0|1",
                    },
                    "data_access": "Desk equity snapshot, disclosures and market.ohlcv",
                    "calibration": "auditable research dossier; not rating or trade signal",
                },
                {
                    "id": "analysis.strategy-validation",
                    "method": "POST",
                    "path": "/api/v1/strategy-validations",
                    "parameters": {
                        "schema_version": "instock-strategy-validation-packet-v1",
                        "source_module": "stock-candidates|czsc|rotation",
                        "as_of": "YYYY-MM-DD",
                        "benchmark": "symbol",
                        "holding_period_sessions": "1..60",
                        "cost_bps_per_side": "0..100",
                        "signals": "2..200 point-in-time decisions",
                    },
                    "data_access": "Desk market.ohlcv only",
                    "calibration": "next-open execution and chronological out-of-sample validation",
                },
                {
                    "id": "analysis.event-flow",
                    "method": "POST",
                    "path": "/api/v1/event-flows",
                    "parameters": {
                        "input_modes": ["Desk A-share symbol", "host event packet"],
                        "symbol": "6-digit CN symbol (optional SH/SZ/BJ suffix)",
                        "asOf": "YYYY-MM-DD (optional latest-window client filter)",
                        "packet": "instock-event-flow-packet-v1 with 1..500 events",
                    },
                    "data_access": "Desk Research HTTP Interface plus market announcement/report/news capabilities",
                    "calibration": "source coverage, objective flow direction, evidence and freshness priority; not return forecast",
                },
                {
                    "id": "analysis.research-book",
                    "method": "POST",
                    "path": "/api/v1/research-books",
                    "parameters": {
                        "schema_version": "instock-research-book-packet-v1",
                        "name": "research book name",
                        "as_of": "YYYY-MM-DD",
                        "items": "1..100 research positions with reasons and invalidation",
                    },
                    "data_access": "host context and analysis snapshot references only",
                    "calibration": "research exposure and risk summary; no storage or trading",
                },
                {
                    "id": "analysis.rotation.supply-chain",
                    "method": "POST",
                    "path": "/api/v1/rotations/supply-chain-research",
                    "parameters": {
                        "schema_version": "1.0",
                        "theme": "research theme",
                        "market": "CN|HK|US|TW|JP|KR|EU|GLOBAL",
                        "as_of": "YYYY-MM-DD",
                        "evidence": "1..300 host-supplied evidence records",
                        "layers": "1..20 scarce-layer assessments",
                        "candidates": "1..100 public-company assessments",
                    },
                    "data_access": "host-supplied packet only; no project-side browsing",
                    "calibration": "research-priority heuristic; not return forecast",
                },
                {
                    "id": "analysis.snapshot",
                    "method": "GET",
                    "path": "/api/v1/analysis-snapshots/{snapshot_id}",
                    "parameters": {"snapshot_id": "stable analysis snapshot id"},
                    "persistence": "process-memory; bounded TTL; cleared on restart",
                },
            ],
            "data_boundary": {
                "runtime_dependency": "MarketDataProvider",
                "default_provider": "newma-desk",
                "browser_secrets": False,
                "historical_replay": {
                    "mode": "latest-800-bars-client-filter",
                    "native_as_of": False,
                    "snapshot_schema": "1.0",
                    "snapshot_query": "/api/v1/analysis-snapshots/{snapshot_id}",
                },
                "batch_scan": {
                    "maximum_symbols": 20,
                    "maximum_workers_per_task": 4,
                    "maximum_active_tasks_default": 2,
                    "cancellation_limit": "does not interrupt an already running upstream HTTP request",
                },
                "rotation_experiment": {
                    "maximum_bars": 800,
                    "parameter_variants": 9,
                    "signal_timing": "close_t_to_next_session_open",
                    "historical_industry_factor": "neutral_no_lookahead",
                    "minimum_evidence": {"coverage_years": 5, "out_of_sample_trades": 30},
                    "known_bias": "fixed current ETF universe has survivorship bias",
                },
                "supply_chain_research": {
                    "input": "point-in-time evidence packet from Newma-Desk Agent/Data",
                    "project_side_fetching": False,
                    "maximum_layers": 20,
                    "maximum_candidates": 100,
                    "maximum_evidence_records": 300,
                    "score_semantics": "research_priority_not_trade_signal",
                },
                "industry_chain_research": {
                    "input": "point-in-time topology and evidence packet from Newma-Desk Agent/Data",
                    "project_side_fetching": False,
                    "maximum_nodes": 60,
                    "maximum_links": 120,
                    "maximum_layers": 20,
                    "maximum_candidates": 100,
                    "score_semantics": "bottleneck_and_research_priority_not_trade_signal",
                },
                "stock_candidates": {
                    "universe_source": "newma-desk CN/HK multi-axis market.scan union",
                    "price_source": "newma-desk market.ohlcv qfq",
                    "fundamental_source": "newma-desk research.equity-comparison plus research.equity-snapshot fallback",
                    "maximum_universe": 200,
                    "maximum_fundamental_requests": 30,
                    "fundamental_batch_size": 4,
                    "fundamental_batch_workers": 3,
                    "fundamental_snapshot_workers": 3,
                    "fundamental_batch_timeout_seconds": 60,
                    "fundamental_snapshot_timeout_seconds": 20,
                    "factor_model": "instock-stock-candidate-score-v3",
                    "history_policy": "full>=80; confidence-adjusted-short=10..79; new-listing-watch<10",
                    "missing_fundamental_policy": "neutral_50",
                    "historical_replay": False,
                    "score_semantics": "research_candidate_not_trade_signal",
                },
                "market_workbench": {
                    "stock_source": "newma-desk market.scan",
                    "breadth_source": "newma-desk market.overview",
                    "emotion_source": "newma-desk market.emotion",
                    "boards": ["gainers", "losers", "amount", "turnover", "volume_ratio"],
                    "historical_replay": False,
                    "score_semantics": "market_snapshot_not_trade_signal",
                },
                "technical_signals": {
                    "universe_source": "newma-desk CN/HK multi-axis market.scan union",
                    "price_source": "newma-desk market.ohlcv qfq",
                    "fundamental_source": "newma-desk research.equity-comparison plus bounded research.equity-snapshot fallback",
                    "fundamental_batch_size": 8,
                    "fundamental_batch_workers": 2,
                    "fundamental_snapshot_fallback_limit": 30,
                    "missing_fundamental_policy": "exclude_when_filter_requested",
                    "strategy_count": 10,
                    "pattern_scope": "curated_explainable_candlestick_patterns",
                    "missing_evidence_policy": "explicit_unavailable_or_needs_evidence",
                    "high_tight_flag_confirmation": "positive institutional net amount from newma-desk capital.dragon-tiger after price setup",
                    "score_semantics": "technical_evidence_density_not_trade_advice",
                },
            },
        })
