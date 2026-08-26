"""Process-local LLM health state and circuit breaker."""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional


class LlmCircuitOpen(RuntimeError):
    def __init__(self, retry_after_seconds: int):
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"llm_circuit_open:{retry_after_seconds}")


@dataclass
class _RuntimeState:
    failure_count: int = 0
    open_until: float = 0.0
    last_error: Optional[str] = None
    last_failure_at: Optional[float] = None
    last_success_at: Optional[float] = None


class LlmRuntimeGuard:
    """Protect model calls and expose an honest local health snapshot."""

    def __init__(
        self,
        failure_threshold: int = 2,
        cooldown_seconds: int = 60,
        clock: Callable[[], float] = time.time,
    ):
        self.failure_threshold = max(1, int(failure_threshold))
        self.cooldown_seconds = max(1, int(cooldown_seconds))
        self.clock = clock
        self._states: Dict[str, _RuntimeState] = {}
        self._lock = threading.Lock()

    def before_request(self, runtime_key: str) -> None:
        now = self.clock()
        with self._lock:
            state = self._states.setdefault(runtime_key, _RuntimeState())
            if state.open_until > now:
                raise LlmCircuitOpen(max(1, math.ceil(state.open_until - now)))
            if state.open_until:
                state.open_until = 0.0

    def record_success(self, runtime_key: str) -> None:
        now = self.clock()
        with self._lock:
            state = self._states.setdefault(runtime_key, _RuntimeState())
            state.failure_count = 0
            state.open_until = 0.0
            state.last_error = None
            state.last_success_at = now

    def record_failure(self, runtime_key: str, error: Any) -> None:
        now = self.clock()
        message = self._safe_error(error)
        with self._lock:
            state = self._states.setdefault(runtime_key, _RuntimeState())
            state.failure_count += 1
            state.last_error = message
            state.last_failure_at = now
            if state.failure_count >= self.failure_threshold:
                state.open_until = now + self.cooldown_seconds

    def health(
        self,
        runtime_key: str,
        configured: bool,
        provider: str,
        model: str,
    ) -> Dict[str, Any]:
        now = self.clock()
        with self._lock:
            state = self._states.setdefault(runtime_key, _RuntimeState())
            circuit_open = configured and state.open_until > now
            retry_after = max(0, math.ceil(state.open_until - now)) if circuit_open else 0
            status = "unconfigured" if not configured else "degraded" if state.failure_count > 0 else "ready"
            return {
                "status": status,
                "configured": bool(configured),
                "provider": provider,
                "model": model,
                "circuit_open": circuit_open,
                "failure_count": state.failure_count,
                "retry_after_seconds": retry_after,
                "last_error": state.last_error,
                "last_failure_at": self._iso(state.last_failure_at),
                "last_success_at": self._iso(state.last_success_at),
                "checked_at": self._iso(now),
            }

    @staticmethod
    def _safe_error(error: Any) -> str:
        message = str(error or "模型请求失败").strip().replace("\n", " ")
        return message[:240]

    @staticmethod
    def _iso(timestamp: Optional[float]) -> Optional[str]:
        if timestamp is None:
            return None
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


_guard = LlmRuntimeGuard()


def get_llm_runtime_guard() -> LlmRuntimeGuard:
    return _guard
