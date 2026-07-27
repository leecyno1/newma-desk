import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

from vibe_visualization_api.data_services.models import DataServicePreferences


SCHEMA = """
CREATE TABLE IF NOT EXISTS data_service_preferences (
  user_id TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  suite_id TEXT NOT NULL,
  capability_services_json TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (user_id, workspace_id, suite_id)
);
"""


class DataServicePreferenceStore:
    def __init__(self, database_path: Path):
        self._database_path = database_path
        self._initialized = False
        self._initialize_lock = threading.Lock()

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        with self._initialize_lock:
            if self._initialized:
                return
            self._database_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self._database_path, timeout=10) as connection:
                connection.executescript(SCHEMA)
            self._initialized = True

    def _connect(self) -> sqlite3.Connection:
        self._ensure_initialized()
        connection = sqlite3.connect(self._database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def get(
        self,
        *,
        user_id: str,
        workspace_id: str,
        suite_id: str,
    ) -> DataServicePreferences:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT capability_services_json, updated_at
                FROM data_service_preferences
                WHERE user_id = ? AND workspace_id = ? AND suite_id = ?
                """,
                (user_id, workspace_id, suite_id),
            ).fetchone()
        if row is None:
            return DataServicePreferences(
                userId=user_id,
                workspaceId=workspace_id,
                suiteId=suite_id,
                capabilityServices={},
                updatedAt=None,
            )
        try:
            routes = json.loads(row["capability_services_json"])
        except (TypeError, ValueError):
            routes = {}
        if not isinstance(routes, dict):
            routes = {}
        return DataServicePreferences(
            userId=user_id,
            workspaceId=workspace_id,
            suiteId=suite_id,
            capabilityServices=routes,
            updatedAt=row["updated_at"],
        )

    def set(
        self,
        *,
        user_id: str,
        workspace_id: str,
        suite_id: str,
        capability_services: dict[str, str],
    ) -> DataServicePreferences:
        updated_at = datetime.now(UTC).isoformat()
        serialized = json.dumps(
            capability_services,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO data_service_preferences (
                  user_id, workspace_id, suite_id,
                  capability_services_json, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, workspace_id, suite_id) DO UPDATE SET
                  capability_services_json = excluded.capability_services_json,
                  updated_at = excluded.updated_at
                """,
                (user_id, workspace_id, suite_id, serialized, updated_at),
            )
        return DataServicePreferences(
            userId=user_id,
            workspaceId=workspace_id,
            suiteId=suite_id,
            capabilityServices=capability_services,
            updatedAt=updated_at,
        )
