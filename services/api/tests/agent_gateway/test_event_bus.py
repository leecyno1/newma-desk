import asyncio

import pytest

from vibe_visualization_api.agent_gateway.event_bus import TaskEventBus
from vibe_visualization_api.agent_gateway.models import TaskEvent


def _event(
    task_id: str,
    sequence: int,
    event_type: str = "progress",
) -> TaskEvent:
    return TaskEvent(
        task_id=task_id,
        sequence=sequence,
        type=event_type,
        data={"sequence": sequence},
    )


@pytest.mark.asyncio
async def test_subscribers_only_receive_their_tasks_events() -> None:
    bus = TaskEventBus()
    first = await bus.subscribe("task-1")
    second = await bus.subscribe("task-2")

    await bus.publish(_event("task-1", 1))

    assert (await asyncio.wait_for(first.get(), timeout=0.1)).task_id == "task-1"
    assert second.empty()


@pytest.mark.asyncio
async def test_unsubscribe_removes_disconnected_subscriber() -> None:
    bus = TaskEventBus()
    queue = await bus.subscribe("task-1")

    await bus.unsubscribe("task-1", queue)
    await bus.publish(_event("task-1", 1))

    assert queue.empty()


@pytest.mark.asyncio
async def test_full_queue_discards_the_oldest_progress_event() -> None:
    bus = TaskEventBus(max_queue_size=3)
    queue = await bus.subscribe("task-1")
    await bus.publish(_event("task-1", 1, "queued"))
    await bus.publish(_event("task-1", 2, "progress"))
    await bus.publish(_event("task-1", 3, "progress"))

    await bus.publish(_event("task-1", 4, "artifact"))

    received = [queue.get_nowait() for _ in range(queue.qsize())]
    assert [(event.sequence, event.type) for event in received] == [
        (1, "queued"),
        (3, "progress"),
        (4, "artifact"),
    ]


@pytest.mark.asyncio
async def test_terminal_event_is_kept_when_queue_has_no_progress() -> None:
    bus = TaskEventBus(max_queue_size=2)
    queue = await bus.subscribe("task-1")
    await bus.publish(_event("task-1", 1, "queued"))
    await bus.publish(_event("task-1", 2, "artifact"))

    await bus.publish(_event("task-1", 3, "completed"))

    received = [queue.get_nowait() for _ in range(queue.qsize())]
    assert received[-1].type == "completed"
    assert all(event.type != "progress" for event in received)
