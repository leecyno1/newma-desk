import hashlib
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
CREATE TABLE IF NOT EXISTS mod_context_instances (
  user_id TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  module_id TEXT NOT NULL,
  instance_id TEXT NOT NULL,
  subject_key TEXT NOT NULL,
  revision INTEGER NOT NULL,
  context_revision TEXT NOT NULL,
  context_json TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (user_id, workspace_id, module_id, instance_id, subject_key)
);
CREATE INDEX IF NOT EXISTS idx_mod_context_instances_latest
  ON mod_context_instances(user_id, workspace_id, module_id, updated_at DESC);
"""


def _subject_key(context: dict[str, Any], instance_id: str) -> str:
    wiki = context.get("wiki")
    subject = wiki.get("primarySubject") if isinstance(wiki, dict) else None
    canonical_id = subject.get("canonicalId") if isinstance(subject, dict) else None
    if isinstance(canonical_id, str) and canonical_id.strip():
        return canonical_id.strip()[:240]
    return instance_id


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
        instance_id: str = "default",
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
        subject_key = _subject_key(context, instance_id)
        context_revision = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:24]
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
            connection.execute(
                """
                INSERT INTO mod_context_instances (
                  user_id, workspace_id, module_id, instance_id, subject_key,
                  revision, context_revision, context_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(
                  user_id, workspace_id, module_id, instance_id, subject_key
                ) DO UPDATE SET
                  revision = excluded.revision,
                  context_revision = excluded.context_revision,
                  context_json = excluded.context_json,
                  updated_at = excluded.updated_at
                """,
                (
                    user_id,
                    workspace_id,
                    module_id,
                    instance_id,
                    subject_key,
                    revision,
                    context_revision,
                    serialized,
                    updated_at,
                ),
            )
        return {
            "moduleId": module_id,
            "instanceId": instance_id,
            "subjectKey": subject_key,
            "contextRevision": context_revision,
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
        instance_id: str | None = None,
        subject_key: str | None = None,
    ) -> dict[str, Any] | None:
        if not self._database_path.exists():
            return None
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            filters = ["user_id = ?", "workspace_id = ?", "module_id = ?"]
            values: list[object] = [user_id, workspace_id, module_id]
            if instance_id is not None:
                filters.append("instance_id = ?")
                values.append(instance_id)
            if subject_key is not None:
                filters.append("subject_key = ?")
                values.append(subject_key)
            row = connection.execute(
                f"""
                SELECT instance_id, subject_key, revision, context_revision,
                       context_json, updated_at
                FROM mod_context_instances
                WHERE {' AND '.join(filters)}
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                values,
            ).fetchone()
            if row is None and instance_id is None and subject_key is None:
                legacy = connection.execute(
                    """
                    SELECT revision, context_json, updated_at
                    FROM mod_contexts
                    WHERE user_id = ? AND workspace_id = ? AND module_id = ?
                    """,
                    (user_id, workspace_id, module_id),
                ).fetchone()
                if legacy is not None:
                    row = {
                        "instance_id": "legacy",
                        "subject_key": "legacy",
                        "revision": legacy["revision"],
                        "context_revision": "legacy",
                        "context_json": legacy["context_json"],
                        "updated_at": legacy["updated_at"],
                    }
        if row is None:
            return None
        context = json.loads(row["context_json"])
        if not isinstance(context, dict):
            raise ValueError("stored Mod context must be an object")
        return {
            "moduleId": module_id,
            "instanceId": row["instance_id"],
            "subjectKey": row["subject_key"],
            "contextRevision": row["context_revision"],
            "revision": row["revision"],
            "userId": user_id,
            "workspaceId": workspace_id,
            "context": context,
            "updatedAt": row["updated_at"],
        }
