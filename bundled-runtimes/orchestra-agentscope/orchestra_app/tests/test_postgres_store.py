from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from orchestra_app.migrate_database import migrate_sqlite_to_postgres
from orchestra_app.models import AgentRuntime, RunSnapshot, utc_now
from orchestra_app.storage import PostgresStore, SQLiteStore


POSTGRES_DSN = os.getenv("ORCHESTRA_TEST_POSTGRES_DSN")
pytestmark = pytest.mark.skipif(not POSTGRES_DSN, reason="未配置PostgreSQL集成测试DSN")


def _snapshot(run_id: str) -> RunSnapshot:
    now = utc_now()
    return RunSnapshot(
        id=run_id,
        topic="PostgreSQL持久化测试",
        mode="demo",
        status="queued",
        phase="queued",
        created_at=now,
        updated_at=now,
        agents={"MACRO-01": AgentRuntime(id="MACRO-01")},
    )


def test_postgres_store_and_concurrent_job_claim() -> None:
    assert POSTGRES_DSN is not None
    run_id = f"pg-{uuid.uuid4().hex}"
    first = PostgresStore(POSTGRES_DSN)
    second = PostgresStore(POSTGRES_DSN)
    try:
        first._connection.execute(  # noqa: SLF001
            "UPDATE jobs SET status='cancelled', lease_owner=NULL, lease_expires_at=NULL "
            "WHERE status IN ('queued', 'running')",
        )
        first.save_run(_snapshot(run_id))
        first.enqueue_job(run_id)
        with ThreadPoolExecutor(max_workers=2) as pool:
            claims = list(
                pool.map(
                    lambda item: item[0].claim_job(item[1], 30),
                    ((first, "worker-a"), (second, "worker-b")),
                ),
            )
        claimed = [claim for claim in claims if claim is not None]
        assert len(claimed) == 1
        assert claimed[0]["run_id"] == run_id
        assert claimed[0]["attempts"] == 1
        assert first.schema_version() == 3
        assert second.load_run(run_id) is not None
    finally:
        first.close()
        second.close()


def test_sqlite_to_postgres_migration(tmp_path: Path) -> None:
    assert POSTGRES_DSN is not None
    source_path = tmp_path / "source.db"
    source = SQLiteStore(source_path)
    run_id = f"migrate-{uuid.uuid4().hex}"
    source.save_run(_snapshot(run_id))
    source.enqueue_job(run_id)
    source.close()

    report = migrate_sqlite_to_postgres(source_path, POSTGRES_DSN)
    target = PostgresStore(POSTGRES_DSN)
    try:
        assert report["tables"]["runs"]["source"] == 1
        assert target.load_run(run_id) is not None
        assert any(job["run_id"] == run_id for job in target.list_jobs())
    finally:
        target.close()
