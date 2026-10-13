from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Any, Protocol

from vibe_visualization_api.data_services.client import DataServiceClient
from vibe_visualization_api.data_services.registry import DataServiceRegistry
from vibe_visualization_api.workflow_runtime.adapters import (
    NodeExecutionContext,
    NodeExecutionResult,
)
from vibe_visualization_api.workflow_runtime.conditions import resolve_path


class HttpCapabilityExecutionPort(Protocol):
    def invoke(
        self,
        *,
        capability_id: str,
        service_id: str | None,
        input_data: dict[str, Any],
        timeout_seconds: float,
    ) -> dict[str, Any]: ...


class DataServiceWorkflowPort:
    """Thread-safe bridge to the existing registered Data Service gateway."""

    def __init__(
        self,
        registry: DataServiceRegistry,
        client: DataServiceClient,
        loop_provider: Callable[[], asyncio.AbstractEventLoop | None],
        *,
        allowed_permissions: str,
        max_timeout_seconds: float = 300,
    ):
        self._registry = registry
        self._client = client
        self._loop_provider = loop_provider
        self._allowed_permissions = {
            permission.strip()
            for permission in allowed_permissions.split(",")
            if permission.strip()
        }
        self._max_timeout_seconds = max_timeout_seconds

    def invoke(
        self,
        *,
        capability_id: str,
        service_id: str | None,
        input_data: dict[str, Any],
        timeout_seconds: float,
    ) -> dict[str, Any]:
        service = self._registry.resolve(capability_id, service_id)
        capability = service.capabilities[capability_id]
        if capability.permission not in self._allowed_permissions:
            raise ValueError(
                f"workflow HTTP permission {capability.permission!r} is not allowed"
            )
        result = self._call(
            self._client.invoke(service, capability_id, input_data),
            timeout_seconds=min(timeout_seconds, self._max_timeout_seconds),
        )
        return {
            "capabilityId": capability_id,
            "serviceId": service.id,
            "permission": capability.permission,
            "data": result,
        }

    def _call(
        self,
        operation: Coroutine[Any, Any, Any],
        *,
        timeout_seconds: float,
    ) -> Any:
        loop = self._loop_provider()
        if loop is None or not loop.is_running():
            operation.close()
            raise RuntimeError("Data Service Runtime is not available")
        future = asyncio.run_coroutine_threadsafe(operation, loop)
        try:
            return future.result(timeout=timeout_seconds)
        except FutureTimeoutError as error:
            future.cancel()
            raise RuntimeError("HTTP capability timed out") from error


class HttpCapabilityNodeExecutionAdapter:
    """Invokes only a server-registered Data Service capability."""

    id = "http_capability"
    _ALLOWED_PARAMETERS = {"capabilityId", "serviceId", "input", "mapping"}

    def __init__(self, port: HttpCapabilityExecutionPort):
        self._port = port

    def execute(
        self,
        context: NodeExecutionContext,
        parameters: dict[str, Any],
    ) -> NodeExecutionResult:
        unexpected = sorted(set(parameters) - self._ALLOWED_PARAMETERS)
        if unexpected:
            raise ValueError(
                "http_capability does not accept parameters: "
                + ", ".join(unexpected)
            )
        capability_id = parameters.get("capabilityId")
        if not isinstance(capability_id, str) or not capability_id.strip():
            raise ValueError("http_capability requires capabilityId")
        capability_id = capability_id.strip()
        service_id = parameters.get("serviceId")
        if service_id is not None and (
            not isinstance(service_id, str) or not service_id.strip()
        ):
            raise ValueError("http_capability serviceId must be a string")
        service_id = service_id.strip() if isinstance(service_id, str) else None
        input_parameters = parameters.get("input") or {}
        if not isinstance(input_parameters, dict):
            raise ValueError("http_capability input must be an object")
        input_data = dict(input_parameters)
        mapping = parameters.get("mapping") or {}
        if not isinstance(mapping, dict):
            raise ValueError("http_capability mapping must be an object")
        source = {
            "run": context.run,
            "node": context.node,
            "input": context.input,
            "data": context.data,
            "artifact": context.artifacts,
            "result": context.results,
        }
        for key, path in mapping.items():
            if not isinstance(key, str) or not key or not isinstance(path, str):
                raise ValueError(
                    "http_capability mapping requires string keys and paths"
                )
            input_data[key] = resolve_path(source, path)
        output = self._port.invoke(
            capability_id=capability_id,
            service_id=service_id,
            input_data=input_data,
            timeout_seconds=float(context.job["timeoutSeconds"]),
        )
        return NodeExecutionResult(output=output)
