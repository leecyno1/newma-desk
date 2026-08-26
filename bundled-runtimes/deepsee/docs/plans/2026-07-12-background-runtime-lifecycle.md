# Background Runtime Lifecycle Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Replace fire-and-forget background loop startup with an explicit runtime that owns task handles, starts idempotently, and cancels/awaits every task during FastAPI shutdown.

**Architecture:** Introduce a small `BackgroundRuntime` registry in `app/background.py`. Runtime configuration remains derived from the existing settings and loop functions, while lifecycle ownership moves into named task handles. Keep `start_background_loops()` as a compatibility entry point, add `stop_background_loops()`, attach the runtime to `app.state`, and close it from `app_lifespan` in a `finally` block.

**Tech Stack:** Python 3.11 asyncio, FastAPI lifespan, pytest/pytest-asyncio-compatible tests using `asyncio.run`, existing background runtime snapshot state.

---

## Constraints

- Preserve every existing loop body, interval, enablement rule, runtime name, and health endpoint field.
- Do not add a queue system, scheduler dependency, process supervisor, restart policy, or candidate-1 changes.
- `asyncio.to_thread` work remains best-effort on cancellation; this task owns asyncio task lifecycle, not forcibly terminating worker threads.
- Do not call the auto-reply transaction from retries or broaden retry behavior.
- Do not modify `app/routers/ai.py`, `app/services/hermes_bridge.py`, `static/index.html`, or `static/modules/wechat-sync.js`.
- Do not stage, commit, reset, or write tests to `data/app.db`.

## Task 1: Define lifecycle behavior with failing tests

**Files:**

- Create: `tests/test_background_runtime_lifecycle.py`
- Read: `app/background.py:20-125`
- Read: `app/background.py:285-572`
- Read: `app/main.py:71-79`

**Step 1: Add a controlled loop spec fixture**

Tests should construct a runtime with an injected spec provider rather than enabling production loops. Use a spec shape equivalent to:

```python
BackgroundLoopSpec(
    name="controlled",
    enabled=True,
    runner=controlled_loop,
)
```

The controlled loop should set a `started` event, wait forever, and set a `finished` event from `finally` when cancelled.

**Step 2: Add idempotent start tests**

Verify:

```python
await runtime.start(app)
first = runtime.tasks["controlled"]
await runtime.start(app)

assert runtime.tasks["controlled"] is first
assert starts == 1
assert app.state.background_runtime is runtime
assert first.get_name() == "deepsee-background:controlled"
```

Also verify disabled specs create no task and mark the existing runtime state as disabled.

**Step 3: Add shutdown tests**

Verify shutdown:

```python
await runtime.shutdown()

assert finished.is_set()
assert runtime.tasks == {}
assert background_state["running"] is False
```

Call shutdown twice and require the second call to be a no-op. Verify a task that has already completed can be recreated by a later `start()` call.

**Step 4: Add FastAPI lifespan tests**

Monkeypatch `app.main.start_background_loops` and `app.main.stop_background_loops`; enter `app_lifespan(app)` directly. Require `stop_background_loops` to run:

- after a normal context exit;
- after an exception raised inside the lifespan context.

**Step 5: Run the new tests and confirm RED**

Run:

```bash
pytest -q tests/test_background_runtime_lifecycle.py
```

Expected: fail because `BackgroundLoopSpec`, `BackgroundRuntime`, `stop_background_loops`, task ownership, and lifespan shutdown do not yet exist.

## Task 2: Add explicit task ownership in `app/background.py`

**Files:**

- Modify: `app/background.py:1-125`
- Modify: `app/background.py:522-572`
- Test: `tests/test_background_runtime_lifecycle.py`

**Step 1: Define the loop spec**

Add an immutable dataclass:

```python
@dataclass(frozen=True)
class BackgroundLoopSpec:
    name: str
    enabled: bool
    runner: Callable[[], Awaitable[None]]
```

**Step 2: Centralize existing enablement decisions**

Create `_build_background_loop_specs()` that returns one spec for every name in `_BACKGROUND_RUNTIME_NAMES`. Preserve current rules exactly:

```text
chatlog_sync             SYNC_INTERVAL_SECONDS > 0
wechat8061_sync          ai config wechatpad_sync_enabled
email_sync               always disabled/manual-only
ext_adapter_sync         LANGBOT_ADAPTER_LOG_DIR configured
news_refresh             NEWSNOW_REFRESH_INTERVAL_SECONDS > 0
news_snapshot            NEWS_SNAPSHOT_INTERVAL_SECONDS > 0
media_collector          MEDIA_COLLECTOR_DAILY_ENABLED
summary_overlay          SUMMARY_OVERLAY_INTERVAL_SECONDS > 0
aggregation_retention    AGGREGATION_RETENTION_INTERVAL_SECONDS > 0
media_cache_cleanup      MEDIA_CACHE_CLEANUP_ENABLED and interval > 0
```

Disabled specs may use their real runner because the runtime must not instantiate or schedule them.

**Step 3: Implement `BackgroundRuntime`**

Required API:

```python
class BackgroundRuntime:
    def __init__(self, spec_provider=_build_background_loop_specs): ...

    @property
    def tasks(self) -> dict[str, asyncio.Task[None]]:
        return dict(self._tasks)

    async def start(self, app: FastAPI | None = None) -> "BackgroundRuntime": ...

    async def shutdown(self) -> None: ...
```

Start behavior:

- attach `self` to `app.state.background_runtime` when an app is supplied;
- mark every spec enabled/disabled through `_bg_mark_enabled`;
- prune completed handles;
- create one named task only when the spec is enabled and no live task exists;
- add a done callback that removes only the matching handle and clears stale `running` state;
- never instantiate coroutine objects for disabled specs.

Shutdown behavior:

- snapshot all owned tasks;
- call `cancel()` on every live task;
- `await asyncio.gather(*tasks, return_exceptions=True)` so cancellation is drained and no “Task was destroyed” warning remains;
- clear matching handles and set their runtime `running` flags to false;
- be safe when called with no tasks or called repeatedly.

Do not catch `asyncio.CancelledError` as a loop failure or increment failure counters.

**Step 4: Keep compatibility functions**

Create one singleton and wrappers:

```python
BACKGROUND_TASK_RUNTIME = BackgroundRuntime()

async def start_background_loops(app: FastAPI | None = None) -> BackgroundRuntime:
    return await BACKGROUND_TASK_RUNTIME.start(app)

async def stop_background_loops(app: FastAPI | None = None) -> None:
    runtime = getattr(getattr(app, "state", None), "background_runtime", None)
    await (runtime or BACKGROUND_TASK_RUNTIME).shutdown()
```

## Task 3: Close the runtime from FastAPI lifespan

**Files:**

- Modify: `app/main.py:11`
- Modify: `app/main.py:71-75`
- Test: `tests/test_background_runtime_lifecycle.py`

**Step 1: Import the stop function**

```python
from .background import start_background_loops, stop_background_loops
```

**Step 2: Use `try/finally` around the lifespan body**

```python
@asynccontextmanager
async def app_lifespan(app: FastAPI):
    await start_background_loops(app)
    try:
        yield
    finally:
        await stop_background_loops(app)
```

Do not swallow shutdown exceptions silently; tests should expose them.

## Task 4: Regression and lifecycle verification

**Files:**

- Test: `tests/test_background_runtime_lifecycle.py`
- Test: `tests/test_production_guardrails.py`
- Test: `tests/test_background_summary_overlay.py`
- Test: `tests/test_sync_run_orchestration.py`
- Test: `tests/test_commercial_readiness.py`

**Step 1: Run focused tests**

Run with a temporary `DATABASE_URL`:

```bash
pytest -q \
  tests/test_background_runtime_lifecycle.py \
  tests/test_background_summary_overlay.py \
  tests/test_sync_run_orchestration.py \
  tests/test_commercial_readiness.py \
  tests/test_production_guardrails.py
```

**Step 2: Verify cancellation hygiene**

Run the lifecycle tests with asyncio debug enabled:

```bash
PYTHONASYNCIODEBUG=1 pytest -q tests/test_background_runtime_lifecycle.py
```

Expected: no pending-task or un-awaited-coroutine warnings.

**Step 3: Verify syntax and protected files**

Run:

```bash
python -m py_compile app/background.py app/main.py tests/test_background_runtime_lifecycle.py
git diff --check -- app/background.py app/main.py tests/test_background_runtime_lifecycle.py
```

Confirm the following protected files retain their pre-task content:

```text
app/routers/ai.py
app/services/hermes_bridge.py
static/index.html
static/modules/wechat-sync.js
```

The working tree must remain unstaged and uncommitted.

