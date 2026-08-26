#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Small daily ledger for Desk sector-flow confirmations."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from threading import RLock
from typing import Any, Mapping, Sequence


class SectorFundFlowHistory:
    """Keep one Desk-derived sector-flow summary per trading day."""

    def __init__(self, db_path: str):
        path = Path(db_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = str(path)
        self._lock = RLock()
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS sector_fund_flow_history ("
                "as_of TEXT PRIMARY KEY, payload_json TEXT NOT NULL)"
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=5)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def upsert(self, as_of: str, rows: Sequence[Mapping[str, Any]]) -> bool:
        day = str(as_of or "").strip()
        payload = []
        for row in rows:
            flow = row.get("sector_fund_flow") if isinstance(row, Mapping) else None
            industry = str(row.get("industry") or "") if isinstance(row, Mapping) else ""
            if industry and isinstance(flow, Mapping) and flow.get("state") == "available":
                payload.append({"industry": industry, "net": float(flow.get("net") or 0)})
        if not day or not payload:
            return False
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO sector_fund_flow_history (as_of, payload_json) VALUES (?, ?) "
                "ON CONFLICT(as_of) DO UPDATE SET payload_json = excluded.payload_json",
                (day, encoded),
            )
        return True

    def recent(self, *, before: str, limit: int = 4) -> list[dict[str, Any]]:
        safe_limit = min(max(int(limit), 1), 20)
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT as_of, payload_json FROM sector_fund_flow_history "
                "WHERE as_of < ? ORDER BY as_of DESC LIMIT ?",
                (str(before), safe_limit),
            ).fetchall()
        return [
            {"as_of": as_of, "flows": json.loads(payload_json)}
            for as_of, payload_json in rows
        ]

    def clear(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("DELETE FROM sector_fund_flow_history")

    def stats(self) -> dict[str, Any]:
        with self._lock, self._connect() as connection:
            entries = int(connection.execute(
                "SELECT COUNT(*) FROM sector_fund_flow_history"
            ).fetchone()[0])
        return {
            "storage": "sqlite",
            "volatile": False,
            "cleared_on_restart": False,
            "entries": entries,
        }


_SECTOR_FUND_FLOW_HISTORY = SectorFundFlowHistory(
    os.environ.get("INSTOCK_SECTOR_FUND_FLOW_DB_PATH", "").strip()
    or str(Path(__file__).resolve().parents[2] / "cache" / "sector_fund_flow.sqlite3")
)


def get_sector_fund_flow_history() -> SectorFundFlowHistory:
    return _SECTOR_FUND_FLOW_HISTORY
