#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Bounded history of complete analysis results for the Mod frontend."""

from __future__ import annotations

import os
import json
import sqlite3
import time
import uuid
from collections import OrderedDict
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Mapping, Optional


HISTORY_SCHEMA_VERSION = "1.0"


class AnalysisHistoryRegistry:
    """Keep copy-isolated analysis versions without overwriting older results."""

    def __init__(
        self,
        *,
        max_entries: int = 200,
        ttl_seconds: float = 604_800,
        clock: Callable[[], float] = time.monotonic,
        db_path: Optional[str] = None,
        wall_clock: Callable[[], float] = time.time,
    ):
        self.max_entries = max(1, int(max_entries))
        self.ttl_seconds = max(1.0, float(ttl_seconds))
        self._clock = clock
        self._wall_clock = wall_clock
        self._lock = RLock()
        self._entries: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
        self.db_path = str(db_path or "").strip()
        if self.db_path:
            path = Path(self.db_path).expanduser()
            path.parent.mkdir(parents=True, exist_ok=True)
            self.db_path = str(path)
            self._init_database()

    @property
    def persistent(self) -> bool:
        return bool(self.db_path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=5)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _init_database(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS analysis_history (
                    history_id TEXT PRIMARY KEY,
                    module_id TEXT NOT NULL,
                    stored_at REAL NOT NULL,
                    entry_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_analysis_history_module_time "
                "ON analysis_history(module_id, stored_at DESC)"
            )

    def _purge_persistent(self, connection: sqlite3.Connection, now: float) -> None:
        connection.execute(
            "DELETE FROM analysis_history WHERE stored_at <= ?",
            (now - self.ttl_seconds,),
        )

    def _trim_persistent(self, connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            "SELECT history_id FROM analysis_history "
            "ORDER BY stored_at DESC, rowid DESC LIMIT -1 OFFSET ?",
            (self.max_entries,),
        ).fetchall()
        if rows:
            connection.executemany(
                "DELETE FROM analysis_history WHERE history_id = ?", rows
            )

    def _purge_expired(self, now: float) -> None:
        expired = [
            history_id
            for history_id, (stored_at, _) in self._entries.items()
            if now - stored_at >= self.ttl_seconds
        ]
        for history_id in expired:
            self._entries.pop(history_id, None)

    @staticmethod
    def _metadata(entry: Mapping[str, Any]) -> dict[str, Any]:
        return {key: deepcopy(value) for key, value in entry.items() if key != "payload"}

    def register(
        self,
        *,
        module_id: str,
        payload: Mapping[str, Any],
        title: str,
        parameters: Optional[Mapping[str, Any]] = None,
        record_type: str = "analysis",
    ) -> dict[str, Any]:
        """Append one complete result and return its lightweight metadata."""

        normalized_module = str(module_id or "").strip()
        normalized_type = str(record_type or "analysis").strip()
        normalized_title = str(title or "").strip()
        if not normalized_module or not normalized_type or not normalized_title:
            raise ValueError("历史记录缺少 module_id、record_type 或 title")
        if not isinstance(payload, Mapping):
            raise ValueError("历史记录 payload 必须是对象")

        stored_payload = deepcopy(dict(payload))
        snapshot = stored_payload.get("snapshot") or {}
        data_window = snapshot.get("data_window") or {}
        stored_parameters = deepcopy(dict(parameters or snapshot.get("parameters") or {}))
        as_of = (
            stored_payload.get("as_of")
            or stored_payload.get("end_date")
            or data_window.get("requested_as_of")
            or data_window.get("end_date")
        )
        symbol = (
            stored_parameters.get("symbol")
            or stored_parameters.get("code")
            or stored_payload.get("symbol")
            or (stored_payload.get("identity") or {}).get("symbol")
            or (stored_payload.get("query") or {}).get("symbol")
        )
        generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
        history_id = f"history-{uuid.uuid4().hex}"
        entry = {
            "schema_version": HISTORY_SCHEMA_VERSION,
            "history_id": history_id,
            "module_id": normalized_module,
            "record_type": normalized_type,
            "title": normalized_title,
            "symbol": str(symbol).strip() if symbol else None,
            "generated_at": generated_at,
            "result_generated_at": (
                stored_payload.get("generated_at") or snapshot.get("generated_at")
            ),
            "as_of": str(as_of) if as_of else None,
            "snapshot_id": snapshot.get("snapshot_id"),
            "parameters": stored_parameters,
            "payload": stored_payload,
        }

        now = self._wall_clock() if self.persistent else self._clock()
        with self._lock:
            if self.persistent:
                with self._connect() as connection:
                    self._purge_persistent(connection, now)
                    connection.execute(
                        "INSERT INTO analysis_history "
                        "(history_id, module_id, stored_at, entry_json) VALUES (?, ?, ?, ?)",
                        (
                            history_id,
                            normalized_module,
                            now,
                            json.dumps(entry, ensure_ascii=False, separators=(",", ":"), default=str),
                        ),
                    )
                    self._trim_persistent(connection)
                return self._metadata(entry)
            self._purge_expired(now)
            self._entries[history_id] = (now, entry)
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)
        return self._metadata(entry)

    def list(self, module_id: str, *, limit: int = 30) -> list[dict[str, Any]]:
        normalized_module = str(module_id or "").strip()
        if not normalized_module:
            return []
        safe_limit = min(max(int(limit), 1), 100)
        now = self._wall_clock() if self.persistent else self._clock()
        with self._lock:
            if self.persistent:
                with self._connect() as connection:
                    self._purge_persistent(connection, now)
                    rows = connection.execute(
                        "SELECT entry_json FROM analysis_history "
                        "WHERE module_id = ? ORDER BY stored_at DESC, rowid DESC LIMIT ?",
                        (normalized_module, safe_limit),
                    ).fetchall()
                return [self._metadata(json.loads(row[0])) for row in rows]
            self._purge_expired(now)
            matches = [
                self._metadata(entry)
                for _, entry in reversed(list(self._entries.values()))
                if entry["module_id"] == normalized_module
            ]
        return matches[:safe_limit]

    def get(self, history_id: str) -> Optional[dict[str, Any]]:
        key = str(history_id or "").strip()
        if not key:
            return None
        now = self._wall_clock() if self.persistent else self._clock()
        with self._lock:
            if self.persistent:
                with self._connect() as connection:
                    self._purge_persistent(connection, now)
                    row = connection.execute(
                        "SELECT entry_json FROM analysis_history WHERE history_id = ?",
                        (key,),
                    ).fetchone()
                return json.loads(row[0]) if row else None
            self._purge_expired(now)
            entry = self._entries.get(key)
            return deepcopy(entry[1]) if entry else None

    def clear(self) -> None:
        with self._lock:
            if self.persistent:
                with self._connect() as connection:
                    connection.execute("DELETE FROM analysis_history")
                return
            self._entries.clear()

    def stats(self) -> dict[str, Any]:
        now = self._wall_clock() if self.persistent else self._clock()
        with self._lock:
            if self.persistent:
                with self._connect() as connection:
                    self._purge_persistent(connection, now)
                    entries = int(connection.execute(
                        "SELECT COUNT(*) FROM analysis_history"
                    ).fetchone()[0])
                    module_rows = connection.execute(
                        "SELECT module_id, COUNT(*) FROM analysis_history "
                        "GROUP BY module_id ORDER BY module_id"
                    ).fetchall()
                return {
                    "storage": "sqlite",
                    "volatile": False,
                    "cleared_on_restart": False,
                    "entries": entries,
                    "max_entries": self.max_entries,
                    "ttl_seconds": self.ttl_seconds,
                    "modules": {str(module): int(count) for module, count in module_rows},
                }
            self._purge_expired(now)
            modules: dict[str, int] = {}
            for _, entry in self._entries.values():
                modules[entry["module_id"]] = modules.get(entry["module_id"], 0) + 1
            return {
                "storage": "process_memory",
                "volatile": True,
                "cleared_on_restart": True,
                "entries": len(self._entries),
                "max_entries": self.max_entries,
                "ttl_seconds": self.ttl_seconds,
                "modules": dict(sorted(modules.items())),
            }


def _setting(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default
    return min(max(value, minimum), maximum)


_ANALYSIS_HISTORY_REGISTRY = AnalysisHistoryRegistry(
    max_entries=_setting("INSTOCK_ANALYSIS_HISTORY_MAX_ENTRIES", 200, 20, 1_000),
    ttl_seconds=_setting("INSTOCK_ANALYSIS_HISTORY_TTL_SECONDS", 604_800, 300, 2_592_000),
    db_path=(
        os.environ.get("INSTOCK_ANALYSIS_HISTORY_DB_PATH", "").strip()
        or str(Path(__file__).resolve().parents[1] / "cache" / "analysis_history.sqlite3")
    ),
)


def get_analysis_history_registry() -> AnalysisHistoryRegistry:
    return _ANALYSIS_HISTORY_REGISTRY
