import asyncio
import sqlite3
from pathlib import Path

from cryptography.fernet import Fernet

from orchestra_app.exports import build_docx, build_pdf
from orchestra_app.job_queue import SQLiteJobQueue
from orchestra_app.models import AgentRuntime, EvidenceRecord, RunSnapshot, utc_now
from orchestra_app.registry import load_profiles
from orchestra_app.security import SecretVault
from orchestra_app.service import CommitteeService
from orchestra_app.storage import SQLiteStore


def test_completed_run_survives_service_recreation(tmp_path: Path) -> None:
    async def scenario() -> None:
        database = tmp_path / "orchestra.db"
        first_store = SQLiteStore(database)
        first_service = CommitteeService(first_store)
        created = await first_service.create_run("持久化测试议题", "demo")
        task = first_service._runs[created.id].task  # noqa: SLF001
        assert task is not None
        await task

        completed = first_service.get_run(created.id)
        event_count = len(first_service.list_events(created.id))
        artifact_count = len(first_service.list_artifacts(created.id, "local-user"))
        first_store.close()

        second_store = SQLiteStore(database)
        second_service = CommitteeService(second_store)
        restored = second_service.get_run(created.id)

        assert restored.status == "completed"
        assert restored.decision == completed.decision
        assert len(second_service.list_events(created.id)) == event_count
        assert len(second_service.list_artifacts(created.id, "local-user")) == artifact_count
        assert second_service.list_runs()[0].id == created.id
        second_store.close()

    asyncio.run(scenario())


def test_interrupted_run_is_recovered_from_durable_queue(tmp_path: Path) -> None:
    async def scenario() -> None:
        database = tmp_path / "recovery.db"
        store = SQLiteStore(database)
        now = utc_now()
        snapshot = RunSnapshot(
            id="recover-me",
            topic="恢复测试",
            mode="demo",
            status="running",
            phase="research",
            created_at=now,
            updated_at=now,
            agents={profile.id: AgentRuntime(id=profile.id) for profile in load_profiles()},
        )
        store.save_run(snapshot)
        queue = SQLiteJobQueue(store)
        await queue.enqueue(snapshot.id)
        claimed = await queue.claim("dead-worker", 30)
        assert claimed is not None and claimed.attempts == 1
        with sqlite3.connect(database) as connection:
            connection.execute(
                "UPDATE jobs SET lease_expires_at='2000-01-01T00:00:00+00:00' WHERE run_id=?",
                (snapshot.id,),
            )
            connection.commit()

        service = CommitteeService(store)
        await service.startup()
        for _ in range(500):
            if service.get_run(snapshot.id).status in {"completed", "failed", "cancelled"}:
                break
            await asyncio.sleep(0.02)

        recovered = service.get_run(snapshot.id)
        events = service.list_events(snapshot.id)
        assert recovered.status == "completed"
        assert any(event.type == "run.recovered" for event in events)
        assert any(event.type == "run.completed" for event in events)
        jobs = await service.list_queue_jobs()
        assert jobs[0]["attempts"] == 2
        store.close()

    asyncio.run(scenario())


def test_secrets_are_encrypted_and_owner_isolated(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "security.db")
    vault = SecretVault(tmp_path / "secret.key")
    service = CommitteeService(store, vault)
    second_user, api_token = service.create_user("第二研究员", "researcher")

    secret = service.create_secret("local-user", "tushare", "主账号", "test-token-123456")
    stored = store.get_secret_ciphertext(secret.id, "local-user")

    assert stored is not None
    assert stored[1] != "test-token-123456"
    assert vault.decrypt(stored[1]) == "test-token-123456"
    assert store.get_secret_ciphertext(secret.id, second_user.id) is None
    assert service.list_secrets(second_user.id) == []
    assert service.verify_user_token(second_user.id, api_token)
    assert not service.verify_user_token(second_user.id, "wrong-token")
    store.close()


def test_secret_vault_can_use_environment_master_key(tmp_path: Path) -> None:
    master_key = Fernet.generate_key()
    environment_vault = SecretVault(
        tmp_path / "must-not-exist.key",
        master_key,
    )

    assert environment_vault.source == "environment"
    assert not environment_vault.key_path.exists()
    assert environment_vault.decrypt(environment_vault.encrypt("secret")) == "secret"


def test_evidence_and_exports_are_persisted(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "evidence.db")
    now = utc_now()
    evidence = EvidenceRecord(
        id="evidence-1",
        source_name="Tushare Pro",
        observed_at="20260724",
        retrieved_at=now,
        tool_name="tushare_query",
        interface_name="daily",
        params={"ts_code": "300570.SZ"},
        excerpt='{"ok": true}',
        content_hash="abc123",
    )
    runtime = AgentRuntime(id="MACRO-01", status="completed", output="阶段报告", evidence=[evidence])
    snapshot = RunSnapshot(
        id="export-run",
        topic="导出测试",
        mode="demo",
        status="completed",
        phase="completed",
        created_at=now,
        updated_at=now,
        agents={"MACRO-01": runtime},
        consensus="共识内容",
        decision="投决内容",
    )
    store.save_run(snapshot)
    store.save_evidence(snapshot.id, "MACRO-01", evidence)
    store.save_artifact(snapshot.id, "research_report", "阶段成果", "阶段报告", 1, "MACRO-01")

    artifacts = store.list_artifacts(snapshot.id)
    evidence_rows = store.list_evidence(snapshot.id)
    pdf = build_pdf(snapshot, artifacts, evidence_rows)
    docx = build_docx(snapshot, artifacts, evidence_rows)

    assert evidence_rows[0]["interface_name"] == "daily"
    assert pdf.startswith(b"%PDF")
    assert docx.startswith(b"PK")
    assert len(pdf) > 1000
    assert len(docx) > 1000
    store.close()
