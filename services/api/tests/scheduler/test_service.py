import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from vibe_visualization_api.config import Settings
from vibe_visualization_api.control_plane.repository import ModuleRepository
from vibe_visualization_api.main import create_app
from vibe_visualization_api.scheduler.service import RefreshSchedulerService
from vibe_visualization_api.scheduler.store import SchedulerStore
from vibe_visualization_api.snapshots.store import SnapshotStore


SHANGHAI = ZoneInfo("Asia/Shanghai")


def scheduled_manifest() -> dict[str, object]:
    return {
        "schemaVersion": "1.0",
        "id": "market-daily",
        "name": "每日股票行情",
        "version": "0.1.0",
        "category": "market",
        "entry": {"type": "structured", "url": "/modules/market-daily/"},
        "permissions": ["market.read"],
        "dataServices": ["market-data"],
        "agentCapabilities": ["market.refresh"],
        "events": {"emits": [], "accepts": []},
        "refresh": {"mode": "schedule", "cron": "0 9 * * *"},
    }


def publish_market_module(repository: ModuleRepository) -> None:
    draft = repository.create_draft(scheduled_manifest())
    repository.publish(draft.module_id, draft.revision)


class FakeMarketClient:
    def __init__(self, result: dict[str, object] | Exception):
        self.result = result
        self.calls = 0

    async def fetch_snapshot(self) -> dict[str, object]:
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def scheduler_service(
    tmp_path: Path,
    market_client: FakeMarketClient,
) -> tuple[
    RefreshSchedulerService,
    SchedulerStore,
    ModuleRepository,
    SnapshotStore,
]:
    database_path = tmp_path / "app.db"
    repository = ModuleRepository(database_path)
    scheduler_store = SchedulerStore(database_path)
    snapshot_store = SnapshotStore(tmp_path, database_path)
    service = RefreshSchedulerService(
        store=scheduler_store,
        repository=repository,
        snapshot_store=snapshot_store,
        market_client=market_client,
    )
    return service, scheduler_store, repository, snapshot_store


@pytest.mark.asyncio
async def test_published_scheduled_module_is_due_in_asia_shanghai(
    tmp_path: Path,
) -> None:
    market_client = FakeMarketClient({"asOf": "2026-07-20T09:00:00+08:00"})
    service, store, repository, snapshots = scheduler_service(
        tmp_path, market_client
    )
    publish_market_module(repository)

    await service.tick(datetime(2026, 7, 20, 8, 59, tzinfo=SHANGHAI))
    job = store.get("market-daily")
    assert job.timezone == "Asia/Shanghai"
    assert job.next_run_at == datetime(2026, 7, 20, 9, 0, tzinfo=SHANGHAI)

    await service.tick(datetime(2026, 7, 20, 9, 0, tzinfo=SHANGHAI))

    assert market_client.calls == 1
    assert snapshots.latest_success("market-daily").data["asOf"] == (
        "2026-07-20T09:00:00+08:00"
    )
    assert store.get("market-daily").status == "idle"


@pytest.mark.asyncio
async def test_disabled_module_is_skipped(tmp_path: Path) -> None:
    market_client = FakeMarketClient({"asOf": "2026-07-20T09:00:00+08:00"})
    service, _, repository, _ = scheduler_service(tmp_path, market_client)
    publish_market_module(repository)
    await service.tick(datetime(2026, 7, 20, 8, 59, tzinfo=SHANGHAI))

    repository.disable("market-daily")
    await service.tick(datetime(2026, 7, 20, 9, 0, tzinfo=SHANGHAI))

    assert market_client.calls == 0


@pytest.mark.asyncio
async def test_two_ticks_cannot_refresh_the_same_module_concurrently(
    tmp_path: Path,
) -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    class BlockingMarketClient(FakeMarketClient):
        async def fetch_snapshot(self) -> dict[str, object]:
            self.calls += 1
            started.set()
            await release.wait()
            return {"asOf": "2026-07-20T09:00:00+08:00"}

    market_client = BlockingMarketClient({})
    service, _, repository, _ = scheduler_service(tmp_path, market_client)
    publish_market_module(repository)
    await service.tick(datetime(2026, 7, 20, 8, 59, tzinfo=SHANGHAI))
    now = datetime(2026, 7, 20, 9, 0, tzinfo=SHANGHAI)

    first_tick = asyncio.create_task(service.tick(now))
    await asyncio.wait_for(started.wait(), timeout=1)
    await service.tick(now)
    release.set()
    await first_tick

    assert market_client.calls == 1


@pytest.mark.asyncio
async def test_failed_refresh_preserves_snapshot_and_advances_next_run(
    tmp_path: Path,
) -> None:
    market_client = FakeMarketClient(RuntimeError("upstream timeout"))
    service, store, repository, snapshots = scheduler_service(
        tmp_path, market_client
    )
    publish_market_module(repository)
    previous = snapshots.write_success(
        "market-daily", {"asOf": "2026-07-19T15:00:00+08:00"}
    )
    await service.tick(datetime(2026, 7, 20, 8, 59, tzinfo=SHANGHAI))
    now = datetime(2026, 7, 20, 9, 0, tzinfo=SHANGHAI)

    await service.tick(now)

    job = store.get("market-daily")
    assert snapshots.latest_success("market-daily").id == previous.id
    assert job.status == "failed"
    assert job.next_run_at == datetime(2026, 7, 21, 9, 0, tzinfo=SHANGHAI)
    assert job.last_error == "upstream timeout"


@pytest.mark.asyncio
async def test_startup_recovers_a_lease_running_for_more_than_30_minutes(
    tmp_path: Path,
) -> None:
    service, store, _, _ = scheduler_service(
        tmp_path, FakeMarketClient({})
    )
    due_at = datetime(2026, 7, 20, 9, 0, tzinfo=SHANGHAI)
    store.ensure_job(
        module_id="market-daily",
        cron="0 9 * * *",
        timezone="Asia/Shanghai",
        now=datetime(2026, 7, 20, 8, 59, tzinfo=SHANGHAI),
    )
    assert store.try_acquire("market-daily", due_at)

    await service.startup(due_at + timedelta(minutes=31))

    job = store.get("market-daily")
    assert job.status == "failed"
    assert job.last_error == "recovered stale scheduler lease"


class SchedulerLifecycleProbe:
    def __init__(self) -> None:
        self.started = 0
        self.stopped = 0

    async def start(self) -> None:
        self.started += 1

    async def stop(self) -> None:
        self.stopped += 1


def test_app_lifespan_starts_scheduler_only_when_enabled(tmp_path: Path) -> None:
    enabled_probe = SchedulerLifecycleProbe()
    enabled_app = create_app(
        Settings(
            runtime_dir=tmp_path / "enabled",
            database_path=tmp_path / "enabled.db",
            enable_scheduler=True,
        ),
        scheduler_service=enabled_probe,
    )
    with TestClient(enabled_app) as client:
        assert client.get("/api/health").status_code == 200
        assert enabled_probe.started == 1
    assert enabled_probe.stopped == 1

    disabled_probe = SchedulerLifecycleProbe()
    disabled_app = create_app(
        Settings(
            runtime_dir=tmp_path / "disabled",
            database_path=tmp_path / "disabled.db",
            enable_scheduler=False,
        ),
        scheduler_service=disabled_probe,
    )
    with TestClient(disabled_app) as client:
        assert client.get("/api/health").status_code == 200
    assert disabled_probe.started == 0
    assert disabled_probe.stopped == 0
