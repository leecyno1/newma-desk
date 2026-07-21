import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

from vibe_visualization_api.agent_gateway.models import AgentPreferences


SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_preferences (
  user_id TEXT PRIMARY KEY,
  default_adapter TEXT NOT NULL,
  module_overrides_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
"""


class AgentPreferenceStore:
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

    def get(self, user_id: str, default_adapter: str) -> AgentPreferences:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT default_adapter, module_overrides_json, updated_at
                FROM agent_preferences
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()
        if row is None:
            return AgentPreferences(
                user_id=user_id,
                default_adapter=default_adapter,
                module_overrides={},
                updated_at=None,
            )
        try:
            overrides = json.loads(row["module_overrides_json"])
        except (TypeError, ValueError):
            overrides = {}
        if not isinstance(overrides, dict):
            overrides = {}
        return AgentPreferences(
            user_id=user_id,
            default_adapter=row["default_adapter"],
            module_overrides=overrides,
            updated_at=row["updated_at"],
        )

    def set(
        self,
        user_id: str,
        default_adapter: str,
        module_overrides: dict[str, str],
    ) -> AgentPreferences:
        updated_at = datetime.now(UTC).isoformat()
        serialized = json.dumps(
            module_overrides,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO agent_preferences (
                  user_id, default_adapter, module_overrides_json, updated_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                  default_adapter = excluded.default_adapter,
                  module_overrides_json = excluded.module_overrides_json,
                  updated_at = excluded.updated_at
                """,
                (user_id, default_adapter, serialized, updated_at),
            )
        return AgentPreferences(
            user_id=user_id,
            default_adapter=default_adapter,
            module_overrides=module_overrides,
            updated_at=updated_at,
        )

    def resolve(
        self,
        user_id: str,
        module_id: str | None,
        default_adapter: str,
    ) -> str:
        preferences = self.get(user_id, default_adapter)
        if module_id is not None:
            selected = preferences.module_overrides.get(module_id)
            if selected:
                return selected
        return preferences.default_adapter
