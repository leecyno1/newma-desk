from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Any

from vibe_visualization_api.agent_gateway.models import AgentTaskCreate
from vibe_visualization_api.agent_gateway.service import AgentTaskService


class AgentGatewayWorkflowPort:
    """Thread-safe bridge from the synchronous workflow engine to Agent Gateway."""

    def __init__(
        self,
        service_provider: Callable[[], AgentTaskService],
        loop_provider: Callable[[], asyncio.AbstractEventLoop | None],
        *,
        command_timeout_seconds: float = 15.0,
    ):
        self._service_provider = service_provider
        self._loop_provider = loop_provider
        self._command_timeout_seconds = command_timeout_seconds

    def create_task(
        self,
        *,
        user_id: str,
        workspace_id: str,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        service = self._service_provider()
        task_request = AgentTaskCreate.model_validate(
            {**request, "userId": user_id}
        )
        task = self._call(
            service.create(task_request, workspace_id=workspace_id)
        )
        return task.model_dump(by_alias=True)

    def get_task(self, task_id: str) -> dict[str, Any]:
        task = self._call(self._service_provider().get(task_id))
        return task.model_dump(by_alias=True)

    def cancel_task(self, task_id: str) -> dict[str, Any]:
        task = self._call(self._service_provider().cancel(task_id))
        return task.model_dump(by_alias=True)

    def _call(self, operation: Coroutine[Any, Any, Any]) -> Any:
        loop = self._loop_provider()
        if loop is None or not loop.is_running():
            operation.close()
            raise RuntimeError("Agent Runtime is not available")
        future = asyncio.run_coroutine_threadsafe(operation, loop)
        try:
            return future.result(timeout=self._command_timeout_seconds)
        except FutureTimeoutError as error:
            future.cancel()
            raise RuntimeError("Agent Gateway command timed out") from error
