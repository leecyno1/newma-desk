import asyncio
from datetime import datetime, timezone
from typing import Protocol

from starlette.concurrency import run_in_threadpool

from vibe_visualization_api.control_plane.repository import ModuleRepository
from vibe_visualization_api.scheduler.models import RefreshJob
from vibe_visualization_api.scheduler.store import SchedulerStore
from vibe_visualization_api.snapshots.store import SnapshotStore


class MarketSnapshotClient(Protocol):
    async def fetch_snapshot(self) -> dict[str, object]: ...


class SchedulerLifecycle(Protocol):
    async def start(self) -> None: ...

    async def stop(self) -> None: ...


class RefreshSchedulerService:
    def __init__(
        self,
        *,
        store: SchedulerStore,
        repository: ModuleRepository,
        snapshot_store: SnapshotStore,
        market_client: MarketSnapshotClient,
        poll_seconds: float = 30.0,
    ):
        self._store = store
        self._repository = repository
        self._snapshot_store = snapshot_store
        self._market_client = market_client
        self._poll_seconds = poll_seconds
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    async def startup(self, now: datetime | None = None) -> None:
        await run_in_threadpool(
            self._store.recover_stale,
            now or datetime.now(timezone.utc),
        )

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop_event = asyncio.Event()
        await self.startup()
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop_event.set()
        await self._task
        self._task = None

    async def tick(self, now: datetime | None = None) -> None:
        tick_at = now or datetime.now(timezone.utc)
        modules = await run_in_threadpool(self._repository.list_published)
        scheduled_ids: set[str] = set()
        for module in modules:
            refresh = module.manifest.get("refresh")
            capabilities = module.manifest.get("agentCapabilities", [])
            if (
                module.module_id != "market-daily"
                or not isinstance(refresh, dict)
                or refresh.get("mode") != "schedule"
                or not isinstance(refresh.get("cron"), str)
                or not isinstance(capabilities, list)
                or "market.refresh" not in capabilities
            ):
                continue
            scheduled_ids.add(module.module_id)
            await run_in_threadpool(
                self._store.ensure_job,
                module_id=module.module_id,
                cron=refresh["cron"],
                timezone="Asia/Shanghai",
                now=tick_at,
            )

        due = await run_in_threadpool(
            self._store.list_due,
            tick_at,
            scheduled_ids,
        )
        if due:
            await asyncio.gather(*(self._run_job(job, tick_at) for job in due))

    async def _run_job(self, job: RefreshJob, started_at: datetime) -> None:
        acquired = await run_in_threadpool(
            self._store.try_acquire,
            job.module_id,
            started_at,
        )
        if not acquired:
            return

        try:
            snapshot = await self._market_client.fetch_snapshot()
            await run_in_threadpool(
                self._snapshot_store.write_success,
                job.module_id,
                snapshot,
            )
        except Exception as error:
            message = str(error).strip() or error.__class__.__name__
            try:
                await run_in_threadpool(
                    self._snapshot_store.write_failure,
                    job.module_id,
                    message,
                )
            finally:
                await run_in_threadpool(
                    self._store.complete_failure,
                    job.module_id,
                    started_at,
                    message,
                )
            return

        await run_in_threadpool(
            self._store.complete_success,
            job.module_id,
            started_at,
        )

    async def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self.tick()
            except Exception:
                pass
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self._poll_seconds,
                )
            except TimeoutError:
                continue
