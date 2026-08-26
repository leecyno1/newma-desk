"""Contract smoke test for LLM health state and circuit breaking."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.llm_runtime import LlmCircuitOpen, LlmRuntimeGuard


class FakeClock:
    def __init__(self):
        self.value = 1_000.0

    def __call__(self):
        return self.value


clock = FakeClock()
guard = LlmRuntimeGuard(failure_threshold=2, cooldown_seconds=60, clock=clock)
runtime_key = "siliconflow:https://api.siliconflow.cn"

ready = guard.health(
    runtime_key=runtime_key,
    configured=True,
    provider="siliconflow",
    model="deepseek-ai/DeepSeek-V4-Flash",
)
assert ready["status"] == "ready"
assert ready["configured"] is True
assert ready["circuit_open"] is False

guard.record_failure(runtime_key, "401 Unauthorized")
first_failure = guard.health(runtime_key, True, "siliconflow", "model")
assert first_failure["status"] == "degraded"
assert first_failure["circuit_open"] is False
guard.record_failure(runtime_key, "401 Unauthorized")

degraded = guard.health(runtime_key, True, "siliconflow", "model")
assert degraded["status"] == "degraded"
assert degraded["circuit_open"] is True
assert degraded["failure_count"] == 2
assert degraded["last_error"] == "401 Unauthorized"

try:
    guard.before_request(runtime_key)
except LlmCircuitOpen as error:
    assert error.retry_after_seconds == 60
else:
    raise AssertionError("Open circuits must reject requests")

clock.value += 61
guard.before_request(runtime_key)
guard.record_success(runtime_key)
recovered = guard.health(runtime_key, True, "siliconflow", "model")
assert recovered["status"] == "ready"
assert recovered["failure_count"] == 0
assert recovered["last_success_at"] is not None

unconfigured = guard.health("anthropic", False, "anthropic", "claude")
assert unconfigured["status"] == "unconfigured"
assert unconfigured["configured"] is False

print("OK LLM runtime guard contract")
