"""Compact, paper-only experiment ledger derived from native backtest artifacts."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = "newma-desk.strategy-ledger.v1"
_COMPLETED_STATUSES = frozenset({"success", "done", "completed", "complete"})
_ACTIVE_STATUSES = frozenset({"queued", "pending", "running", "in_progress", "cancelling"})
_FAILED_STATUSES = frozenset({"failed", "error", "aborted"})
_CANCELLED_STATUSES = frozenset({"cancelled", "canceled"})
_TEMPLATE_NAMES = {
    "buy_and_hold": "Buy and Hold",
    "sma_crossover": "SMA Crossover",
}
_METRIC_ALIASES = {
    "total_return": ("total_return",),
    "annualized_return": ("annualized_return", "annual_return"),
    "max_drawdown": ("max_drawdown", "max_dd"),
    "volatility": ("volatility", "annualized_volatility"),
    "sharpe": ("sharpe", "sharpe_ratio"),
    "sortino": ("sortino", "sortino_ratio"),
    "win_rate": ("win_rate",),
    "turnover": ("avg_turnover", "turnover", "portfolio_turnover"),
    "total_turnover": ("total_turnover",),
    "fees": ("fees", "total_fees", "commission_paid"),
    "trade_count": ("trade_count", "trades"),
    "benchmark_return": ("benchmark_return",),
    "excess_return": ("excess_return", "active_return"),
}


def _artifact_reference(
    run_dir: Path,
    run_card: Mapping[str, Any],
    relative_path: str,
) -> dict[str, Any] | None:
    for raw in run_card.get("artifacts", []) if isinstance(run_card.get("artifacts"), list) else []:
        artifact = _mapping(raw)
        if artifact.get("path") == relative_path:
            return {
                key: artifact[key]
                for key in ("path", "size_bytes", "sha256")
                if key in artifact
            }
    path = run_dir / relative_path
    if not path.is_file():
        return None
    return {
        "path": relative_path,
        "size_bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _constraint_summary(config: Mapping[str, Any]) -> dict[str, Any]:
    raw = config.get("constraints")
    constraints = raw if isinstance(raw, list) else []
    types: list[str] = []
    group_count = 0
    for item in constraints[:20]:
        spec = _mapping(item)
        kind = str(spec.get("type") or "").strip()
        if kind and kind not in types:
            types.append(kind[:80])
        if kind == "group_exposure":
            groups = spec.get("groups")
            if isinstance(groups, Mapping):
                group_count += len(set(str(value) for value in groups.values()))
    optimizer = str(config.get("optimizer") or "").strip() or None
    return {
        "configured_count": len(constraints),
        "types": types,
        "group_count": group_count,
        "optimizer": optimizer,
        "status": "applied" if constraints and optimizer else ("ignored" if constraints else "off"),
    }


def _risk_summary(
    run_dir: Path,
    run_card: Mapping[str, Any],
    metrics: Mapping[str, Any],
) -> dict[str, Any]:
    artifact = _artifact_reference(run_dir, run_card, "artifacts/risk_xray.json")
    report = _load_json(run_dir / "artifacts" / "risk_xray.json") if artifact else {}
    concentration = _mapping(report.get("concentration"))
    volatility = _mapping(report.get("volatility"))
    drawdown = _mapping(report.get("drawdown"))
    tail = _mapping(report.get("tail_risk"))
    return {
        "available": bool(artifact),
        "hhi": _first_number(concentration.get("hhi"), metrics.get("risk_xray_hhi")),
        "effective_n": _first_number(
            concentration.get("effective_n"), metrics.get("risk_xray_effective_n")
        ),
        "annualized_volatility": _first_number(
            volatility.get("annualized_vol"), metrics.get("risk_xray_annualized_vol")
        ),
        "max_drawdown": _first_number(
            drawdown.get("max_drawdown"), metrics.get("risk_xray_max_drawdown")
        ),
        "var_95": _number(tail.get("var_95")),
        "expected_shortfall_95": _number(tail.get("expected_shortfall_95")),
        "average_invested": _number(metrics.get("risk_xray_avg_invested")),
        "artifact": artifact,
    }


def _rebalance_summary(
    run_dir: Path,
    run_card: Mapping[str, Any],
    metrics: Mapping[str, Any],
) -> dict[str, Any]:
    artifact = _artifact_reference(run_dir, run_card, "artifacts/rebalance_notes.json")
    notes = _load_json(run_dir / "artifacts" / "rebalance_notes.json") if artifact else {}
    summary = _mapping(notes.get("summary"))
    count = _number(summary.get("rebalance_count"))
    if count is None:
        count = _number(metrics.get("rebalance_count"))
    return {
        "available": bool(artifact),
        "count": int(count) if count is not None else None,
        "target_turnover_total": _first_number(
            summary.get("turnover_total"), metrics.get("rebalance_turnover_total")
        ),
        "target_turnover_mean": _first_number(
            summary.get("turnover_mean"), metrics.get("rebalance_turnover_mean")
        ),
        "target_turnover_max": _first_number(
            summary.get("turnover_max"), metrics.get("rebalance_turnover_max")
        ),
        "largest_rebalance_date": summary.get("largest_rebalance_date"),
        "artifact": artifact,
    }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return {}
    return _mapping(value)


def _load_metric_row(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            row = next(csv.DictReader(handle), None)
    except (OSError, csv.Error, UnicodeError):
        return {}
    return dict(row) if row else {}


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _first_number(*values: Any) -> float | None:
    for value in values:
        parsed = _number(value)
        if parsed is not None:
            return parsed
    return None


def _metric_catalog(raw: Mapping[str, Any]) -> dict[str, float | int | None]:
    catalog: dict[str, float | int | None] = {}
    for key, aliases in _METRIC_ALIASES.items():
        value = None
        for alias in aliases:
            parsed = _number(raw.get(alias))
            if parsed is not None:
                value = parsed
                break
        if key == "trade_count" and value is not None:
            catalog[key] = max(0, int(value))
        else:
            catalog[key] = value
    return catalog


def _simple_parameters(value: Any) -> dict[str, Any]:
    parameters: dict[str, Any] = {}
    for key, item in list(_mapping(value).items())[:20]:
        if isinstance(item, bool) or item is None or isinstance(item, (str, int, float)):
            parameters[str(key)[:80]] = item
    return parameters


def _stable_hash(value: Mapping[str, Any]) -> str:
    payload = {
        str(key): item
        for key, item in value.items()
        if not str(key).startswith("_")
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _unique_strings(value: Any, *, limit: int = 100) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    result: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text[:80])
        if len(result) >= limit:
            break
    return result


def _infer_market(symbols: list[str]) -> str | None:
    markets: set[str] = set()
    for raw_symbol in symbols:
        symbol = raw_symbol.upper()
        if symbol.endswith((".SH", ".SZ", ".BJ")) or (symbol.isdigit() and len(symbol) == 6):
            markets.add("CN")
        elif symbol.endswith(".HK"):
            markets.add("HK")
        elif symbol.endswith((".NS", ".BO")):
            markets.add("IN")
        elif "USDT" in symbol or symbol.endswith(("-USD", "/USD")):
            markets.add("CRYPTO")
        else:
            markets.add("US")
    if not markets:
        return None
    return next(iter(markets)) if len(markets) == 1 else "MULTI"


def _normalized_status(raw_status: Any, metrics: Mapping[str, Any]) -> str:
    status = str(raw_status or "").strip().lower()
    if status in _COMPLETED_STATUSES:
        return "completed"
    if status in _ACTIVE_STATUSES:
        return status
    if status in _FAILED_STATUSES:
        return "failed"
    if status in _CANCELLED_STATUSES:
        return "cancelled"
    return "completed" if metrics.get("total_return") is not None else "partial"


def _quality(
    *,
    status: str,
    metrics: Mapping[str, Any],
    start_date: str | None,
    end_date: str | None,
    commission_rate: float | None,
) -> dict[str, Any]:
    flags: list[str] = []
    if status in _ACTIVE_STATUSES:
        flags.append("experiment_active")
    if status in {"failed", "cancelled", "partial"}:
        flags.append(f"experiment_{status}")
    if metrics.get("total_return") is None:
        flags.append("missing_total_return")
    if metrics.get("max_drawdown") is None or metrics.get("sharpe") is None:
        flags.append("missing_risk_metrics")
    if not start_date or not end_date:
        flags.append("missing_dataset_window")
    trade_count = metrics.get("trade_count")
    if isinstance(trade_count, int) and 0 <= trade_count < 30:
        flags.append("low_trade_sample")
    if commission_rate is None:
        flags.append("missing_cost_assumption")
    elif commission_rate == 0:
        flags.append("zero_cost_assumption")

    if status in _ACTIVE_STATUSES:
        level = "pending"
    elif status == "completed" and not any(flag.startswith("missing_") for flag in flags):
        level = "complete"
    elif status == "completed" and metrics.get("total_return") is not None:
        level = "usable"
    else:
        level = "limited"
    return {"level": level, "flags": flags}


def _attribution(
    metrics: Mapping[str, Any],
    commission_rate: float | None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    def append(kind: str, factor: str, value: Any, unit: str, note: str) -> None:
        if value is None:
            return
        items.append(
            {
                "kind": kind,
                "factor": factor,
                "value": value,
                "unit": unit,
                "note": note,
            }
        )

    append("return", "net_return", metrics.get("total_return"), "ratio", "Net paper-backtest return")
    append(
        "return",
        "benchmark_return",
        metrics.get("benchmark_return"),
        "ratio",
        "Reference-market return over the same window",
    )
    append(
        "return",
        "excess_return",
        metrics.get("excess_return"),
        "ratio",
        "Return relative to the recorded benchmark",
    )
    append(
        "risk",
        "max_drawdown",
        metrics.get("max_drawdown"),
        "ratio",
        "Largest peak-to-trough paper loss",
    )
    append(
        "cost",
        "commission_rate",
        commission_rate,
        "rate",
        "Configured per-trade commission assumption; not a broker statement",
    )
    append(
        "cost",
        "estimated_fees",
        metrics.get("fees"),
        "currency",
        "Estimated costs emitted by the backtest engine",
    )
    append(
        "activity",
        "trade_count",
        metrics.get("trade_count"),
        "count",
        "Completed paper trades in this experiment",
    )
    return items


def build_strategy_ledger(
    run_dir: Path,
    *,
    config: Mapping[str, Any] | None = None,
    metrics: Mapping[str, Any] | None = None,
    run_card: Mapping[str, Any] | None = None,
    state: Mapping[str, Any] | None = None,
    request_payload: Mapping[str, Any] | None = None,
    design: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one deterministic experiment record from a native run directory."""
    run_dir = Path(run_dir)
    resolved_config = _mapping(config) or _load_json(run_dir / "config.json")
    resolved_card = _mapping(run_card) or _load_json(run_dir / "run_card.json")
    resolved_state = _mapping(state) or _load_json(run_dir / "state.json")
    resolved_request = _mapping(request_payload) or _load_json(run_dir / "req.json")
    resolved_design = _mapping(design) or _load_json(run_dir / "design_spec.json")
    raw_metrics = (
        _mapping(metrics)
        or _mapping(resolved_card.get("metrics"))
        or _load_metric_row(run_dir / "artifacts" / "metrics.csv")
    )
    metric_catalog = _metric_catalog(raw_metrics)

    request = _mapping(resolved_request.get("request"))
    backtest = _mapping(resolved_card.get("backtest"))
    reproducibility = _mapping(resolved_card.get("reproducibility"))
    template_id = str(
        resolved_design.get("template_id")
        or resolved_config.get("quick_template_id")
        or request.get("template_id")
        or ""
    ).strip() or None
    strategy_hash = str(
        reproducibility.get("strategy_hash")
        or resolved_design.get("signal_sha256")
        or ""
    ).strip() or None
    config_hash = str(reproducibility.get("config_hash") or "").strip() or _stable_hash(resolved_config)
    strategy_id = str(resolved_design.get("strategy_id") or "").strip()
    if not strategy_id:
        if template_id:
            strategy_id = f"vibe-trading.{template_id.replace('_', '-')}"
        elif strategy_hash:
            strategy_id = f"vibe-trading.strategy-{strategy_hash[:12]}"
        else:
            strategy_id = "vibe-trading.custom-strategy"
    strategy_name = str(resolved_design.get("name") or "").strip()
    if not strategy_name:
        strategy_name = _TEMPLATE_NAMES.get(template_id or "", "Vibe Trading Strategy")
    template_version = str(
        resolved_design.get("template_version")
        or resolved_design.get("generator_version")
        or ""
    ).strip() or None
    version_parts = [part for part in (template_version, strategy_hash[:12] if strategy_hash else None) if part]
    strategy_version = "+".join(version_parts) or f"config-{config_hash[:12]}"

    parameters = (
        _simple_parameters(resolved_design.get("parameters"))
        or _simple_parameters(resolved_request.get("normalized_params"))
        or _simple_parameters(request.get("params"))
    )
    if not parameters:
        parameters = _simple_parameters(
            {
                key: resolved_config.get(key)
                for key in ("initial_cash", "commission", "fast_window", "slow_window")
                if key in resolved_config
            }
        )

    symbols = _unique_strings(backtest.get("codes") or resolved_config.get("codes"))
    if not symbols and request.get("symbol"):
        symbols = [str(request["symbol"]).strip().upper()[:80]]
    start_date = str(backtest.get("start_date") or resolved_config.get("start_date") or request.get("start_date") or "").strip() or None
    end_date = str(backtest.get("end_date") or resolved_config.get("end_date") or request.get("end_date") or "").strip() or None
    timeframe = str(backtest.get("interval") or resolved_config.get("interval") or "").strip() or None
    data_sources = _unique_strings(resolved_card.get("data_sources"))
    commission_rate = _number(resolved_config.get("commission"))
    status = _normalized_status(resolved_state.get("status"), metric_catalog)
    generated_at = str(
        resolved_state.get("finished_at")
        or resolved_card.get("generated_at")
        or resolved_state.get("created_at")
        or ""
    ).strip() or _now_iso()
    ledger_seed = {
        "run_id": run_dir.name,
        "strategy_id": strategy_id,
        "strategy_version": strategy_version,
        "config_hash": config_hash,
    }
    ledger_hash = _stable_hash(ledger_seed)[:24]
    quality = _quality(
        status=status,
        metrics=metric_catalog,
        start_date=start_date,
        end_date=end_date,
        commission_rate=commission_rate,
    )
    attribution = _attribution(metric_catalog, commission_rate)
    risk = _risk_summary(run_dir, resolved_card, raw_metrics)
    rebalances = _rebalance_summary(run_dir, resolved_card, raw_metrics)
    constraints = _constraint_summary(resolved_config)

    return {
        "schema_version": SCHEMA_VERSION,
        "ledger_id": f"vibe-trading-{ledger_hash}",
        "experiment": {
            "id": run_dir.name,
            "revision": config_hash[:12],
            "created_at": resolved_state.get("created_at") or generated_at,
            "started_at": resolved_state.get("started_at"),
            "finished_at": resolved_state.get("finished_at"),
        },
        "mode": "paper-only",
        "execution_mode": "paper",
        "status": status,
        "strategy": {
            "id": strategy_id,
            "name": strategy_name[:160],
            "version": strategy_version[:80],
            "template_id": template_id,
            "parameters": parameters,
        },
        "dataset": {
            "symbols": symbols,
            "market": _infer_market(symbols),
            "start_date": start_date,
            "end_date": end_date,
            "timeframe": timeframe,
            "source": "newma-desk",
            "data_sources": data_sources,
        },
        "metrics": metric_catalog,
        "risk": risk,
        "rebalances": rebalances,
        "constraints": constraints,
        "attribution": attribution,
        "cost_model": {
            "commission_rate": commission_rate,
            "realized_fees_available": metric_catalog.get("fees") is not None,
        },
        "quality": quality,
        "generated_at": generated_at,
        "provenance": {
            "runtime": "vibe-trading-native",
            "data_policy": "desk-unified",
            "execution_policy": "paper-only",
            "artifact_policy": "run-directory",
            "methodology": "quantdinger-inspired-native-extraction",
        },
    }


def write_strategy_ledger(
    run_dir: Path,
    *,
    config: Mapping[str, Any],
    metrics: Mapping[str, Any],
    run_card: Mapping[str, Any],
) -> dict[str, Any]:
    """Materialize the compact ledger next to the run card without a database."""
    run_dir = Path(run_dir)
    completed_state = _load_json(run_dir / "state.json")
    completed_state.update(
        {
            "status": "success",
            "finished_at": run_card.get("generated_at") or _now_iso(),
        }
    )
    ledger = build_strategy_ledger(
        run_dir,
        config=config,
        metrics=metrics,
        run_card=run_card,
        state=completed_state,
    )
    path = run_dir / "strategy_ledger.json"
    temporary = run_dir / ".strategy_ledger.json.tmp"
    temporary.write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return ledger
