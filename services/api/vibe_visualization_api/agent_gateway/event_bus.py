import asyncio
from collections.abc import Callable

from vibe_visualization_api.agent_gateway.models import TaskEvent


TERMINAL_EVENT_TYPES = {"completed", "failed", "cancelled"}


def _remove_oldest_matching(
    queue: asyncio.Queue[TaskEvent],
    predicate: Callable[[TaskEvent], bool],
) -> bool:
    retained: list[TaskEvent] = []
    removed = False
    while not queue.empty():
        event = queue.get_nowait()
        queue.task_done()
        if not removed and predicate(event):
            removed = True
            continue
        retained.append(event)
    for event in retained:
        queue.put_nowait(event)
    return removed


class TaskEventBus:
    def __init__(self, max_queue_size: int = 100):
        if max_queue_size < 1:
            raise ValueError("max_queue_size must be at least one")
        self._max_queue_size = max_queue_size
        self._subscribers: dict[str, set[asyncio.Queue[TaskEvent]]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, task_id: str) -> asyncio.Queue[TaskEvent]:
        queue: asyncio.Queue[TaskEvent] = asyncio.Queue(maxsize=self._max_queue_size)
        async with self._lock:
            self._subscribers.setdefault(task_id, set()).add(queue)
        return queue

    async def unsubscribe(
        self,
        task_id: str,
        queue: asyncio.Queue[TaskEvent],
    ) -> None:
        async with self._lock:
            subscribers = self._subscribers.get(task_id)
            if subscribers is None:
                return
            subscribers.discard(queue)
            if not subscribers:
                self._subscribers.pop(task_id, None)

    async def publish(self, event: TaskEvent) -> None:
        async with self._lock:
            subscribers = tuple(self._subscribers.get(event.task_id, ()))
        for queue in subscribers:
            self._publish_to_queue(queue, event)

    @staticmethod
    def _publish_to_queue(
        queue: asyncio.Queue[TaskEvent],
        event: TaskEvent,
    ) -> None:
        if not queue.full():
            queue.put_nowait(event)
            return

        removed = _remove_oldest_matching(
            queue,
            lambda queued: queued.type == "progress",
        )
        if not removed and event.type in TERMINAL_EVENT_TYPES:
            removed = _remove_oldest_matching(
                queue,
                lambda queued: queued.type not in TERMINAL_EVENT_TYPES,
            )
        if not removed:
            if event.type in TERMINAL_EVENT_TYPES:
                raise RuntimeError(
                    "a bounded task queue cannot contain only terminal events"
                )
            return
        queue.put_nowait(event)
