import ipaddress
import os
import socket
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

import httpx
from starlette.concurrency import run_in_threadpool

from vibe_visualization_api.data_services.models import DataServiceDescriptor
from vibe_visualization_api.schema_validation import validate_json_contract


class DataServiceClientError(Exception):
    """Base error for safe data service invocation."""


class UnsafeServiceUrl(DataServiceClientError):
    """Raised when a service URL violates the configured network policy."""


class UnknownServiceCapability(DataServiceClientError):
    """Raised when a browser requests an unregistered service capability."""


class UnsupportedServiceTransport(DataServiceClientError):
    """Raised when invocation is not supported for a service transport."""


class MissingServiceSecret(DataServiceClientError):
    """Raised when a registered server-side Secret reference is unresolved."""


class UpstreamServiceError(DataServiceClientError):
    """Raised when a registered upstream request fails safely."""


def _resolved_addresses(
    host: str, port: int
) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        return {
            ipaddress.ip_address(address[4][0])
            for address in socket.getaddrinfo(
                host,
                port,
                type=socket.SOCK_STREAM,
            )
        }
    except (OSError, ValueError) as error:
        raise UnsafeServiceUrl("data service host could not be resolved") from error


def validate_service_url(
    url: str,
    *,
    public_mode: bool,
    allowed_hosts: list[str] | None = None,
) -> None:
    try:
        parsed = urlsplit(url)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as error:
        raise UnsafeServiceUrl("data service URL is invalid") from error
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise UnsafeServiceUrl("data service URL must use HTTP or HTTPS")

    host = parsed.hostname.casefold().rstrip(".")
    if not public_mode:
        allowed = {item.casefold().rstrip(".") for item in (allowed_hosts or [])}
        if host not in allowed:
            raise UnsafeServiceUrl("data service host is not in the local allowlist")
        return

    if host == "localhost" or host.endswith(".localhost"):
        raise UnsafeServiceUrl("data service host is not public")
    try:
        addresses = {ipaddress.ip_address(host)}
    except ValueError:
        addresses = _resolved_addresses(host, port)
    if not addresses or any(not address.is_global for address in addresses):
        raise UnsafeServiceUrl("data service host is not public")


class DataServiceClient:
    def __init__(
        self,
        *,
        public_mode: bool,
        secret_resolver: Callable[[str], str | None] | None = None,
        response_adapters: dict[str, Callable[[str, Any], Any]] | None = None,
        client: httpx.AsyncClient | None = None,
    ):
        self._public_mode = public_mode
        self._secret_resolver = secret_resolver or os.environ.get
        self._response_adapters = response_adapters or {}
        self._client = client

    async def invoke(
        self,
        service: DataServiceDescriptor,
        capability_id: str,
        input_data: dict[str, Any],
    ) -> Any:
        if service.transport != "rest":
            raise UnsupportedServiceTransport(
                "data service transport is not invokable over REST"
            )
        try:
            capability = service.capabilities[capability_id]
        except KeyError as error:
            raise UnknownServiceCapability(
                f"capability {capability_id!r} is not registered"
            ) from error

        validate_json_contract(
            capability.input_schema,
            input_data,
            direction="input",
        )

        url = f"{str(service.base_url).rstrip('/')}{capability.path}"
        await run_in_threadpool(
            validate_service_url,
            url,
            public_mode=self._public_mode,
            allowed_hosts=service.allowed_hosts,
        )
        headers: dict[str, str] = {}
        if service.auth_secret:
            secret = self._secret_resolver(service.auth_secret)
            if not secret:
                raise MissingServiceSecret("data service Secret is not configured")
            headers["Authorization"] = f"Bearer {secret}"

        timeout = httpx.Timeout(service.timeout_seconds)
        client = self._client or httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            trust_env=False,
        )
        owns_client = self._client is None
        request_arguments: dict[str, object] = {
            "headers": headers,
            "timeout": timeout,
            "follow_redirects": False,
        }
        if capability.method == "GET":
            request_arguments["params"] = input_data
        else:
            request_arguments["json"] = input_data
        try:
            response = await client.request(
                capability.method,
                url,
                **request_arguments,
            )
        except httpx.TimeoutException as error:
            raise UpstreamServiceError("data service timed out") from error
        except httpx.RequestError as error:
            raise UpstreamServiceError("data service is unavailable") from error
        finally:
            if owns_client:
                await client.aclose()

        if not 200 <= response.status_code < 300:
            raise UpstreamServiceError("data service request failed")
        try:
            result = response.json()
        except ValueError as error:
            raise UpstreamServiceError(
                "data service returned an invalid response"
            ) from error
        adapter = self._response_adapters.get(service.id)
        if adapter is not None:
            try:
                result = adapter(capability_id, result)
            except (TypeError, ValueError) as error:
                raise UpstreamServiceError(
                    "data service returned an invalid response"
                ) from error
        validate_json_contract(
            capability.output_schema,
            result,
            direction="output",
        )
        return result
