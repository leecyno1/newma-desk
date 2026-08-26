#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Small bounded caches shared by expensive analysis handlers."""

from __future__ import annotations

import time
import asyncio
from collections import OrderedDict
from copy import deepcopy
from threading import RLock
from typing import Any, Callable


class BoundedTTLCache:
    def __init__(
        self,
        *,
        max_entries: int,
        ttl_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.max_entries = max(1, int(max_entries))
        self.ttl_seconds = max(1.0, float(ttl_seconds))
        self._clock = clock
        self._lock = RLock()
        self._entries: OrderedDict[Any, tuple[float, Any]] = OrderedDict()

    def _purge_expired(self, now: float) -> None:
        expired = [
            key
            for key, (stored_at, _) in self._entries.items()
            if now - stored_at >= self.ttl_seconds
        ]
        for key in expired:
            self._entries.pop(key, None)

    def get(self, key: Any) -> Any | None:
        now = self._clock()
        with self._lock:
            self._purge_expired(now)
            entry = self._entries.pop(key, None)
            if entry is None:
                return None
            self._entries[key] = entry
            return deepcopy(entry[1])

    def set(self, key: Any, value: Any) -> None:
        now = self._clock()
        with self._lock:
            self._purge_expired(now)
            self._entries.pop(key, None)
            self._entries[key] = (now, deepcopy(value))
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def stats(self) -> dict[str, Any]:
        now = self._clock()
        with self._lock:
            self._purge_expired(now)
            return {
                "storage": "process_memory",
                "volatile": True,
                "entries": len(self._entries),
                "max_entries": self.max_entries,
                "ttl_seconds": self.ttl_seconds,
            }


class AsyncTaskCoalescer:
    """Share one active async task per cache key without event-loop globals."""

    def __init__(self):
        self._tasks: dict[Any, asyncio.Task] = {}

    def get(self, key: Any) -> asyncio.Task | None:
        task = self._tasks.get(key)
        if task is not None and task.get_loop() is not asyncio.get_running_loop():
            self._tasks.pop(key, None)
            return None
        return task

    def set(self, key: Any, task: asyncio.Task) -> None:
        self._tasks[key] = task

    def discard(self, key: Any, task: asyncio.Task) -> None:
        if self._tasks.get(key) is task:
            self._tasks.pop(key, None)

    def clear(self) -> None:
        self._tasks.clear()

    def __len__(self) -> int:
        return len(self._tasks)
