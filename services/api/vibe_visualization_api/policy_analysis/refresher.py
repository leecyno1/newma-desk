from __future__ import annotations

import asyncio
from pathlib import Path

from vibe_visualization_api.policy_analysis.service import policy_dashboard


class PolicyRefreshService:
    def __init__(
        self,
        *,
        database_path: Path,
        rsshub_base_url: str,
        timeout_seconds: float,
        interval_seconds: float,
    ):
        self._database_path = database_path
        self._rsshub_base_url = rsshub_base_url
        self._timeout_seconds = timeout_seconds
        self._interval_seconds = interval_seconds
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if not self._rsshub_base_url or (self._task and not self._task.done()):
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop_event.set()
        await self._task
        self._task = None

    async def refresh(self) -> None:
        await policy_dashboard(
            database_path=self._database_path,
            rsshub_base_url=self._rsshub_base_url,
            timeout_seconds=self._timeout_seconds,
            refresh=True,
        )

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self.refresh()
            except Exception:
                pass
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self._interval_seconds
                )
            except TimeoutError:
                continue
