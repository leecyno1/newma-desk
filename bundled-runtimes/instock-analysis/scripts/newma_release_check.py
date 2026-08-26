#!/usr/bin/env python3
"""One-command release gate for the Newma-Desk attached InStock suite.

The checker intentionally owns no process lifecycle and contains no Docker
path.  Offline checks validate this repository.  ``--live`` additionally uses
an existing Newma-Desk workspace and running stack for native compilation,
runtime certification and HTTP contract probes.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener


ROOT = Path(__file__).resolve().parents[1]
SUITE_PATH = ROOT / "integrations" / "newma-desk" / "instock-suite" / "suite.json"
STORE_PATH = ROOT / "integrations" / "newma-desk" / "store.json"
EXPECTED_HEALTH_DEPENDENCIES = {
    "czsc": "0.10.12",
    "TA-Lib": "0.6.8",
    "rs-czsc": "0.1.26.post260402",
}
EXPECTED_API_METRIC_ROUTES = {
    "/api/v1/health",
    "/api/v1/capabilities",
    "/api/v1/czsc/analyses",
    "/api/v1/czsc/scans",
    "/api/v1/czsc/scans/{scan_id}",
    "/api/v1/rotations/snapshots",
    "/api/v1/rotations/experiments",
    "/api/v1/rotations/supply-chain-research",
    "/api/v1/industry-chain/research",
    "/api/v1/stock-candidates/snapshots",
    "/api/v1/stock-research/dossiers",
    "/api/v1/strategy-validations",
    "/api/v1/event-flows",
    "/api/v1/research-books",
    "/api/v1/market-workbench/snapshots",
    "/api/v1/market-maps/snapshots",
    "/api/v1/technical-signals/snapshots",
    "/api/v1/analysis-history",
    "/api/v1/analysis-history/{history_id}",
    "/api/v1/analysis-snapshots/{snapshot_id}",
    "/api/v1/unmatched",
}
DELIVERY_SOURCE_PREFIXES = (
    ".github/workflows/",
    "docs/",
    "instock/",
    "integrations/",
    "scripts/",
    "tests/",
)
DELIVERY_ROOT_FILES = {
    ".gitignore",
    "CONTEXT.md",
    "README.md",
    "requirements.txt",
    "requirements-attached.txt",
    "requirements-attached.constraints.txt",
    "requirements-dev.txt",
}
_DIRECT_HTTP_OPENER = build_opener(ProxyHandler({}))


@dataclass(frozen=True)
class ProcessCheck:
    name: str
    command: tuple[str, ...]
    cwd: Path
    env: Mapping[str, str] = field(default_factory=dict)
    warn_on_miss: bool = False


@dataclass
class CheckResult:
    name: str
    status: str
    duration_seconds: float
    detail: str = ""
    warnings: list[str] = field(default_factory=list)


def _process_checks(root: Path, python: str) -> list[ProcessCheck]:
    native_probe = """
from instock.web.integration_api import _native_analysis_runtime_readiness
result = _native_analysis_runtime_readiness()
print(result)
raise SystemExit(0 if result.get('status') == 'ready' else 1)
""".strip()
    return [
        ProcessCheck("python-tests", (python, "-m", "pytest", "-q"), root),
        ProcessCheck("python-dependencies", (python, "-m", "pip", "check"), root),
        ProcessCheck("python-native-runtime", (python, "-c", native_probe), root),
        ProcessCheck(
            "python-compile",
            (python, "-m", "compileall", "-q", "instock", "tests", "scripts"),
            root,
        ),
        ProcessCheck(
            "bridge-javascript",
            ("node", "--check", "instock/web/static/js/vibedesk-bridge.js"),
            root,
        ),
        ProcessCheck("git-diff", ("git", "diff", "--check"), root),
    ]


def _newma_checks(root: Path, newma_workspace: Path) -> list[ProcessCheck]:
    compiler_source = """
import { pathToFileURL } from 'node:url';
import { loadModStore } from './scripts/lib/mod-store.mjs';
import { checkModManifest } from './scripts/check-mod-compatibility.mjs';
const store = await loadModStore({storeUrl: pathToFileURL(process.env.INSTOCK_RELEASE_STORE)});
const rows = store.mods.map((mod) => ({
  id: mod.id,
  version: mod.manifest.version,
  result: checkModManifest(mod.manifest),
}));
console.log(JSON.stringify({
  suites: store.suites.map((suite) => ({id: suite.id, version: suite.descriptor.version})),
  mods: rows,
}, null, 2));
if (rows.some((row) => row.result.contractStatus !== 'passed')) process.exitCode = 1;
""".strip()
    descriptor_source = """
import json
import os
from pathlib import Path
from vibe_visualization_api.data_services.models import DataServiceDescriptor
path = Path(os.environ['INSTOCK_RELEASE_DATA_SERVICE'])
descriptor = DataServiceDescriptor.model_validate(json.loads(path.read_text('utf-8')))
print(json.dumps({
    'id': descriptor.id,
    'base_url': str(descriptor.base_url),
    'health_path': descriptor.health_path,
    'transport': descriptor.transport,
    'capabilities': sorted(descriptor.capabilities),
}, ensure_ascii=False, indent=2))
""".strip()
    runtime_contract_source = """
import asyncio
import json
import os
from datetime import date
from pathlib import Path
from vibe_visualization_api.data_services.client import DataServiceClient
from vibe_visualization_api.data_services.models import DataServiceDescriptor

async def main():
    path = Path(os.environ['INSTOCK_RELEASE_DATA_SERVICE'])
    descriptor = DataServiceDescriptor.model_validate(json.loads(path.read_text('utf-8')))
    client = DataServiceClient(public_mode=False)
    calls = {
        'analysis.czsc': {'code': '300502', 'period': 'daily', 'bars': 120},
        'analysis.czsc.scan': {
            'symbols': ['300502'], 'period': 'daily', 'bars': 120, 'maxWorkers': 1,
        },
        'analysis.rotation': {'window': 60, 'benchmark': '510300', 'refresh': '0'},
        'analysis.rotation.experiment': {
            'benchmark': '510300', 'rebalanceDays': 10, 'costBps': 25, 'refresh': '0',
        },
        'analysis.market-workbench': {'scanLimit': 50},
        'analysis.market-map': {'capacity': 100},
        'analysis.stock-candidates': {
            'universeSize': 30, 'outputSize': 10, 'bars': 120,
        },
        'analysis.stock-research': {
            'symbol': '300502', 'period': 'daily', 'bars': 120,
        },
        'analysis.technical-signals': {
            'universeSize': 30, 'bars': 260, 'maxWorkers': 4,
        },
        'analysis.strategy-validation': {
            'schema_version': 'instock-strategy-validation-packet-v1',
            'strategy': {'id': 'release-probe', 'name': 'release probe', 'source_module': 'czsc'},
            'as_of': date.today().isoformat(), 'benchmark': '510300',
            'holding_period_sessions': 5, 'cost_bps_per_side': 25,
            'signals': [
                {'decision_date': '2026-06-02', 'symbols': ['300502']},
                {'decision_date': '2026-06-16', 'symbols': ['300502']},
                {'decision_date': '2026-06-30', 'symbols': ['300502']},
                {'decision_date': '2026-07-14', 'symbols': ['300502']},
            ],
        },
        'analysis.event-flow': {
            'symbol': '300502',
        },
        'analysis.research-book': {
            'schema_version': 'instock-research-book-packet-v1',
            'name': 'release probe', 'as_of': date.today().isoformat(),
            'items': [{
                'symbol': '300502', 'name': 'probe', 'market': 'CN', 'sector': '通信',
                'target_weight_pct': 10, 'thesis': 'contract probe thesis',
                'invalidation': ['probe invalidation'], 'risk_tags': ['probe risk'],
                'snapshot_ids': [],
            }],
        },
        'analysis.industry-chain': {
            'schema_version': '2.0',
            'theme': 'attached runtime contract probe',
            'market': 'CN',
            'as_of': date.today().isoformat(),
            'evidence': [{
                'id': 'probe-evidence', 'claim': 'host supplied contract evidence',
                'strength': 'strong', 'source_type': 'runtime_probe',
                'source_ref': 'newma://release-check/probe',
                'observed_at': date.today().isoformat(),
            }],
            'chain': {
                'nodes': [{
                    'id': 'probe-layer', 'name': 'probe layer',
                    'stage': 'midstream',
                    'role': 'contract-only deterministic probe',
                    'evidence_ids': ['probe-evidence'],
                }],
                'links': [],
            },
            'layers': [{
                'id': 'probe-layer', 'name': 'probe layer',
                'node_id': 'probe-layer',
                'constraint': 'contract-only deterministic probe',
                'ratings': {
                    'demand_pressure': 3, 'chokepoint_severity': 3,
                    'supplier_concentration': 3, 'expansion_difficulty': 3,
                    'substitution_difficulty': 3,
                },
                'evidence_ids': ['probe-evidence'],
            }],
            'candidates': [{
                'symbol': '300502.SZ', 'name': 'probe candidate', 'market': 'CN',
                'layer_id': 'probe-layer',
                'ratings': {
                    'exposure_purity': 3, 'valuation_disconnect': 3,
                    'catalyst_timing': 3, 'financial_resilience': 3,
                },
                'penalties': {
                    'dilution_financing': 0, 'governance': 0, 'geopolitics': 0,
                    'liquidity': 0, 'hype_risk': 0, 'accounting_quality': 0,
                    'cyclicality': 0, 'alternative_design_risk': 0,
                },
                'evidence_ids': ['probe-evidence'],
                'invalidation': ['host evidence becomes stale'],
            }],
        },
    }
    summary = {}
    for capability_id, input_data in calls.items():
        result = await client.invoke(descriptor, capability_id, input_data)
        data = result.get('data') or {}
        if capability_id == 'analysis.czsc':
            summary[capability_id] = {
                'analysis_version': ((data.get('engine') or {}).get('analysis_version')),
                'snapshot_id': ((data.get('snapshot') or {}).get('snapshot_id')),
            }
        elif capability_id == 'analysis.czsc.scan':
            summary[capability_id] = {
                'scan_id': data.get('scan_id'), 'status': data.get('status'),
            }
        elif capability_id == 'analysis.rotation':
            summary[capability_id] = {
                'successful_count': data.get('successful_count'),
                'market_breadth': ((data.get('market_breadth') or {}).get('breadth')),
            }
        elif capability_id == 'analysis.rotation.experiment':
            summary[capability_id] = {
                'verdict': ((data.get('verdict') or {}).get('state')),
                'variants': len(data.get('parameter_surface') or []),
                'stress_tests': len(data.get('stress_tests') or []),
            }
        elif capability_id == 'analysis.market-workbench':
            summary[capability_id] = {
                'data_state': data.get('data_state'),
                'boards': len(data.get('leaderboards') or {}),
                'snapshot_id': ((data.get('snapshot') or {}).get('snapshot_id')),
            }
        elif capability_id == 'analysis.market-map':
            summary[capability_id] = {
                'data_state': data.get('data_state'),
                'securities': ((data.get('coverage') or {}).get('displayed_securities')),
                'pool_kind': ((data.get('coverage') or {}).get('pool_kind')),
                'snapshot_id': ((data.get('snapshot') or {}).get('snapshot_id')),
            }
        elif capability_id == 'analysis.stock-candidates':
            summary[capability_id] = {
                'data_state': data.get('data_state'),
                'candidates': len(data.get('candidates') or []),
                'top_symbol': ((data.get('summary') or {}).get('top_symbol')),
                'fundamental_available': ((data.get('coverage') or {}).get('fundamental_available_count')),
                'factors': sorted(((data.get('factor_model') or {}).get('weights') or {}).keys()),
                'snapshot_id': ((data.get('snapshot') or {}).get('snapshot_id')),
            }
        elif capability_id == 'analysis.stock-research':
            summary[capability_id] = {
                'data_state': data.get('data_state'),
                'symbol': ((data.get('identity') or {}).get('symbol')),
                'technical_bias': ((data.get('assessment') or {}).get('technical_bias')),
                'snapshot_id': ((data.get('snapshot') or {}).get('snapshot_id')),
            }
        elif capability_id == 'analysis.technical-signals':
            summary[capability_id] = {
                'data_state': data.get('data_state'),
                'rows': len(data.get('rows') or []),
                'failed_count': ((data.get('coverage') or {}).get('failed_count')),
                'short_history_watch_count': ((data.get('coverage') or {}).get('short_history_watch_count')),
                'strategies': len(((data.get('catalog') or {}).get('strategies')) or []),
                'snapshot_id': ((data.get('snapshot') or {}).get('snapshot_id')),
            }
        elif capability_id == 'analysis.strategy-validation':
            summary[capability_id] = {
                'verdict': data.get('verdict'),
                'executed_signals': ((data.get('coverage') or {}).get('executed_signals')),
                'snapshot_id': ((data.get('snapshot') or {}).get('snapshot_id')),
            }
        elif capability_id == 'analysis.event-flow':
            summary[capability_id] = {
                'events': ((data.get('summary') or {}).get('deduplicated_events')),
                'sources': ((data.get('coverage') or {}).get('requested_sources')),
                'failed_sources': ((data.get('coverage') or {}).get('failed_sources')),
                'snapshot_id': ((data.get('snapshot') or {}).get('snapshot_id')),
            }
        elif capability_id == 'analysis.research-book':
            summary[capability_id] = {
                'items': ((data.get('summary') or {}).get('items')),
                'snapshot_id': ((data.get('snapshot') or {}).get('snapshot_id')),
            }
        else:
            summary[capability_id] = {
                'data_state': data.get('data_state'),
                'layers': len(data.get('layers') or []),
                'candidates': len(data.get('candidates') or []),
                'snapshot_id': ((data.get('snapshot') or {}).get('snapshot_id')),
            }
    print(json.dumps(summary, ensure_ascii=False, indent=2))

asyncio.run(main())
""".strip()
    api_python = newma_workspace / "services" / "api" / ".venv" / "bin" / "python"
    descriptor_env = {"INSTOCK_RELEASE_DATA_SERVICE": str(
        root / "integrations" / "newma-desk" / "data-service.json"
    )}
    theme_files = (
        root / "instock" / "web" / "templates" / "czsc_chart.html",
        root / "instock" / "web" / "templates" / "rotation.html",
        root / "instock" / "web" / "templates" / "industry_chain.html",
        root / "instock" / "web" / "templates" / "stock_candidates.html",
        root / "instock" / "web" / "templates" / "stock_research.html",
        root / "instock" / "web" / "templates" / "strategy_validation.html",
        root / "instock" / "web" / "templates" / "event_flow.html",
        root / "instock" / "web" / "templates" / "research_book.html",
        root / "instock" / "web" / "templates" / "market_workbench.html",
        root / "instock" / "web" / "templates" / "technical_signals.html",
        root / "instock" / "web" / "static" / "css" / "vibedesk-theme.css",
        root / "instock" / "web" / "static" / "js" / "vibedesk-bridge.js",
    )
    return [
        ProcessCheck(
            "newma-suite-compiler",
            ("node", "--input-type=module", "-e", compiler_source),
            newma_workspace,
            {"INSTOCK_RELEASE_STORE": str(STORE_PATH)},
        ),
        ProcessCheck(
            "newma-data-service-descriptor",
            (str(api_python), "-c", descriptor_source),
            newma_workspace,
            descriptor_env,
        ),
        ProcessCheck(
            "newma-theme",
            ("npm", "run", "mods:theme:check", "--", *(str(path) for path in theme_files)),
            newma_workspace,
        ),
        ProcessCheck(
            "newma-core-stack-status",
            ("npm", "run", "dev:status"),
            newma_workspace,
            warn_on_miss=True,
        ),
        ProcessCheck(
            "newma-data-service-runtime-contracts",
            (str(api_python), "-c", runtime_contract_source),
            newma_workspace,
            descriptor_env,
        ),
        ProcessCheck(
            "newma-level-two-certification",
            (
                "npm", "run", "mods:certify", "--", "--mod",
                "instock-czsc,instock-rotation",
            ),
            newma_workspace,
        ),
    ]


def _run_process(check: ProcessCheck) -> CheckResult:
    started = time.monotonic()
    print(f"RUN  {check.name}", flush=True)
    environment = os.environ.copy()
    environment.update(check.env)
    try:
        completed = subprocess.run(
            check.command,
            cwd=check.cwd,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
    except OSError as exc:
        return CheckResult(
            name=check.name,
            status="failed",
            duration_seconds=round(time.monotonic() - started, 3),
            detail=str(exc),
        )
    detail = completed.stdout.strip()
    status = "passed" if completed.returncode == 0 else "failed"
    warnings = [
        line.strip() for line in detail.splitlines()
        if line.strip().startswith("MISS ")
    ]
    if (
        check.warn_on_miss
        and status == "failed"
        and warnings
        and not any(
            "InStock Analysis" in warning or "Newma-Desk API" in warning
            for warning in warnings
        )
        and "Error:" not in detail
        and "FAIL " not in detail
    ):
        status = "passed"
    print(f"{status.upper():4} {check.name} ({time.monotonic() - started:.2f}s)")
    if detail:
        print(detail)
    if not check.warn_on_miss:
        warnings = []
    return CheckResult(
        name=check.name,
        status=status,
        duration_seconds=round(time.monotonic() - started, 3),
        detail=detail,
        warnings=warnings,
    )


def _json_and_delivery_check(root: Path) -> CheckResult:
    started = time.monotonic()
    errors: list[str] = []
    constraints = root / "requirements-attached.constraints.txt"
    if not constraints.is_file():
        errors.append("attached runtime constraints snapshot is missing")
    else:
        constraint_source = constraints.read_text("utf-8").lower()
        for dependency, version in EXPECTED_HEALTH_DEPENDENCIES.items():
            normalized = dependency.lower()
            if f"{normalized}=={version.lower()}" not in constraint_source:
                errors.append(
                    f"attached constraints omitted certified dependency {dependency}=={version}"
                )
    json_files = sorted((root / "integrations").rglob("*.json"))
    for path in json_files:
        try:
            json.loads(path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{path.relative_to(root)}: {exc}")
    forbidden = [
        root / "docker",
        root / ".github" / "workflows" / "docker-image.yml",
        root / ".github" / "workflows" / "azure-container-webapp.yml",
    ]
    errors.extend(
        f"forbidden standalone deployment asset exists: {path.relative_to(root)}"
        for path in forbidden
        if path.exists()
    )
    untracked_delivery_files = _untracked_delivery_files(root)
    if untracked_delivery_files:
        errors.append(
            "untracked delivery files would be missing from a clean checkout: "
            + ", ".join(untracked_delivery_files[:20])
        )
    detail = f"validated {len(json_files)} JSON descriptors; Docker assets absent"
    if errors:
        detail = "\n".join(errors)
    result = CheckResult(
        name="delivery-contract",
        status="failed" if errors else "passed",
        duration_seconds=round(time.monotonic() - started, 3),
        detail=detail,
    )
    print(f"{result.status.upper():4} {result.name}\n{result.detail}")
    return result


def _request_json(url: str, timeout: float = 90.0) -> tuple[int, Any]:
    request = Request(url, headers={"Accept": "application/json"})
    try:
        with _DIRECT_HTTP_OPENER.open(request, timeout=timeout) as response:
            return int(response.status), json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            payload: Any = json.loads(body)
        except json.JSONDecodeError:
            payload = body
        return int(exc.code), payload


def _request_status(url: str, timeout: float = 30.0) -> int:
    request = Request(url, headers={"Accept": "text/html,application/json"})
    try:
        with _DIRECT_HTTP_OPENER.open(request, timeout=timeout) as response:
            return int(response.status)
    except HTTPError as exc:
        return int(exc.code)


def _request_json_post(
    url: str,
    payload: Mapping[str, Any],
    timeout: float = 90.0,
) -> tuple[int, Any]:
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with _DIRECT_HTTP_OPENER.open(request, timeout=timeout) as response:
            return int(response.status), json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            response_payload: Any = json.loads(body)
        except json.JSONDecodeError:
            response_payload = body
        return int(exc.code), response_payload


def _nested(value: Mapping[str, Any], *keys: str) -> Any:
    current: Any = value
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _health_contract_errors(status: int, payload: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if status != 200 or payload.get("ok") is not True:
        errors.append(f"health failed: HTTP {status}")
        return errors

    health = _nested(payload, "data") or {}
    if health.get("status") != "ok":
        errors.append("health status is not ok")
    if _nested(health, "runtime", "mode") != "newma-desk-attached":
        errors.append("health runtime mode is not newma-desk-attached")
    if not _nested(health, "runtime", "instance", "id"):
        errors.append("health runtime instance id is missing")
    if not _nested(health, "runtime", "instance", "started_at"):
        errors.append("health runtime start time is missing")
    if _nested(health, "runtime", "state", "volatile_state_cleared_on_restart") is not True:
        errors.append("health runtime does not declare volatile restart behavior")
    for state_name in (
        "analysis_snapshots", "czsc_scans", "rotation_snapshots",
        "rotation_experiments", "api_requests",
    ):
        if _nested(health, "runtime", "state", state_name, "volatile") is not True:
            errors.append(f"health runtime state {state_name} is not declared volatile")
    if _nested(health, "runtime", "state", "analysis_history", "storage") != "sqlite":
        errors.append("health analysis history is not sqlite-backed")
    if _nested(health, "runtime", "state", "analysis_history", "volatile") is not False:
        errors.append("health analysis history is not declared persistent")
    if _nested(health, "runtime", "state", "analysis_history", "cleared_on_restart") is not False:
        errors.append("health analysis history is cleared on restart")
    if _nested(health, "runtime", "state", "sector_fund_flow_history", "storage") != "sqlite":
        errors.append("health sector fund-flow history is not sqlite-backed")
    if _nested(health, "runtime", "state", "sector_fund_flow_history", "volatile") is not False:
        errors.append("health sector fund-flow history is not persistent")
    if _nested(health, "runtime", "state", "api_requests", "route_labels") != "fixed_templates":
        errors.append("health API metrics do not use fixed route templates")
    api_metrics = _nested(health, "runtime", "state", "api_requests") or {}
    totals = api_metrics.get("totals") or {}
    if not isinstance(totals.get("requests"), int) or totals.get("requests", -1) < 0:
        errors.append("health API metrics request total is invalid")
    for label, metric in (api_metrics.get("routes") or {}).items():
        try:
            _, route = label.split(" ", 1)
        except ValueError:
            errors.append(f"health API metric label is malformed: {label}")
            continue
        if route not in EXPECTED_API_METRIC_ROUTES:
            errors.append(f"health API metric route is not a fixed template: {route}")
        latency = metric.get("latency_ms") or {}
        if not isinstance(latency.get("sample_size"), int):
            errors.append(f"health API metric latency sample is invalid: {label}")
    if _nested(health, "readiness", "status") != "ready":
        errors.append("health readiness is not ready")
    if _nested(health, "readiness", "analysis_dependencies") is not True:
        errors.append("health analysis dependencies are not ready")
    if _nested(health, "readiness", "market_data") is not True:
        errors.append("health Desk market data is not ready")
    if _nested(health, "market_data", "status") != "ready":
        errors.append("health Desk market data probe is unavailable")
    if _nested(health, "readiness", "distribution_metadata") is not True:
        errors.append("health distribution metadata is not ready")
    if _nested(health, "readiness", "native_runtime", "status") != "ready":
        errors.append("health native analysis runtime is not ready")
    if _nested(health, "readiness", "native_runtime", "isolation") != "subprocess":
        errors.append("health native analysis runtime was not checked in isolation")

    dependencies = health.get("dependencies") or {}
    for package, expected_version in EXPECTED_HEALTH_DEPENDENCIES.items():
        dependency = dependencies.get(package) or {}
        installed_version = dependency.get("installed_version")
        if dependency.get("status") != "ready":
            errors.append(f"health dependency {package} is not ready")
        if installed_version != expected_version:
            errors.append(
                f"health dependency {package} version mismatch: "
                f"runtime={installed_version}, certified={expected_version}"
            )
    return errors


def _live_contract_check(base_url: str) -> CheckResult:
    started = time.monotonic()
    base = base_url.rstrip("/")
    errors: list[str] = []
    warnings: list[str] = []
    suite = json.loads(SUITE_PATH.read_text("utf-8"))

    try:
        health_status, health = _request_json(f"{base}/api/v1/health", timeout=30)
        errors.extend(_health_contract_errors(health_status, health))

        suite_status, discovery = _request_json(
            f"{base}/.well-known/newma-desk-suite.json", timeout=30
        )
        if not isinstance(discovery, Mapping):
            errors.append(
                f"suite discovery returned a non-object payload: HTTP {suite_status}"
            )
        elif suite_status != 200 or discovery.get("version") != suite.get("version"):
            errors.append(
                f"suite discovery mismatch: HTTP {suite_status}, "
                f"runtime={discovery.get('version')}, source={suite.get('version')}"
            )

        for route in ("/mods/market-workbench", "/mods/market-map", "/mods/stock-candidates", "/mods/technical-signals", "/mods/czsc", "/mods/rotation", "/mods/industry-chain", "/mods/stock-research", "/mods/strategy-validation", "/mods/event-flow", "/mods/research-book"):
            status = _request_status(f"{base}{route}")
            if status != 200:
                errors.append(f"{route} returned HTTP {status}")
        legacy_status = _request_status(f"{base}/instock/data")
        if legacy_status != 404:
            errors.append(f"attached runtime leaked /instock/data as HTTP {legacy_status}")

        analysis_query = urlencode({"code": "300502", "period": "daily", "bars": 120})
        analysis_status, analysis = _request_json(
            f"{base}/api/v1/czsc/analyses?{analysis_query}"
        )
        provenance = _nested(analysis, "data", "snapshot", "provenance") or {}
        if analysis_status != 200 or analysis.get("ok") is not True:
            errors.append(f"CZSC live analysis failed: HTTP {analysis_status}")
        if provenance.get("provider") != "newma-desk":
            errors.append("CZSC provenance provider is not newma-desk")
        if provenance.get("adjust") != "qfq":
            errors.append("CZSC live analysis is not confirmed qfq")
        if not provenance.get("upstream_source"):
            errors.append("CZSC live analysis omitted upstream_source")

        rotation_query = urlencode({"window": 60, "benchmark": "510300", "refresh": 0})
        rotation_status, rotation = _request_json(
            f"{base}/api/v1/rotations/snapshots?{rotation_query}"
        )
        if rotation_status != 200 or rotation.get("ok") is not True:
            errors.append(f"rotation live analysis failed: HTTP {rotation_status}")
        if int(_nested(rotation, "data", "successful_count") or 0) < 1:
            errors.append("rotation returned no successful ETF candidates")
        breadth_state = _nested(rotation, "data", "market_breadth", "state")
        if breadth_state != "available":
            warnings.append("Desk aggregate market breadth is currently unavailable")
        if _nested(rotation, "data", "data_state") == "partial":
            warnings.extend(str(item) for item in (_nested(rotation, "data", "warnings") or []))

        market_query = urlencode({"scanLimit": 50})
        market_status, market = _request_json(
            f"{base}/api/v1/market-workbench/snapshots?{market_query}", timeout=90
        )
        if market_status != 200 or market.get("ok") is not True:
            errors.append(f"market-workbench live analysis failed: HTTP {market_status}")
        if _nested(market, "data", "engine", "name") != "instock-market-workbench":
            errors.append("market-workbench live analysis returned the wrong engine")
        if int(_nested(market, "data", "coverage", "successful_boards") or 0) < 1:
            errors.append("market-workbench returned no successful market board")

        market_map_query = urlencode({"capacity": 100})
        market_map_status, market_map = _request_json(
            f"{base}/api/v1/market-maps/snapshots?{market_map_query}", timeout=90
        )
        if market_map_status != 200 or market_map.get("ok") is not True:
            errors.append(f"market-map live analysis failed: HTTP {market_map_status}")
        if _nested(market_map, "data", "engine", "name") != "instock-market-map":
            errors.append("market-map live analysis returned the wrong engine")
        if int(_nested(market_map, "data", "coverage", "displayed_securities") or 0) < 1:
            errors.append("market-map returned no displayed securities")

        industry_packet = json.loads((
            ROOT / "integrations" / "newma-desk" / "examples" /
            "supply-chain-research.packet.json"
        ).read_text("utf-8"))
        industry_status, industry = _request_json_post(
            f"{base}/api/v1/industry-chain/research", industry_packet
        )
        if industry_status != 200 or industry.get("ok") is not True:
            errors.append(f"industry-chain live analysis failed: HTTP {industry_status}")
        if _nested(industry, "data", "engine", "name") != "instock-industry-chain-research":
            errors.append("industry-chain live analysis returned the wrong engine")
        if int(_nested(industry, "data", "summary", "chain_node_count") or 0) < 1:
            errors.append("industry-chain live analysis returned no chain nodes")

        candidate_query = urlencode({"universeSize": 30, "outputSize": 10, "bars": 120})
        candidate_status, candidates = _request_json(
            f"{base}/api/v1/stock-candidates/snapshots?{candidate_query}", timeout=120
        )
        if candidate_status != 200 or candidates.get("ok") is not True:
            errors.append(f"stock-candidates live analysis failed: HTTP {candidate_status}")
        if _nested(candidates, "data", "engine", "name") != "instock-stock-candidate-engine":
            errors.append("stock-candidates live analysis returned the wrong engine")
        if int(_nested(candidates, "data", "coverage", "analyzed_count") or 0) < 1:
            errors.append("stock-candidates returned no analyzed A-share candidates")
        if _nested(candidates, "data", "data_state") != "complete":
            errors.append("stock-candidates live analysis returned partial data")
        if int(_nested(candidates, "data", "coverage", "fundamental_available_count") or 0) < 1:
            errors.append("stock-candidates returned no available Desk financial snapshot")
        candidate_factors = set(
            (_nested(candidates, "data", "factor_model", "weights") or {}).keys()
        )
        if not {"quality", "growth"}.issubset(candidate_factors):
            errors.append("stock-candidates factor model omitted quality or growth")

        signal_query = urlencode({"universeSize": 30, "bars": 260, "maxWorkers": 4})
        signal_status, signals = _request_json(
            f"{base}/api/v1/technical-signals/snapshots?{signal_query}", timeout=120
        )
        if signal_status != 200 or signals.get("ok") is not True:
            errors.append(f"technical-signals live analysis failed: HTTP {signal_status}")
        if _nested(signals, "data", "engine", "name") != "instock-technical-signal-center":
            errors.append("technical-signals live analysis returned the wrong engine")
        if int(_nested(signals, "data", "coverage", "analyzed_count") or 0) < 1:
            errors.append("technical-signals returned no analyzed securities")
        signal_coverage = _nested(signals, "data", "coverage") or {}
        analyzed_count = int(signal_coverage.get("analyzed_count") or 0)
        watch_count = int(signal_coverage.get("short_history_watch_count") or 0)
        eligible_count = int(signal_coverage.get("eligible_count") or 0)
        if _nested(signals, "data", "data_state") != "complete":
            errors.append("technical-signals full-window analysis returned partial data")
        if int(signal_coverage.get("failed_count") or 0) != 0:
            errors.append("technical-signals full-window analysis reported market-data failures")
        if analyzed_count + watch_count != eligible_count:
            errors.append("technical-signals coverage did not account for the full eligible pool")
        watchlist = _nested(signals, "data", "short_history_watchlist") or []
        if len(watchlist) != watch_count:
            errors.append("technical-signals short-history watchlist count mismatch")
        if len(_nested(signals, "data", "catalog", "strategies") or []) != 10:
            errors.append("technical-signals did not expose all ten classic strategies")

        research_query = urlencode({"symbol": "300502", "period": "daily", "bars": 120})
        research_status, research = _request_json(
            f"{base}/api/v1/stock-research/dossiers?{research_query}", timeout=120
        )
        if research_status != 200 or research.get("ok") is not True:
            errors.append(f"stock-research live analysis failed: HTTP {research_status}")
        if _nested(research, "data", "engine", "name") != "instock-stock-research-dossier":
            errors.append("stock-research live analysis returned the wrong engine")
        if _nested(research, "data", "identity", "symbol") != "300502":
            errors.append("stock-research returned the wrong A-share identity")

        validation_packet = {
            "schema_version": "instock-strategy-validation-packet-v1",
            "strategy": {"id": "release-probe", "name": "release probe", "source_module": "czsc"},
            "as_of": date.today().isoformat(),
            "benchmark": "510300",
            "holding_period_sessions": 5,
            "cost_bps_per_side": 25,
            "signals": [
                {"decision_date": "2026-06-02", "symbols": ["300502"]},
                {"decision_date": "2026-06-16", "symbols": ["300502"]},
                {"decision_date": "2026-06-30", "symbols": ["300502"]},
                {"decision_date": "2026-07-14", "symbols": ["300502"]},
            ],
        }
        validation_status, validation = _request_json_post(
            f"{base}/api/v1/strategy-validations", validation_packet, timeout=120
        )
        if validation_status != 200 or validation.get("ok") is not True:
            errors.append(f"strategy-validation live analysis failed: HTTP {validation_status}")
        if _nested(validation, "data", "engine", "name") != "instock-strategy-validation":
            errors.append("strategy-validation returned the wrong engine")
        if int(_nested(validation, "data", "coverage", "executed_signals") or 0) < 1:
            errors.append("strategy-validation returned no executed signals")

        event_packet = {"symbol": "300502"}
        event_status, event_flow = _request_json_post(
            f"{base}/api/v1/event-flows", event_packet, timeout=120
        )
        if event_status != 200 or event_flow.get("ok") is not True:
            errors.append(f"event-flow live analysis failed: HTTP {event_status}")
        if _nested(event_flow, "data", "engine", "name") != "instock-event-flow":
            errors.append("event-flow returned the wrong engine")
        if int(_nested(event_flow, "data", "summary", "deduplicated_events") or 0) < 1:
            errors.append("event-flow returned no normalized events")
        if int(_nested(event_flow, "data", "coverage", "requested_sources") or 0) != 10:
            errors.append("event-flow did not probe all ten Desk evidence sources")

        book_packet = {
            "schema_version": "instock-research-book-packet-v1",
            "name": "release probe", "as_of": date.today().isoformat(),
            "items": [{
                "symbol": "300502", "name": "probe", "market": "CN", "sector": "通信",
                "target_weight_pct": 10, "thesis": "contract probe thesis",
                "invalidation": ["probe invalidation"], "risk_tags": ["probe risk"],
                "snapshot_ids": [],
            }],
        }
        book_status, book = _request_json_post(
            f"{base}/api/v1/research-books", book_packet, timeout=120
        )
        if book_status != 200 or book.get("ok") is not True:
            errors.append(f"research-book live analysis failed: HTTP {book_status}")
        if _nested(book, "data", "engine", "name") != "instock-research-book":
            errors.append("research-book returned the wrong engine")
        if int(_nested(book, "data", "summary", "items") or 0) < 1:
            errors.append("research-book returned no research items")
    except (OSError, URLError, ValueError, json.JSONDecodeError) as exc:
        errors.append(str(exc))

    detail = "live pages, attached-only routes, market workbench, market map, technical signals, CZSC, A-share candidates, stock research, strategy validation, event flow, research book, rotation and industry-chain probes passed"
    if errors:
        detail = "\n".join(errors)
    result = CheckResult(
        name="live-contract",
        status="failed" if errors else "passed",
        duration_seconds=round(time.monotonic() - started, 3),
        detail=detail,
        warnings=list(dict.fromkeys(warnings)),
    )
    print(f"{result.status.upper():4} {result.name} ({result.duration_seconds:.2f}s)")
    print(result.detail)
    for warning in result.warnings:
        print(f"WARN {warning}")
    return result


def _discover_newma_workspace(explicit: str | None) -> Path | None:
    candidates: Iterable[Path]
    if explicit:
        candidates = (Path(explicit).expanduser(),)
    elif os.environ.get("NEWMA_DESK_WORKSPACE"):
        candidates = (Path(os.environ["NEWMA_DESK_WORKSPACE"]).expanduser(),)
    else:
        candidates = (ROOT.parent / "newma-desk",)
    for candidate in candidates:
        resolved = candidate.resolve()
        if (resolved / "scripts" / "lib" / "mod-store.mjs").is_file():
            return resolved
    return None


def _write_report(path: str, results: Sequence[CheckResult]) -> None:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    source = _source_evidence(ROOT)
    payload = {
        "suite_version": json.loads(SUITE_PATH.read_text("utf-8"))["version"],
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": source,
        "status": "passed" if all(item.status == "passed" for item in results) else "failed",
        "checks": [asdict(item) for item in results],
    }
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(f"REPORT {target}")


def _git_output(root: Path, *args: str) -> str | None:
    try:
        completed = subprocess.run(
            ("git", *args),
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        return None
    return completed.stdout.strip() if completed.returncode == 0 else None


def _untracked_delivery_files(root: Path) -> list[str]:
    status = _git_output(
        root, "status", "--porcelain=v1", "--untracked-files=all"
    )
    if status is None:
        return []
    paths = []
    for line in status.splitlines():
        if not line.startswith("?? "):
            continue
        path = line[3:].strip().strip('"')
        if path in DELIVERY_ROOT_FILES or path.startswith(DELIVERY_SOURCE_PREFIXES):
            paths.append(path)
    return sorted(paths)


def _source_evidence(root: Path) -> dict[str, Any]:
    status = _git_output(root, "status", "--porcelain")
    untracked_delivery_files = _untracked_delivery_files(root)
    return {
        "repository": _git_output(root, "remote", "get-url", "origin"),
        "head": _git_output(root, "rev-parse", "HEAD"),
        "upstream_head": _git_output(root, "rev-parse", "origin/master"),
        "worktree_dirty": None if status is None else bool(status),
        "untracked_delivery_files": untracked_delivery_files,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the Newma-Desk attached InStock suite")
    parser.add_argument("--live", action="store_true", help="run Newma native and live HTTP checks")
    parser.add_argument("--newma-workspace", help="path to an existing Newma-Desk workspace")
    parser.add_argument("--base-url", default="http://127.0.0.1:9988")
    parser.add_argument("--report", help="optional JSON report path")
    args = parser.parse_args(argv)

    results = [_json_and_delivery_check(ROOT)]
    for check in _process_checks(ROOT, sys.executable):
        results.append(_run_process(check))

    if args.live:
        newma_workspace = _discover_newma_workspace(args.newma_workspace)
        if newma_workspace is None:
            results.append(CheckResult(
                name="newma-workspace",
                status="failed",
                duration_seconds=0.0,
                detail="Newma-Desk workspace not found; use --newma-workspace",
            ))
        else:
            for check in _newma_checks(ROOT, newma_workspace):
                results.append(_run_process(check))
            results.append(_live_contract_check(args.base_url))

    if args.report:
        _write_report(args.report, results)
    failed = [item.name for item in results if item.status != "passed"]
    if failed:
        print(f"RELEASE CHECK FAILED: {', '.join(failed)}")
        return 1
    warning_count = sum(len(item.warnings) for item in results)
    print(f"RELEASE CHECK PASSED: {len(results)} checks, {warning_count} warnings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
