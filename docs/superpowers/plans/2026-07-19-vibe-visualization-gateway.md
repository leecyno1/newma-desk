# vibe-visualization Agent and Data Gateway Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an Agent-neutral task gateway, OpenAI-compatible adapter, data-service registry, module action routing, SSE progress, server-side secrets, and browser SDK calls.

**Architecture:** Keep Gateway, Control Plane, and Data Service Registry as focused packages inside the single FastAPI process. Persist task state and audit records in SQLite, stream progress over SSE, and expose a stable adapter interface so Hermes or other external agents can be added without changing modules.

**Tech Stack:** FastAPI, Pydantic 2, SQLite, httpx, SSE, React/TypeScript Module SDK, Pytest, Vitest

---

## File Structure

```text
services/api/vibe_visualization_api/agent_gateway/
├── models.py                  # task and event schemas
├── store.py                   # task persistence
├── event_bus.py               # bounded in-process SSE fan-out
├── service.py                 # routing and adapter orchestration
├── routes.py                  # HTTP/SSE API
└── adapters/
    ├── base.py                # adapter protocol
    └── openai_compatible.py   # first concrete adapter
services/api/vibe_visualization_api/data_services/
├── models.py                  # registered service descriptors
├── registry.py                # service and capability discovery
├── client.py                  # safe HTTP forwarding
└── routes.py                  # discovery and invocation endpoints
packages/module-sdk/src/agent.ts
```

### Task 1: Define Agent task and event contracts

**Files:**
- Create: `services/api/vibe_visualization_api/agent_gateway/models.py`
- Test: `services/api/tests/agent_gateway/test_models.py`

- [ ] **Step 1: Write failing validation tests**

```py
import pytest
from pydantic import ValidationError

from vibe_visualization_api.agent_gateway.models import AdapterEvent, AgentTaskCreate, TaskEvent


def test_agent_task_requires_a_capability_or_prompt() -> None:
    with pytest.raises(ValidationError):
        AgentTaskCreate(module_id="market-daily", prompt="", capability=None)


def test_task_event_has_monotonic_sequence() -> None:
    event = TaskEvent(task_id="task-1", sequence=1, type="progress", data={"message": "loading"})
    assert event.sequence == 1


def test_adapter_event_has_no_persistence_identity() -> None:
    event = AdapterEvent(type="completed", data={"answer": "done"})
    assert event.type == "completed"
```

- [ ] **Step 2: Run the test to verify failure**

Run: `services/api/.venv/bin/pytest services/api/tests/agent_gateway/test_models.py -v`

Expected: FAIL because the models do not exist.

- [ ] **Step 3: Implement the models**

```py
from typing import Any, Literal
from pydantic import BaseModel, Field, model_validator


class AgentTaskCreate(BaseModel):
    module_id: str | None = None
    capability: str | None = None
    prompt: str = ""
    context: dict[str, Any] = Field(default_factory=dict)
    input: dict[str, Any] = Field(default_factory=dict)
    adapter: str | None = None

    @model_validator(mode="after")
    def require_intent(self):
        if not self.prompt.strip() and not self.capability:
            raise ValueError("prompt or capability is required")
        return self


class TaskEvent(BaseModel):
    task_id: str
    sequence: int = Field(ge=1)
    type: Literal["queued", "progress", "artifact", "completed", "failed", "cancelled"]
    data: dict[str, Any] = Field(default_factory=dict)


class AdapterEvent(BaseModel):
    type: Literal["progress", "artifact", "completed", "failed", "cancelled"]
    data: dict[str, Any] = Field(default_factory=dict)


class AgentTask(BaseModel):
    id: str
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    request: AgentTaskCreate
    result: dict[str, Any] | None = None
    error: str | None = None
```

- [ ] **Step 4: Run the tests**

Run: `services/api/.venv/bin/pytest services/api/tests/agent_gateway/test_models.py -v`

Expected: PASS.

- [ ] **Step 5: Commit task contracts**

```bash
git add services/api/vibe_visualization_api/agent_gateway services/api/tests/agent_gateway
git commit -m "feat: define agent task contracts"
```

### Task 2: Implement durable task storage and SSE events

**Files:**
- Create: `services/api/vibe_visualization_api/agent_gateway/store.py`
- Create: `services/api/vibe_visualization_api/agent_gateway/event_bus.py`
- Test: `services/api/tests/agent_gateway/test_store.py`
- Test: `services/api/tests/agent_gateway/test_event_bus.py`

- [ ] **Step 1: Write failing storage tests**

```py
def test_task_store_persists_events_in_order(tmp_path) -> None:
    store = TaskStore(tmp_path / "tasks.db")
    task = store.create(AgentTaskCreate(prompt="explain the move"))
    store.append_event(task.id, "progress", {"message": "loading"})
    store.append_event(task.id, "completed", {"answer": "done"})
    assert [event.sequence for event in store.list_events(task.id)] == [1, 2, 3]
    assert store.get(task.id).status == "completed"
```

The first event is the automatically inserted `queued` event.

- [ ] **Step 2: Run tests to confirm failure**

Run: `services/api/.venv/bin/pytest services/api/tests/agent_gateway/test_store.py -v`

Expected: FAIL because `TaskStore` does not exist.

- [ ] **Step 3: Add SQLite tables and TaskStore**

Add tables `agent_tasks` and `agent_task_events`. Use a foreign key with `ON DELETE CASCADE`, unique `(task_id, sequence)`, UTC ISO timestamps, and JSON payloads. Implement:

```py
class TaskStore:
    def create(self, request: AgentTaskCreate) -> AgentTask: ...
    def get(self, task_id: str) -> AgentTask: ...
    def append_event(self, task_id: str, event_type: str, data: dict[str, object]) -> TaskEvent: ...
    def list_events(self, task_id: str, after: int = 0) -> list[TaskEvent]: ...
    def cancel(self, task_id: str) -> AgentTask: ...
```

Map terminal events to task status in the same transaction.

- [ ] **Step 4: Write and implement the bounded event bus**

Test that one task's subscribers never receive another task's events and that a disconnected subscriber is removed.

Implement:

```py
class TaskEventBus:
    async def subscribe(self, task_id: str) -> asyncio.Queue[TaskEvent]: ...
    async def unsubscribe(self, task_id: str, queue: asyncio.Queue[TaskEvent]) -> None: ...
    async def publish(self, event: TaskEvent) -> None: ...
```

Use queue size 100. If full, discard the oldest `progress` event but never discard a terminal event.

- [ ] **Step 5: Run store and bus tests**

Run: `services/api/.venv/bin/pytest services/api/tests/agent_gateway/test_store.py services/api/tests/agent_gateway/test_event_bus.py -v`

Expected: PASS.

- [ ] **Step 6: Commit task persistence**

```bash
git add services/api/vibe_visualization_api/agent_gateway services/api/tests/agent_gateway
git commit -m "feat: persist and stream agent task events"
```

### Task 3: Define the Agent Adapter protocol and fake adapter

**Files:**
- Create: `services/api/vibe_visualization_api/agent_gateway/adapters/base.py`
- Create: `services/api/tests/agent_gateway/fakes.py`
- Test: `services/api/tests/agent_gateway/test_adapter_contract.py`

- [ ] **Step 1: Write the adapter contract test**

```py
async def test_adapter_streams_progress_and_completion() -> None:
    adapter = FakeAgentAdapter()
    events = [event async for event in adapter.run(AgentTaskCreate(prompt="hello"))]
    assert [event.type for event in events] == ["progress", "completed"]
    assert events[-1].data["answer"] == "fake: hello"
```

- [ ] **Step 2: Define the protocol**

```py
from collections.abc import AsyncIterator
from typing import Protocol


class AgentAdapter(Protocol):
    id: str

    async def capabilities(self) -> list[str]: ...
    async def run(self, request: AgentTaskCreate) -> AsyncIterator[AdapterEvent]: ...
    async def cancel(self, task_id: str) -> None: ...
```

- [ ] **Step 3: Implement `FakeAgentAdapter` for deterministic tests**

Yield a `progress` event and a `completed` event without network access. Use it in every service and route test that is not specifically testing an external adapter.

- [ ] **Step 4: Run tests and commit**

Run: `services/api/.venv/bin/pytest services/api/tests/agent_gateway/test_adapter_contract.py -v`

Expected: PASS.

```bash
git add services/api/vibe_visualization_api/agent_gateway/adapters services/api/tests/agent_gateway
git commit -m "feat: define agent adapter protocol"
```

### Task 4: Implement the OpenAI-compatible adapter

**Files:**
- Modify: `services/api/vibe_visualization_api/config.py`
- Create: `services/api/vibe_visualization_api/agent_gateway/adapters/openai_compatible.py`
- Test: `services/api/tests/agent_gateway/test_openai_adapter.py`
- Create: `.env.example`

- [ ] **Step 1: Add server-only configuration**

```py
class Settings(BaseSettings):
    # existing fields
    agent_default_adapter: str = "openai-compatible"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: str = ""
    openai_model: str = "gpt-5.6"
    agent_timeout_seconds: float = 120.0
```

`.env.example` must list the same variables with an empty API key. Never expose the key through any API response.

- [ ] **Step 2: Write failing HTTP mock tests**

Use `httpx.MockTransport` to assert:

- Request URL ends in `/chat/completions`.
- Authorization header is present server-side.
- Module context and capability are included in the user message.
- A 401 becomes a failed task event with safe text and no key.
- Timeout becomes a failed task event marked `upstream_timeout`.

- [ ] **Step 3: Implement the adapter**

```py
class OpenAICompatibleAdapter:
    id = "openai-compatible"

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None): ...

    async def capabilities(self) -> list[str]:
        return ["chat", "module.explain", "module.generate-view"]

    async def run(self, request: AgentTaskCreate) -> AsyncIterator[AdapterEvent]:
        yield AdapterEvent(type="progress", data={"message": "calling model"})
        # POST a non-streaming MVP request; the Gateway still streams lifecycle events over SSE.
        # Parse choices[0].message.content and yield AdapterEvent(type="completed", data={"answer": content}).
```

Use `httpx.Timeout(settings.agent_timeout_seconds)` and `follow_redirects=False`. Do not allow the request to override `base_url` or API key.

- [ ] **Step 4: Run adapter tests**

Run: `services/api/.venv/bin/pytest services/api/tests/agent_gateway/test_openai_adapter.py -v`

Expected: PASS with no external network calls.

- [ ] **Step 5: Commit the adapter**

```bash
git add .env.example services/api
git commit -m "feat: add OpenAI-compatible agent adapter"
```

### Task 5: Add capability discovery and task routing

**Files:**
- Create: `services/api/vibe_visualization_api/agent_gateway/registry.py`
- Create: `services/api/vibe_visualization_api/agent_gateway/service.py`
- Create: `services/api/vibe_visualization_api/agent_gateway/routes.py`
- Modify: `services/api/vibe_visualization_api/main.py`
- Test: `services/api/tests/agent_gateway/test_routes.py`

- [ ] **Step 1: Write failing route tests**

```py
def test_capability_discovery_lists_adapters_and_module_actions(client) -> None:
    response = client.get("/api/capabilities")
    assert response.status_code == 200
    assert response.json()["adapters"][0]["id"] == "fake"


def test_create_task_returns_202_and_sse_events(client) -> None:
    created = client.post("/api/agent/tasks", json={"prompt": "hello"})
    assert created.status_code == 202
    task_id = created.json()["id"]
    assert client.get(f"/api/agent/tasks/{task_id}").status_code == 200
```

- [ ] **Step 2: Implement adapter registry**

```py
class AgentAdapterRegistry:
    def __init__(self, adapters: list[AgentAdapter], default_id: str): ...
    def get(self, adapter_id: str | None = None) -> AgentAdapter: ...
    async def describe(self) -> list[dict[str, object]]: ...
```

Reject unknown adapters with a domain error mapped to HTTP 400.

- [ ] **Step 3: Implement AgentTaskService**

Create a task, start an `asyncio.Task`, normalize adapter events with the real task ID and monotonic sequences, persist each event, publish it to subscribers, and keep a task handle for cancellation.

- [ ] **Step 4: Implement API routes**

```py
POST /api/agent/tasks                 # 202 with AgentTask
GET  /api/agent/tasks/{task_id}       # current state
GET  /api/agent/tasks/{task_id}/events?after=0  # text/event-stream
POST /api/agent/tasks/{task_id}/cancel
GET  /api/capabilities
```

SSE records must use `id: <sequence>`, `event: <type>`, and JSON `data:`. Replay persisted events after `after`, then subscribe for new events until a terminal event.

- [ ] **Step 5: Run route tests**

Run: `services/api/.venv/bin/pytest services/api/tests/agent_gateway -v`

Expected: PASS.

- [ ] **Step 6: Commit task routing**

```bash
git add services/api/vibe_visualization_api services/api/tests/agent_gateway
git commit -m "feat: expose agent gateway task API"
```

### Task 6: Implement the Data Service Registry and safe client

**Files:**
- Create: `services/api/vibe_visualization_api/data_services/models.py`
- Create: `services/api/vibe_visualization_api/data_services/registry.py`
- Create: `services/api/vibe_visualization_api/data_services/client.py`
- Create: `services/api/vibe_visualization_api/data_services/routes.py`
- Test: `services/api/tests/data_services/test_registry.py`
- Test: `services/api/tests/data_services/test_client.py`

- [ ] **Step 1: Write failing registry and SSRF tests**

```py
def test_registry_discovers_capabilities() -> None:
    registry = DataServiceRegistry([market_service])
    assert registry.capabilities() == ["market.indices", "market.overview"]


@pytest.mark.parametrize("url", [
    "http://169.254.169.254/latest/meta-data",
    "file:///etc/passwd",
    "javascript:alert(1)",
])
def test_client_rejects_unsafe_targets(url) -> None:
    with pytest.raises(UnsafeServiceUrl):
        validate_service_url(url, public_mode=True)
```

- [ ] **Step 2: Define service descriptors**

```py
class DataServiceDescriptor(BaseModel):
    id: str
    base_url: AnyHttpUrl
    health_path: str = "/health"
    transport: Literal["rest", "mcp", "sse", "websocket"]
    capabilities: dict[str, ServiceCapability]
    timeout_seconds: float = Field(default=15, gt=0, le=300)
    auth_secret: str | None = None
```

`ServiceCapability` must declare method, path, input schema name, output schema name, and permission.

- [ ] **Step 3: Implement safe forwarding**

The client must only call registered method/path pairs. Resolve DNS and reject cloud metadata, loopback, link-local, and private ranges in public mode. In local mode, allow only hosts explicitly present in the descriptor allowlist. Set fixed timeouts and do not follow redirects.

- [ ] **Step 4: Expose discovery and invocation routes**

```text
GET  /api/data-services
GET  /api/data-services/capabilities
POST /api/data-services/{service_id}/invoke/{capability_id}
```

Do not accept arbitrary URLs or arbitrary paths from the browser.

- [ ] **Step 5: Run tests and commit**

Run: `services/api/.venv/bin/pytest services/api/tests/data_services -v`

Expected: PASS.

```bash
git add services/api/vibe_visualization_api/data_services services/api/tests/data_services
git commit -m "feat: add safe data service registry"
```

### Task 7: Route module actions through permissions

**Files:**
- Create: `services/api/vibe_visualization_api/control_plane/permissions.py`
- Create: `services/api/vibe_visualization_api/control_plane/actions.py`
- Modify: `services/api/vibe_visualization_api/control_plane/routes.py`
- Test: `services/api/tests/control_plane/test_actions.py`

- [ ] **Step 1: Write failing action authorization tests**

Test these cases:

- Published module can call a declared read capability.
- Undeclared capability returns HTTP 403.
- Disabled module returns HTTP 409.
- `trade.execute` returns HTTP 428 unless `confirmation_token` is present and valid for the same user, module, action, and payload hash.

- [ ] **Step 2: Implement permission decisions**

```py
@dataclass(frozen=True)
class ActionDecision:
    allowed: bool
    reason: str
    requires_confirmation: bool = False


def authorize_action(manifest: dict[str, object], capability: str) -> ActionDecision:
    permissions = set(manifest.get("permissions", []))
    if capability == "trade.execute":
        return ActionDecision("trade.execute" in permissions, "trade confirmation required", True)
    return ActionDecision(capability in set(manifest.get("agentCapabilities", [])), "capability declaration")
```

- [ ] **Step 3: Implement the action route**

`POST /api/modules/{module_id}/actions/{action_id}` loads the published Manifest, authorizes the capability, then routes to an Agent Adapter or Data Service capability declared by the module. Record module ID, user ID, action, payload hash, decision, task ID, and timestamp in the audit table.

- [ ] **Step 4: Run tests and commit**

Run: `services/api/.venv/bin/pytest services/api/tests/control_plane/test_actions.py -v`

Expected: PASS.

```bash
git add services/api/vibe_visualization_api/control_plane services/api/tests/control_plane
git commit -m "feat: authorize module actions"
```

### Task 8: Add Agent and data calls to the browser Module SDK

**Files:**
- Create: `packages/module-sdk/src/agent.ts`
- Create: `packages/module-sdk/src/data.ts`
- Modify: `packages/module-sdk/src/index.ts`
- Test: `packages/module-sdk/src/agent.test.ts`
- Test: `packages/module-sdk/src/data.test.ts`

- [ ] **Step 1: Write failing SDK tests**

```ts
it("creates an agent task and subscribes after the returned task id", async () => {
  const client = createGatewayClient({ baseUrl: "http://localhost:8901" });
  const task = await client.createTask({ moduleId: "market-daily", capability: "market.explain", prompt: "解释异动" });
  expect(task.id).toBe("task-1");
  expect(client.eventsUrl(task.id)).toBe("http://localhost:8901/api/agent/tasks/task-1/events");
});
```

- [ ] **Step 2: Implement typed client methods**

```ts
createTask(input): Promise<AgentTask>
getTask(taskId): Promise<AgentTask>
cancelTask(taskId): Promise<AgentTask>
eventsUrl(taskId, after?): string
invokeModuleAction(moduleId, actionId, input): Promise<AgentTask | unknown>
invokeDataService(serviceId, capabilityId, input): Promise<unknown>
```

Throw `GatewayError` containing HTTP status and safe response detail. Never accept or store model API keys in the SDK.

- [ ] **Step 3: Run all SDK tests and build**

Run:

```bash
npm run test:run -w @vibe-visualization/module-sdk
npm run typecheck -w @vibe-visualization/module-sdk
npm run build
```

Expected: PASS.

- [ ] **Step 4: Commit the Gateway SDK**

```bash
git add packages/module-sdk package-lock.json
git commit -m "feat: expose gateway clients to modules"
```

## Gateway Completion Gate

Do not start the market module plan until:

- Fake adapter task creation, SSE replay, live events, cancellation, and persistence pass.
- OpenAI-compatible adapter tests pass without network access.
- Secrets never appear in API responses or logs.
- Data Service Registry rejects unregistered paths and unsafe URLs.
- Module action permissions and trade confirmation tests pass.
- Module SDK can invoke both Agent tasks and registered data services.
