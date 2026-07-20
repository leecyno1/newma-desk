from collections.abc import AsyncIterator

from vibe_visualization_api.agent_gateway.models import (
    AdapterEvent,
    AgentTaskCreate,
)


class FakeAgentAdapter:
    id = "fake"

    def __init__(self) -> None:
        self.requests: list[AgentTaskCreate] = []
        self.cancelled_task_ids: list[str] = []

    async def capabilities(self) -> list[str]:
        return ["chat", "module.explain"]

    async def run(
        self,
        request: AgentTaskCreate,
    ) -> AsyncIterator[AdapterEvent]:
        self.requests.append(request)
        yield AdapterEvent(type="progress", data={"message": "working"})
        intent = request.prompt or request.capability or ""
        yield AdapterEvent(
            type="completed",
            data={"answer": f"fake: {intent}"},
        )

    async def cancel(self, task_id: str) -> None:
        self.cancelled_task_ids.append(task_id)
