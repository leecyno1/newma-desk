#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Persistent forward-only ledger for the ETF rotation shadow strategy."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from threading import RLock
from typing import Any, Mapping, Optional


class RotationShadowState:
    """Store one immutable shadow-strategy state per benchmark and trading day."""

    def __init__(self, db_path: str):
        path = Path(db_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = str(path)
        self._lock = RLock()
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS rotation_shadow_state ("
                "benchmark TEXT NOT NULL, "
                "as_of TEXT NOT NULL, "
                "strategy_id TEXT NOT NULL, "
                "lifecycle_state TEXT NOT NULL, "
                "signal_id TEXT NOT NULL, "
                "payload_json TEXT NOT NULL, "
                "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                "PRIMARY KEY (benchmark, as_of))"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_rotation_shadow_latest "
                "ON rotation_shadow_state (benchmark, as_of DESC)"
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=5)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    @staticmethod
    def _decode(payload_json: str) -> dict[str, Any]:
        payload = json.loads(payload_json)
        return payload if isinstance(payload, dict) else {}

    def record(self, benchmark: str, state: Mapping[str, Any]) -> bool:
        """Append a state once; a same-day refresh can never replace it."""

        code = str(benchmark or "").strip()
        day = str(state.get("as_of") or "").strip()
        strategy_id = str(state.get("strategy_id") or "").strip()
        models = state.get("models")
        if not code or not day or not strategy_id or not isinstance(models, list) or not models:
            return False
        payload = dict(state)
        payload["benchmark"] = code
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        with self._lock, self._connect() as connection:
            latest = connection.execute(
                "SELECT MAX(as_of) FROM rotation_shadow_state WHERE benchmark = ?",
                (code,),
            ).fetchone()[0]
            if latest and day <= str(latest):
                return False
            cursor = connection.execute(
                "INSERT OR IGNORE INTO rotation_shadow_state "
                "(benchmark, as_of, strategy_id, lifecycle_state, signal_id, payload_json) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    code,
                    day,
                    strategy_id,
                    str(state.get("lifecycle_state") or "unavailable"),
                    str(state.get("signal_id") or ""),
                    encoded,
                ),
            )
        return cursor.rowcount == 1

    def latest(self, benchmark: str) -> Optional[dict[str, Any]]:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM rotation_shadow_state "
                "WHERE benchmark = ? ORDER BY as_of DESC LIMIT 1",
                (str(benchmark),),
            ).fetchone()
        return self._decode(row[0]) if row else None

    def recent(
        self,
        *,
        benchmark: Optional[str] = None,
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        safe_limit = min(max(int(limit), 1), 200)
        with self._lock, self._connect() as connection:
            if benchmark:
                rows = connection.execute(
                    "SELECT payload_json FROM rotation_shadow_state "
                    "WHERE benchmark = ? ORDER BY as_of DESC LIMIT ?",
                    (str(benchmark), safe_limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT payload_json FROM rotation_shadow_state "
                    "ORDER BY as_of DESC, benchmark LIMIT ?",
                    (safe_limit,),
                ).fetchall()
        return [self._decode(row[0]) for row in rows]

    def clear(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("DELETE FROM rotation_shadow_state")

    def stats(self) -> dict[str, Any]:
        with self._lock, self._connect() as connection:
            entries, benchmarks, latest_as_of, signals = connection.execute(
                "SELECT COUNT(*), COUNT(DISTINCT benchmark), MAX(as_of), "
                "SUM(CASE WHEN signal_id <> '' THEN 1 ELSE 0 END) "
                "FROM rotation_shadow_state"
            ).fetchone()
        return {
            "storage": "sqlite",
            "volatile": False,
            "cleared_on_restart": False,
            "entries": int(entries or 0),
            "benchmarks": int(benchmarks or 0),
            "signal_entries": int(signals or 0),
            "latest_as_of": str(latest_as_of or ""),
        }


_ROTATION_SHADOW_STATE = RotationShadowState(
    os.environ.get("INSTOCK_ROTATION_SHADOW_DB_PATH", "").strip()
    or str(Path(__file__).resolve().parents[2] / "cache" / "rotation_shadow_state.sqlite3")
)


def get_rotation_shadow_state() -> RotationShadowState:
    return _ROTATION_SHADOW_STATE
