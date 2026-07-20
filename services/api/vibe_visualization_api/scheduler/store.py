import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from croniter import croniter

from vibe_visualization_api.scheduler.models import RefreshJob


DDL = """
CREATE TABLE IF NOT EXISTS refresh_jobs (
  module_id TEXT PRIMARY KEY,
  cron TEXT NOT NULL,
  timezone TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('idle','running','failed')),
  next_run_at TEXT NOT NULL,
  last_success_at TEXT,
  last_error TEXT,
  lease_started_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_refresh_jobs_status
ON refresh_jobs(status, next_run_at);
"""


def next_run_at(cron: str, timezone_name: str, after: datetime) -> datetime:
    zone = ZoneInfo(timezone_name)
    localized = after.astimezone(zone)
    return croniter(cron, localized).get_next(datetime)


def _parse_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value is not None else None


def _stored_job(row: sqlite3.Row) -> RefreshJob:
    return RefreshJob(
        module_id=row["module_id"],
        cron=row["cron"],
        timezone=row["timezone"],
        status=row["status"],
        next_run_at=datetime.fromisoformat(row["next_run_at"]),
        last_success_at=_parse_datetime(row["last_success_at"]),
        last_error=row["last_error"],
    )


class SchedulerStore:
    def __init__(self, database_path: Path):
        self._database_path = database_path
        connection = self._connect()
        connection.close()

    def _connect(self) -> sqlite3.Connection:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._database_path, timeout=5.0)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA busy_timeout = 5000")
            connection.executescript(DDL)
        except BaseException:
            connection.close()
            raise
        return connection

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
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

    def ensure_job(
        self,
        *,
        module_id: str,
        cron: str,
        timezone: str,
        now: datetime,
    ) -> RefreshJob:
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM refresh_jobs WHERE module_id = ?",
                (module_id,),
            ).fetchone()
            if row is None:
                connection.execute(
                    """
                    INSERT INTO refresh_jobs (
                      module_id, cron, timezone, status, next_run_at,
                      last_success_at, last_error, lease_started_at
                    ) VALUES (?, ?, ?, 'idle', ?, NULL, NULL, NULL)
                    """,
                    (
                        module_id,
                        cron,
                        timezone,
                        next_run_at(cron, timezone, now).isoformat(),
                    ),
                )
            elif row["cron"] != cron or row["timezone"] != timezone:
                connection.execute(
                    """
                    UPDATE refresh_jobs
                    SET cron = ?, timezone = ?, status = 'idle',
                        next_run_at = ?, last_error = NULL,
                        lease_started_at = NULL
                    WHERE module_id = ?
                    """,
                    (
                        cron,
                        timezone,
                        next_run_at(cron, timezone, now).isoformat(),
                        module_id,
                    ),
                )
            stored = connection.execute(
                "SELECT * FROM refresh_jobs WHERE module_id = ?",
                (module_id,),
            ).fetchone()
        return _stored_job(stored)

    def get(self, module_id: str) -> RefreshJob:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM refresh_jobs WHERE module_id = ?",
                (module_id,),
            ).fetchone()
            if row is None:
                raise KeyError(module_id)
            return _stored_job(row)
        finally:
            connection.close()

    def list_due(self, now: datetime, module_ids: set[str]) -> list[RefreshJob]:
        if not module_ids:
            return []
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT * FROM refresh_jobs
                WHERE status IN ('idle','failed')
                ORDER BY next_run_at, module_id
                """
            ).fetchall()
        finally:
            connection.close()
        instant = now.astimezone(timezone.utc)
        return [
            _stored_job(row)
            for row in rows
            if row["module_id"] in module_ids
            and datetime.fromisoformat(row["next_run_at"]).astimezone(timezone.utc)
            <= instant
        ]

    def try_acquire(self, module_id: str, now: datetime) -> bool:
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT status, next_run_at FROM refresh_jobs WHERE module_id = ?",
                (module_id,),
            ).fetchone()
            if row is None or row["status"] == "running":
                return False
            if datetime.fromisoformat(row["next_run_at"]).astimezone(
                timezone.utc
            ) > now.astimezone(timezone.utc):
                return False
            result = connection.execute(
                """
                UPDATE refresh_jobs
                SET status = 'running', lease_started_at = ?
                WHERE module_id = ? AND status IN ('idle','failed')
                """,
                (now.isoformat(), module_id),
            )
            return result.rowcount == 1

    def complete_success(self, module_id: str, finished_at: datetime) -> None:
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT cron, timezone FROM refresh_jobs WHERE module_id = ?",
                (module_id,),
            ).fetchone()
            if row is None:
                raise KeyError(module_id)
            connection.execute(
                """
                UPDATE refresh_jobs
                SET status = 'idle', next_run_at = ?, last_success_at = ?,
                    last_error = NULL, lease_started_at = NULL
                WHERE module_id = ? AND status = 'running'
                """,
                (
                    next_run_at(
                        row["cron"], row["timezone"], finished_at
                    ).isoformat(),
                    finished_at.isoformat(),
                    module_id,
                ),
            )

    def complete_failure(
        self,
        module_id: str,
        finished_at: datetime,
        error: str,
    ) -> None:
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT cron, timezone FROM refresh_jobs WHERE module_id = ?",
                (module_id,),
            ).fetchone()
            if row is None:
                raise KeyError(module_id)
            connection.execute(
                """
                UPDATE refresh_jobs
                SET status = 'failed', next_run_at = ?, last_error = ?,
                    lease_started_at = NULL
                WHERE module_id = ? AND status = 'running'
                """,
                (
                    next_run_at(
                        row["cron"], row["timezone"], finished_at
                    ).isoformat(),
                    error[:1000],
                    module_id,
                ),
            )

    def recover_stale(
        self,
        now: datetime,
        *,
        max_age: timedelta = timedelta(minutes=30),
    ) -> int:
        recovered = 0
        cutoff = now.astimezone(timezone.utc) - max_age
        with self._transaction() as connection:
            rows = connection.execute(
                """
                SELECT module_id, lease_started_at
                FROM refresh_jobs
                WHERE status = 'running'
                """
            ).fetchall()
            for row in rows:
                lease_started_at = _parse_datetime(row["lease_started_at"])
                if (
                    lease_started_at is None
                    or lease_started_at.astimezone(timezone.utc) <= cutoff
                ):
                    connection.execute(
                        """
                        UPDATE refresh_jobs
                        SET status = 'failed',
                            last_error = 'recovered stale scheduler lease',
                            lease_started_at = NULL
                        WHERE module_id = ? AND status = 'running'
                        """,
                        (row["module_id"],),
                    )
                    recovered += 1
        return recovered
