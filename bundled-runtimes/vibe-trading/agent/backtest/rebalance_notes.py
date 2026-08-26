"""Summarize requested target-weight changes without duplicating trade logs."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from backtest.validation import _json_safe


def _empty_notes() -> dict[str, Any]:
    return {
        "rebalances": [],
        "summary": {
            "rebalance_count": 0,
            "turnover_total": 0.0,
            "turnover_mean": 0.0,
            "turnover_max": 0.0,
            "largest_rebalance_date": None,
        },
    }


def compute_rebalance_notes(
    target_pos: pd.DataFrame,
    *,
    top_n: int = 5,
    epsilon: float = 1e-6,
) -> dict[str, Any]:
    """Return decision turnover, entries, exits and largest requested moves."""
    if isinstance(top_n, bool) or top_n < 1:
        raise ValueError("top_n must be a positive integer")
    if isinstance(epsilon, bool) or not math.isfinite(epsilon) or epsilon < 0:
        raise ValueError("epsilon must be a finite non-negative number")
    if target_pos is None or target_pos.empty or len(target_pos) < 2:
        return _empty_notes()

    frame = target_pos.fillna(0.0)
    values = frame.to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("target positions contain non-finite values")
    codes = [str(code) for code in frame.columns]
    rebalances: list[dict[str, Any]] = []

    previous = values[0]
    for index in range(1, len(values)):
        current = values[index]
        delta = current - previous
        turnover = 0.5 * float(np.abs(delta).sum())
        if turnover > epsilon:
            date = frame.index[index]
            entries = [
                {"code": codes[column], "weight": float(current[column])}
                for column in range(len(codes))
                if abs(previous[column]) <= epsilon and abs(current[column]) > epsilon
            ]
            exits = [
                {"code": codes[column], "weight": float(previous[column])}
                for column in range(len(codes))
                if abs(current[column]) <= epsilon and abs(previous[column]) > epsilon
            ]
            moves = sorted(
                (
                    {
                        "code": codes[column],
                        "from": float(previous[column]),
                        "to": float(current[column]),
                        "delta": float(delta[column]),
                    }
                    for column in range(len(codes))
                    if abs(delta[column]) > epsilon
                ),
                key=lambda move: (-abs(move["delta"]), move["code"]),
            )[:top_n]
            rebalances.append(
                {
                    "date": str(date.date()) if hasattr(date, "date") else str(date),
                    "turnover": turnover,
                    "entries": entries,
                    "exits": exits,
                    "top_moves": moves,
                }
            )
        previous = current

    turnovers = [item["turnover"] for item in rebalances]
    largest = max(rebalances, key=lambda item: item["turnover"]) if rebalances else None
    return {
        "rebalances": rebalances,
        "summary": {
            "rebalance_count": len(rebalances),
            "turnover_total": float(sum(turnovers)),
            "turnover_mean": float(np.mean(turnovers)) if turnovers else 0.0,
            "turnover_max": float(max(turnovers)) if turnovers else 0.0,
            "largest_rebalance_date": largest["date"] if largest else None,
        },
    }


def write_rebalance_notes(path: Path, notes: Mapping[str, Any]) -> dict[str, Any]:
    """Write strict JSON and return the sanitized payload."""
    payload = _json_safe(dict(notes))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )
    return payload
