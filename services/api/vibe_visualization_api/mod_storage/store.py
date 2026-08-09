import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS mod_storage_documents (
  user_id TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  module_id TEXT NOT NULL,
  namespace TEXT NOT NULL,
  document_key TEXT NOT NULL,
  schema_version INTEGER NOT NULL,
  revision INTEGER NOT NULL,
  value_json TEXT NOT NULL,
  size_bytes INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (
    user_id,
    workspace_id,
    module_id,
    namespace,
    document_key
  )
);
CREATE INDEX IF NOT EXISTS idx_mod_storage_namespace
ON mod_storage_documents (
  user_id,
  workspace_id,
  module_id,
  namespace,
  document_key
);
"""


class ModStorageError(Exception):
    """Base error for Desk-managed Mod storage."""


class ModStorageNotFoundError(ModStorageError):
    """Raised when a requested document does not exist."""


class ModStorageConflictError(ModStorageError):
    """Raised when optimistic concurrency detects a stale revision."""


class ModStorageQuotaError(ModStorageError):
    """Raised when a document or namespace exceeds its declared quota."""


class ModStorageCorruptError(ModStorageError):
    """Raised when persisted JSON cannot be decoded."""


class ModStorageStore:
    def __init__(self, database_path: Path):
        self._database_path = database_path

    def _connect(self) -> sqlite3.Connection:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _serialize(value: Any) -> tuple[str, int]:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return encoded, len(encoded.encode("utf-8"))

    @staticmethod
    def _document(row: sqlite3.Row) -> dict[str, Any]:
        try:
            value = json.loads(row["value_json"])
        except json.JSONDecodeError as error:
            raise ModStorageCorruptError("stored Mod document is corrupt") from error
        return {
            "moduleId": str(row["module_id"]),
            "namespace": str(row["namespace"]),
            "key": str(row["document_key"]),
            "schemaVersion": int(row["schema_version"]),
            "revision": int(row["revision"]),
            "value": value,
            "sizeBytes": int(row["size_bytes"]),
            "createdAt": str(row["created_at"]),
            "updatedAt": str(row["updated_at"]),
        }

    def get(
        self,
        *,
        user_id: str,
        workspace_id: str,
        module_id: str,
        namespace: str,
        key: str,
    ) -> dict[str, Any]:
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            row = connection.execute(
                """
                SELECT * FROM mod_storage_documents
                WHERE user_id = ? AND workspace_id = ? AND module_id = ?
                  AND namespace = ? AND document_key = ?
                """,
                (user_id, workspace_id, module_id, namespace, key),
            ).fetchone()
        if row is None:
            raise ModStorageNotFoundError("Mod storage document was not found")
        return self._document(row)

    def list_documents(
        self,
        *,
        user_id: str,
        workspace_id: str,
        module_id: str,
        namespace: str,
        cursor: str | None,
        limit: int,
    ) -> dict[str, Any]:
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            rows = connection.execute(
                """
                SELECT * FROM mod_storage_documents
                WHERE user_id = ? AND workspace_id = ? AND module_id = ?
                  AND namespace = ? AND document_key > ?
                ORDER BY document_key ASC
                LIMIT ?
                """,
                (
                    user_id,
                    workspace_id,
                    module_id,
                    namespace,
                    cursor or "",
                    limit + 1,
                ),
            ).fetchall()
        has_more = len(rows) > limit
        selected = rows[:limit]
        return {
            "items": [self._document(row) for row in selected],
            "nextCursor": (
                str(selected[-1]["document_key"])
                if has_more and selected
                else None
            ),
        }

    def put(
        self,
        *,
        user_id: str,
        workspace_id: str,
        module_id: str,
        namespace: str,
        key: str,
        schema_version: int,
        expected_revision: int,
        value: Any,
        quota_bytes: int,
        max_item_bytes: int,
    ) -> dict[str, Any]:
        serialized, size_bytes = self._serialize(value)
        if size_bytes > max_item_bytes:
            raise ModStorageQuotaError("Mod storage document is too large")
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute(
                """
                SELECT revision, size_bytes, created_at
                FROM mod_storage_documents
                WHERE user_id = ? AND workspace_id = ? AND module_id = ?
                  AND namespace = ? AND document_key = ?
                """,
                (user_id, workspace_id, module_id, namespace, key),
            ).fetchone()
            current_revision = int(current["revision"]) if current else 0
            if current_revision != expected_revision:
                raise ModStorageConflictError("Mod storage revision is stale")
            namespace_size = connection.execute(
                """
                SELECT COALESCE(SUM(size_bytes), 0) AS total
                FROM mod_storage_documents
                WHERE user_id = ? AND workspace_id = ? AND module_id = ?
                  AND namespace = ?
                """,
                (user_id, workspace_id, module_id, namespace),
            ).fetchone()
            total_bytes = int(namespace_size["total"])
            previous_size = int(current["size_bytes"]) if current else 0
            if total_bytes - previous_size + size_bytes > quota_bytes:
                raise ModStorageQuotaError("Mod storage namespace quota exceeded")
            revision = current_revision + 1
            created_at = str(current["created_at"]) if current else now
            connection.execute(
                """
                INSERT INTO mod_storage_documents (
                  user_id, workspace_id, module_id, namespace, document_key,
                  schema_version, revision, value_json, size_bytes,
                  created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (
                  user_id, workspace_id, module_id, namespace, document_key
                ) DO UPDATE SET
                  schema_version = excluded.schema_version,
                  revision = excluded.revision,
                  value_json = excluded.value_json,
                  size_bytes = excluded.size_bytes,
                  updated_at = excluded.updated_at
                """,
                (
                    user_id,
                    workspace_id,
                    module_id,
                    namespace,
                    key,
                    schema_version,
                    revision,
                    serialized,
                    size_bytes,
                    created_at,
                    now,
                ),
            )
            row = connection.execute(
                """
                SELECT * FROM mod_storage_documents
                WHERE user_id = ? AND workspace_id = ? AND module_id = ?
                  AND namespace = ? AND document_key = ?
                """,
                (user_id, workspace_id, module_id, namespace, key),
            ).fetchone()
        if row is None:
            raise ModStorageNotFoundError("Mod storage document was not found")
        return self._document(row)

    def delete(
        self,
        *,
        user_id: str,
        workspace_id: str,
        module_id: str,
        namespace: str,
        key: str,
        expected_revision: int,
    ) -> None:
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT revision FROM mod_storage_documents
                WHERE user_id = ? AND workspace_id = ? AND module_id = ?
                  AND namespace = ? AND document_key = ?
                """,
                (user_id, workspace_id, module_id, namespace, key),
            ).fetchone()
            if row is None:
                raise ModStorageNotFoundError("Mod storage document was not found")
            if int(row["revision"]) != expected_revision:
                raise ModStorageConflictError("Mod storage revision is stale")
            connection.execute(
                """
                DELETE FROM mod_storage_documents
                WHERE user_id = ? AND workspace_id = ? AND module_id = ?
                  AND namespace = ? AND document_key = ?
                """,
                (user_id, workspace_id, module_id, namespace, key),
            )
