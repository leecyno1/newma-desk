import pytest

from vibe_visualization_api.agent_gateway.adapters.base import AgentAdapter
from vibe_visualization_api.agent_gateway.models import AgentTaskCreate
from tests.agent_gateway.fakes import FakeAgentAdapter


async def _collect(adapter: AgentAdapter, request: AgentTaskCreate):
    return [event async for event in adapter.run(request)]


async def _cancel(adapter: AgentAdapter, task_id: str) -> None:
    await adapter.cancel(task_id)


def test_fake_adapter_satisfies_the_runtime_protocol() -> None:
    assert isinstance(FakeAgentAdapter(), AgentAdapter)


@pytest.mark.asyncio
async def test_adapter_streams_progress_and_completion() -> None:
    adapter = FakeAgentAdapter()

    events = await _collect(adapter, AgentTaskCreate(prompt="hello"))

    assert [event.type for event in events] == ["progress", "completed"]
    assert events[-1].data["answer"] == "fake: hello"
    assert adapter.requests[0].prompt == "hello"


@pytest.mark.asyncio
async def test_adapter_exposes_capabilities_and_cancellation() -> None:
    adapter = FakeAgentAdapter()

    assert await adapter.capabilities() == ["chat", "module.explain"]
    await _cancel(adapter, "task-1")

    assert adapter.cancelled_task_ids == ["task-1"]
