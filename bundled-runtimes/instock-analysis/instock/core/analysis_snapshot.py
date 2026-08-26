#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Traceable metadata for reproducible analysis results.

The module keeps provenance, coverage, freshness, and stable digests behind one
small interface shared by CZSC and rotation.  It intentionally stores summaries
instead of full chart payloads so Desk Context remains compact.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections import OrderedDict
from copy import deepcopy
from datetime import date, datetime
from threading import RLock
from typing import Any, Callable, Mapping, Optional

import numpy as np
import pandas as pd


SNAPSHOT_SCHEMA_VERSION = "1.0"


class AnalysisSnapshotRegistry:
    """Bounded process-memory registry for compact analysis snapshots.

    The registry intentionally stores only the metadata returned by
    :func:`build_analysis_snapshot`; full K-line frames and chart payloads stay
    outside this module.  Entries are copy-isolated, TTL-bound, and evicted in
    least-recently-used order.
    """

    def __init__(
        self,
        *,
        max_entries: int = 512,
        ttl_seconds: float = 86_400,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.max_entries = max(1, int(max_entries))
        self.ttl_seconds = max(1.0, float(ttl_seconds))
        self._clock = clock
        self._lock = RLock()
        self._entries: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()

    def _purge_expired(self, now: float) -> None:
        expired = [
            snapshot_id
            for snapshot_id, (registered_at, _) in self._entries.items()
            if now - registered_at >= self.ttl_seconds
        ]
        for snapshot_id in expired:
            self._entries.pop(snapshot_id, None)

    def register(self, snapshot: Mapping[str, Any]) -> dict[str, Any]:
        """Register one snapshot and return an isolated copy."""

        snapshot_id = str(snapshot.get("snapshot_id") or "").strip()
        if not snapshot_id or snapshot.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
            raise ValueError("分析快照缺少有效 snapshot_id 或 schema_version")
        stored = deepcopy(dict(snapshot))
        now = self._clock()
        with self._lock:
            self._purge_expired(now)
            self._entries.pop(snapshot_id, None)
            self._entries[snapshot_id] = (now, stored)
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)
        return deepcopy(stored)

    def get(self, snapshot_id: str) -> Optional[dict[str, Any]]:
        """Return an isolated snapshot, or ``None`` when absent or expired."""

        key = str(snapshot_id or "").strip()
        if not key:
            return None
        now = self._clock()
        with self._lock:
            self._purge_expired(now)
            entry = self._entries.pop(key, None)
            if entry is None:
                return None
            self._entries[key] = entry
            return deepcopy(entry[1])

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def stats(self) -> dict[str, Any]:
        now = self._clock()
        with self._lock:
            self._purge_expired(now)
            return {
                "storage": "process_memory",
                "volatile": True,
                "entries": len(self._entries),
                "max_entries": self.max_entries,
                "ttl_seconds": self.ttl_seconds,
            }


def _registry_setting(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default
    return min(max(value, minimum), maximum)


_ANALYSIS_SNAPSHOT_REGISTRY = AnalysisSnapshotRegistry(
    max_entries=_registry_setting("INSTOCK_SNAPSHOT_REGISTRY_MAX_ENTRIES", 512, 16, 10_000),
    ttl_seconds=_registry_setting("INSTOCK_SNAPSHOT_REGISTRY_TTL_SECONDS", 86_400, 60, 604_800),
)


def get_analysis_snapshot_registry() -> AnalysisSnapshotRegistry:
    """Return the process-local snapshot registry used by HTTP handlers."""

    return _ANALYSIS_SNAPSHOT_REGISTRY


def normalize_as_of(value: Any, *, reject_future: bool = False) -> Optional[str]:
    """Return an ISO date or ``None`` for an empty historical anchor."""

    if value is None or str(value).strip() == "":
        return None
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip()) is None:
        raise ValueError("历史截止日期须为 YYYY-MM-DD")
    try:
        timestamp = pd.Timestamp(value).normalize()
    except (TypeError, ValueError) as exc:
        raise ValueError("历史截止日期须为 YYYY-MM-DD") from exc
    if pd.isna(timestamp):
        raise ValueError("历史截止日期须为 YYYY-MM-DD")
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_convert("Asia/Shanghai").tz_localize(None)
    if reject_future and timestamp.date() > date.today():
        raise ValueError("历史截止日期不能晚于今天")
    return timestamp.strftime("%Y-%m-%d")


def _canonical(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return pd.Timestamp(value).isoformat()
    if isinstance(value, Mapping):
        return {str(key): _canonical(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (list, tuple, set)):
        return [_canonical(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        number = float(value)
        return round(number, 10) if np.isfinite(number) else None
    if pd.isna(value):
        return None
    return str(value)


def _digest(value: Any) -> str:
    encoded = json.dumps(
        _canonical(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _frame_input(frame: pd.DataFrame) -> dict[str, Any]:
    columns = [
        column
        for column in ("date", "open", "high", "low", "close", "volume", "amount")
        if column in frame.columns
    ]
    rows = []
    for values in frame[columns].itertuples(index=False, name=None):
        rows.append(dict(zip(columns, values)))
    return {"columns": columns, "rows": rows}


def _freshness(end_date: str, requested_as_of: Optional[str]) -> dict[str, Any]:
    end = pd.Timestamp(end_date).date()
    anchor = pd.Timestamp(requested_as_of).date() if requested_as_of else date.today()
    lag_days = max((anchor - end).days, 0)
    if requested_as_of:
        state = "historical"
        resolution = "exact" if end.isoformat() == requested_as_of else "previous_session"
    else:
        state = "fresh" if lag_days <= 3 else "delayed" if lag_days <= 7 else "stale"
        resolution = "latest"
    return {
        "state": state,
        "resolution": resolution,
        "calendar_lag_days": lag_days,
    }


def build_analysis_snapshot(
    *,
    analysis_name: str,
    analysis_version: str,
    parameters: Mapping[str, Any],
    frame: pd.DataFrame,
    requested_bars: int,
    provider_name: str,
    result_summary: Mapping[str, Any],
    input_summary: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Build a compact, stable snapshot describing one completed analysis."""

    if frame is None or frame.empty:
        raise ValueError("无法为空行情创建分析快照")

    start_date = pd.Timestamp(frame["date"].iloc[0]).strftime("%Y-%m-%d")
    end_date = pd.Timestamp(frame["date"].iloc[-1]).strftime("%Y-%m-%d")
    requested_as_of = normalize_as_of(parameters.get("asOf") or parameters.get("as_of"))
    actual_bars = len(frame)
    coverage = "complete" if actual_bars >= int(requested_bars) else "partial"
    limitations = list(frame.attrs.get("replay_limitations") or [])
    if coverage == "partial" and "requested_window_not_fully_covered" not in limitations:
        limitations.append("requested_window_not_fully_covered")

    compact_input = {
        "symbol": parameters.get("symbol") or parameters.get("benchmark"),
        "period": parameters.get("period", "daily"),
        "bar_count": actual_bars,
        "first_close": float(frame["close"].iloc[0]),
        "last_close": float(frame["close"].iloc[-1]),
        **dict(input_summary or {}),
    }
    canonical_parameters = _canonical(dict(parameters))
    input_digest = _digest(_frame_input(frame))
    result_digest = _digest(result_summary)
    stable_material = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "analysis": {"name": analysis_name, "version": analysis_version},
        "parameters": canonical_parameters,
        "data_window": {"start_date": start_date, "end_date": end_date},
        "provider": provider_name,
        "input_digest": input_digest,
        "result_digest": result_digest,
    }
    snapshot_hash = _digest(stable_material).split(":", 1)[1]

    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "snapshot_id": f"{analysis_name}:{snapshot_hash[:24]}",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "analysis": {"name": analysis_name, "version": str(analysis_version)},
        "parameters": canonical_parameters,
        "data_window": {
            "requested_as_of": requested_as_of,
            "start_date": start_date,
            "end_date": end_date,
            "requested_bars": int(requested_bars),
            "actual_bars": actual_bars,
            "coverage": coverage,
            "source_window_start": frame.attrs.get("source_window_start", start_date),
            "source_window_end": frame.attrs.get("source_window_end", end_date),
        },
        "provenance": {
            "provider": provider_name,
            "endpoint": frame.attrs.get("data_endpoint", ""),
            "adjust": frame.attrs.get("adjust", "unknown"),
            "upstream_source": frame.attrs.get("upstream_source", ""),
            "upstream_as_of": frame.attrs.get("upstream_as_of", ""),
            "market": frame.attrs.get("upstream_market", ""),
            "timeframe": frame.attrs.get("upstream_timeframe", ""),
            "as_of_mode": frame.attrs.get("as_of_mode", "latest"),
            "upstream_limit": frame.attrs.get("upstream_limit"),
            "upstream_has_more": frame.attrs.get("upstream_has_more"),
            "limitations": limitations,
        },
        "freshness": _freshness(end_date, requested_as_of),
        "input": {"digest": input_digest, "summary": _canonical(compact_input)},
        "result": {"digest": result_digest, "summary": _canonical(result_summary)},
    }
