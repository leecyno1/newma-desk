from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from vibe_visualization_api.agent_gateway.models import AgentTaskCreate
from vibe_visualization_api.agent_gateway.store import (
    InvalidTaskStateError,
    TaskNotFoundError,
    TaskStore,
)


def test_task_store_persists_events_in_order(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "tasks.db")
    task = store.create(AgentTaskCreate(prompt="explain the move"))

    store.append_event(task.id, "progress", {"message": "loading"})
    store.append_event(task.id, "completed", {"answer": "done"})

    assert [event.sequence for event in store.list_events(task.id)] == [1, 2, 3]
    persisted = store.get(task.id)
    assert persisted.status == "completed"
    assert persisted.result == {"answer": "done"}
    assert persisted.error is None


def test_task_store_reopens_with_camel_case_request_data(tmp_path: Path) -> None:
    database_path = tmp_path / "tasks.db"
    created = TaskStore(database_path).create(
        AgentTaskCreate(
            module_id="market-daily",
            capability="market.explain",
            prompt="解释异动",
            context={"securityCode": "600519"},
        )
    )

    reopened = TaskStore(database_path).get(created.id)

    assert reopened.request.module_id == "market-daily"
    assert reopened.request.prompt == "解释异动"
    assert reopened.request.context == {"securityCode": "600519"}


def test_list_events_replays_only_after_requested_sequence(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "tasks.db")
    task = store.create(AgentTaskCreate(prompt="hello"))
    store.append_event(task.id, "progress", {"step": 1})
    store.append_event(task.id, "artifact", {"url": "/artifact/1"})

    events = store.list_events(task.id, after=1)

    assert [event.sequence for event in events] == [2, 3]
    with pytest.raises(ValueError):
        store.list_events(task.id, after=-1)


def test_missing_task_raises_domain_error(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "tasks.db")

    with pytest.raises(TaskNotFoundError):
        store.get("missing")
    with pytest.raises(TaskNotFoundError):
        store.append_event("missing", "progress", {})


def test_terminal_task_rejects_later_events(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "tasks.db")
    task = store.create(AgentTaskCreate(prompt="hello"))
    store.append_event(task.id, "completed", {"answer": "done"})

    with pytest.raises(InvalidTaskStateError):
        store.append_event(task.id, "progress", {"message": "late"})


def test_cancel_persists_a_terminal_event_and_is_idempotent(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "tasks.db")
    task = store.create(AgentTaskCreate(prompt="hello"))
    store.append_event(task.id, "progress", {"message": "running"})

    cancelled = store.cancel(task.id)
    cancelled_again = store.cancel(task.id)

    assert cancelled.status == "cancelled"
    assert cancelled_again == cancelled
    assert [event.type for event in store.list_events(task.id)] == [
        "queued",
        "progress",
        "cancelled",
    ]


def test_completed_task_cannot_be_cancelled(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "tasks.db")
    task = store.create(AgentTaskCreate(prompt="hello"))
    store.append_event(task.id, "completed", {"answer": "done"})

    with pytest.raises(InvalidTaskStateError):
        store.cancel(task.id)


def test_concurrent_appends_allocate_unique_sequences(tmp_path: Path) -> None:
    database_path = tmp_path / "tasks.db"
    store = TaskStore(database_path)
    task = store.create(AgentTaskCreate(prompt="hello"))

    def append(index: int) -> int:
        event = TaskStore(database_path).append_event(
            task.id,
            "progress",
            {"index": index},
        )
        return event.sequence

    with ThreadPoolExecutor(max_workers=4) as executor:
        sequences = list(executor.map(append, range(8)))

    assert sorted(sequences) == list(range(2, 10))
    assert [event.sequence for event in store.list_events(task.id)] == list(
        range(1, 10)
    )
