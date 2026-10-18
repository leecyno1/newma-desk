from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path


class CapitalHistoryStore:
    """Keep dated source observations, not just the most recent dashboard."""

    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS capital_observations (
                dataset TEXT NOT NULL, symbol TEXT NOT NULL, date TEXT NOT NULL,
                payload TEXT NOT NULL, received_at TEXT NOT NULL,
                PRIMARY KEY (dataset, symbol, date)
            );
            CREATE TABLE IF NOT EXISTS capital_fetches (
                dataset TEXT NOT NULL, symbol TEXT NOT NULL,
                start_date TEXT NOT NULL, end_date TEXT NOT NULL,
                status TEXT NOT NULL, reason TEXT NOT NULL, received_at TEXT NOT NULL,
                PRIMARY KEY (dataset, symbol)
            );
        """)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def read(self, dataset: str, symbol: str, start: str, end: str) -> tuple[list[dict], dict]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM capital_observations WHERE dataset=? AND symbol=? AND date BETWEEN ? AND ? ORDER BY date",
                (dataset, symbol, start, end),
            ).fetchall()
            run = connection.execute(
                "SELECT * FROM capital_fetches WHERE dataset=? AND symbol=?", (dataset, symbol),
            ).fetchone()
        return [json.loads(row["payload"]) for row in rows], dict(run) if run else {}

    def save_once(self, dataset: str, symbol: str, row: dict) -> dict:
        """Freeze the first observed cohort, including an empty but valid candidate set."""
        with self._connect() as connection:
            connection.execute("INSERT OR IGNORE INTO capital_observations VALUES (?, ?, ?, ?, ?)",
                               (dataset, symbol, row["date"], json.dumps(row, ensure_ascii=False), row["capturedAt"]))
            saved = connection.execute("SELECT payload FROM capital_observations WHERE dataset=? AND symbol=? AND date=?",
                                       (dataset, symbol, row["date"])).fetchone()
        return json.loads(saved["payload"])

    def read_page(self, dataset: str, symbol: str, start: str, end: str, page: int, page_size: int) -> dict:
        """Browse stored observations without the live research window or a remote fetch."""
        with self._connect() as connection:
            params = (dataset, symbol, start, end)
            total = connection.execute(
                "SELECT COUNT(*) FROM capital_observations WHERE dataset=? AND symbol=? AND date BETWEEN ? AND ?", params,
            ).fetchone()[0]
            page_count = max(1, (total + page_size - 1) // page_size)
            page = min(page, page_count)
            rows = connection.execute(
                "SELECT payload FROM capital_observations WHERE dataset=? AND symbol=? AND date BETWEEN ? AND ? ORDER BY date DESC LIMIT ? OFFSET ?",
                (*params, page_size, (page - 1) * page_size),
            ).fetchall()
        return {"rows": [json.loads(row["payload"]) for row in rows], "total": total,
                "page": page, "pageSize": page_size, "pageCount": page_count}

    def save(self, dataset: str, symbol: str, rows: list[dict], *, start: str, end: str,
             status: str, reason: str, received_at: str, replace_window: bool = False) -> None:
        with self._connect() as connection:
            if replace_window and status in {"ready", "empty"}:
                connection.execute(
                    "DELETE FROM capital_observations WHERE dataset=? AND symbol=? AND date BETWEEN ? AND ?",
                    (dataset, symbol, start, end),
                )
            connection.executemany(
                """INSERT INTO capital_observations VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(dataset, symbol, date) DO UPDATE SET
                   payload=excluded.payload, received_at=excluded.received_at""",
                [(dataset, symbol, row["date"], json.dumps(row, ensure_ascii=False), received_at) for row in rows],
            )
            connection.execute(
                """INSERT INTO capital_fetches VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(dataset, symbol) DO UPDATE SET
                   start_date=excluded.start_date, end_date=excluded.end_date,
                   status=excluded.status, reason=excluded.reason, received_at=excluded.received_at""",
                (dataset, symbol, start, end, status, reason, received_at),
            )
