from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Callable


SCHEMA = """
CREATE TABLE IF NOT EXISTS creator_studio_runs (
  user_id TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  title TEXT NOT NULL,
  status TEXT NOT NULL,
  document_json TEXT NOT NULL,
  revision INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (user_id, workspace_id, run_id)
);

CREATE INDEX IF NOT EXISTS creator_studio_runs_scope_updated
ON creator_studio_runs(user_id, workspace_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS creator_studio_events (
  sequence INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  action_id TEXT,
  stage_id TEXT,
  node_id TEXT,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS creator_studio_events_scope_sequence
ON creator_studio_events(user_id, workspace_id, run_id, sequence);

CREATE TABLE IF NOT EXISTS creator_execution_jobs (
  user_id TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  job_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  stage_id TEXT NOT NULL,
  node_id TEXT NOT NULL,
  executor_id TEXT NOT NULL,
  status TEXT NOT NULL,
  progress INTEGER NOT NULL,
  cancel_requested INTEGER NOT NULL DEFAULT 0,
  document_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (user_id, workspace_id, job_id)
);

CREATE INDEX IF NOT EXISTS creator_execution_jobs_run_updated
ON creator_execution_jobs(user_id, workspace_id, run_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS creator_execution_jobs_status
ON creator_execution_jobs(status, updated_at);

CREATE TABLE IF NOT EXISTS creator_editor_sessions (
  user_id TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  session_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  stage_id TEXT NOT NULL,
  node_id TEXT NOT NULL,
  status TEXT NOT NULL,
  document_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (user_id, workspace_id, session_id)
);

CREATE INDEX IF NOT EXISTS creator_editor_sessions_run_updated
ON creator_editor_sessions(user_id, workspace_id, run_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS creator_marketplace_presets (
  user_id TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  preset_id TEXT NOT NULL,
  item_id TEXT NOT NULL,
  item_kind TEXT NOT NULL,
  document_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (user_id, workspace_id, preset_id)
);

CREATE INDEX IF NOT EXISTS creator_marketplace_presets_scope_updated
ON creator_marketplace_presets(user_id, workspace_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS creator_marketplace_preset_versions (
  user_id TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  preset_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  document_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (user_id, workspace_id, preset_id, version)
);

CREATE INDEX IF NOT EXISTS creator_marketplace_preset_versions_scope
ON creator_marketplace_preset_versions(user_id, workspace_id, preset_id, version DESC);
"""


class CreatorRunNotFoundError(Exception):
    """Raised when a scoped Creator Studio run does not exist."""


class CreatorRunConflictError(Exception):
    """Raised when a command targets a stale run revision."""


class CreatorJobNotFoundError(Exception):
    """Raised when a scoped Creator execution job does not exist."""


class CreatorEditorSessionNotFoundError(Exception):
    """Raised when a scoped Creator editor session does not exist."""


class CreatorPresetNotFoundError(Exception):
    """Raised when a scoped Creator Marketplace preset does not exist."""


class CreatorPresetConflictError(Exception):
    """Raised when a preset update targets a stale version."""


class CreatorRunRepository:
    def __init__(self, database_path: Path):
        self._database_path = database_path

    def _connect(self) -> sqlite3.Connection:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict[str, Any]:
        return json.loads(row["document_json"])

    @staticmethod
    def _insert_event(
        connection: sqlite3.Connection,
        *,
        user_id: str,
        workspace_id: str,
        run_id: str,
        event: dict[str, Any],
    ) -> None:
        cursor = connection.execute(
            """
            INSERT INTO creator_studio_events (
              user_id, workspace_id, run_id, event_type, action_id,
              stage_id, node_id, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                workspace_id,
                run_id,
                event["type"],
                event.get("actionId"),
                event.get("stageId"),
                event.get("nodeId"),
                json.dumps(event.get("payload", {}), ensure_ascii=False),
                event["createdAt"],
            ),
        )
        event["sequence"] = int(cursor.lastrowid)

    @staticmethod
    def _write_run(
        connection: sqlite3.Connection,
        *,
        user_id: str,
        workspace_id: str,
        document: dict[str, Any],
        revision: int,
    ) -> None:
        connection.execute(
            """
            UPDATE creator_studio_runs
            SET title = ?, status = ?, document_json = ?,
                revision = ?, updated_at = ?
            WHERE user_id = ? AND workspace_id = ? AND run_id = ?
            """,
            (
                document["title"],
                document["status"],
                json.dumps(document, ensure_ascii=False),
                revision,
                document["updatedAt"],
                user_id,
                workspace_id,
                document["runId"],
            ),
        )

    def list_runs(
        self,
        *,
        user_id: str,
        workspace_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            rows = connection.execute(
                """
                SELECT document_json FROM creator_studio_runs
                WHERE user_id = ? AND workspace_id = ?
                ORDER BY updated_at DESC, run_id
                LIMIT ?
                """,
                (user_id, workspace_id, limit),
            ).fetchall()
        return [self._decode(row) for row in rows]

    def get_run(
        self,
        *,
        user_id: str,
        workspace_id: str,
        run_id: str,
    ) -> dict[str, Any]:
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            row = connection.execute(
                """
                SELECT document_json FROM creator_studio_runs
                WHERE user_id = ? AND workspace_id = ? AND run_id = ?
                """,
                (user_id, workspace_id, run_id),
            ).fetchone()
        if row is None:
            raise CreatorRunNotFoundError(run_id)
        return self._decode(row)

    def list_presets(self, *, user_id: str, workspace_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            rows = connection.execute(
                """
                SELECT document_json FROM creator_marketplace_presets
                WHERE user_id = ? AND workspace_id = ?
                ORDER BY updated_at DESC, preset_id
                """,
                (user_id, workspace_id),
            ).fetchall()
        return [self._decode(row) for row in rows]

    def get_preset(
        self,
        *,
        user_id: str,
        workspace_id: str,
        preset_id: str,
    ) -> dict[str, Any]:
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            row = connection.execute(
                """
                SELECT document_json FROM creator_marketplace_presets
                WHERE user_id = ? AND workspace_id = ? AND preset_id = ?
                """,
                (user_id, workspace_id, preset_id),
            ).fetchone()
        if row is None:
            raise CreatorPresetNotFoundError(preset_id)
        return self._decode(row)

    def create_preset(
        self,
        *,
        user_id: str,
        workspace_id: str,
        document: dict[str, Any],
    ) -> dict[str, Any]:
        encoded = json.dumps(document, ensure_ascii=False)
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            connection.execute(
                """
                INSERT INTO creator_marketplace_presets (
                  user_id, workspace_id, preset_id, item_id, item_kind,
                  document_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    workspace_id,
                    document["presetId"],
                    document["itemId"],
                    document["itemKind"],
                    encoded,
                    document["createdAt"],
                    document["updatedAt"],
                ),
            )
            connection.execute(
                """
                INSERT INTO creator_marketplace_preset_versions (
                  user_id, workspace_id, preset_id, version, document_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    workspace_id,
                    document["presetId"],
                    document["version"],
                    encoded,
                    document["updatedAt"],
                ),
            )
            connection.commit()
        return document

    def list_preset_versions(
        self,
        *,
        user_id: str,
        workspace_id: str,
        preset_id: str,
    ) -> list[dict[str, Any]]:
        current = self.get_preset(
            user_id=user_id,
            workspace_id=workspace_id,
            preset_id=preset_id,
        )
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            rows = connection.execute(
                """
                SELECT document_json FROM creator_marketplace_preset_versions
                WHERE user_id = ? AND workspace_id = ? AND preset_id = ?
                ORDER BY version DESC
                """,
                (user_id, workspace_id, preset_id),
            ).fetchall()
        versions = [self._decode(row) for row in rows]
        if not any(item.get("version") == current.get("version") for item in versions):
            versions.insert(0, current)
        return versions

    def get_preset_version(
        self,
        *,
        user_id: str,
        workspace_id: str,
        preset_id: str,
        version: int,
    ) -> dict[str, Any]:
        current = self.get_preset(
            user_id=user_id,
            workspace_id=workspace_id,
            preset_id=preset_id,
        )
        if current.get("version") == version:
            return current
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            row = connection.execute(
                """
                SELECT document_json FROM creator_marketplace_preset_versions
                WHERE user_id = ? AND workspace_id = ? AND preset_id = ? AND version = ?
                """,
                (user_id, workspace_id, preset_id, version),
            ).fetchone()
        if row is None:
            raise CreatorPresetNotFoundError(f"{preset_id}@{version}")
        return self._decode(row)

    def update_preset(
        self,
        *,
        user_id: str,
        workspace_id: str,
        document: dict[str, Any],
        expected_version: int,
    ) -> dict[str, Any]:
        encoded = json.dumps(document, ensure_ascii=False)
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            row = connection.execute(
                """
                SELECT document_json FROM creator_marketplace_presets
                WHERE user_id = ? AND workspace_id = ? AND preset_id = ?
                """,
                (user_id, workspace_id, document["presetId"]),
            ).fetchone()
            if row is None:
                raise CreatorPresetNotFoundError(document["presetId"])
            current = self._decode(row)
            if current.get("version") != expected_version:
                raise CreatorPresetConflictError(document["presetId"])
            connection.execute(
                """
                INSERT OR IGNORE INTO creator_marketplace_preset_versions (
                  user_id, workspace_id, preset_id, version, document_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id, workspace_id, current["presetId"], current["version"],
                    json.dumps(current, ensure_ascii=False), current["updatedAt"],
                ),
            )
            connection.execute(
                """
                INSERT INTO creator_marketplace_preset_versions (
                  user_id, workspace_id, preset_id, version, document_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id, workspace_id, document["presetId"], document["version"],
                    encoded, document["updatedAt"],
                ),
            )
            connection.execute(
                """
                UPDATE creator_marketplace_presets
                SET document_json = ?, updated_at = ?
                WHERE user_id = ? AND workspace_id = ? AND preset_id = ?
                """,
                (encoded, document["updatedAt"], user_id, workspace_id, document["presetId"]),
            )
            connection.commit()
        return document

    def create_run(
        self,
        *,
        user_id: str,
        workspace_id: str,
        document: dict[str, Any],
        event: dict[str, Any],
    ) -> dict[str, Any]:
        encoded_event = json.dumps(event.get("payload", {}), ensure_ascii=False)
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            try:
                connection.execute(
                    """
                    INSERT INTO creator_studio_runs (
                      user_id, workspace_id, run_id, title, status,
                      document_json, revision, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        workspace_id,
                        document["runId"],
                        document["title"],
                        document["status"],
                        json.dumps(document, ensure_ascii=False),
                        document["revision"],
                        document["createdAt"],
                        document["updatedAt"],
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise CreatorRunConflictError(document["runId"]) from error
            cursor = connection.execute(
                """
                INSERT INTO creator_studio_events (
                  user_id, workspace_id, run_id, event_type, action_id,
                  stage_id, node_id, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    workspace_id,
                    document["runId"],
                    event["type"],
                    event.get("actionId"),
                    event.get("stageId"),
                    event.get("nodeId"),
                    encoded_event,
                    event["createdAt"],
                ),
            )
            event["sequence"] = int(cursor.lastrowid)
            document.setdefault("events", []).append(event)
            connection.execute(
                """
                UPDATE creator_studio_runs SET document_json = ?
                WHERE user_id = ? AND workspace_id = ? AND run_id = ?
                """,
                (
                    json.dumps(document, ensure_ascii=False),
                    user_id,
                    workspace_id,
                    document["runId"],
                ),
            )
        return document

    def update_run(
        self,
        *,
        user_id: str,
        workspace_id: str,
        document: dict[str, Any],
        expected_revision: int,
        event: dict[str, Any],
    ) -> dict[str, Any]:
        run_id = str(document["runId"])
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            row = connection.execute(
                """
                SELECT revision FROM creator_studio_runs
                WHERE user_id = ? AND workspace_id = ? AND run_id = ?
                """,
                (user_id, workspace_id, run_id),
            ).fetchone()
            if row is None:
                raise CreatorRunNotFoundError(run_id)
            if int(row["revision"]) != expected_revision:
                raise CreatorRunConflictError(run_id)
            next_revision = expected_revision + 1
            cursor = connection.execute(
                """
                INSERT INTO creator_studio_events (
                  user_id, workspace_id, run_id, event_type, action_id,
                  stage_id, node_id, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    workspace_id,
                    run_id,
                    event["type"],
                    event.get("actionId"),
                    event.get("stageId"),
                    event.get("nodeId"),
                    json.dumps(event.get("payload", {}), ensure_ascii=False),
                    event["createdAt"],
                ),
            )
            event["sequence"] = int(cursor.lastrowid)
            document["revision"] = next_revision
            document.setdefault("events", []).append(event)
            connection.execute(
                """
                UPDATE creator_studio_runs
                SET title = ?, status = ?, document_json = ?,
                    revision = ?, updated_at = ?
                WHERE user_id = ? AND workspace_id = ? AND run_id = ?
                """,
                (
                    document["title"],
                    document["status"],
                    json.dumps(document, ensure_ascii=False),
                    next_revision,
                    document["updatedAt"],
                    user_id,
                    workspace_id,
                    run_id,
                ),
            )
        return document

    def update_run_with_job(
        self,
        *,
        user_id: str,
        workspace_id: str,
        document: dict[str, Any],
        expected_revision: int,
        event: dict[str, Any],
        job: dict[str, Any],
    ) -> dict[str, Any]:
        """Atomically persist a queued node state and its execution job."""

        run_id = str(document["runId"])
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT revision FROM creator_studio_runs
                WHERE user_id = ? AND workspace_id = ? AND run_id = ?
                """,
                (user_id, workspace_id, run_id),
            ).fetchone()
            if row is None:
                raise CreatorRunNotFoundError(run_id)
            if int(row["revision"]) != expected_revision:
                raise CreatorRunConflictError(run_id)

            connection.execute(
                """
                INSERT INTO creator_execution_jobs (
                  user_id, workspace_id, job_id, run_id, stage_id, node_id,
                  executor_id, status, progress, cancel_requested,
                  document_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    workspace_id,
                    job["jobId"],
                    job["runId"],
                    job["stageId"],
                    job["nodeId"],
                    job["executorId"],
                    job["status"],
                    job["progress"],
                    int(bool(job.get("cancelRequested"))),
                    json.dumps(job, ensure_ascii=False),
                    job["createdAt"],
                    job["updatedAt"],
                ),
            )
            self._insert_event(
                connection,
                user_id=user_id,
                workspace_id=workspace_id,
                run_id=run_id,
                event=event,
            )
            next_revision = expected_revision + 1
            document["revision"] = next_revision
            document.setdefault("events", []).append(event)
            self._write_run(
                connection,
                user_id=user_id,
                workspace_id=workspace_id,
                document=document,
                revision=next_revision,
            )
        return document

    def mutate_run(
        self,
        *,
        user_id: str,
        workspace_id: str,
        run_id: str,
        mutate: Callable[[dict[str, Any]], None],
        event: dict[str, Any],
    ) -> dict[str, Any]:
        """Apply a background execution update against the latest run revision."""

        with self._connect() as connection:
            connection.executescript(SCHEMA)
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT document_json, revision FROM creator_studio_runs
                WHERE user_id = ? AND workspace_id = ? AND run_id = ?
                """,
                (user_id, workspace_id, run_id),
            ).fetchone()
            if row is None:
                raise CreatorRunNotFoundError(run_id)
            document = self._decode(row)
            mutate(document)
            document["updatedAt"] = event["createdAt"]
            self._insert_event(
                connection,
                user_id=user_id,
                workspace_id=workspace_id,
                run_id=run_id,
                event=event,
            )
            next_revision = int(row["revision"]) + 1
            document["revision"] = next_revision
            document.setdefault("events", []).append(event)
            self._write_run(
                connection,
                user_id=user_id,
                workspace_id=workspace_id,
                document=document,
                revision=next_revision,
            )
        return document

    def get_job(
        self,
        *,
        user_id: str,
        workspace_id: str,
        job_id: str,
    ) -> dict[str, Any]:
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            row = connection.execute(
                """
                SELECT document_json FROM creator_execution_jobs
                WHERE user_id = ? AND workspace_id = ? AND job_id = ?
                """,
                (user_id, workspace_id, job_id),
            ).fetchone()
        if row is None:
            raise CreatorJobNotFoundError(job_id)
        return self._decode(row)

    def list_jobs(
        self,
        *,
        user_id: str,
        workspace_id: str,
        run_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            rows = connection.execute(
                """
                SELECT document_json FROM creator_execution_jobs
                WHERE user_id = ? AND workspace_id = ? AND run_id = ?
                ORDER BY updated_at DESC, job_id
                LIMIT ?
                """,
                (user_id, workspace_id, run_id, limit),
            ).fetchall()
        return [self._decode(row) for row in rows]

    def list_incomplete_jobs(self) -> list[dict[str, Any]]:
        if not self._database_path.exists():
            return []
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            rows = connection.execute(
                """
                SELECT document_json FROM creator_execution_jobs
                WHERE status IN ('queued', 'running')
                ORDER BY created_at, job_id
                """
            ).fetchall()
        return [self._decode(row) for row in rows]

    def update_job(self, document: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            cursor = connection.execute(
                """
                UPDATE creator_execution_jobs
                SET status = ?, progress = ?, cancel_requested = ?,
                    document_json = ?, updated_at = ?
                WHERE user_id = ? AND workspace_id = ? AND job_id = ?
                """,
                (
                    document["status"],
                    int(document.get("progress") or 0),
                    int(bool(document.get("cancelRequested"))),
                    json.dumps(document, ensure_ascii=False),
                    document["updatedAt"],
                    document["userId"],
                    document["workspaceId"],
                    document["jobId"],
                ),
            )
            if cursor.rowcount != 1:
                raise CreatorJobNotFoundError(str(document["jobId"]))
        return document

    def request_job_cancel(
        self,
        *,
        user_id: str,
        workspace_id: str,
        job_id: str,
        requested_at: str,
    ) -> dict[str, Any]:
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT document_json FROM creator_execution_jobs
                WHERE user_id = ? AND workspace_id = ? AND job_id = ?
                """,
                (user_id, workspace_id, job_id),
            ).fetchone()
            if row is None:
                raise CreatorJobNotFoundError(job_id)
            document = self._decode(row)
            if document.get("status") not in {"succeeded", "failed", "cancelled"}:
                document["cancelRequested"] = True
                document["cancelRequestedAt"] = requested_at
                document["updatedAt"] = requested_at
                connection.execute(
                    """
                    UPDATE creator_execution_jobs
                    SET cancel_requested = 1, document_json = ?, updated_at = ?
                    WHERE user_id = ? AND workspace_id = ? AND job_id = ?
                    """,
                    (
                        json.dumps(document, ensure_ascii=False),
                        requested_at,
                        user_id,
                        workspace_id,
                        job_id,
                    ),
                )
        return document

    def create_editor_session(self, document: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            connection.execute(
                """
                INSERT OR IGNORE INTO creator_editor_sessions (
                  user_id, workspace_id, session_id, run_id, stage_id, node_id,
                  status, document_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document["userId"],
                    document["workspaceId"],
                    document["sessionId"],
                    document["runId"],
                    document["stageId"],
                    document["nodeId"],
                    document["status"],
                    json.dumps(document, ensure_ascii=False),
                    document["createdAt"],
                    document["updatedAt"],
                ),
            )
        return self.get_editor_session(
            user_id=str(document["userId"]),
            workspace_id=str(document["workspaceId"]),
            session_id=str(document["sessionId"]),
        )

    def get_editor_session(
        self,
        *,
        user_id: str,
        workspace_id: str,
        session_id: str,
    ) -> dict[str, Any]:
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            row = connection.execute(
                """
                SELECT document_json FROM creator_editor_sessions
                WHERE user_id = ? AND workspace_id = ? AND session_id = ?
                """,
                (user_id, workspace_id, session_id),
            ).fetchone()
        if row is None:
            raise CreatorEditorSessionNotFoundError(session_id)
        return self._decode(row)

    def list_editor_sessions(
        self,
        *,
        user_id: str,
        workspace_id: str,
        run_id: str,
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            rows = connection.execute(
                """
                SELECT document_json FROM creator_editor_sessions
                WHERE user_id = ? AND workspace_id = ? AND run_id = ?
                ORDER BY updated_at DESC, session_id
                """,
                (user_id, workspace_id, run_id),
            ).fetchall()
        return [self._decode(row) for row in rows]

    def update_editor_session(self, document: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            cursor = connection.execute(
                """
                UPDATE creator_editor_sessions
                SET status = ?, document_json = ?, updated_at = ?
                WHERE user_id = ? AND workspace_id = ? AND session_id = ?
                """,
                (
                    document["status"],
                    json.dumps(document, ensure_ascii=False),
                    document["updatedAt"],
                    document["userId"],
                    document["workspaceId"],
                    document["sessionId"],
                ),
            )
            if cursor.rowcount != 1:
                raise CreatorEditorSessionNotFoundError(
                    str(document["sessionId"])
                )
        return document

    def list_events(
        self,
        *,
        user_id: str,
        workspace_id: str,
        run_id: str,
        after: int = 0,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            rows = connection.execute(
                """
                SELECT * FROM creator_studio_events
                WHERE user_id = ? AND workspace_id = ? AND run_id = ?
                  AND sequence > ?
                ORDER BY sequence
                LIMIT ?
                """,
                (user_id, workspace_id, run_id, after, limit),
            ).fetchall()
        return [
            {
                "sequence": int(row["sequence"]),
                "type": row["event_type"],
                "actionId": row["action_id"],
                "stageId": row["stage_id"],
                "nodeId": row["node_id"],
                "payload": json.loads(row["payload_json"]),
                "createdAt": row["created_at"],
            }
            for row in rows
        ]
