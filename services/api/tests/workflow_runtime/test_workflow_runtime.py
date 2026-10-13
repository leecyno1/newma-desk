from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import json
import time
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from tests.agent_gateway.fakes import FakeAgentAdapter
from vibe_visualization_api.config import Settings
from vibe_visualization_api.data_services.models import (
    DataServiceDescriptor,
    ServiceCapability,
)
from vibe_visualization_api.main import create_app
from vibe_visualization_api.workflow_control.models import (
    WorkflowPrincipalCreate,
    WorkflowRunCreate,
    WorkflowTemplateCreate,
)
from vibe_visualization_api.workflow_control.service import WorkflowControlService
from vibe_visualization_api.workflow_runtime.adapters import (
    AgentRuntimeNodeExecutionAdapter,
    NodeExecutionAdapterRegistry,
    NodeExecutionContext,
    NodeExecutionResult,
)
from vibe_visualization_api.workflow_runtime.conditions import (
    ConditionExpressionError,
    evaluate_condition,
)
from vibe_visualization_api.workflow_runtime.engine import WorkflowRuntimeEngine
from vibe_visualization_api.workflow_runtime.http_capability import (
    HttpCapabilityNodeExecutionAdapter,
)
from vibe_visualization_api.workflow_runtime.remote_agent import (
    RemoteServerAgentNodeExecutionAdapter,
)
from vibe_visualization_api.workflow_runtime.signing import WorkflowRequestSigner


class MutableClock:
    def __init__(self):
        self.value = datetime(2026, 8, 31, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.value

    def advance(self, seconds: int) -> None:
        self.value += timedelta(seconds=seconds)


class FlakyAdapter:
    id = "flaky"

    def __init__(self):
        self.calls = 0

    def execute(
        self,
        context: NodeExecutionContext,
        parameters: dict[str, Any],
    ) -> NodeExecutionResult:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("temporary failure")
        return NodeExecutionResult(output={"calls": self.calls})


class SlowOnceAdapter:
    id = "slow_once"

    def __init__(self, clock: MutableClock):
        self.clock = clock
        self.calls = 0

    def execute(
        self,
        context: NodeExecutionContext,
        parameters: dict[str, Any],
    ) -> NodeExecutionResult:
        self.calls += 1
        if self.calls == 1:
            self.clock.advance(2)
        return NodeExecutionResult(output={"calls": self.calls})


class FakeAgentTaskPort:
    def __init__(self):
        self.requests: list[dict[str, Any]] = []
        self.cancelled: list[str] = []
        self.gets = 0

    def create_task(
        self,
        *,
        user_id: str,
        workspace_id: str,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        self.requests.append(
            {"userId": user_id, "workspaceId": workspace_id, **request}
        )
        return {
            "id": "agent-task-1",
            "status": "queued",
            "request": {"adapter": "fake"},
        }

    def get_task(self, task_id: str) -> dict[str, Any]:
        self.gets += 1
        return {
            "id": task_id,
            "status": "completed",
            "request": {"adapter": "fake"},
            "result": {"answer": "done"},
        }

    def cancel_task(self, task_id: str) -> dict[str, Any]:
        self.cancelled.append(task_id)
        return {"id": task_id, "status": "cancelled", "request": {}}


class FakeHttpCapabilityPort:
    def __init__(self):
        self.calls: list[dict[str, Any]] = []

    def invoke(self, **request: Any) -> dict[str, Any]:
        self.calls.append(request)
        return {
            "capabilityId": request["capability_id"],
            "serviceId": request["service_id"] or "default-service",
            "permission": "market.read",
            "data": {"ok": True, **request["input_data"]},
        }


class FakeWorkflowDataServiceClient:
    def __init__(self):
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    async def invoke(
        self,
        service: DataServiceDescriptor,
        capability_id: str,
        input_data: dict[str, Any],
    ) -> dict[str, Any]:
        self.calls.append((service.id, capability_id, input_data))
        return {"accepted": True, "input": input_data}


def setup_runtime(
    database_path: Path,
    *,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]] | None = None,
    clock: MutableClock | None = None,
    adapters: list[Any] | None = None,
):
    control = WorkflowControlService(database_path)
    owner = control.identity(organization_id="org-1", user_id="owner")["id"]
    template = control.create_template(
        organization_id="org-1",
        actor_principal_id=owner,
        request=WorkflowTemplateCreate(
            name="Runtime test",
            nodes=nodes,
            edges=edges or [],
        ),
    )
    run = control.create_run(
        organization_id="org-1",
        actor_principal_id=owner,
        request=WorkflowRunCreate(template_id=template["id"], title="Runtime run"),
    )
    engine = WorkflowRuntimeEngine(
        database_path,
        control,
        adapters=NodeExecutionAdapterRegistry(adapters),
        clock=clock or MutableClock(),
    )
    return control, engine, owner, run


def start(engine: WorkflowRuntimeEngine, owner: str, run: dict[str, Any], **kwargs):
    return engine.start(
        organization_id="org-1",
        actor_principal_id=owner,
        run_id=run["id"],
        trigger_type="manual",
        idempotency_key=kwargs.pop("idempotency_key", "runtime-once"),
        input_payload=kwargs.pop("input_payload", {}),
        **kwargs,
    )


def test_condition_interpreter_supports_paths_without_eval():
    context = {
        "run": {"status": "active"},
        "data": {"source": {"score": 3}},
        "enabled": True,
    }
    assert evaluate_condition(
        "enabled and data.source.score >= 3 and run.status == 'active'",
        context,
    )
    with pytest.raises(ConditionExpressionError):
        evaluate_condition("__import__('os').system('echo unsafe')", context)


def test_runtime_executes_condition_edges_and_persists_adapter_output(tmp_path: Path):
    control, engine, owner, run = setup_runtime(
        tmp_path / "workflow.db",
        nodes=[
            {
                "id": "source",
                "name": "Source",
                "roleKey": "owner",
                "executorId": "noop",
                "executorParameters": {"score": 3},
            },
            {
                "id": "target",
                "name": "Target",
                "roleKey": "owner",
                "executorId": "data_transform",
                "executorParameters": {
                    "mapping": {"score": "data.source.runtimeOutput.score"}
                },
            },
        ],
        edges=[
            {
                "source": "source",
                "target": "target",
                "kind": "condition",
                "condition": "data.source.runtimeOutput.score >= minimum",
                "parameters": {"minimum": 3},
            }
        ],
    )

    execution = start(engine, owner, run)

    assert execution["status"] == "completed"
    assert [(job["nodeId"], job["status"]) for job in execution["jobs"]] == [
        ("source", "completed"),
        ("target", "completed"),
    ]
    assert execution["jobs"][1]["result"] == {"score": 3}
    data = control.repository.list_node_data("org-1", run["id"])
    assert any(
        item["nodeId"] == "source"
        and item["slotKey"] == "runtimeOutput"
        and item["payload"]["score"] == 3
        for item in data
    )


def test_agent_handoff_preserves_requested_target(tmp_path: Path):
    _control, engine, owner, run = setup_runtime(
        tmp_path / "workflow.db",
        nodes=[
            {
                "id": "handoff",
                "name": "Handoff",
                "roleKey": "owner",
                "executorId": "agent_handoff",
                "executorParameters": {
                    "principalId": "agent-reviewer",
                    "instruction": "review the result",
                },
            }
        ],
    )

    execution = start(engine, owner, run)

    assert execution["jobs"][0]["result"]["handoff"] == {
        "status": "requested",
        "targetPrincipalId": "agent-reviewer",
        "instruction": "review the result",
        "executionId": execution["id"],
        "nodeId": "handoff",
    }


def test_false_condition_skips_downstream_and_idempotency_returns_same_execution(
    tmp_path: Path,
):
    _control, engine, owner, run = setup_runtime(
        tmp_path / "workflow.db",
        nodes=[
            {
                "id": "source",
                "name": "Source",
                "roleKey": "owner",
                "executorId": "noop",
            },
            {
                "id": "target",
                "name": "Target",
                "roleKey": "owner",
                "executorId": "noop",
            },
        ],
        edges=[
            {
                "source": "source",
                "target": "target",
                "kind": "condition",
                "condition": "enabled == True",
                "parameters": {"enabled": False},
            }
        ],
    )

    first = start(engine, owner, run, idempotency_key="same-trigger")
    second = start(engine, owner, run, idempotency_key="same-trigger")

    assert first["id"] == second["id"]
    assert first["status"] == "completed"
    assert first["jobs"][1]["status"] == "skipped"
    assert len(engine.list("org-1", run["id"])) == 1


def test_retry_wait_recovers_after_adapter_failure(tmp_path: Path):
    clock = MutableClock()
    flaky = FlakyAdapter()
    _control, engine, owner, run = setup_runtime(
        tmp_path / "workflow.db",
        nodes=[
            {
                "id": "work",
                "name": "Work",
                "roleKey": "owner",
                "executorId": "flaky",
                "retryLimit": 1,
                "retryDelaySeconds": 5,
            }
        ],
        clock=clock,
        adapters=[flaky],
    )

    first = start(engine, owner, run)
    assert first["status"] == "running"
    assert first["jobs"][0]["status"] == "retry_wait"
    clock.advance(5)
    completed = engine.tick(
        organization_id="org-1",
        execution_id=first["id"],
    )
    assert completed["status"] == "completed"
    assert completed["jobs"][0]["attempt"] == 2
    assert flaky.calls == 2


def test_timeout_enters_retry_and_succeeds_on_next_attempt(tmp_path: Path):
    clock = MutableClock()
    adapter = SlowOnceAdapter(clock)
    _control, engine, owner, run = setup_runtime(
        tmp_path / "workflow.db",
        nodes=[
            {
                "id": "slow",
                "name": "Slow",
                "roleKey": "owner",
                "executorId": "slow_once",
                "retryLimit": 1,
                "retryDelaySeconds": 5,
                "timeoutSeconds": 1,
            }
        ],
        clock=clock,
        adapters=[adapter],
    )

    first = start(engine, owner, run)
    assert first["jobs"][0]["status"] == "retry_wait"
    assert first["jobs"][0]["error"]["type"] == "TimeoutError"
    clock.advance(5)
    completed = engine.tick(
        organization_id="org-1",
        execution_id=first["id"],
    )
    assert completed["status"] == "completed"
    assert completed["jobs"][0]["attempt"] == 2


def test_agent_runtime_job_polls_existing_gateway_task_without_new_attempt(
    tmp_path: Path,
):
    port = FakeAgentTaskPort()
    adapter = AgentRuntimeNodeExecutionAdapter(port)
    _control, engine, owner, run = setup_runtime(
        tmp_path / "workflow.db",
        nodes=[
            {
                "id": "agent-work",
                "name": "Agent Work",
                "description": "Analyze the workflow input",
                "roleKey": "owner",
                "executorId": "agent_runtime",
                "executorParameters": {"mode": "research"},
            }
        ],
        adapters=[adapter],
    )

    waiting = start(engine, owner, run, user_id="workflow-user")

    assert waiting["status"] == "running"
    assert waiting["jobs"][0]["status"] == "waiting"
    assert waiting["jobs"][0]["result"]["agentTaskId"] == "agent-task-1"
    completed = engine.tick(
        organization_id="org-1",
        execution_id=waiting["id"],
    )
    assert completed["status"] == "completed"
    assert completed["jobs"][0]["attempt"] == 1
    assert completed["jobs"][0]["result"]["output"] == {"answer": "done"}
    assert port.requests[0]["userId"] == "workflow-user"
    assert port.requests[0]["profile"] == "deep"


def test_remote_server_agent_adapter_signs_and_polls_same_task(tmp_path: Path):
    secret = "remote-agent-test-secret"
    signer = WorkflowRequestSigner(secret)
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = request.content
        signer.verify(
            timestamp=request.headers["X-Newma-Agent-Timestamp"],
            signature=request.headers["X-Newma-Agent-Signature"],
            scope=(
                "remote-agent:org-1:"
                f"{request.method}:{request.url.path}"
            ),
            body=body,
        )
        assert request.headers["X-Workspace-Id"] == "org-1"
        if request.method == "POST":
            payload = json.loads(body)
            assert payload["userId"] == "workflow-user"
            assert payload["workspaceId"] == "org-1"
            assert payload["request"]["userId"] == "workflow-user"
            assert payload["request"]["context"]["workflow"]["organizationId"] == "org-1"
            return httpx.Response(
                202,
                json={"id": "remote-task-1", "status": "queued"},
            )
        return httpx.Response(
            200,
            json={
                "id": "remote-task-1",
                "status": "completed",
                "result": {"answer": "remote done"},
            },
        )

    control, engine, owner, run = setup_runtime(
        tmp_path / "workflow.db",
        nodes=[
            {
                "id": "remote-work",
                "name": "Remote work",
                "roleKey": "owner",
                "executorId": "server_agent",
                "executorParameters": {
                    "principalId": "agent:remote",
                    "prompt": "analyze remotely",
                },
            }
        ],
    )
    control.create_principal(
        organization_id="org-1",
        actor_principal_id=owner,
        request=WorkflowPrincipalCreate(
            principal_id="agent:remote",
            kind="server_agent",
            name="Remote Agent",
            endpoint="http://agent.example",
            capabilities=["workflow.execute"],
        ),
    )
    client = httpx.Client(transport=httpx.MockTransport(handle))
    engine.adapters = NodeExecutionAdapterRegistry(
        [
            RemoteServerAgentNodeExecutionAdapter(
                control,
                secret=secret,
                allowed_hosts="agent.example",
                client=client,
            )
        ]
    )

    waiting = start(engine, owner, run, user_id="workflow-user")
    assert waiting["jobs"][0]["status"] == "waiting"
    completed = engine.tick(
        organization_id="org-1",
        execution_id=waiting["id"],
    )

    assert completed["status"] == "completed"
    assert completed["jobs"][0]["attempt"] == 1
    assert completed["jobs"][0]["result"]["output"] == {
        "answer": "remote done"
    }
    assert [request.method for request in requests] == ["POST", "GET"]
    client.close()


def test_agent_runtime_waits_for_required_human_review(tmp_path: Path):
    port = FakeAgentTaskPort()
    adapter = AgentRuntimeNodeExecutionAdapter(port)
    control, engine, owner, run = setup_runtime(
        tmp_path / "workflow.db",
        nodes=[
            {
                "id": "reviewed-agent-work",
                "name": "Reviewed Agent Work",
                "roleKey": "owner",
                "requiresReview": True,
                "executorId": "agent_runtime",
            }
        ],
        adapters=[adapter],
    )
    waiting = start(engine, owner, run)
    reviewed = engine.tick(
        organization_id="org-1",
        execution_id=waiting["id"],
    )

    assert reviewed["jobs"][0]["status"] == "waiting"
    assert control.repository.get_run("org-1", run["id"])["nodes"][0]["status"] == "waiting_review"
    unchanged = engine.tick(
        organization_id="org-1",
        execution_id=waiting["id"],
    )
    assert unchanged["jobs"][0]["status"] == "waiting"
    assert port.gets == 1


def test_http_capability_adapter_maps_workflow_input_and_rejects_url_override():
    port = FakeHttpCapabilityPort()
    adapter = HttpCapabilityNodeExecutionAdapter(port)
    context = NodeExecutionContext(
        organization_id="org-1",
        execution_id="execution-1",
        user_id="user-1",
        run={"id": "run-1"},
        node={"id": "node-1"},
        job={"timeoutSeconds": 30},
        input={"symbol": "600000"},
        data={},
        artifacts={},
        results={},
    )

    result = adapter.execute(
        context,
        {
            "capabilityId": "market.quote",
            "input": {"market": "CN"},
            "mapping": {"symbol": "input.symbol"},
        },
    )

    assert result.output["data"]["symbol"] == "600000"
    assert port.calls[0]["input_data"] == {
        "market": "CN",
        "symbol": "600000",
    }
    with pytest.raises(ValueError, match="does not accept parameters"):
        adapter.execute(
            context,
            {
                "capabilityId": "market.quote",
                "url": "http://169.254.169.254/latest/meta-data",
            },
        )
    assert len(port.calls) == 1


def test_pause_resume_cancel_and_restart_recovery(tmp_path: Path):
    database_path = tmp_path / "workflow.db"
    control, engine, owner, run = setup_runtime(
        database_path,
        nodes=[
            {
                "id": "work",
                "name": "Work",
                "roleKey": "owner",
                "executorId": "noop",
            }
        ],
    )
    execution = start(engine, owner, run, dispatch=False)
    paused = engine.pause(
        organization_id="org-1",
        execution_id=execution["id"],
        reason="inspect",
    )
    assert paused["status"] == "paused"
    assert engine.tick(
        organization_id="org-1",
        execution_id=execution["id"],
    )["jobs"][0]["status"] == "pending"

    restarted = WorkflowRuntimeEngine(database_path, control)
    completed = restarted.resume(
        organization_id="org-1",
        execution_id=execution["id"],
    )
    assert completed["status"] == "completed"

    second_run = control.create_run(
        organization_id="org-1",
        actor_principal_id=owner,
        request=WorkflowRunCreate(
            template_id=run["templateId"],
            title="Cancelled run",
        ),
    )
    cancellable = start(
        restarted,
        owner,
        second_run,
        idempotency_key="cancel-once",
        dispatch=False,
    )
    cancelled = restarted.cancel(
        organization_id="org-1",
        execution_id=cancellable["id"],
        reason="stop",
    )
    assert cancelled["status"] == "cancelled"
    assert cancelled["jobs"][0]["status"] == "cancelled"
    assert control.repository.get_run("org-1", second_run["id"])["status"] == "cancelled"


def test_event_and_schedule_triggers_create_new_run_instances(tmp_path: Path):
    clock = MutableClock()
    control, engine, owner, source_run = setup_runtime(
        tmp_path / "workflow.db",
        nodes=[
            {
                "id": "work",
                "name": "Work",
                "roleKey": "owner",
                "executorId": "noop",
            }
        ],
        clock=clock,
    )
    event_trigger = engine.create_trigger(
        organization_id="org-1",
        actor_principal_id=owner,
        run_id=source_run["id"],
        trigger_type="event",
        event_type="research.ready",
        interval_seconds=None,
        input_payload={"source": "event"},
        user_id="owner",
    )
    schedule_trigger = engine.create_trigger(
        organization_id="org-1",
        actor_principal_id=owner,
        run_id=source_run["id"],
        trigger_type="schedule",
        event_type=None,
        interval_seconds=60,
        input_payload={"source": "schedule"},
        user_id="owner",
    )

    event_execution = engine.emit_event(
        organization_id="org-1",
        event_type="research.ready",
        idempotency_key="event-1",
        input_payload={"recordId": "record-1"},
    )[0]
    duplicate = engine.emit_event(
        organization_id="org-1",
        event_type="research.ready",
        idempotency_key="event-1",
        input_payload={"recordId": "record-1"},
    )[0]

    assert event_execution["id"] == duplicate["id"]
    assert event_execution["runId"] != source_run["id"]
    assert event_execution["input"]["triggerId"] == event_trigger["id"]
    assert engine.tick(
        organization_id="org-1",
        execution_id=event_execution["id"],
    )["status"] == "completed"

    clock.advance(60)
    schedule_execution = engine.dispatch_due_schedules()[0]
    assert schedule_execution["runId"] not in {
        source_run["id"],
        event_execution["runId"],
    }
    assert schedule_execution["input"]["triggerId"] == schedule_trigger["id"]
    assert control.repository.get_run(
        "org-1", schedule_execution["runId"]
    )["status"] == "active"


def test_cron_trigger_uses_declared_timezone_and_validates_expression(tmp_path: Path):
    clock = MutableClock()
    _control, engine, owner, source_run = setup_runtime(
        tmp_path / "workflow.db",
        nodes=[
            {
                "id": "work",
                "name": "Work",
                "roleKey": "owner",
                "executorId": "noop",
            }
        ],
        clock=clock,
    )

    trigger = engine.create_trigger(
        organization_id="org-1",
        actor_principal_id=owner,
        run_id=source_run["id"],
        trigger_type="schedule",
        event_type=None,
        interval_seconds=None,
        cron_expression="0 9 * * 1-5",
        timezone="Asia/Shanghai",
        input_payload={},
        user_id="owner",
    )

    assert trigger["cronExpression"] == "0 9 * * 1-5"
    assert trigger["timezone"] == "Asia/Shanghai"
    assert trigger["nextFireAt"] == "2026-08-31T01:00:00+00:00"
    with pytest.raises(ValueError, match="invalid workflow schedule"):
        engine.create_trigger(
            organization_id="org-1",
            actor_principal_id=owner,
            run_id=source_run["id"],
            trigger_type="schedule",
            event_type=None,
            interval_seconds=None,
            cron_expression="not a cron",
            timezone="Asia/Shanghai",
            input_payload={},
            user_id="owner",
        )


def test_workflow_runtime_routes_start_and_return_idempotent_execution(client):
    headers = {"X-User-Id": "runtime-owner", "X-Workspace-Id": "runtime-org"}
    control = client.app.state.workflow_control_service
    owner = control.identity(organization_id="runtime-org", user_id="runtime-owner")["id"]
    template = control.create_template(
        organization_id="runtime-org",
        actor_principal_id=owner,
        request=WorkflowTemplateCreate(
            name="Route runtime",
            nodes=[
                {
                    "id": "route-work",
                    "name": "Route work",
                    "roleKey": "owner",
                    "executorId": "noop",
                }
            ],
        ),
    )
    run = control.create_run(
        organization_id="runtime-org",
        actor_principal_id=owner,
        request=WorkflowRunCreate(template_id=template["id"], title="Route run"),
    )
    path = f"/api/workflows/runtime/runs/{run['id']}/executions"
    first = client.post(
        path,
        headers=headers,
        json={"idempotencyKey": "route-trigger", "triggerType": "api"},
    )
    second = client.post(
        path,
        headers=headers,
        json={"idempotencyKey": "route-trigger", "triggerType": "api"},
    )

    assert first.status_code == 201
    assert first.json()["status"] in {"queued", "running", "completed"}
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]

    execution = second.json()
    deadline = time.monotonic() + 2
    while execution["status"] in {"queued", "running"} and time.monotonic() < deadline:
        time.sleep(0.02)
        execution = client.get(
            f"/api/workflows/runtime/executions/{execution['id']}",
            headers=headers,
        ).json()
    assert execution["status"] == "completed"


def test_workflow_runtime_event_route_dispatches_persistent_trigger(client):
    headers = {"X-User-Id": "event-owner", "X-Workspace-Id": "event-org"}
    control = client.app.state.workflow_control_service
    owner = control.identity(organization_id="event-org", user_id="event-owner")["id"]
    template = control.create_template(
        organization_id="event-org",
        actor_principal_id=owner,
        request=WorkflowTemplateCreate(
            name="Event runtime",
            nodes=[
                {
                    "id": "event-work",
                    "name": "Event work",
                    "roleKey": "owner",
                    "executorId": "noop",
                }
            ],
        ),
    )
    source_run = control.create_run(
        organization_id="event-org",
        actor_principal_id=owner,
        request=WorkflowRunCreate(
            template_id=template["id"],
            title="Event blueprint",
        ),
    )
    created_trigger = client.post(
        f"/api/workflows/runtime/runs/{source_run['id']}/triggers",
        headers=headers,
        json={"triggerType": "event", "eventType": "research.ready"},
    )
    assert created_trigger.status_code == 201

    published = client.post(
        "/api/workflows/runtime/events/research.ready",
        headers=headers,
        json={"idempotencyKey": "research-record-1", "input": {"recordId": "1"}},
    )
    duplicate = client.post(
        "/api/workflows/runtime/events/research.ready",
        headers=headers,
        json={"idempotencyKey": "research-record-1", "input": {"recordId": "1"}},
    )
    assert published.status_code == 202
    execution = published.json()["executions"][0]
    assert duplicate.json()["executions"][0]["id"] == execution["id"]
    assert execution["runId"] != source_run["id"]

    deadline = time.monotonic() + 2
    while execution["status"] in {"queued", "running"} and time.monotonic() < deadline:
        time.sleep(0.02)
        execution = client.get(
            f"/api/workflows/runtime/executions/{execution['id']}",
            headers=headers,
        ).json()
    assert execution["status"] == "completed"
    assert control.repository.get_run("event-org", source_run["id"])["status"] == "active"


def test_signed_webhook_verifies_body_scope_and_replay_idempotency(tmp_path: Path):
    secret = "workflow-webhook-test-secret"
    settings = Settings(
        runtime_dir=tmp_path,
        database_path=tmp_path / "workflow-webhook.db",
        workflow_webhook_secret=secret,
    )
    application = create_app(settings)
    with TestClient(application) as client:
        headers = {"X-User-Id": "owner", "X-Workspace-Id": "webhook-org"}
        control = client.app.state.workflow_control_service
        owner = control.identity(organization_id="webhook-org", user_id="owner")["id"]
        template = control.create_template(
            organization_id="webhook-org",
            actor_principal_id=owner,
            request=WorkflowTemplateCreate(
                name="Webhook runtime",
                nodes=[
                    {
                        "id": "webhook-work",
                        "name": "Webhook work",
                        "roleKey": "owner",
                        "executorId": "noop",
                    }
                ],
            ),
        )
        source_run = control.create_run(
            organization_id="webhook-org",
            actor_principal_id=owner,
            request=WorkflowRunCreate(
                template_id=template["id"],
                title="Webhook blueprint",
            ),
        )
        trigger = client.post(
            f"/api/workflows/runtime/runs/{source_run['id']}/triggers",
            headers=headers,
            json={"triggerType": "event", "eventType": "research.ready"},
        )
        assert trigger.status_code == 201

        body = json.dumps(
            {"idempotencyKey": "signed-event-1", "input": {"recordId": "1"}},
            separators=(",", ":"),
        ).encode()
        timestamp = str(int(time.time()))
        signature = WorkflowRequestSigner(secret).sign(
            timestamp=timestamp,
            scope="webhook:webhook-org:research.ready",
            body=body,
        )
        webhook_headers = {
            "Content-Type": "application/json",
            "X-Workspace-Id": "webhook-org",
            "X-Newma-Webhook-Timestamp": timestamp,
            "X-Newma-Webhook-Signature": signature,
        }
        first = client.post(
            "/api/workflows/runtime/webhooks/events/research.ready",
            headers=webhook_headers,
            content=body,
        )
        duplicate = client.post(
            "/api/workflows/runtime/webhooks/events/research.ready",
            headers=webhook_headers,
            content=body,
        )

        assert first.status_code == 202
        assert duplicate.status_code == 202
        assert first.json()["executions"][0]["id"] == duplicate.json()["executions"][0]["id"]
        rejected = client.post(
            "/api/workflows/runtime/webhooks/events/research.ready",
            headers={
                **webhook_headers,
                "X-Workspace-Id": "another-workspace",
            },
            content=body,
        )
        assert rejected.status_code == 401


def test_signed_webhook_requires_configured_secret(client):
    body = b'{"idempotencyKey":"signed-event-1","input":{}}'
    response = client.post(
        "/api/workflows/runtime/webhooks/events/research.ready",
        headers={
            "Content-Type": "application/json",
            "X-Workspace-Id": "webhook-org",
            "X-Newma-Webhook-Timestamp": str(int(time.time())),
            "X-Newma-Webhook-Signature": f"sha256={'0' * 64}",
        },
        content=body,
    )
    assert response.status_code == 503


def test_remote_agent_routes_verify_signature_and_isolate_workspace(tmp_path: Path):
    secret = "remote-agent-route-secret"
    fake = FakeAgentAdapter()
    settings = Settings(
        runtime_dir=tmp_path,
        database_path=tmp_path / "remote-agent-route.db",
        agent_default_adapter=fake.id,
        workflow_server_agent_secret=secret,
    )
    application = create_app(settings, agent_adapters=[fake])
    signer = WorkflowRequestSigner(secret)

    def signed_headers(
        workspace_id: str,
        method: str,
        path: str,
        body: bytes = b"",
    ) -> dict[str, str]:
        timestamp = str(int(time.time()))
        return {
            "Content-Type": "application/json",
            "X-Workspace-Id": workspace_id,
            "X-Newma-Agent-Timestamp": timestamp,
            "X-Newma-Agent-Signature": signer.sign(
                timestamp=timestamp,
                scope=f"remote-agent:{workspace_id}:{method}:{path}",
                body=body,
            ),
        }

    path = "/api/workflows/runtime/remote-agent/tasks"
    body = json.dumps(
        {
            "userId": "remote-user",
            "workspaceId": "remote-org",
            "request": {
                "userId": "remote-user",
                "moduleId": "workflow-runs",
                "capability": "module.analyze",
                "profile": "deep",
                "prompt": "execute remote node",
                "context": {
                    "workflow": {"organizationId": "tampered-workspace"}
                },
            },
        },
        separators=(",", ":"),
    ).encode()
    with TestClient(application) as client:
        created = client.post(
            path,
            headers=signed_headers("remote-org", "POST", path, body),
            content=body,
        )
        assert created.status_code == 202
        task = created.json()
        task_path = f"{path}/{task['id']}"

        other_workspace = client.get(
            task_path,
            headers=signed_headers("another-org", "GET", task_path),
        )
        assert other_workspace.status_code == 404

        response = task
        deadline = time.monotonic() + 2
        while response["status"] in {"queued", "running"} and time.monotonic() < deadline:
            time.sleep(0.02)
            polled = client.get(
                task_path,
                headers=signed_headers("remote-org", "GET", task_path),
            )
            assert polled.status_code == 200
            response = polled.json()
        assert response["status"] == "completed"
        assert response["request"]["context"]["workflow"]["organizationId"] == "remote-org"

        rejected = client.get(
            task_path,
            headers={
                **signed_headers("remote-org", "GET", task_path),
                "X-Newma-Agent-Signature": f"sha256={'0' * 64}",
            },
        )
        assert rejected.status_code == 401

        mismatched_body = body.replace(b'"remote-org"', b'"another-org"', 1)
        mismatch = client.post(
            path,
            headers=signed_headers(
                "remote-org",
                "POST",
                path,
                mismatched_body,
            ),
            content=mismatched_body,
        )
        assert mismatch.status_code == 401


def test_remote_agent_routes_require_configured_secret(client):
    path = "/api/workflows/runtime/remote-agent/tasks"
    body = b'{"userId":"user","workspaceId":"org","request":{"userId":"user","prompt":"work"}}'
    response = client.post(
        path,
        headers={
            "Content-Type": "application/json",
            "X-Workspace-Id": "org",
            "X-Newma-Agent-Timestamp": str(int(time.time())),
            "X-Newma-Agent-Signature": f"sha256={'0' * 64}",
        },
        content=body,
    )
    assert response.status_code == 503


def test_workflow_runtime_route_executes_through_agent_gateway(tmp_path: Path):
    fake = FakeAgentAdapter()
    settings = Settings(
        runtime_dir=tmp_path,
        database_path=tmp_path / "workflow-agent.db",
        agent_default_adapter=fake.id,
    )
    application = create_app(settings, agent_adapters=[fake])
    with TestClient(application) as client:
        headers = {
            "X-User-Id": "workflow-agent-user",
            "X-Workspace-Id": "workflow-agent-org",
        }
        control = client.app.state.workflow_control_service
        owner = control.identity(
            organization_id="workflow-agent-org",
            user_id="workflow-agent-user",
        )["id"]
        template = control.create_template(
            organization_id="workflow-agent-org",
            actor_principal_id=owner,
            request=WorkflowTemplateCreate(
                name="Agent runtime route",
                nodes=[
                    {
                        "id": "agent-route",
                        "name": "Agent route",
                        "roleKey": "owner",
                        "executorId": "agent_runtime",
                        "executorParameters": {"prompt": "analyze this workflow"},
                    }
                ],
            ),
        )
        run = control.create_run(
            organization_id="workflow-agent-org",
            actor_principal_id=owner,
            request=WorkflowRunCreate(
                template_id=template["id"],
                title="Agent route run",
            ),
        )
        created = client.post(
            f"/api/workflows/runtime/runs/{run['id']}/executions",
            headers=headers,
            json={"idempotencyKey": "agent-route-once"},
        )
        assert created.status_code == 201
        execution = created.json()
        deadline = time.monotonic() + 2
        while execution["status"] in {"queued", "running"} and time.monotonic() < deadline:
            time.sleep(0.02)
            execution = client.get(
                f"/api/workflows/runtime/executions/{execution['id']}",
                headers=headers,
            ).json()

        assert execution["status"] == "completed"
        assert execution["jobs"][0]["result"]["output"] == {
            "answer": "fake: analyze this workflow"
        }
        assert fake.requests[0].user_id == "workflow-agent-user"


def test_workflow_runtime_invokes_registered_http_capability(tmp_path: Path):
    data_client = FakeWorkflowDataServiceClient()
    service = DataServiceDescriptor(
        id="workflow-data",
        base_url="http://127.0.0.1:9000",
        transport="rest",
        allowed_hosts=["127.0.0.1"],
        capabilities={
            "market.workflow-quote": ServiceCapability(
                method="POST",
                path="/quote",
                input_schema={"type": "object", "additionalProperties": True},
                output_schema={"type": "object", "additionalProperties": True},
                permission="market.read",
            )
        },
    )
    settings = Settings(
        runtime_dir=tmp_path,
        database_path=tmp_path / "workflow-http.db",
        workflow_http_allowed_permissions="market.read",
    )
    application = create_app(
        settings,
        data_services=[service],
        data_service_client=data_client,
    )
    with TestClient(application) as client:
        headers = {
            "X-User-Id": "workflow-http-user",
            "X-Workspace-Id": "workflow-http-org",
        }
        control = client.app.state.workflow_control_service
        owner = control.identity(
            organization_id="workflow-http-org",
            user_id="workflow-http-user",
        )["id"]
        template = control.create_template(
            organization_id="workflow-http-org",
            actor_principal_id=owner,
            request=WorkflowTemplateCreate(
                name="HTTP capability runtime",
                nodes=[
                    {
                        "id": "http-route",
                        "name": "HTTP route",
                        "roleKey": "owner",
                        "executorId": "http_capability",
                        "executorParameters": {
                            "capabilityId": "market.workflow-quote",
                            "serviceId": "workflow-data",
                            "input": {"market": "CN"},
                            "mapping": {"symbol": "input.symbol"},
                        },
                    }
                ],
            ),
        )
        run = control.create_run(
            organization_id="workflow-http-org",
            actor_principal_id=owner,
            request=WorkflowRunCreate(
                template_id=template["id"],
                title="HTTP capability run",
            ),
        )
        created = client.post(
            f"/api/workflows/runtime/runs/{run['id']}/executions",
            headers=headers,
            json={
                "idempotencyKey": "http-capability-once",
                "input": {"symbol": "600000"},
            },
        )
        assert created.status_code == 201
        execution = created.json()
        deadline = time.monotonic() + 2
        while execution["status"] in {"queued", "running"} and time.monotonic() < deadline:
            time.sleep(0.02)
            execution = client.get(
                f"/api/workflows/runtime/executions/{execution['id']}",
                headers=headers,
            ).json()

        assert execution["status"] == "completed"
        assert execution["jobs"][0]["result"] == {
            "capabilityId": "market.workflow-quote",
            "serviceId": "workflow-data",
            "permission": "market.read",
            "data": {
                "accepted": True,
                "input": {"market": "CN", "symbol": "600000"},
            },
        }
        assert data_client.calls == [
            (
                "workflow-data",
                "market.workflow-quote",
                {"market": "CN", "symbol": "600000"},
            )
        ]


def test_workflow_runtime_denies_http_write_permission_by_default(tmp_path: Path):
    data_client = FakeWorkflowDataServiceClient()
    service = DataServiceDescriptor(
        id="workflow-write-data",
        base_url="http://127.0.0.1:9000",
        transport="rest",
        allowed_hosts=["127.0.0.1"],
        capabilities={
            "market.workflow-refresh": ServiceCapability(
                method="POST",
                path="/refresh",
                input_schema={"type": "object", "additionalProperties": False},
                output_schema={"type": "object", "additionalProperties": True},
                permission="market.write",
            )
        },
    )
    settings = Settings(
        runtime_dir=tmp_path,
        database_path=tmp_path / "workflow-http-denied.db",
    )
    application = create_app(
        settings,
        data_services=[service],
        data_service_client=data_client,
    )
    with TestClient(application) as client:
        headers = {
            "X-User-Id": "workflow-http-user",
            "X-Workspace-Id": "workflow-http-org",
        }
        control = client.app.state.workflow_control_service
        owner = control.identity(
            organization_id="workflow-http-org",
            user_id="workflow-http-user",
        )["id"]
        template = control.create_template(
            organization_id="workflow-http-org",
            actor_principal_id=owner,
            request=WorkflowTemplateCreate(
                name="Denied HTTP capability",
                nodes=[
                    {
                        "id": "http-write",
                        "name": "HTTP write",
                        "roleKey": "owner",
                        "executorId": "http_capability",
                        "executorParameters": {
                            "capabilityId": "market.workflow-refresh"
                        },
                    }
                ],
            ),
        )
        run = control.create_run(
            organization_id="workflow-http-org",
            actor_principal_id=owner,
            request=WorkflowRunCreate(
                template_id=template["id"],
                title="Denied HTTP run",
            ),
        )
        created = client.post(
            f"/api/workflows/runtime/runs/{run['id']}/executions",
            headers=headers,
            json={"idempotencyKey": "http-write-denied"},
        )
        assert created.status_code == 201
        execution = created.json()
        deadline = time.monotonic() + 2
        while execution["status"] in {"queued", "running"} and time.monotonic() < deadline:
            time.sleep(0.02)
            execution = client.get(
                f"/api/workflows/runtime/executions/{execution['id']}",
                headers=headers,
            ).json()

        assert execution["status"] == "failed"
        assert "market.write" in execution["jobs"][0]["error"]["message"]
        assert data_client.calls == []
