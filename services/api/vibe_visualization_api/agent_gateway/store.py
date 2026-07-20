import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from vibe_visualization_api.agent_gateway.models import (
    AgentTask,
    AgentTaskCreate,
    TaskEvent,
)


DDL = """
CREATE TABLE IF NOT EXISTS agent_tasks (
  id TEXT PRIMARY KEY,
  status TEXT NOT NULL CHECK(
    status IN ('queued','running','completed','failed','cancelled')
  ),
  request_json TEXT NOT NULL,
  result_json TEXT,
  error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_task_events (
  task_id TEXT NOT NULL,
  sequence INTEGER NOT NULL CHECK(sequence >= 1),
  type TEXT NOT NULL CHECK(
    type IN ('queued','progress','artifact','completed','failed','cancelled')
  ),
  data_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (task_id, sequence),
  FOREIGN KEY (task_id) REFERENCES agent_tasks(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_agent_task_events_task
  ON agent_task_events(task_id, sequence);
"""

TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


class TaskStoreError(Exception):
    """Base error for durable Agent task operations."""


class TaskNotFoundError(TaskStoreError):
    """Raised when an Agent task does not exist."""


class InvalidTaskStateError(TaskStoreError):
    """Raised when an event is incompatible with the current task state."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_object(value: str | None) -> dict[str, Any] | None:
    if value is None:
        return None
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("stored Agent task JSON must be an object")
    return cast(dict[str, Any], parsed)


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=5.0)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.executescript(DDL)
    except BaseException:
        connection.close()
        raise
    return connection


def _stored_task(row: sqlite3.Row) -> AgentTask:
    request = _json_object(row["request_json"])
    if request is None:
        raise ValueError("stored Agent task request is missing")
    return AgentTask(
        id=row["id"],
        status=row["status"],
        request=AgentTaskCreate.model_validate(request),
        result=_json_object(row["result_json"]),
        error=row["error"],
    )


def _stored_event(row: sqlite3.Row) -> TaskEvent:
    data = _json_object(row["data_json"])
    if data is None:
        raise ValueError("stored Agent task event data is missing")
    return TaskEvent(
        task_id=row["task_id"],
        sequence=row["sequence"],
        type=row["type"],
        data=data,
    )


class TaskStore:
    def __init__(self, database_path: Path):
        self._database_path = database_path
        connection = _connect(self._database_path)
        connection.close()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = _connect(self._database_path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
        except BaseException:
            connection.rollback()
            raise
        else:
            connection.commit()
        finally:
            connection.close()

    def create(self, request: AgentTaskCreate) -> AgentTask:
        task_id = f"task-{uuid4().hex}"
        created_at = _utc_now()
        request_json = _json_dumps(request.model_dump(mode="json"))
        with self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO agent_tasks (
                  id, status, request_json, result_json, error,
                  created_at, updated_at
                ) VALUES (?, 'queued', ?, NULL, NULL, ?, ?)
                """,
                (task_id, request_json, created_at, created_at),
            )
            connection.execute(
                """
                INSERT INTO agent_task_events (
                  task_id, sequence, type, data_json, created_at
                ) VALUES (?, 1, 'queued', ?, ?)
                """,
                (task_id, _json_dumps({}), created_at),
            )
            row = self._get_task_row(connection, task_id)
        return _stored_task(row)

    def get(self, task_id: str) -> AgentTask:
        connection = _connect(self._database_path)
        try:
            return _stored_task(self._get_task_row(connection, task_id))
        finally:
            connection.close()

    def append_event(
        self,
        task_id: str,
        event_type: str,
        data: dict[str, object],
    ) -> TaskEvent:
        with self._transaction() as connection:
            event = self._append_event(
                connection,
                task_id,
                event_type,
                data,
            )
        return event

    def list_events(self, task_id: str, after: int = 0) -> list[TaskEvent]:
        if after < 0:
            raise ValueError("after must be greater than or equal to zero")
        connection = _connect(self._database_path)
        try:
            self._get_task_row(connection, task_id)
            rows = connection.execute(
                """
                SELECT task_id, sequence, type, data_json, created_at
                FROM agent_task_events
                WHERE task_id = ? AND sequence > ?
                ORDER BY sequence
                """,
                (task_id, after),
            ).fetchall()
            return [_stored_event(row) for row in rows]
        finally:
            connection.close()

    def cancel(self, task_id: str) -> AgentTask:
        with self._transaction() as connection:
            current_row = self._get_task_row(connection, task_id)
            current_status = cast(str, current_row["status"])
            if current_status == "cancelled":
                return _stored_task(current_row)
            if current_status in {"completed", "failed"}:
                raise InvalidTaskStateError(
                    f"task {task_id!r} is already {current_status}"
                )
            self._append_event(
                connection,
                task_id,
                "cancelled",
                {},
            )
            updated_row = self._get_task_row(connection, task_id)
        return _stored_task(updated_row)

    def _append_event(
        self,
        connection: sqlite3.Connection,
        task_id: str,
        event_type: str,
        data: dict[str, object],
    ) -> TaskEvent:
        current_row = self._get_task_row(connection, task_id)
        current_status = cast(str, current_row["status"])
        if current_status in TERMINAL_STATUSES:
            raise InvalidTaskStateError(f"task {task_id!r} is already {current_status}")
        if event_type == "queued":
            raise InvalidTaskStateError("queued is only valid when creating a task")

        sequence_row = connection.execute(
            """
            SELECT COALESCE(MAX(sequence), 0) + 1 AS next_sequence
            FROM agent_task_events
            WHERE task_id = ?
            """,
            (task_id,),
        ).fetchone()
        sequence = cast(int, sequence_row["next_sequence"])
        event = TaskEvent(
            task_id=task_id,
            sequence=sequence,
            type=event_type,
            data=data,
        )
        now = _utc_now()
        connection.execute(
            """
            INSERT INTO agent_task_events (
              task_id, sequence, type, data_json, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                task_id,
                sequence,
                event.type,
                _json_dumps(event.data),
                now,
            ),
        )

        status = "running"
        result_json: str | None = None
        error: str | None = None
        if event.type == "completed":
            status = "completed"
            result_json = _json_dumps(event.data)
        elif event.type == "failed":
            status = "failed"
            candidate = event.data.get("error", event.data.get("message"))
            error = candidate if isinstance(candidate, str) else "agent task failed"
        elif event.type == "cancelled":
            status = "cancelled"

        connection.execute(
            """
            UPDATE agent_tasks
            SET status = ?, result_json = ?, error = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, result_json, error, now, task_id),
        )
        return event

    @staticmethod
    def _get_task_row(
        connection: sqlite3.Connection,
        task_id: str,
    ) -> sqlite3.Row:
        row = connection.execute(
            """
            SELECT id, status, request_json, result_json, error,
                   created_at, updated_at
            FROM agent_tasks
            WHERE id = ?
            """,
            (task_id,),
        ).fetchone()
        if row is None:
            raise TaskNotFoundError(f"task {task_id!r} was not found")
        return row
