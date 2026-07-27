import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS mod_contexts (
  user_id TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  module_id TEXT NOT NULL,
  revision INTEGER NOT NULL,
  context_json TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (user_id, workspace_id, module_id)
);
"""


class ModContextStore:
    def __init__(self, database_path: Path):
        self._database_path = database_path

    def _connect(self) -> sqlite3.Connection:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def put(
        self,
        *,
        user_id: str,
        workspace_id: str,
        module_id: str,
        revision: int,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        updated_at = datetime.now(UTC).isoformat()
        serialized = json.dumps(
            context,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            connection.execute(
                """
                INSERT INTO mod_contexts (
                  user_id, workspace_id, module_id, revision,
                  context_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, workspace_id, module_id) DO UPDATE SET
                  revision = excluded.revision,
                  context_json = excluded.context_json,
                  updated_at = excluded.updated_at
                """,
                (
                    user_id,
                    workspace_id,
                    module_id,
                    revision,
                    serialized,
                    updated_at,
                ),
            )
        return {
            "moduleId": module_id,
            "revision": revision,
            "userId": user_id,
            "workspaceId": workspace_id,
            "context": context,
            "updatedAt": updated_at,
        }

    def get(
        self,
        *,
        user_id: str,
        workspace_id: str,
        module_id: str,
    ) -> dict[str, Any] | None:
        if not self._database_path.exists():
            return None
        with self._connect() as connection:
            table = connection.execute(
                """
                SELECT 1 FROM sqlite_master
                WHERE type = 'table' AND name = 'mod_contexts'
                """
            ).fetchone()
            if table is None:
                return None
            row = connection.execute(
                """
                SELECT revision, context_json, updated_at
                FROM mod_contexts
                WHERE user_id = ? AND workspace_id = ? AND module_id = ?
                """,
                (user_id, workspace_id, module_id),
            ).fetchone()
        if row is None:
            return None
        context = json.loads(row["context_json"])
        if not isinstance(context, dict):
            raise ValueError("stored Mod context must be an object")
        return {
            "moduleId": module_id,
            "revision": row["revision"],
            "userId": user_id,
            "workspaceId": workspace_id,
            "context": context,
            "updatedAt": row["updated_at"],
        }
