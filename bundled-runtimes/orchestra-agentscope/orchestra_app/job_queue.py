from __future__ import annotations

import asyncio
import json
import secrets
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from .models import utc_now
from .storage import SQLiteStore


@dataclass(frozen=True)
class ClaimedJob:
    run_id: str
    attempts: int


class JobQueue(Protocol):
    backend_name: str

    async def start(self) -> None: ...

    async def close(self) -> None: ...

    async def enqueue(self, run_id: str) -> None: ...

    async def ensure(self, run_id: str) -> None: ...

    async def claim(self, worker_id: str, lease_seconds: int) -> ClaimedJob | None: ...

    async def renew(self, run_id: str, worker_id: str, lease_seconds: int) -> bool: ...

    async def complete(self, run_id: str, worker_id: str) -> bool: ...

    async def release(self, run_id: str, worker_id: str, delay_seconds: float = 0) -> bool: ...

    async def fail(
        self,
        run_id: str,
        worker_id: str,
        error: str,
        max_attempts: int,
        retry_delay_seconds: float,
    ) -> str: ...

    async def cancel(self, run_id: str) -> bool: ...

    async def stats(self) -> dict[str, Any]: ...

    async def list_jobs(self, limit: int = 50) -> list[dict[str, Any]]: ...


class SQLiteJobQueue:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    @property
    def backend_name(self) -> str:
        return f"{self.store.backend_name}-durable"

    async def start(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def enqueue(self, run_id: str) -> None:
        self.store.enqueue_job(run_id)

    async def ensure(self, run_id: str) -> None:
        self.store.ensure_job(run_id)

    async def claim(self, worker_id: str, lease_seconds: int) -> ClaimedJob | None:
        row = self.store.claim_job(worker_id, lease_seconds)
        if row is None:
            return None
        return ClaimedJob(run_id=row["run_id"], attempts=int(row["attempts"]))

    async def renew(self, run_id: str, worker_id: str, lease_seconds: int) -> bool:
        return self.store.renew_job(run_id, worker_id, lease_seconds)

    async def complete(self, run_id: str, worker_id: str) -> bool:
        return self.store.complete_job(run_id, worker_id)

    async def release(self, run_id: str, worker_id: str, delay_seconds: float = 0) -> bool:
        return self.store.release_job(run_id, worker_id, delay_seconds)

    async def fail(
        self,
        run_id: str,
        worker_id: str,
        error: str,
        max_attempts: int,
        retry_delay_seconds: float,
    ) -> str:
        return self.store.fail_job(
            run_id,
            worker_id,
            error,
            max_attempts,
            retry_delay_seconds,
        )

    async def cancel(self, run_id: str) -> bool:
        return self.store.cancel_job(run_id)

    async def stats(self) -> dict[str, Any]:
        return {"backend": self.backend_name, **self.store.job_stats()}

    async def list_jobs(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.store.list_jobs(limit)


class RedisJobQueue:
    backend_name = "redis-durable"

    def __init__(self, redis_url: str, prefix: str = "orchestra", client: Any = None) -> None:
        self.redis_url = redis_url
        self.prefix = prefix.rstrip(":")
        self._redis: Any = client

    @property
    def _jobs_key(self) -> str:
        return f"{self.prefix}:jobs"

    @property
    def _ready_key(self) -> str:
        return f"{self.prefix}:ready"

    @property
    def _processing_key(self) -> str:
        return f"{self.prefix}:processing"

    @property
    def _lock_key(self) -> str:
        return f"{self.prefix}:queue-lock"

    async def start(self) -> None:
        if self._redis is not None:
            await self._redis.ping()
            return
        try:
            from redis.asyncio import Redis
        except ImportError as error:
            raise RuntimeError("Redis队列需要安装 agentscope[storage-redis]。") from error
        self._redis = Redis.from_url(self.redis_url, decode_responses=True)
        await self._redis.ping()

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()

    @asynccontextmanager
    async def _lock(self):
        token = secrets.token_urlsafe(24)
        deadline = time.monotonic() + 2
        while not await self._redis.set(self._lock_key, token, nx=True, ex=10):
            if time.monotonic() >= deadline:
                raise TimeoutError("Redis任务队列锁等待超时。")
            await asyncio.sleep(0.05)
        try:
            yield
        finally:
            try:
                from redis.exceptions import WatchError

                while True:
                    pipeline = self._redis.pipeline()
                    try:
                        await pipeline.watch(self._lock_key)
                        if await pipeline.get(self._lock_key) != token:
                            await pipeline.reset()
                            break
                        pipeline.multi()
                        pipeline.delete(self._lock_key)
                        await pipeline.execute()
                        break
                    except WatchError:
                        continue
                    finally:
                        await pipeline.reset()
            except ImportError:
                if await self._redis.get(self._lock_key) == token:
                    await self._redis.delete(self._lock_key)

    async def _read(self, run_id: str) -> dict[str, Any] | None:
        raw = await self._redis.hget(self._jobs_key, run_id)
        return json.loads(raw) if raw else None

    async def _write(self, run_id: str, payload: dict[str, Any]) -> None:
        await self._redis.hset(
            self._jobs_key,
            run_id,
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        )

    async def enqueue(self, run_id: str) -> None:
        now = time.time()
        async with self._lock():
            existing = await self._read(run_id) or {}
            payload = {
                **existing,
                "run_id": run_id,
                "status": "queued",
                "attempts": int(existing.get("attempts", 0)),
                "available_at": now,
                "lease_owner": None,
                "lease_expires_at": None,
                "last_error": existing.get("last_error"),
                "updated_at": utc_now(),
            }
            await self._write(run_id, payload)
            await self._redis.zrem(self._processing_key, run_id)
            await self._redis.zadd(self._ready_key, {run_id: now})

    async def ensure(self, run_id: str) -> None:
        if not await self._redis.hexists(self._jobs_key, run_id):
            await self.enqueue(run_id)

    async def _recover_expired(self, now: float) -> None:
        expired = await self._redis.zrangebyscore(self._processing_key, 0, now)
        for run_id in expired:
            payload = await self._read(run_id)
            if payload is None:
                await self._redis.zrem(self._processing_key, run_id)
                continue
            payload.update(
                status="queued",
                available_at=now,
                lease_owner=None,
                lease_expires_at=None,
                updated_at=utc_now(),
            )
            await self._write(run_id, payload)
            await self._redis.zrem(self._processing_key, run_id)
            await self._redis.zadd(self._ready_key, {run_id: now})

    async def claim(self, worker_id: str, lease_seconds: int) -> ClaimedJob | None:
        now = time.time()
        async with self._lock():
            await self._recover_expired(now)
            ready = await self._redis.zrangebyscore(self._ready_key, 0, now, start=0, num=1)
            if not ready:
                return None
            run_id = ready[0]
            payload = await self._read(run_id)
            if payload is None:
                await self._redis.zrem(self._ready_key, run_id)
                return None
            attempts = int(payload.get("attempts", 0)) + 1
            lease_expires = now + lease_seconds
            payload.update(
                status="running",
                attempts=attempts,
                lease_owner=worker_id,
                lease_expires_at=lease_expires,
                updated_at=utc_now(),
            )
            await self._write(run_id, payload)
            await self._redis.zrem(self._ready_key, run_id)
            await self._redis.zadd(self._processing_key, {run_id: lease_expires})
            return ClaimedJob(run_id=run_id, attempts=attempts)

    async def renew(self, run_id: str, worker_id: str, lease_seconds: int) -> bool:
        async with self._lock():
            payload = await self._read(run_id)
            if not payload or payload.get("status") != "running" or payload.get("lease_owner") != worker_id:
                return False
            lease_expires = time.time() + lease_seconds
            payload["lease_expires_at"] = lease_expires
            payload["updated_at"] = utc_now()
            await self._write(run_id, payload)
            await self._redis.zadd(self._processing_key, {run_id: lease_expires})
            return True

    async def complete(self, run_id: str, worker_id: str) -> bool:
        return await self._finish(run_id, worker_id, "completed")

    async def release(self, run_id: str, worker_id: str, delay_seconds: float = 0) -> bool:
        async with self._lock():
            payload = await self._read(run_id)
            if not payload or payload.get("lease_owner") != worker_id:
                return False
            available_at = time.time() + max(0, delay_seconds)
            payload.update(
                status="queued",
                available_at=available_at,
                lease_owner=None,
                lease_expires_at=None,
                updated_at=utc_now(),
            )
            await self._write(run_id, payload)
            await self._redis.zrem(self._processing_key, run_id)
            await self._redis.zadd(self._ready_key, {run_id: available_at})
            return True

    async def fail(
        self,
        run_id: str,
        worker_id: str,
        error: str,
        max_attempts: int,
        retry_delay_seconds: float,
    ) -> str:
        async with self._lock():
            payload = await self._read(run_id)
            if not payload or payload.get("lease_owner") != worker_id:
                return "missing"
            status = "queued" if int(payload.get("attempts", 0)) < max_attempts else "failed"
            available_at = time.time() + (retry_delay_seconds if status == "queued" else 0)
            payload.update(
                status=status,
                available_at=available_at,
                lease_owner=None,
                lease_expires_at=None,
                last_error=error,
                updated_at=utc_now(),
            )
            await self._write(run_id, payload)
            await self._redis.zrem(self._processing_key, run_id)
            if status == "queued":
                await self._redis.zadd(self._ready_key, {run_id: available_at})
            return status

    async def cancel(self, run_id: str) -> bool:
        async with self._lock():
            payload = await self._read(run_id)
            if not payload or payload.get("status") in {"completed", "failed", "cancelled"}:
                return False
            payload.update(
                status="cancelled",
                lease_owner=None,
                lease_expires_at=None,
                updated_at=utc_now(),
            )
            await self._write(run_id, payload)
            await self._redis.zrem(self._ready_key, run_id)
            await self._redis.zrem(self._processing_key, run_id)
            return True

    async def _finish(self, run_id: str, worker_id: str, status: str) -> bool:
        async with self._lock():
            payload = await self._read(run_id)
            if not payload or payload.get("lease_owner") != worker_id:
                return False
            payload.update(
                status=status,
                lease_owner=None,
                lease_expires_at=None,
                last_error=None,
                updated_at=utc_now(),
            )
            await self._write(run_id, payload)
            await self._redis.zrem(self._processing_key, run_id)
            return True

    async def stats(self) -> dict[str, Any]:
        values = await self._redis.hvals(self._jobs_key)
        jobs = [json.loads(value) for value in values]
        counts: dict[str, int] = {}
        for job in jobs:
            status = str(job.get("status", "unknown"))
            counts[status] = counts.get(status, 0) + 1
        queued = [float(job["available_at"]) for job in jobs if job.get("status") == "queued"]
        oldest = min(queued) if queued else None
        return {
            "backend": self.backend_name,
            "total": len(jobs),
            "queued": counts.get("queued", 0),
            "running": counts.get("running", 0),
            "completed": counts.get("completed", 0),
            "failed": counts.get("failed", 0),
            "cancelled": counts.get("cancelled", 0),
            "oldest_queued_at": (
                datetime.fromtimestamp(oldest, timezone.utc).isoformat() if oldest else None
            ),
            "max_attempts_seen": max((int(job.get("attempts", 0)) for job in jobs), default=0),
        }

    async def list_jobs(self, limit: int = 50) -> list[dict[str, Any]]:
        values = await self._redis.hvals(self._jobs_key)
        jobs = [json.loads(value) for value in values]
        jobs.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)
        for job in jobs[:limit]:
            available_at = job.get("available_at")
            if isinstance(available_at, (int, float)):
                job["available_at"] = datetime.fromtimestamp(available_at, timezone.utc).isoformat()
            lease_expires = job.get("lease_expires_at")
            if isinstance(lease_expires, (int, float)):
                job["lease_expires_at"] = datetime.fromtimestamp(
                    lease_expires,
                    timezone.utc,
                ).isoformat()
        return jobs[:limit]
