from __future__ import annotations

import json
import time
from typing import Any
from urllib.parse import urlsplit

import httpx

from vibe_visualization_api.workflow_control.service import WorkflowControlService
from vibe_visualization_api.workflow_runtime.adapters import (
    AgentRuntimeNodeExecutionAdapter,
    NodeExecutionContext,
    NodeExecutionResult,
)
from vibe_visualization_api.workflow_runtime.signing import WorkflowRequestSigner


class RemoteServerAgentNodeExecutionAdapter:
    """Delegates one node to another Desk/Newma Agent Gateway."""

    id = "server_agent"

    def __init__(
        self,
        control: WorkflowControlService,
        *,
        secret: str,
        allowed_hosts: str,
        timeout_seconds: float = 15.0,
        signature_tolerance_seconds: int = 300,
        client: httpx.Client | None = None,
    ):
        self._control = control
        self._signer = WorkflowRequestSigner(
            secret,
            tolerance_seconds=signature_tolerance_seconds,
        )
        self._allowed_hosts = {
            host.strip().casefold() for host in allowed_hosts.split(",") if host.strip()
        }
        self._timeout = httpx.Timeout(timeout_seconds)
        self._client = client

    def execute(
        self,
        context: NodeExecutionContext,
        parameters: dict[str, Any],
    ) -> NodeExecutionResult:
        previous = context.job.get("result")
        if isinstance(previous, dict) and previous.get("remoteTaskId"):
            return self.poll(context, parameters, previous)
        principal = self._principal(context, parameters)
        agent_request = AgentRuntimeNodeExecutionAdapter._request(context, parameters)
        agent_request["userId"] = context.user_id
        payload = {
            "userId": context.user_id,
            "workspaceId": context.organization_id,
            "request": agent_request,
        }
        task = self._request(
            principal,
            context.organization_id,
            "POST",
            "/api/workflows/runtime/remote-agent/tasks",
            payload,
        )
        return self._task_result(principal["id"], task)

    def poll(
        self,
        context: NodeExecutionContext,
        parameters: dict[str, Any],
        state: dict[str, Any],
    ) -> NodeExecutionResult:
        principal = self._principal_by_id(
            context.organization_id,
            str(state["remotePrincipalId"]),
        )
        task_id = str(state["remoteTaskId"])
        task = self._request(
            principal,
            context.organization_id,
            "GET",
            f"/api/workflows/runtime/remote-agent/tasks/{task_id}",
        )
        return self._task_result(principal["id"], task)

    def cancel(
        self,
        context: NodeExecutionContext,
        parameters: dict[str, Any],
        state: dict[str, Any],
    ) -> None:
        principal_id = state.get("remotePrincipalId")
        task_id = state.get("remoteTaskId")
        if not principal_id or not task_id:
            return
        principal = self._principal_by_id(
            context.organization_id,
            str(principal_id),
        )
        self._request(
            principal,
            context.organization_id,
            "POST",
            f"/api/workflows/runtime/remote-agent/tasks/{task_id}/cancel",
        )

    def _principal(
        self,
        context: NodeExecutionContext,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        principal_id = str(
            parameters.get("principalId")
            or context.node.get("accountablePrincipalId")
            or ""
        )
        return self._principal_by_id(context.organization_id, principal_id)

    def _principal_by_id(
        self,
        organization_id: str,
        principal_id: str,
    ) -> dict[str, Any]:
        principal = self._control.repository.get_principal(
            organization_id,
            principal_id,
        )
        if principal["kind"] != "server_agent" or principal["status"] != "active":
            raise ValueError("target principal is not an active Server Agent")
        if "workflow.execute" not in principal.get("capabilities", []):
            raise ValueError("target Server Agent lacks workflow.execute capability")
        self._base_url(principal)
        if not self._signer.available:
            raise RuntimeError("Remote Server Agent signing is not configured")
        return principal

    def _base_url(self, principal: dict[str, Any]) -> str:
        endpoint = str(principal.get("endpoint") or "").rstrip("/")
        parsed = urlsplit(endpoint)
        host = (parsed.hostname or "").casefold()
        if parsed.scheme not in {"http", "https"} or host not in self._allowed_hosts:
            raise ValueError("Server Agent endpoint host is not allowed")
        return endpoint

    def _request(
        self,
        principal: dict[str, Any],
        workspace_id: str,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body = (
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
            if payload is not None
            else b""
        )
        timestamp = str(int(time.time()))
        signature = self._signer.sign(
            timestamp=timestamp,
            scope=f"remote-agent:{workspace_id}:{method}:{path}",
            body=body,
        )
        client = self._client or httpx.Client(
            timeout=self._timeout,
            follow_redirects=False,
            trust_env=False,
        )
        owns_client = self._client is None
        try:
            response = client.request(
                method,
                f"{self._base_url(principal)}{path}",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Workspace-Id": workspace_id,
                    "X-Newma-Agent-Timestamp": timestamp,
                    "X-Newma-Agent-Signature": signature,
                },
                follow_redirects=False,
            )
            if response.status_code >= 400:
                raise RuntimeError("Remote Server Agent rejected the request")
            try:
                task = response.json()
            except ValueError as error:
                raise RuntimeError(
                    "Remote Server Agent returned invalid data"
                ) from error
        except httpx.TimeoutException as error:
            raise RuntimeError("Remote Server Agent timed out") from error
        except httpx.RequestError as error:
            raise RuntimeError("Remote Server Agent is unavailable") from error
        finally:
            if owns_client:
                client.close()
        if not isinstance(task, dict) or not task.get("id") or not task.get("status"):
            raise RuntimeError("Remote Server Agent returned invalid data")
        return task

    @staticmethod
    def _task_result(
        principal_id: str,
        task: dict[str, Any],
    ) -> NodeExecutionResult:
        task_id = str(task["id"])
        status = str(task["status"])
        reference = {
            "remoteTaskId": task_id,
            "remotePrincipalId": principal_id,
            "status": status,
        }
        if status in {"queued", "running"}:
            return NodeExecutionResult(status="waiting", output=reference)
        if status == "completed":
            return NodeExecutionResult(
                output={**reference, "output": task.get("result") or {}},
            )
        if status == "cancelled":
            raise RuntimeError(f"Remote Agent task {task_id} was cancelled")
        raise RuntimeError(task.get("error") or f"Remote Agent task {task_id} failed")
