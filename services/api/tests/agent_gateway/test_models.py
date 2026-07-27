import pytest
from pydantic import ValidationError

from vibe_visualization_api.agent_gateway.models import (
    AdapterEvent,
    AgentTask,
    AgentTaskCreate,
    TaskEvent,
)


def test_agent_task_requires_a_capability_or_prompt() -> None:
    with pytest.raises(ValidationError):
        AgentTaskCreate(module_id="market-daily", prompt="", capability=None)


def test_agent_task_rejects_whitespace_only_intent() -> None:
    with pytest.raises(ValidationError):
        AgentTaskCreate(prompt="   ", capability=None)


def test_agent_task_accepts_capability_without_prompt() -> None:
    request = AgentTaskCreate(
        module_id="market-daily",
        capability="market.explain",
    )

    assert request.prompt == ""
    assert request.capability == "market.explain"


def test_agent_task_accepts_and_serializes_camel_case_module_id() -> None:
    request = AgentTaskCreate.model_validate(
        {"moduleId": "market-daily", "prompt": "解释异动"}
    )

    assert request.module_id == "market-daily"
    assert request.model_dump(mode="json") == {
        "userId": "local-user",
        "moduleId": "market-daily",
        "capability": None,
        "memoryScope": "user-agent-mod",
        "prompt": "解释异动",
        "context": {},
        "input": {},
        "adapter": None,
    }


def test_agent_task_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        AgentTaskCreate(prompt="hello", apiKey="must-not-be-accepted")


def test_task_event_has_monotonic_sequence() -> None:
    event = TaskEvent(
        task_id="task-1",
        sequence=1,
        type="progress",
        data={"message": "loading"},
    )

    assert event.sequence == 1


def test_task_event_rejects_non_positive_sequence() -> None:
    with pytest.raises(ValidationError):
        TaskEvent(task_id="task-1", sequence=0, type="queued")


def test_adapter_event_has_no_persistence_identity() -> None:
    event = AdapterEvent(type="completed", data={"answer": "done"})

    assert event.type == "completed"
    assert event.model_dump(mode="json") == {
        "type": "completed",
        "data": {"answer": "done"},
    }
    with pytest.raises(ValidationError):
        AdapterEvent(
            taskId="task-1",
            sequence=1,
            type="completed",
            data={"answer": "done"},
        )


def test_agent_task_embeds_the_original_request() -> None:
    task = AgentTask(
        id="task-1",
        status="queued",
        request=AgentTaskCreate(prompt="hello"),
    )

    assert task.id == "task-1"
    assert task.request.prompt == "hello"
    assert task.result is None
    assert task.error is None
