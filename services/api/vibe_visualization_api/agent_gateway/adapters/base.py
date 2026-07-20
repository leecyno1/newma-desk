from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from vibe_visualization_api.agent_gateway.models import (
    AdapterEvent,
    AgentTaskCreate,
)


@runtime_checkable
class AgentAdapter(Protocol):
    id: str

    async def capabilities(self) -> list[str]:
        ...

    def run(self, request: AgentTaskCreate) -> AsyncIterator[AdapterEvent]:
        ...

    async def cancel(self, task_id: str) -> None:
        ...
