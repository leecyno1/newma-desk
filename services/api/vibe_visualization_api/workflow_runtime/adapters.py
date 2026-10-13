from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from vibe_visualization_api.workflow_runtime.conditions import resolve_path


class UnknownNodeExecutionAdapterError(ValueError):
    """Raised when a workflow references an unregistered executor."""


@dataclass(frozen=True)
class NodeExecutionContext:
    organization_id: str
    execution_id: str
    user_id: str
    run: dict[str, Any]
    node: dict[str, Any]
    job: dict[str, Any]
    input: dict[str, Any]
    data: dict[str, Any]
    artifacts: dict[str, Any]
    results: dict[str, Any]


@dataclass(frozen=True)
class NodeExecutionResult:
    status: str = "completed"
    output: dict[str, Any] = field(default_factory=dict)


class NodeExecutionAdapter(Protocol):
    id: str

    def execute(
        self,
        context: NodeExecutionContext,
        parameters: dict[str, Any],
    ) -> NodeExecutionResult: ...


class AgentTaskExecutionPort(Protocol):
    def create_task(
        self,
        *,
        user_id: str,
        workspace_id: str,
        request: dict[str, Any],
    ) -> dict[str, Any]: ...

    def get_task(self, task_id: str) -> dict[str, Any]: ...

    def cancel_task(self, task_id: str) -> dict[str, Any]: ...


class NoopNodeExecutionAdapter:
    id = "noop"

    def execute(
        self,
        context: NodeExecutionContext,
        parameters: dict[str, Any],
    ) -> NodeExecutionResult:
        return NodeExecutionResult(
            output={"ok": True, "nodeId": context.node["id"], **parameters}
        )


class DataTransformNodeExecutionAdapter:
    id = "data_transform"

    def execute(
        self,
        context: NodeExecutionContext,
        parameters: dict[str, Any],
    ) -> NodeExecutionResult:
        source = {
            "run": context.run,
            "node": context.node,
            "input": context.input,
            "data": context.data,
            "artifact": context.artifacts,
            "result": context.results,
        }
        output = dict(parameters.get("constants") or {})
        for key, path in (parameters.get("mapping") or {}).items():
            if not isinstance(path, str):
                raise ValueError("data_transform mapping values must be paths")
            output[key] = resolve_path(source, path)
        return NodeExecutionResult(output=output)


class ApprovalWaitNodeExecutionAdapter:
    id = "approval_wait"

    def execute(
        self,
        context: NodeExecutionContext,
        parameters: dict[str, Any],
    ) -> NodeExecutionResult:
        return NodeExecutionResult(
            status="waiting",
            output={
                "nodeId": context.node["id"],
                "message": parameters.get("message") or "等待人工执行或审核",
            },
        )


class AgentHandoffNodeExecutionAdapter:
    id = "agent_handoff"

    def execute(
        self,
        context: NodeExecutionContext,
        parameters: dict[str, Any],
    ) -> NodeExecutionResult:
        target = parameters.get("principalId") or context.node.get(
            "accountablePrincipalId"
        )
        return NodeExecutionResult(
            output={
                "handoff": {
                    "status": "requested",
                    "targetPrincipalId": target,
                    "instruction": parameters.get("instruction", ""),
                    "executionId": context.execution_id,
                    "nodeId": context.node["id"],
                }
            }
        )


class AgentRuntimeNodeExecutionAdapter:
    """Runs a workflow node through the existing Desk/Newma Agent Gateway."""

    id = "agent_runtime"

    def __init__(self, port: AgentTaskExecutionPort):
        self._port = port

    def execute(
        self,
        context: NodeExecutionContext,
        parameters: dict[str, Any],
    ) -> NodeExecutionResult:
        previous = context.job.get("result")
        if isinstance(previous, dict) and previous.get("agentTaskId"):
            return self.poll(context, parameters, previous)
        task = self._port.create_task(
            user_id=context.user_id,
            workspace_id=context.organization_id,
            request=self._request(context, parameters),
        )
        return self._task_result(task)

    def poll(
        self,
        context: NodeExecutionContext,
        parameters: dict[str, Any],
        state: dict[str, Any],
    ) -> NodeExecutionResult:
        return self._task_result(self._port.get_task(str(state["agentTaskId"])))

    def cancel(
        self,
        context: NodeExecutionContext,
        parameters: dict[str, Any],
        state: dict[str, Any],
    ) -> None:
        task_id = state.get("agentTaskId")
        if task_id:
            self._port.cancel_task(str(task_id))

    @staticmethod
    def _request(
        context: NodeExecutionContext,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        prompt = str(
            parameters.get("prompt")
            or context.node.get("description")
            or context.node.get("name")
            or "执行当前工作流节点"
        ).strip()
        profile = str(parameters.get("profile") or parameters.get("mode") or "deep")
        profile = {"research": "deep", "modify": "edit"}.get(profile, profile)
        adapter = parameters.get("adapter")
        request = {
            "moduleId": parameters.get("moduleId") or "workflow-runs",
            "capability": parameters.get("capability") or "module.analyze",
            "profile": profile,
            "prompt": prompt,
            "context": {
                "workflow": {
                    "organizationId": context.organization_id,
                    "executionId": context.execution_id,
                    "runId": context.run["id"],
                    "nodeId": context.node["id"],
                    "node": context.node,
                    "input": context.input,
                    "data": context.data,
                    "artifacts": context.artifacts,
                    "results": context.results,
                }
            },
            "input": dict(parameters.get("input") or {}),
        }
        if adapter and adapter != "auto":
            request["adapter"] = adapter
        for source, target in (
            ("model", "model"),
            ("commandProfile", "commandProfile"),
        ):
            if parameters.get(source):
                request[target] = parameters[source]
        return request

    @staticmethod
    def _task_result(task: dict[str, Any]) -> NodeExecutionResult:
        task_id = str(task["id"])
        status = str(task["status"])
        request = task.get("request")
        adapter = request.get("adapter") if isinstance(request, dict) else None
        reference = {
            "agentTaskId": task_id,
            "status": status,
            **({"adapter": adapter} if adapter else {}),
        }
        if status in {"queued", "running"}:
            return NodeExecutionResult(status="waiting", output=reference)
        if status == "completed":
            return NodeExecutionResult(
                output={**reference, "output": task.get("result") or {}},
            )
        if status == "cancelled":
            raise RuntimeError(f"Agent task {task_id} was cancelled")
        raise RuntimeError(task.get("error") or f"Agent task {task_id} failed")


class NodeExecutionAdapterRegistry:
    def __init__(self, adapters: list[NodeExecutionAdapter] | None = None):
        defaults: list[NodeExecutionAdapter] = [
            NoopNodeExecutionAdapter(),
            DataTransformNodeExecutionAdapter(),
            ApprovalWaitNodeExecutionAdapter(),
            AgentHandoffNodeExecutionAdapter(),
        ]
        self._adapters = {adapter.id: adapter for adapter in defaults}
        for adapter in adapters or []:
            self._adapters[adapter.id] = adapter

    def require(self, adapter_id: str) -> NodeExecutionAdapter:
        adapter = self._adapters.get(adapter_id)
        if adapter is None:
            raise UnknownNodeExecutionAdapterError(adapter_id)
        return adapter

    def ids(self) -> list[str]:
        return sorted(self._adapters)
