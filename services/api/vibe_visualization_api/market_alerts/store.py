import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from vibe_visualization_api.market_alerts.models import (
    MarketAlertCreate,
    MarketAlertUpdate,
)


SCHEMA = """
CREATE TABLE IF NOT EXISTS market_alerts (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  security_json TEXT NOT NULL,
  direction TEXT NOT NULL CHECK(direction IN ('above', 'below')),
  price REAL NOT NULL CHECK(price > 0),
  label TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS market_alerts_owner_updated_idx
  ON market_alerts(user_id, workspace_id, updated_at DESC);
"""


class MarketAlertStoreError(Exception):
    """Base error for shared market alerts."""


class MarketAlertNotFoundError(MarketAlertStoreError):
    """Raised when an alert is unavailable to the current owner."""


class MarketAlertLimitError(MarketAlertStoreError):
    """Raised when a workspace exceeds its lightweight rule limit."""


class MarketAlertStore:
    MAX_ALERTS_PER_WORKSPACE = 200

    def __init__(self, database_path: Path):
        self._database_path = database_path

    def _connect(self) -> sqlite3.Connection:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": str(row["id"]),
            "userId": str(row["user_id"]),
            "workspaceId": str(row["workspace_id"]),
            "security": json.loads(row["security_json"]),
            "direction": str(row["direction"]),
            "price": float(row["price"]),
            "label": str(row["label"]),
            "enabled": bool(row["enabled"]),
            "createdAt": str(row["created_at"]),
            "updatedAt": str(row["updated_at"]),
        }

    def list(
        self,
        *,
        user_id: str,
        workspace_id: str,
        enabled: bool | None = None,
    ) -> dict[str, Any]:
        query = """
            SELECT * FROM market_alerts
            WHERE user_id = ? AND workspace_id = ?
        """
        parameters: list[Any] = [user_id, workspace_id]
        if enabled is not None:
            query += " AND enabled = ?"
            parameters.append(1 if enabled else 0)
        query += " ORDER BY updated_at DESC, id DESC"
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            rows = connection.execute(query, parameters).fetchall()
        return {
            "userId": user_id,
            "workspaceId": workspace_id,
            "items": [self._row(row) for row in rows],
        }

    def create(
        self,
        *,
        user_id: str,
        workspace_id: str,
        alert: MarketAlertCreate,
    ) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
        alert_id = str(uuid4())
        security_json = json.dumps(
            alert.security.model_dump(mode="json", by_alias=True),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        label = alert.label or (
            f"{alert.security.name} "
            f"{'上穿' if alert.direction == 'above' else '下穿'} {alert.price:g}"
        )
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            connection.execute("BEGIN IMMEDIATE")
            count = connection.execute(
                """
                SELECT COUNT(*) FROM market_alerts
                WHERE user_id = ? AND workspace_id = ?
                """,
                (user_id, workspace_id),
            ).fetchone()[0]
            if int(count) >= self.MAX_ALERTS_PER_WORKSPACE:
                raise MarketAlertLimitError("market alert workspace limit reached")
            connection.execute(
                """
                INSERT INTO market_alerts (
                  id, user_id, workspace_id, security_json, direction,
                  price, label, enabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    alert_id,
                    user_id,
                    workspace_id,
                    security_json,
                    alert.direction,
                    alert.price,
                    label,
                    1 if alert.enabled else 0,
                    now,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM market_alerts WHERE id = ?",
                (alert_id,),
            ).fetchone()
        return self._row(row)

    def update(
        self,
        *,
        user_id: str,
        workspace_id: str,
        alert_id: str,
        update: MarketAlertUpdate,
    ) -> dict[str, Any]:
        fields = update.model_dump(exclude_unset=True)
        assignments = []
        parameters: list[Any] = []
        for name in ("direction", "price", "label", "enabled"):
            if name not in fields:
                continue
            assignments.append(f"{name} = ?")
            value = fields[name]
            parameters.append(1 if name == "enabled" and value else 0 if name == "enabled" else value)
        assignments.append("updated_at = ?")
        parameters.append(datetime.now(UTC).isoformat())
        parameters.extend([alert_id, user_id, workspace_id])
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                f"""
                UPDATE market_alerts SET {', '.join(assignments)}
                WHERE id = ? AND user_id = ? AND workspace_id = ?
                """,
                parameters,
            )
            if cursor.rowcount != 1:
                raise MarketAlertNotFoundError("market alert was not found")
            row = connection.execute(
                "SELECT * FROM market_alerts WHERE id = ?",
                (alert_id,),
            ).fetchone()
        return self._row(row)

    def delete(
        self,
        *,
        user_id: str,
        workspace_id: str,
        alert_id: str,
    ) -> dict[str, Any]:
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                DELETE FROM market_alerts
                WHERE id = ? AND user_id = ? AND workspace_id = ?
                """,
                (alert_id, user_id, workspace_id),
            )
            if cursor.rowcount != 1:
                raise MarketAlertNotFoundError("market alert was not found")
        return {"id": alert_id, "deleted": True}
