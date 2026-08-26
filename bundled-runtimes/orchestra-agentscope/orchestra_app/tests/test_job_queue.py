import asyncio
from pathlib import Path

from fakeredis.aioredis import FakeRedis

from orchestra_app.job_queue import RedisJobQueue, SQLiteJobQueue
from orchestra_app.models import AgentRuntime, RunSnapshot, utc_now
from orchestra_app.service import CommitteeService
from orchestra_app.storage import SQLiteStore


def _save_run(store: SQLiteStore, run_id: str) -> None:
    now = utc_now()
    store.save_run(
        RunSnapshot(
            id=run_id,
            topic="队列测试",
            mode="demo",
            status="queued",
            phase="queued",
            created_at=now,
            updated_at=now,
            agents={"agent": AgentRuntime(id="agent")},
        ),
    )


def test_sqlite_queue_claim_lease_retry_and_schema_version(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = SQLiteStore(tmp_path / "queue.db")
        _save_run(store, "run-1")
        queue = SQLiteJobQueue(store)
        await queue.enqueue("run-1")

        first = await queue.claim("worker-1", 30)
        assert first is not None and first.attempts == 1
        assert await queue.claim("worker-2", 30) is None
        assert await queue.renew("run-1", "worker-1", 30)
        assert await queue.fail("run-1", "worker-1", "temporary", 2, 0) == "queued"

        second = await queue.claim("worker-2", 30)
        assert second is not None and second.attempts == 2
        assert await queue.fail("run-1", "worker-2", "terminal", 2, 0) == "failed"
        stats = await queue.stats()
        assert stats["failed"] == 1
        assert stats["max_attempts_seen"] == 2
        assert store.schema_version() == 3
        store.close()

    asyncio.run(scenario())


def test_redis_queue_claim_release_and_complete() -> None:
    async def scenario() -> None:
        client = FakeRedis(decode_responses=True)
        queue = RedisJobQueue("redis://unused", "orchestra-test", client=client)
        await queue.start()
        await queue.enqueue("run-redis")

        first = await queue.claim("worker-1", 30)
        assert first is not None and first.attempts == 1
        assert await queue.claim("worker-2", 30) is None
        assert await queue.release("run-redis", "worker-1")

        second = await queue.claim("worker-2", 30)
        assert second is not None and second.attempts == 2
        assert await queue.renew("run-redis", "worker-2", 30)
        assert await queue.complete("run-redis", "worker-2")
        stats = await queue.stats()
        assert stats["backend"] == "redis-durable"
        assert stats["completed"] == 1
        await queue.close()

    asyncio.run(scenario())


def test_unavailable_external_queue_falls_back_to_sqlite(tmp_path: Path) -> None:
    class UnavailableQueue:
        backend_name = "redis-durable"

        async def start(self) -> None:
            raise ConnectionError("redis unavailable")

    async def scenario() -> None:
        store = SQLiteStore(tmp_path / "fallback.db")
        service = CommitteeService(store, queue=UnavailableQueue())  # type: ignore[arg-type]
        await service.startup()
        stats = await service.queue_stats()
        assert stats["backend"] == "sqlite-durable"
        assert stats["fallback_reason"] == "redis unavailable"
        await service.shutdown()
        store.close()

    asyncio.run(scenario())
