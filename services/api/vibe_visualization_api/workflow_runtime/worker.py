from __future__ import annotations

import asyncio

from starlette.concurrency import run_in_threadpool

from vibe_visualization_api.workflow_runtime.engine import WorkflowRuntimeEngine


class WorkflowRuntimeWorker:
    """Keeps persisted workflow executions moving independently of the UI."""

    def __init__(
        self,
        engine: WorkflowRuntimeEngine,
        *,
        poll_seconds: float = 0.5,
        batch_size: int = 100,
    ):
        self._engine = engine
        self._poll_seconds = poll_seconds
        self._batch_size = batch_size
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop_event.set()
        await self._task
        self._task = None

    async def tick(self) -> None:
        await run_in_threadpool(
            self._engine.dispatch_due_schedules,
            limit=self._batch_size,
        )
        timestamp = self._engine.current_timestamp()
        refs = await run_in_threadpool(
            self._engine.repository.list_runnable_execution_refs,
            timestamp,
            limit=self._batch_size,
        )
        for ref in refs:
            try:
                await run_in_threadpool(
                    self._engine.tick,
                    organization_id=ref["organizationId"],
                    execution_id=ref["executionId"],
                )
            except Exception:
                continue

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
