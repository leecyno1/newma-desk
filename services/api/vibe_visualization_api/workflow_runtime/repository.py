from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any
from uuid import uuid4

from vibe_visualization_api.workflow_control.repository import now_iso


SCHEMA = """
CREATE TABLE IF NOT EXISTS workflow_runtime_executions (
  organization_id TEXT NOT NULL,
  id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  status TEXT NOT NULL,
  trigger_type TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  requested_by TEXT NOT NULL,
  user_id TEXT NOT NULL DEFAULT 'local-user',
  input_json TEXT NOT NULL,
  error_json TEXT,
  created_at TEXT NOT NULL,
  started_at TEXT,
  paused_at TEXT,
  completed_at TEXT,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (organization_id, id),
  UNIQUE (organization_id, run_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS workflow_runtime_executions_run
ON workflow_runtime_executions(organization_id, run_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS workflow_runtime_jobs (
  organization_id TEXT NOT NULL,
  id TEXT NOT NULL,
  execution_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  node_id TEXT NOT NULL,
  position INTEGER NOT NULL DEFAULT 0,
  executor_id TEXT NOT NULL,
  status TEXT NOT NULL,
  attempt INTEGER NOT NULL,
  max_attempts INTEGER NOT NULL,
  timeout_seconds INTEGER NOT NULL,
  retry_delay_seconds INTEGER NOT NULL,
  available_at TEXT,
  lease_owner TEXT,
  lease_expires_at TEXT,
  started_at TEXT,
  deadline_at TEXT,
  completed_at TEXT,
  input_json TEXT NOT NULL,
  result_json TEXT,
  error_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (organization_id, id),
  UNIQUE (organization_id, execution_id, node_id)
);

CREATE INDEX IF NOT EXISTS workflow_runtime_jobs_dispatch
ON workflow_runtime_jobs(organization_id, execution_id, status, available_at);

CREATE TABLE IF NOT EXISTS workflow_runtime_events (
  sequence INTEGER PRIMARY KEY AUTOINCREMENT,
  organization_id TEXT NOT NULL,
  execution_id TEXT NOT NULL,
  job_id TEXT,
  event_type TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS workflow_runtime_events_execution
ON workflow_runtime_events(organization_id, execution_id, sequence DESC);

CREATE TABLE IF NOT EXISTS workflow_runtime_triggers (
  organization_id TEXT NOT NULL,
  id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  trigger_type TEXT NOT NULL,
  event_type TEXT,
  interval_seconds INTEGER,
  cron_expression TEXT,
  timezone TEXT,
  next_fire_at TEXT,
  enabled INTEGER NOT NULL DEFAULT 1,
  requested_by TEXT NOT NULL,
  user_id TEXT NOT NULL,
  input_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (organization_id, id)
);

CREATE INDEX IF NOT EXISTS workflow_runtime_triggers_dispatch
ON workflow_runtime_triggers(
  organization_id, trigger_type, enabled, event_type, next_fire_at
);
"""


class WorkflowRuntimeNotFoundError(Exception):
    """Raised when a runtime execution or job does not exist."""


class WorkflowRuntimeConflictError(Exception):
    """Raised when a runtime transition targets an incompatible state."""


class WorkflowRuntimeRepository:
    def __init__(self, database_path: Path):
        self._database_path = database_path

    def _connect(self) -> sqlite3.Connection:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _prepare(connection: sqlite3.Connection) -> None:
        connection.executescript(SCHEMA)
        job_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(workflow_runtime_jobs)"
            ).fetchall()
        }
        if "position" not in job_columns:
            connection.execute(
                "ALTER TABLE workflow_runtime_jobs ADD COLUMN position INTEGER NOT NULL DEFAULT 0"
            )
        execution_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(workflow_runtime_executions)"
            ).fetchall()
        }
        if "user_id" not in execution_columns:
            connection.execute(
                "ALTER TABLE workflow_runtime_executions ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local-user'"
            )
        trigger_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(workflow_runtime_triggers)"
            ).fetchall()
        }
        if "cron_expression" not in trigger_columns:
            connection.execute(
                "ALTER TABLE workflow_runtime_triggers ADD COLUMN cron_expression TEXT"
            )
        if "timezone" not in trigger_columns:
            connection.execute(
                "ALTER TABLE workflow_runtime_triggers ADD COLUMN timezone TEXT"
            )

    @staticmethod
    def _decode(value: str | None, default: Any = None) -> Any:
        return default if value is None else json.loads(value)

    @classmethod
    def _execution(cls, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "organizationId": row["organization_id"],
            "runId": row["run_id"],
            "status": row["status"],
            "triggerType": row["trigger_type"],
            "idempotencyKey": row["idempotency_key"],
            "requestedBy": row["requested_by"],
            "userId": row["user_id"],
            "input": json.loads(row["input_json"]),
            "error": cls._decode(row["error_json"]),
            "createdAt": row["created_at"],
            "startedAt": row["started_at"],
            "pausedAt": row["paused_at"],
            "completedAt": row["completed_at"],
            "updatedAt": row["updated_at"],
        }

    @classmethod
    def _job(cls, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "organizationId": row["organization_id"],
            "executionId": row["execution_id"],
            "runId": row["run_id"],
            "nodeId": row["node_id"],
            "position": row["position"],
            "executorId": row["executor_id"],
            "status": row["status"],
            "attempt": row["attempt"],
            "maxAttempts": row["max_attempts"],
            "timeoutSeconds": row["timeout_seconds"],
            "retryDelaySeconds": row["retry_delay_seconds"],
            "availableAt": row["available_at"],
            "leaseOwner": row["lease_owner"],
            "leaseExpiresAt": row["lease_expires_at"],
            "startedAt": row["started_at"],
            "deadlineAt": row["deadline_at"],
            "completedAt": row["completed_at"],
            "input": json.loads(row["input_json"]),
            "result": cls._decode(row["result_json"]),
            "error": cls._decode(row["error_json"]),
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    @classmethod
    def _trigger(cls, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "organizationId": row["organization_id"],
            "runId": row["run_id"],
            "triggerType": row["trigger_type"],
            "eventType": row["event_type"],
            "intervalSeconds": row["interval_seconds"],
            "cronExpression": row["cron_expression"],
            "timezone": row["timezone"],
            "nextFireAt": row["next_fire_at"],
            "enabled": bool(row["enabled"]),
            "requestedBy": row["requested_by"],
            "userId": row["user_id"],
            "input": json.loads(row["input_json"]),
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    @staticmethod
    def _event(
        connection: sqlite3.Connection,
        *,
        organization_id: str,
        execution_id: str,
        event_type: str,
        payload: dict[str, Any],
        job_id: str | None = None,
        timestamp: str | None = None,
    ) -> None:
        connection.execute(
            """
            INSERT INTO workflow_runtime_events (
              organization_id, execution_id, job_id, event_type,
              payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                organization_id,
                execution_id,
                job_id,
                event_type,
                json.dumps(payload, ensure_ascii=False),
                timestamp or now_iso(),
            ),
        )

    def create_execution(
        self,
        *,
        organization_id: str,
        run_id: str,
        trigger_type: str,
        idempotency_key: str,
        requested_by: str,
        user_id: str,
        input_payload: dict[str, Any],
        jobs: list[dict[str, Any]],
        timestamp: str,
    ) -> tuple[dict[str, Any], bool]:
        execution_id = f"execution-{uuid4().hex[:20]}"
        with self._connect() as connection:
            self._prepare(connection)
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT id FROM workflow_runtime_executions
                WHERE organization_id = ? AND run_id = ? AND idempotency_key = ?
                """,
                (organization_id, run_id, idempotency_key),
            ).fetchone()
            if existing is not None:
                execution_id = existing["id"]
                created = False
            else:
                connection.execute(
                    """
                    INSERT INTO workflow_runtime_executions (
                      organization_id, id, run_id, status, trigger_type,
                      idempotency_key, requested_by, user_id, input_json, error_json,
                      created_at, started_at, paused_at, completed_at, updated_at
                    ) VALUES (?, ?, ?, 'queued', ?, ?, ?, ?, ?, NULL, ?, NULL, NULL, NULL, ?)
                    """,
                    (
                        organization_id,
                        execution_id,
                        run_id,
                        trigger_type,
                        idempotency_key,
                        requested_by,
                        user_id,
                        json.dumps(input_payload, ensure_ascii=False),
                        timestamp,
                        timestamp,
                    ),
                )
                for job in jobs:
                    connection.execute(
                        """
                        INSERT INTO workflow_runtime_jobs (
                          organization_id, id, execution_id, run_id, node_id, position,
                          executor_id, status, attempt, max_attempts,
                          timeout_seconds, retry_delay_seconds, available_at,
                          lease_owner, lease_expires_at, started_at, deadline_at,
                          completed_at, input_json, result_json, error_json,
                          created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, NULL, NULL,
                                  NULL, NULL, ?, ?, ?, NULL, ?, ?)
                        """,
                        (
                            organization_id,
                            job["id"],
                            execution_id,
                            run_id,
                            job["nodeId"],
                            job["position"],
                            job["executorId"],
                            job["status"],
                            job["maxAttempts"],
                            job["timeoutSeconds"],
                            job["retryDelaySeconds"],
                            job.get("availableAt"),
                            job.get("completedAt"),
                            json.dumps(job.get("input", {}), ensure_ascii=False),
                            (
                                json.dumps(job["result"], ensure_ascii=False)
                                if job.get("result") is not None
                                else None
                            ),
                            timestamp,
                            timestamp,
                        ),
                    )
                self._event(
                    connection,
                    organization_id=organization_id,
                    execution_id=execution_id,
                    event_type="execution.created",
                    payload={
                        "runId": run_id,
                        "triggerType": trigger_type,
                        "jobCount": len(jobs),
                    },
                    timestamp=timestamp,
                )
                created = True
        return self.snapshot(organization_id, execution_id), created

    def get_execution(
        self,
        organization_id: str,
        execution_id: str,
    ) -> dict[str, Any]:
        with self._connect() as connection:
            self._prepare(connection)
            row = connection.execute(
                """
                SELECT * FROM workflow_runtime_executions
                WHERE organization_id = ? AND id = ?
                """,
                (organization_id, execution_id),
            ).fetchone()
        if row is None:
            raise WorkflowRuntimeNotFoundError(execution_id)
        return self._execution(row)

    def list_executions(
        self,
        organization_id: str,
        run_id: str | None = None,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM workflow_runtime_executions WHERE organization_id = ?"
        parameters: list[Any] = [organization_id]
        if run_id:
            query += " AND run_id = ?"
            parameters.append(run_id)
        query += " ORDER BY updated_at DESC, id"
        with self._connect() as connection:
            self._prepare(connection)
            rows = connection.execute(query, parameters).fetchall()
        return [self._execution(row) for row in rows]

    def list_runnable_execution_refs(
        self,
        timestamp: str,
        *,
        limit: int = 100,
    ) -> list[dict[str, str]]:
        if not self._database_path.exists():
            return []
        with self._connect() as connection:
            try:
                rows = connection.execute(
                    """
                    SELECT DISTINCT e.organization_id, e.id
                    FROM workflow_runtime_executions e
                    LEFT JOIN workflow_runtime_jobs j
                      ON j.organization_id = e.organization_id
                     AND j.execution_id = e.id
                    WHERE e.status = 'queued'
                       OR (
                         e.status = 'running'
                         AND (
                           j.status = 'ready'
                           OR (j.status = 'retry_wait' AND j.available_at <= ?)
                           OR (
                             j.status IN ('leased', 'running')
                             AND (
                               (j.lease_expires_at IS NOT NULL AND j.lease_expires_at <= ?)
                               OR (j.deadline_at IS NOT NULL AND j.deadline_at <= ?)
                             )
                           )
                           OR (
                             j.status = 'waiting'
                             AND j.deadline_at IS NOT NULL
                           )
                         )
                       )
                    ORDER BY e.updated_at, e.id
                    LIMIT ?
                    """,
                    (timestamp, timestamp, timestamp, limit),
                ).fetchall()
            except sqlite3.OperationalError as error:
                if "no such table" in str(error):
                    return []
                raise
        return [
            {
                "organizationId": row["organization_id"],
                "executionId": row["id"],
            }
            for row in rows
        ]

    def create_trigger(
        self,
        *,
        organization_id: str,
        run_id: str,
        trigger_type: str,
        event_type: str | None,
        interval_seconds: int | None,
        cron_expression: str | None,
        timezone: str | None,
        next_fire_at: str | None,
        enabled: bool,
        requested_by: str,
        user_id: str,
        input_payload: dict[str, Any],
        timestamp: str,
    ) -> dict[str, Any]:
        trigger_id = f"trigger-{uuid4().hex[:20]}"
        with self._connect() as connection:
            self._prepare(connection)
            connection.execute(
                """
                INSERT INTO workflow_runtime_triggers (
                  organization_id, id, run_id, trigger_type, event_type,
                  interval_seconds, cron_expression, timezone, next_fire_at,
                  enabled, requested_by, user_id, input_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    organization_id,
                    trigger_id,
                    run_id,
                    trigger_type,
                    event_type,
                    interval_seconds,
                    cron_expression,
                    timezone,
                    next_fire_at,
                    int(enabled),
                    requested_by,
                    user_id,
                    json.dumps(input_payload, ensure_ascii=False),
                    timestamp,
                    timestamp,
                ),
            )
        return self.get_trigger(organization_id, trigger_id)

    def get_trigger(
        self,
        organization_id: str,
        trigger_id: str,
    ) -> dict[str, Any]:
        with self._connect() as connection:
            self._prepare(connection)
            row = connection.execute(
                """
                SELECT * FROM workflow_runtime_triggers
                WHERE organization_id = ? AND id = ?
                """,
                (organization_id, trigger_id),
            ).fetchone()
        if row is None:
            raise WorkflowRuntimeNotFoundError(trigger_id)
        return self._trigger(row)

    def list_triggers(
        self,
        organization_id: str,
        run_id: str | None = None,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM workflow_runtime_triggers WHERE organization_id = ?"
        parameters: list[Any] = [organization_id]
        if run_id:
            query += " AND run_id = ?"
            parameters.append(run_id)
        query += " ORDER BY created_at, id"
        with self._connect() as connection:
            self._prepare(connection)
            rows = connection.execute(query, parameters).fetchall()
        return [self._trigger(row) for row in rows]

    def set_trigger_enabled(
        self,
        *,
        organization_id: str,
        trigger_id: str,
        enabled: bool,
        next_fire_at: str | None,
        timestamp: str,
    ) -> dict[str, Any]:
        with self._connect() as connection:
            self._prepare(connection)
            connection.execute(
                """
                UPDATE workflow_runtime_triggers
                SET enabled = ?, next_fire_at = ?, updated_at = ?
                WHERE organization_id = ? AND id = ?
                """,
                (
                    int(enabled),
                    next_fire_at,
                    timestamp,
                    organization_id,
                    trigger_id,
                ),
            )
        return self.get_trigger(organization_id, trigger_id)

    def list_event_triggers(
        self,
        organization_id: str,
        event_type: str,
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            self._prepare(connection)
            rows = connection.execute(
                """
                SELECT * FROM workflow_runtime_triggers
                WHERE organization_id = ? AND trigger_type = 'event'
                  AND enabled = 1 AND event_type = ?
                ORDER BY created_at, id
                """,
                (organization_id, event_type),
            ).fetchall()
        return [self._trigger(row) for row in rows]

    def list_due_schedule_triggers(
        self,
        timestamp: str,
        *,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if not self._database_path.exists():
            return []
        with self._connect() as connection:
            try:
                rows = connection.execute(
                    """
                    SELECT * FROM workflow_runtime_triggers
                    WHERE trigger_type = 'schedule' AND enabled = 1
                      AND next_fire_at IS NOT NULL AND next_fire_at <= ?
                    ORDER BY next_fire_at, id
                    LIMIT ?
                    """,
                    (timestamp, limit),
                ).fetchall()
            except sqlite3.OperationalError as error:
                if "no such table" in str(error):
                    return []
                raise
        return [
            {**self._trigger(row), "scheduledFor": row["next_fire_at"]}
            for row in rows
        ]

    def advance_schedule_trigger(
        self,
        *,
        organization_id: str,
        trigger_id: str,
        scheduled_for: str,
        next_fire_at: str,
        timestamp: str,
    ) -> bool:
        with self._connect() as connection:
            self._prepare(connection)
            cursor = connection.execute(
                """
                    UPDATE workflow_runtime_triggers
                    SET next_fire_at = ?, updated_at = ?
                WHERE organization_id = ? AND id = ? AND next_fire_at = ?
                """,
                (
                    next_fire_at,
                    timestamp,
                    organization_id,
                    trigger_id,
                    scheduled_for,
                ),
            )
        return cursor.rowcount == 1

    def list_jobs(
        self,
        organization_id: str,
        execution_id: str,
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            self._prepare(connection)
            rows = connection.execute(
                """
                SELECT * FROM workflow_runtime_jobs
                WHERE organization_id = ? AND execution_id = ?
                ORDER BY position, id
                """,
                (organization_id, execution_id),
            ).fetchall()
        return [self._job(row) for row in rows]

    def get_job(
        self,
        organization_id: str,
        execution_id: str,
        job_id: str,
    ) -> dict[str, Any]:
        with self._connect() as connection:
            self._prepare(connection)
            row = connection.execute(
                """
                SELECT * FROM workflow_runtime_jobs
                WHERE organization_id = ? AND execution_id = ? AND id = ?
                """,
                (organization_id, execution_id, job_id),
            ).fetchone()
        if row is None:
            raise WorkflowRuntimeNotFoundError(job_id)
        return self._job(row)

    def snapshot(self, organization_id: str, execution_id: str) -> dict[str, Any]:
        execution = self.get_execution(organization_id, execution_id)
        return {**execution, "jobs": self.list_jobs(organization_id, execution_id)}

    def set_execution_status(
        self,
        *,
        organization_id: str,
        execution_id: str,
        status: str,
        expected_statuses: set[str],
        timestamp: str,
        reason: str = "",
        error: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        placeholders = ",".join("?" for _ in expected_statuses)
        started_at = timestamp if status == "running" else None
        paused_at = timestamp if status == "paused" else None
        completed_at = (
            timestamp if status in {"completed", "failed", "cancelled"} else None
        )
        with self._connect() as connection:
            self._prepare(connection)
            cursor = connection.execute(
                f"""
                UPDATE workflow_runtime_executions
                SET status = ?,
                    started_at = COALESCE(started_at, ?),
                    paused_at = ?, completed_at = ?, error_json = ?, updated_at = ?
                WHERE organization_id = ? AND id = ?
                  AND status IN ({placeholders})
                """,
                [
                    status,
                    started_at,
                    paused_at,
                    completed_at,
                    json.dumps(error, ensure_ascii=False) if error is not None else None,
                    timestamp,
                    organization_id,
                    execution_id,
                    *sorted(expected_statuses),
                ],
            )
            if cursor.rowcount != 1:
                current = connection.execute(
                    """
                    SELECT status FROM workflow_runtime_executions
                    WHERE organization_id = ? AND id = ?
                    """,
                    (organization_id, execution_id),
                ).fetchone()
                if current is None:
                    raise WorkflowRuntimeNotFoundError(execution_id)
                raise WorkflowRuntimeConflictError(
                    f"execution {execution_id} is {current['status']}"
                )
            self._event(
                connection,
                organization_id=organization_id,
                execution_id=execution_id,
                event_type=f"execution.{status}",
                payload={"reason": reason} if reason else {},
                timestamp=timestamp,
            )
        return self.snapshot(organization_id, execution_id)

    def transition_job(
        self,
        *,
        organization_id: str,
        execution_id: str,
        job_id: str,
        status: str,
        expected_statuses: set[str],
        timestamp: str,
        fields: dict[str, Any] | None = None,
        event_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        column_names = {
            "availableAt": "available_at",
            "leaseOwner": "lease_owner",
            "leaseExpiresAt": "lease_expires_at",
            "startedAt": "started_at",
            "deadlineAt": "deadline_at",
            "completedAt": "completed_at",
            "result": "result_json",
            "error": "error_json",
        }
        updates = ["status = ?", "updated_at = ?"]
        values: list[Any] = [status, timestamp]
        for key, value in (fields or {}).items():
            column = column_names[key]
            updates.append(f"{column} = ?")
            if key in {"result", "error"} and value is not None:
                value = json.dumps(value, ensure_ascii=False)
            values.append(value)
        placeholders = ",".join("?" for _ in expected_statuses)
        values.extend(
            [organization_id, execution_id, job_id, *sorted(expected_statuses)]
        )
        with self._connect() as connection:
            self._prepare(connection)
            cursor = connection.execute(
                f"""
                UPDATE workflow_runtime_jobs
                SET {', '.join(updates)}
                WHERE organization_id = ? AND execution_id = ? AND id = ?
                  AND status IN ({placeholders})
                """,
                values,
            )
            if cursor.rowcount != 1:
                current = connection.execute(
                    """
                    SELECT status FROM workflow_runtime_jobs
                    WHERE organization_id = ? AND execution_id = ? AND id = ?
                    """,
                    (organization_id, execution_id, job_id),
                ).fetchone()
                if current is None:
                    raise WorkflowRuntimeNotFoundError(job_id)
                raise WorkflowRuntimeConflictError(
                    f"job {job_id} is {current['status']}"
                )
            self._event(
                connection,
                organization_id=organization_id,
                execution_id=execution_id,
                job_id=job_id,
                event_type=f"job.{status}",
                payload=event_payload or {},
                timestamp=timestamp,
            )
        return self.get_job(organization_id, execution_id, job_id)

    def lease_next_ready_job(
        self,
        *,
        organization_id: str,
        execution_id: str,
        worker_id: str,
        timestamp: str,
        lease_expires_at: str,
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            self._prepare(connection)
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT * FROM workflow_runtime_jobs
                WHERE organization_id = ? AND execution_id = ? AND status = 'ready'
                  AND (available_at IS NULL OR available_at <= ?)
                ORDER BY position, id
                LIMIT 1
                """,
                (organization_id, execution_id, timestamp),
            ).fetchone()
            if row is None:
                return None
            cursor = connection.execute(
                """
                UPDATE workflow_runtime_jobs
                SET status = 'leased', attempt = attempt + 1,
                    lease_owner = ?, lease_expires_at = ?, updated_at = ?
                WHERE organization_id = ? AND execution_id = ? AND id = ?
                  AND status = 'ready'
                """,
                (
                    worker_id,
                    lease_expires_at,
                    timestamp,
                    organization_id,
                    execution_id,
                    row["id"],
                ),
            )
            if cursor.rowcount != 1:
                return None
            self._event(
                connection,
                organization_id=organization_id,
                execution_id=execution_id,
                job_id=row["id"],
                event_type="job.leased",
                payload={"workerId": worker_id, "leaseExpiresAt": lease_expires_at},
                timestamp=timestamp,
            )
            leased = connection.execute(
                """
                SELECT * FROM workflow_runtime_jobs
                WHERE organization_id = ? AND execution_id = ? AND id = ?
                """,
                (organization_id, execution_id, row["id"]),
            ).fetchone()
        assert leased is not None
        return self._job(leased)

    def make_due_retries_ready(
        self,
        *,
        organization_id: str,
        execution_id: str,
        timestamp: str,
    ) -> list[str]:
        with self._connect() as connection:
            self._prepare(connection)
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                """
                SELECT id FROM workflow_runtime_jobs
                WHERE organization_id = ? AND execution_id = ?
                  AND status = 'retry_wait' AND available_at <= ?
                ORDER BY available_at, id
                """,
                (organization_id, execution_id, timestamp),
            ).fetchall()
            ids = [row["id"] for row in rows]
            for job_id in ids:
                connection.execute(
                    """
                    UPDATE workflow_runtime_jobs
                    SET status = 'ready', error_json = NULL, updated_at = ?
                    WHERE organization_id = ? AND execution_id = ? AND id = ?
                    """,
                    (timestamp, organization_id, execution_id, job_id),
                )
                self._event(
                    connection,
                    organization_id=organization_id,
                    execution_id=execution_id,
                    job_id=job_id,
                    event_type="job.ready",
                    payload={"reason": "retry_due"},
                    timestamp=timestamp,
                )
        return ids

    def list_expired_jobs(
        self,
        *,
        organization_id: str,
        execution_id: str,
        timestamp: str,
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            self._prepare(connection)
            rows = connection.execute(
                """
                SELECT * FROM workflow_runtime_jobs
                WHERE organization_id = ? AND execution_id = ?
                  AND status IN ('leased', 'running', 'waiting')
                  AND (
                    (lease_expires_at IS NOT NULL AND lease_expires_at <= ?)
                    OR (deadline_at IS NOT NULL AND deadline_at <= ?)
                  )
                ORDER BY updated_at, id
                """,
                (organization_id, execution_id, timestamp, timestamp),
            ).fetchall()
        return [self._job(row) for row in rows]

    def list_events(
        self,
        organization_id: str,
        execution_id: str,
        limit: int = 300,
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            self._prepare(connection)
            rows = connection.execute(
                """
                SELECT * FROM workflow_runtime_events
                WHERE organization_id = ? AND execution_id = ?
                ORDER BY sequence DESC LIMIT ?
                """,
                (organization_id, execution_id, limit),
            ).fetchall()
        return [
            {
                "sequence": row["sequence"],
                "executionId": row["execution_id"],
                "jobId": row["job_id"],
                "type": row["event_type"],
                "payload": json.loads(row["payload_json"]),
                "createdAt": row["created_at"],
            }
            for row in rows
        ]
