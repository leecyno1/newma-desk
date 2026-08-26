#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Observed candidate lifecycle derived from persisted analysis snapshots."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence

LIFECYCLE_SCHEMA_VERSION = "2.0"
LIFECYCLE_COMPARISON_SCOPE = "same_candidate_configuration"


def enrich_candidate_lifecycle(
    result: Mapping[str, Any],
    history_records: Sequence[Mapping[str, Any]],
    *,
    parameters: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Attach observation-only lifecycle fields without changing candidate scores."""

    enriched = deepcopy(dict(result))
    observations: dict[str, dict[str, dict[str, Any]]] = {}
    for record in history_records:
        if parameters is not None and not _same_candidate_configuration(
            record.get("parameters"), parameters
        ):
            continue
        payload = record.get("payload") if isinstance(record, Mapping) else None
        if not isinstance(payload, Mapping):
            continue
        as_of = str(payload.get("as_of") or record.get("as_of") or "").strip()
        if not as_of or as_of in observations:
            continue
        observations[as_of] = _candidate_map(payload.get("candidates"))

    current_as_of = str(enriched.get("as_of") or "").strip()
    current_candidates = enriched.get("candidates") or []
    observations[current_as_of] = _candidate_map(current_candidates)
    observation_dates = sorted(date for date in observations if date)
    previous_as_of = (
        observation_dates[-2]
        if len(observation_dates) >= 2 and observation_dates[-1] == current_as_of
        else ""
    )
    previous = observations.get(previous_as_of, {})
    state_counts = {"new": 0, "continuing": 0, "returned": 0}

    for candidate in current_candidates:
        symbol = str(candidate.get("symbol") or "")
        appearances = [
            date for date in observation_dates if symbol in observations[date]
        ]
        previously_seen = [date for date in appearances if date != current_as_of]
        if symbol in previous:
            state = "continuing"
        elif previously_seen:
            state = "returned"
        else:
            state = "new"
        state_counts[state] += 1

        streak = 0
        for date in reversed(observation_dates):
            if symbol not in observations[date]:
                break
            streak += 1
        prior = previous.get(symbol)
        candidate["lifecycle"] = {
            "state": state,
            "first_seen_as_of": appearances[0] if appearances else current_as_of,
            "last_seen_as_of": current_as_of,
            "observed_periods": len(appearances),
            "consecutive_observations": streak,
            "previous_as_of": previous_as_of or None,
            "previous_rank": int(prior["rank"]) if prior else None,
            "rank_change": (
                int(prior["rank"]) - int(candidate.get("rank") or 0)
                if prior else None
            ),
            "previous_score": round(float(prior["score"]), 2) if prior else None,
            "score_change": (
                round(float(candidate.get("score") or 0) - float(prior["score"]), 2)
                if prior else None
            ),
        }

    enriched["candidate_lifecycle"] = {
        "schema_version": LIFECYCLE_SCHEMA_VERSION,
        "comparison_scope": LIFECYCLE_COMPARISON_SCOPE,
        "semantics": "observed_candidate_history_not_return_backtest",
        "observation_count": len(observation_dates),
        "first_as_of": observation_dates[0] if observation_dates else current_as_of,
        "latest_as_of": current_as_of,
        "previous_as_of": previous_as_of or None,
        "summary": state_counts,
    }
    return enriched


def _candidate_map(raw_candidates: Any) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("symbol") or ""): {
            "rank": int(item.get("rank") or 0),
            "score": float(item.get("score") or 0),
        }
        for item in (raw_candidates or [])
        if isinstance(item, Mapping) and item.get("symbol")
    }


def _same_candidate_configuration(raw: Any, current: Mapping[str, Any]) -> bool:
    if not isinstance(raw, Mapping):
        return False
    keys = (
        "market",
        "universeMode",
        "universeSize",
        "outputSize",
        "bars",
        "profile",
        "filters",
    )
    return all(_freeze(raw.get(key)) == _freeze(current.get(key)) for key in keys)


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return tuple(sorted((str(key), _freeze(item)) for key, item in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value
