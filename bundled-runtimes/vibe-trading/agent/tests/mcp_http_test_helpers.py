"""Shared helpers for HTTP-based MCP integration tests."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

import requests

_PYTHON = sys.executable
_DIAGNOSTIC_BODY_LIMIT = 500
_NO_PROXY_ENV_VARS = ("NO_PROXY", "no_proxy")
_LOOPBACK_NO_PROXY_HOSTS = ("127.0.0.1", "localhost")


@dataclass(frozen=True)
class HttpMCPServerHandle:
    """Running HTTP MCP fixture plus context useful when remote discovery fails."""

    process: subprocess.Popen[str]
    port: int
    command: tuple[str, ...]
    ready_url: str
    ready_request_kwargs: dict[str, Any]
    last_ready_probe: str = ""

    def __iter__(self) -> Iterator[Any]:
        yield self.process
        yield self.port

    def diagnostics(self) -> str:
        """Return non-blocking diagnostics for assertion messages."""
        lines = [
            "HTTP MCP fixture diagnostics:",
            f"  command: {' '.join(self.command)}",
            f"  selected_port: {self.port}",
            f"  ready_url: {self.ready_url}",
            f"  process_exit_code: {self.process.poll()}",
        ]
        if self.last_ready_probe:
            lines.append(f"  last_ready_probe: {self.last_ready_probe}")
        lines.append(f"  live_probe: {_probe_ready_url(self.ready_url, self.ready_request_kwargs)}")
        if self.process.poll() is None:
            lines.append("  stdout/stderr: unavailable while fixture process is running")
        else:
            lines.append(f"  stdout/stderr: {_collect_process_output(self.process).strip() or '<empty>'}")
        return "\n".join(lines)


def make_single_server_agent_json(
    tmp_path: Path,
    server_name: str,
    *,
    transport_type: str,
    url: str,
    **server_kwargs: Any,
) -> Path:
    """Write a minimal agent.json with one remote MCP server."""
    config: dict[str, Any] = {
        "mcpServers": {
            server_name: {
                "type": transport_type,
                "url": url,
                **server_kwargs,
            }
        }
    }
    cfg_path = tmp_path / "agent.json"
    cfg_path.write_text(json.dumps(config))
    return cfg_path


@contextmanager
def reserved_local_port() -> Iterator[int]:
    """Reserve a loopback port for the lifetime of the context."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        yield int(sock.getsockname()[1])


def stop_http_mcp_server(proc: subprocess.Popen[str]) -> None:
    """Terminate an HTTP MCP subprocess and wait for clean exit."""
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def _collect_process_output(proc: subprocess.Popen[str]) -> str:
    """Return subprocess stdout after ensuring the process has exited."""
    if proc.poll() is None:
        stop_http_mcp_server(proc)
    return proc.stdout.read() if proc.stdout is not None else ""


def _probe_ready_url(ready_url: str, request_kwargs: dict[str, Any] | None = None) -> str:
    request_kwargs = dict(request_kwargs or {})
    stream = bool(request_kwargs.get("stream"))
    try:
        response = requests.get(ready_url, timeout=0.5, **request_kwargs)
    except requests.RequestException as exc:
        return f"{type(exc).__name__}: {exc}"

    try:
        return _summarize_response(response, stream=stream)
    finally:
        response.close()


def _summarize_response(response: requests.Response, *, stream: bool = False) -> str:
    content_type = response.headers.get("content-type", "")
    if stream:
        body = "<streaming response body omitted>"
    else:
        body = response.text[:_DIAGNOSTIC_BODY_LIMIT]
    return f"status={response.status_code} content-type={content_type!r} body={body!r}"


def _format_start_failure(
    service_name: str,
    proc: subprocess.Popen[str],
    *,
    command: list[str],
    ready_url: str,
    port: int | None = None,
    last_probe: str = "",
    reason: str,
) -> RuntimeError:
    output = _collect_process_output(proc)
    lines = [
        f"{service_name} {reason}",
        f"command: {' '.join(command)}",
        f"selected_port: {port if port is not None else '<unknown>'}",
        f"ready_url: {ready_url}",
        f"process_exit_code: {proc.returncode}",
    ]
    if last_probe:
        lines.append(f"last_ready_probe: {last_probe}")
    lines.append(f"stdout/stderr: {output.strip() or '<empty>'}")
    return RuntimeError("\n".join(lines))


def _merge_loopback_no_proxy(value: str | None) -> str:
    entries = [entry.strip() for entry in (value or "").split(",") if entry.strip()]
    lowered = {entry.lower() for entry in entries}
    for host in _LOOPBACK_NO_PROXY_HOSTS:
        if host not in lowered:
            entries.append(host)
    return ",".join(entries)


@contextmanager
def _loopback_proxy_bypass() -> Iterator[None]:
    """Keep local FastMCP fixture traffic out of developer/system HTTP proxies."""
    original = {name: os.environ.get(name) for name in _NO_PROXY_ENV_VARS}
    merged = _merge_loopback_no_proxy(original.get("NO_PROXY") or original.get("no_proxy"))
    for name in _NO_PROXY_ENV_VARS:
        os.environ[name] = merged
    try:
        yield
    finally:
        for name, value in original.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def start_http_mcp_server(
    fixture_server: Path,
    *,
    ready_url: str,
    service_name: str,
    extra_args: list[str],
    ready_statuses: set[int] | None = None,
    ready_request_kwargs: dict[str, Any] | None = None,
) -> subprocess.Popen[str]:
    """Start an HTTP MCP subprocess and wait until the endpoint is reachable."""
    command = [_PYTHON, str(fixture_server), *extra_args]
    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    request_kwargs = dict(ready_request_kwargs or {})
    accepted_statuses = set(ready_statuses or {200})
    last_probe = ""

    for _ in range(40):
        if proc.poll() is not None:
            raise _format_start_failure(
                service_name,
                proc,
                command=command,
                ready_url=ready_url,
                last_probe=last_probe,
                reason=f"failed to start with exit code {proc.returncode}",
            )
        try:
            response = requests.get(ready_url, timeout=0.5, **request_kwargs)
            last_probe = _summarize_response(response, stream=bool(request_kwargs.get("stream")))
            if response.status_code in accepted_statuses:
                response.close()
                return proc
            response.close()
        except requests.RequestException as exc:
            last_probe = f"{type(exc).__name__}: {exc}"
            time.sleep(0.2)

    stop_http_mcp_server(proc)
    raise _format_start_failure(
        service_name,
        proc,
        command=command,
        ready_url=ready_url,
        last_probe=last_probe,
        reason="did not become ready within 8 seconds",
    )


def start_http_mcp_server_on_random_port(
    fixture_server: Path,
    *,
    service_name: str,
    ready_url_builder: Callable[[int], str],
    extra_args_builder: Callable[[int], list[str]],
    ready_statuses: set[int] | None = None,
    ready_request_kwargs: dict[str, Any] | None = None,
    max_attempts: int = 5,
) -> HttpMCPServerHandle:
    """Start an HTTP MCP subprocess on an OS-assigned port."""
    last_error: RuntimeError | None = None

    for _ in range(max_attempts):
        with tempfile.TemporaryDirectory(prefix="mcp-port-") as temp_dir:
            port_file = Path(temp_dir) / "port.txt"
            command = [_PYTHON, str(fixture_server), *extra_args_builder(0), "--port-file", str(port_file)]
            proc = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            try:
                port = _wait_for_server_port(proc, port_file, service_name=service_name)
                ready_url = ready_url_builder(port)
                last_probe = _wait_for_http_ready(
                    proc,
                    ready_url=ready_url,
                    service_name=service_name,
                    ready_statuses=ready_statuses,
                    ready_request_kwargs=ready_request_kwargs,
                    command=command,
                    port=port,
                )
                return HttpMCPServerHandle(
                    process=proc,
                    port=port,
                    command=tuple(command),
                    ready_url=ready_url,
                    ready_request_kwargs=dict(ready_request_kwargs or {}),
                    last_ready_probe=last_probe,
                )
            except RuntimeError as exc:
                last_error = exc
                stop_http_mcp_server(proc)

    if last_error is not None:
        raise last_error
    raise RuntimeError(f"{service_name} could not obtain an available port")


def _wait_for_server_port(
    proc: subprocess.Popen[str],
    port_file: Path,
    *,
    service_name: str,
    timeout_seconds: float = 8.0,
) -> int:
    """Wait until the fixture writes back its bound port."""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if proc.poll() is not None:
            output = _collect_process_output(proc)
            raise RuntimeError(f"{service_name} failed to start with exit code {proc.returncode}: {output}")
        if port_file.exists():
            try:
                return int(port_file.read_text(encoding="utf-8").strip())
            except ValueError:
                pass
        time.sleep(0.05)

    output = _collect_process_output(proc)
    raise RuntimeError(f"{service_name} did not write its listening port within 8 seconds: {output}")


def _wait_for_http_ready(
    proc: subprocess.Popen[str],
    *,
    ready_url: str,
    service_name: str,
    command: list[str],
    port: int,
    ready_statuses: set[int] | None = None,
    ready_request_kwargs: dict[str, Any] | None = None,
    timeout_seconds: float = 8.0,
) -> str:
    """Poll the fixture endpoint until it is reachable."""
    request_kwargs = dict(ready_request_kwargs or {})
    accepted_statuses = set(ready_statuses or {200})
    deadline = time.time() + timeout_seconds
    last_probe = ""

    while time.time() < deadline:
        if proc.poll() is not None:
            raise _format_start_failure(
                service_name,
                proc,
                command=command,
                ready_url=ready_url,
                port=port,
                last_probe=last_probe,
                reason=f"failed to start with exit code {proc.returncode}",
            )
        try:
            response = requests.get(ready_url, timeout=0.5, **request_kwargs)
            last_probe = _summarize_response(response, stream=bool(request_kwargs.get("stream")))
            if response.status_code in accepted_statuses:
                response.close()
                return last_probe
            response.close()
        except requests.RequestException as exc:
            last_probe = f"{type(exc).__name__}: {exc}"
            time.sleep(0.2)

    raise _format_start_failure(
        service_name,
        proc,
        command=command,
        ready_url=ready_url,
        port=port,
        last_probe=last_probe,
        reason="did not become ready within 8 seconds",
    )


@contextmanager
def running_http_mcp_server(
    fixture_server: Path,
    *,
    ready_url: str,
    service_name: str,
    extra_args: list[str],
    ready_statuses: set[int] | None = None,
    ready_request_kwargs: dict[str, Any] | None = None,
) -> Iterator[subprocess.Popen[str]]:
    """Context manager that runs a FastMCP HTTP server for one test."""
    with _loopback_proxy_bypass():
        proc = start_http_mcp_server(
            fixture_server,
            ready_url=ready_url,
            service_name=service_name,
            extra_args=extra_args,
            ready_statuses=ready_statuses,
            ready_request_kwargs=ready_request_kwargs,
        )
        try:
            yield proc
        finally:
            stop_http_mcp_server(proc)


@contextmanager
def running_http_mcp_server_on_random_port(
    fixture_server: Path,
    *,
    service_name: str,
    ready_url_builder: Callable[[int], str],
    extra_args_builder: Callable[[int], list[str]],
    ready_statuses: set[int] | None = None,
    ready_request_kwargs: dict[str, Any] | None = None,
    max_attempts: int = 5,
) -> Iterator[HttpMCPServerHandle]:
    """Context manager that runs a FastMCP HTTP server on a retryable free port."""
    with _loopback_proxy_bypass():
        handle = start_http_mcp_server_on_random_port(
            fixture_server,
            service_name=service_name,
            ready_url_builder=ready_url_builder,
            extra_args_builder=extra_args_builder,
            ready_statuses=ready_statuses,
            ready_request_kwargs=ready_request_kwargs,
            max_attempts=max_attempts,
        )
        try:
            yield handle
        finally:
            stop_http_mcp_server(handle.process)
