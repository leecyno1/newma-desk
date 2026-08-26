"""Runner module for executing generated backtest code and collecting artifacts."""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Dict, Optional

from rich.console import Console


console = Console(stderr=True)


_PROXY_ENV_KEYS = frozenset(
    {
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "no_proxy",
    }
)

_RUNTIME_ENV_KEYS = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "USERNAME",
        "USERPROFILE",
        "SHELL",
        "TMPDIR",
        "TEMP",
        "TMP",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "PATHEXT",
        "APPDATA",
        "LOCALAPPDATA",
        "PROGRAMDATA",
        "LANG",
        "TZ",
        "XDG_CACHE_HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "VIRTUAL_ENV",
        "CONDA_PREFIX",
        "LD_LIBRARY_PATH",
        "DYLD_LIBRARY_PATH",
        "DYLD_FALLBACK_LIBRARY_PATH",
        "PYTHONHOME",
        "PYTHONPATH",
        "PYTHONNOUSERSITE",
        "REQUESTS_CA_BUNDLE",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "CURL_CA_BUNDLE",
        "TUSHARE_TOKEN",
        "FINNHUB_API_KEY",
        "ALPHAVANTAGE_API_KEY",
        "TIINGO_API_KEY",
        "FMP_API_KEY",
        "FRED_API_KEY",
        "VIBE_TRADING_IWENCAI_KEY",
        "VIBE_TRADING_SEC_UA",
        "VIBE_TRADING_DATA_CACHE",
        "VIBE_TRADING_ALLOWED_RUN_ROOTS",
        "CCXT_EXCHANGE",
        "CCXT_TIMEOUT_MS",
        "CCXT_FETCH_BUDGET_S",
        "OKX_TIMEOUT_S",
        "OKX_FETCH_BUDGET_S",
        "RSSHUB_BASE_URL",
        "RSSHUB_TIMEOUT_S",
        "RSSHUB_FETCH_BUDGET_S",
        "FUTU_HOST",
        "FUTU_PORT",
        "VIBE_TRADING_EASTMONEY_MIN_INTERVAL",
        "VIBE_TRADING_SINA_MIN_INTERVAL",
        "VIBE_TRADING_STOOQ_MIN_INTERVAL",
        "VIBE_TRADING_YAHOO_MIN_INTERVAL",
        "VIBE_TRADING_SEC_MIN_INTERVAL",
        "VIBE_TRADING_FINNHUB_MIN_INTERVAL",
        "VIBE_TRADING_ALPHAVANTAGE_MIN_INTERVAL",
        "VIBE_TRADING_TIINGO_MIN_INTERVAL",
        "VIBE_TRADING_FMP_MIN_INTERVAL",
        "VIBE_TRADING_FRED_MIN_INTERVAL",
        "VIBE_TRADING_IWENCAI_MIN_INTERVAL",
        "VIBE_TRADING_THS_MIN_INTERVAL",
    }
    | _PROXY_ENV_KEYS
)

_RUNTIME_ENV_PREFIXES = ("LC_",)


def _is_runtime_env_key_allowed(key: str) -> bool:
    """Return whether an environment key is safe for generated backtest code."""

    return key in _RUNTIME_ENV_KEYS or key.startswith(_RUNTIME_ENV_PREFIXES)


def _copy_runtime_env() -> dict[str, str]:
    """Copy the narrow environment needed by the backtest subprocess.

    Generated strategy code is executed in this subprocess, so avoid inheriting
    LLM, API server, broker, live-trading, or advisory credentials by default.
    The allowlist keeps OS/Python basics, proxy/cert settings, and read-only
    market-data configuration needed by the built-in loaders.
    """

    return {key: value for key, value in os.environ.items() if _is_runtime_env_key_allowed(key)}


@dataclass
class RunResult:
    """Container for runner execution outputs.

    Attributes:
        success: Whether subprocess exited with code 0.
        exit_code: Subprocess return code.
        stdout: Captured stdout text.
        stderr: Captured stderr text.
        artifacts: Existing artifact file paths keyed by artifact name.
        timed_out: Whether the subprocess exceeded the configured deadline.
        reason: Stable machine-readable failure reason, when applicable.
    """

    success: bool
    exit_code: int
    stdout: str
    stderr: str
    artifacts: dict[str, Path]
    timed_out: bool = False
    reason: str | None = None


_MAX_CAPTURE_BYTES = 256 * 1024
_CAPTURE_READ_BYTES = 64 * 1024
_MAX_CONSOLE_CHARS = 8 * 1024
_TIMEOUT_EXIT_CODE = 124
_TERMINATION_GRACE_SECONDS = 1.0


class _BoundedLogCapture:
    """Keep the newest subprocess output in a fixed-size on-disk ring."""

    def __init__(self, path: Path, max_bytes: int = _MAX_CAPTURE_BYTES) -> None:
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        self.path = path
        self.max_bytes = max_bytes
        self._handle = path.open("w+b")
        self._retained_bytes = 0
        self._total_bytes = 0
        self._write_offset = 0

    def write(self, payload: bytes) -> None:
        """Write bytes without ever allowing the backing file to exceed the cap."""

        if not payload:
            return

        self._total_bytes += len(payload)
        if len(payload) >= self.max_bytes:
            self._handle.seek(0)
            self._handle.write(payload[-self.max_bytes :])
            self._handle.truncate(self.max_bytes)
            self._retained_bytes = self.max_bytes
            self._write_offset = 0
            self._handle.flush()
            return

        if self._retained_bytes < self.max_bytes:
            available = self.max_bytes - self._retained_bytes
            initial = payload[:available]
            self._handle.seek(self._retained_bytes)
            self._handle.write(initial)
            self._retained_bytes += len(initial)
            self._write_offset = self._retained_bytes % self.max_bytes
            payload = payload[len(initial) :]

        if payload:
            first_length = min(len(payload), self.max_bytes - self._write_offset)
            self._handle.seek(self._write_offset)
            self._handle.write(payload[:first_length])
            if first_length < len(payload):
                self._handle.seek(0)
                self._handle.write(payload[first_length:])
            self._write_offset = (self._write_offset + len(payload)) % self.max_bytes

        self._handle.flush()

    def finalize(self, message: str | None = None) -> str:
        """Materialize a chronological tail and truncation marker, then close."""

        if message:
            self.write(("\n" + message.rstrip() + "\n").encode("utf-8"))

        tail = self._read_ordered_tail()
        output = self._with_truncation_marker(tail)
        self._handle.seek(0)
        self._handle.write(output)
        self._handle.truncate(len(output))
        self._handle.close()
        return output.decode("utf-8", errors="ignore")

    def close(self) -> None:
        """Close the backing file when process creation fails."""

        if not self._handle.closed:
            self._handle.close()

    def _read_ordered_tail(self) -> bytes:
        self._handle.flush()
        if self._retained_bytes < self.max_bytes:
            self._handle.seek(0)
            return self._handle.read(self._retained_bytes)

        self._handle.seek(self._write_offset)
        newest_tail = self._handle.read(self.max_bytes - self._write_offset)
        self._handle.seek(0)
        return newest_tail + self._handle.read(self._write_offset)

    def _with_truncation_marker(self, tail: bytes) -> bytes:
        """Prefix a complete marker when it fits, otherwise preserve the raw tail."""

        if self._total_bytes <= self.max_bytes:
            return tail

        retained = len(tail)
        while True:
            discarded = self._total_bytes - retained
            marker = (
                f"[runner output truncated: discarded {discarded} leading bytes; "
                f"retained final {retained} bytes]\n"
            ).encode("utf-8")
            available = self.max_bytes - len(marker)
            if available < 0:
                return tail[-self.max_bytes :]
            next_retained = min(len(tail), available)
            if next_retained == retained:
                retained_tail = tail[-retained:] if retained else b""
                return marker + retained_tail
            retained = next_retained


def _drain_sync_stream(stream: BinaryIO, capture: _BoundedLogCapture) -> None:
    """Drain one blocking subprocess pipe into a bounded capture."""

    try:
        while chunk := stream.read(_CAPTURE_READ_BYTES):
            capture.write(chunk)
    finally:
        stream.close()


async def _drain_async_stream(
    stream: asyncio.StreamReader,
    capture: _BoundedLogCapture,
) -> None:
    """Drain one asyncio subprocess pipe into a bounded capture."""

    while chunk := await stream.read(_CAPTURE_READ_BYTES):
        capture.write(chunk)


_ARTIFACTS_SPEC = {
    "defaults": {"required": ["equity", "metrics", "trades"]},
    "schemas": {
        "equity_csv": {
            "columns": [
                {"name": "timestamp", "type": "string"},
                {"name": "ret", "type": "float"},
                {"name": "equity", "type": "float"},
                {"name": "drawdown", "type": "float"},
            ],
        },
        "metrics_csv": {
            "columns": [
                {"name": "final_value", "type": "float"},
                {"name": "total_return", "type": "float"},
                {"name": "annual_return", "type": "float"},
                {"name": "max_drawdown", "type": "float"},
                {"name": "sharpe", "type": "float"},
                {"name": "win_rate", "type": "float"},
                {"name": "trade_count", "type": "integer"},
            ],
        },
        "trade_log": {
            "columns": [
                {"name": "timestamp", "type": "string"},
                {"name": "code", "type": "string"},
                {"name": "side", "type": "string"},
                {"name": "price", "type": "float"},
                {"name": "qty", "type": "float"},
                {"name": "reason", "type": "string"},
            ],
        },
    },
    "artifacts": {
        "equity": {"schema": "equity_csv", "path": "artifacts/equity.csv"},
        "metrics": {"schema": "metrics_csv", "path": "artifacts/metrics.csv"},
        "trades": {"schema": "trade_log", "path": "artifacts/trades.csv"},
        "positions": {"schema": "positions_csv", "path": "artifacts/positions.csv"},
        "run_card_json": {"schema": "json", "path": "run_card.json"},
        "run_card_md": {"schema": "markdown", "path": "run_card.md"},
    },
}


def _expand_artifacts_spec(spec: Dict[str, Any] | None) -> Dict[str, Dict[str, Any]]:
    """Expand artifacts_spec into a name -> metadata dict.

    Args:
        spec: Raw artifact spec.

    Returns:
        Expanded artifact metadata mapping.
    """
    if not isinstance(spec, dict):
        return {}
    schemas = spec.get("schemas") or {}
    artifacts = spec.get("artifacts") or {}
    defaults = spec.get("defaults") or {}
    required = set(defaults.get("required") or [])
    expanded: Dict[str, Dict[str, Any]] = {}
    for name, meta in artifacts.items():
        if not isinstance(meta, dict):
            continue
        schema_name = meta.get("schema")
        schema = schemas.get(schema_name, {}) if isinstance(schemas, dict) else {}
        expanded[name] = {
            "path": meta.get("path"),
            "required": bool(meta.get("required", name in required)),
            "columns": meta.get("columns") or schema.get("columns"),
        }
    return expanded


class Runner:
    """Execute entry scripts inside a run directory and collect outputs."""

    def __init__(self, timeout: float = 300, artifacts_spec: Optional[Dict[str, Any]] = None) -> None:
        """Initialize runner.

        Args:
            timeout: Max subprocess runtime in seconds.
            artifacts_spec: Artifact spec from config.
        """

        self.timeout = timeout
        self.artifacts_spec = artifacts_spec or _ARTIFACTS_SPEC
        self.artifact_entries = _expand_artifacts_spec(self.artifacts_spec)

    def _python_ready(self, python_cmd: str) -> bool:
        """Check whether a Python interpreter can import runtime dependencies.

        Args:
            python_cmd: Interpreter executable path.

        Returns:
            True if required imports succeed, otherwise False.
        """

        # macOS Python launched from a virtualenv can export this launcher
        # variable.  It overrides the interpreter prefix of child processes,
        # so a probe of the Trading venv may silently run against the API venv
        # instead.  The actual backtest environment is already allowlisted by
        # ``_copy_runtime_env``; remove the launcher for the probe as well.
        probe_env = os.environ.copy()
        probe_env.pop("__PYVENV_LAUNCHER__", None)

        try:
            probe = subprocess.run(
                [
                    python_cmd,
                    "-c",
                    "import pandas,numpy,yaml,pydantic,yfinance; print('ok')",
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=probe_env,
                text=True,
                timeout=20,
            )
            return probe.returncode == 0
        except Exception:
            return False

    def _pick_python_interpreter(self) -> str:
        """Pick the first usable interpreter for backtest execution.

        Returns:
            Interpreter command path.
        """

        for path in self._python_candidates():
            if not path.exists():
                continue
            cmd = str(path)
            if self._python_ready(cmd):
                return cmd
        # ``sys.executable`` can also be rewritten by the launcher variable;
        # use the base executable as the final fallback when available.
        return str(getattr(sys, "_base_executable", sys.executable))

    @staticmethod
    def _python_candidates() -> list[Path]:
        """Return local runtime candidates from narrowest to broadest scope."""
        agent_root = Path(__file__).resolve().parents[2]
        workspace_root = agent_root.parent
        return [
            workspace_root / ".venv" / "Scripts" / "python.exe",
            workspace_root / ".venv" / "bin" / "python",
            agent_root / ".venv" / "Scripts" / "python.exe",
            agent_root / ".venv" / "bin" / "python",
            Path(sys.executable),
        ]

    def _build_runtime_env(self, run_dir: Path, *, pythonpath_extra: Path | None = None) -> dict[str, str]:
        """Build subprocess env and enforce no-proxy execution.

        Args:
            run_dir: Current run directory.
            pythonpath_extra: Additional path to prepend to PYTHONPATH.

        Returns:
            Environment mapping for subprocess.
        """

        env = _copy_runtime_env()
        env.update(
            {
                "PYTHONUNBUFFERED": "1",
                "PYTHONIOENCODING": "utf-8",
                "PYTHONUTF8": "1",
            }
        )

        if pythonpath_extra:
            existing = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = str(pythonpath_extra) + (os.pathsep + existing if existing else "")

        # Preserve system proxy settings; data sources (OKX/yfinance) need network access
        # NOTE: do NOT override HOME/USERPROFILE — data libraries (yfinance, akshare)
        # cache downloads under ~/; overriding HOME causes full re-download every run.

        return env

    def _prepare_process(
        self,
        entry_script: Path,
        run_dir: Path,
        *,
        cwd: Path | None,
        cli_args: list[str] | None,
    ) -> tuple[list[str], Path, dict[str, str]]:
        """Build the shared command, working directory, and safe environment."""

        (run_dir / "logs").mkdir(parents=True, exist_ok=True)
        effective_cwd = cwd or entry_script.parent
        env = self._build_runtime_env(
            run_dir,
            pythonpath_extra=cwd if cwd else None,
        )
        python_cmd = self._pick_python_interpreter()
        console.print(f"[dim]Runner: using Python: {python_cmd}[/dim]")
        command = [python_cmd, str(entry_script)]
        if cli_args:
            command.extend(cli_args)
        return command, effective_cwd, env

    def _finalize_result(
        self,
        run_dir: Path,
        *,
        returncode: int,
        stdout: str,
        stderr: str,
        timed_out: bool = False,
        reason: str | None = None,
    ) -> RunResult:
        """Persist process logs and collect the declared artifacts."""

        logs_dir = run_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        (logs_dir / "runner_stdout.txt").write_text(stdout, encoding="utf-8")
        (logs_dir / "runner_stderr.txt").write_text(stderr, encoding="utf-8")

        success = returncode == 0 and not timed_out and reason is None
        (logs_dir / "runner_result.json").write_text(
            json.dumps(
                {
                    "success": success,
                    "exit_code": returncode,
                    "timed_out": timed_out,
                    "reason": reason,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        if stdout:
            console.print(f"[dim]Runner stdout:[/dim]\n{stdout[-_MAX_CONSOLE_CHARS:]}")
        if stderr:
            console.print(f"[red]Runner stderr:[/red]\n{stderr[-_MAX_CONSOLE_CHARS:]}")

        artifacts: dict[str, Path] = {}
        for name, info in self.artifact_entries.items():
            rel_path = info.get("path")
            if not isinstance(rel_path, str) or not rel_path.strip():
                continue
            target = run_dir / Path(rel_path)
            if target.exists():
                artifacts[name] = target

        return RunResult(
            success=success,
            exit_code=returncode,
            stdout=stdout,
            stderr=stderr,
            artifacts=artifacts,
            timed_out=timed_out,
            reason=reason,
        )

    @staticmethod
    def _log_paths(run_dir: Path) -> tuple[Path, Path]:
        """Return bounded-capture log paths, creating their parent directory."""

        logs_dir = run_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        return logs_dir / "runner_stdout.txt", logs_dir / "runner_stderr.txt"

    def _finalize_captures(
        self,
        run_dir: Path,
        *,
        returncode: int,
        stdout_capture: _BoundedLogCapture,
        stderr_capture: _BoundedLogCapture,
        stderr_message: str | None = None,
        timed_out: bool = False,
        reason: str | None = None,
    ) -> RunResult:
        """Materialize both capture rings and build the persisted result."""

        return self._finalize_result(
            run_dir,
            returncode=returncode,
            stdout=stdout_capture.finalize(),
            stderr=stderr_capture.finalize(stderr_message),
            timed_out=timed_out,
            reason=reason,
        )

    @staticmethod
    def _process_group_kwargs() -> dict[str, Any]:
        """Start each backtest in an independently terminable process group."""

        if os.name == "posix":
            return {"start_new_session": True}
        if os.name == "nt":
            return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        return {}

    @staticmethod
    def _process_group_alive(process_id: int) -> bool:
        """Return whether a POSIX process group still has any members."""

        if os.name != "posix":
            return False
        try:
            os.killpg(process_id, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    @staticmethod
    def _signal_process_group(process_id: int, sig: int) -> None:
        """Best-effort signal delivery to a dedicated POSIX process group."""

        try:
            os.killpg(process_id, sig)
        except ProcessLookupError:
            pass

    @staticmethod
    def _taskkill_windows_process_tree(process_id: int) -> None:
        """Force-stop a Windows process tree without adding a runtime package."""

        subprocess.run(
            ["taskkill", "/PID", str(process_id), "/T", "/F"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )

    def _terminate_sync_process_tree(self, process: subprocess.Popen[Any]) -> None:
        """Terminate a synchronous child and all descendants, then reap it."""

        if os.name == "posix":
            self._signal_process_group(process.pid, signal.SIGTERM)
            deadline = time.monotonic() + _TERMINATION_GRACE_SECONDS
            while self._process_group_alive(process.pid) and time.monotonic() < deadline:
                process.poll()
                time.sleep(0.02)
            if self._process_group_alive(process.pid):
                self._signal_process_group(process.pid, signal.SIGKILL)
        elif os.name == "nt":
            try:
                self._taskkill_windows_process_tree(process.pid)
            except (OSError, subprocess.SubprocessError):
                if process.poll() is None:
                    process.kill()
        elif process.poll() is None:
            process.kill()

        try:
            process.wait(timeout=_TERMINATION_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            if process.poll() is None:
                process.kill()
            process.wait()

    async def _terminate_async_process_tree(
        self,
        process: asyncio.subprocess.Process,
        wait_task: asyncio.Task[int],
    ) -> None:
        """Terminate an async child group without interrupting cancellation cleanup."""

        if os.name == "posix":
            self._signal_process_group(process.pid, signal.SIGTERM)
            deadline = asyncio.get_running_loop().time() + _TERMINATION_GRACE_SECONDS
            while (
                self._process_group_alive(process.pid)
                and asyncio.get_running_loop().time() < deadline
            ):
                await asyncio.sleep(0.02)
            if self._process_group_alive(process.pid):
                self._signal_process_group(process.pid, signal.SIGKILL)
        elif os.name == "nt":
            try:
                await asyncio.to_thread(self._taskkill_windows_process_tree, process.pid)
            except (OSError, subprocess.SubprocessError):
                if process.returncode is None:
                    process.kill()
        elif process.returncode is None:
            process.kill()

        try:
            await asyncio.wait_for(
                asyncio.shield(wait_task),
                timeout=_TERMINATION_GRACE_SECONDS,
            )
        except TimeoutError:
            if process.returncode is None:
                process.kill()
            await wait_task

    async def _finalize_async_cancellation(
        self,
        run_dir: Path,
        *,
        process: asyncio.subprocess.Process,
        wait_task: asyncio.Task[int],
        drain_future: asyncio.Future[list[None]],
        stdout_capture: _BoundedLogCapture,
        stderr_capture: _BoundedLogCapture,
    ) -> None:
        """Reap a cancelled run, drain its pipes, and persist the terminal state."""

        process_tree_alive = process.returncode is None or (
            os.name == "posix" and self._process_group_alive(process.pid)
        )
        if process_tree_alive:
            await self._terminate_async_process_tree(process, wait_task)
        else:
            await asyncio.shield(wait_task)

        await asyncio.shield(drain_future)
        self._finalize_captures(
            run_dir,
            returncode=process.returncode if process.returncode is not None else -15,
            stdout_capture=stdout_capture,
            stderr_capture=stderr_capture,
            stderr_message=(
                "backtest cancelled; process group terminated"
                if process_tree_alive
                else "backtest cancelled after process exit; output drained"
            ),
            reason="cancelled",
        )

    def execute(
        self,
        entry_script: Path,
        run_dir: Path,
        *,
        cwd: Path | None = None,
        cli_args: list[str] | None = None,
    ) -> RunResult:
        """Run entry script and collect logs and artifacts.

        Args:
            entry_script: Entry script path.
            run_dir: Current run directory.
            cwd: Working directory for subprocess (default: entry_script.parent).
            cli_args: Additional CLI arguments appended to subprocess command.

        Returns:
            RunResult object with process output and discovered artifacts.
        """

        console.print(f"[blue]Runner: executing {entry_script}[/blue]")
        start_time = time.time()
        console.print("[dim]Runner: starting backtest subprocess...[/dim]")
        cmd, effective_cwd, env = self._prepare_process(
            entry_script,
            run_dir,
            cwd=cwd,
            cli_args=cli_args,
        )

        stdout_path, stderr_path = self._log_paths(run_dir)
        stdout_capture = _BoundedLogCapture(stdout_path)
        stderr_capture = _BoundedLogCapture(stderr_path)
        try:
            process = subprocess.Popen(
                cmd,
                cwd=str(effective_cwd),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                **self._process_group_kwargs(),
            )
        except BaseException:
            stdout_capture.close()
            stderr_capture.close()
            raise

        assert process.stdout is not None
        assert process.stderr is not None
        drain_threads = [
            threading.Thread(
                target=_drain_sync_stream,
                args=(process.stdout, stdout_capture),
                daemon=True,
            ),
            threading.Thread(
                target=_drain_sync_stream,
                args=(process.stderr, stderr_capture),
                daemon=True,
            ),
        ]
        for thread in drain_threads:
            thread.start()

        try:
            returncode = process.wait(timeout=self.timeout)
        except subprocess.TimeoutExpired:
            self._terminate_sync_process_tree(process)
            for thread in drain_threads:
                thread.join()
            reason = f"backtest timed out after {self.timeout:g} seconds"
            return self._finalize_captures(
                run_dir,
                returncode=_TIMEOUT_EXIT_CODE,
                stdout_capture=stdout_capture,
                stderr_capture=stderr_capture,
                stderr_message=reason,
                timed_out=True,
                reason="timeout",
            )
        except BaseException:
            self._terminate_sync_process_tree(process)
            for thread in drain_threads:
                thread.join()
            self._finalize_captures(
                run_dir,
                returncode=process.returncode if process.returncode is not None else -15,
                stdout_capture=stdout_capture,
                stderr_capture=stderr_capture,
                stderr_message="backtest cancelled; process group terminated",
                reason="cancelled",
            )
            raise

        for thread in drain_threads:
            thread.join()

        elapsed = time.time() - start_time
        console.print(f"[blue]Runner: subprocess finished in {elapsed:.2f}s[/blue]")
        return self._finalize_captures(
            run_dir,
            returncode=returncode,
            stdout_capture=stdout_capture,
            stderr_capture=stderr_capture,
        )

    async def execute_async(
        self,
        entry_script: Path,
        run_dir: Path,
        *,
        cwd: Path | None = None,
        cli_args: list[str] | None = None,
    ) -> RunResult:
        """Run the same fixed entrypoint asynchronously with real cancellation.

        Cancelling the awaiting task terminates the child process before the
        cancellation propagates. This keeps HTTP job cancellation from leaving
        an orphaned pandas/backtest process behind.
        """

        console.print(f"[blue]Runner: executing {entry_script}[/blue]")
        started_at = time.time()
        cmd, effective_cwd, env = await asyncio.to_thread(
            self._prepare_process,
            entry_script,
            run_dir,
            cwd=cwd,
            cli_args=cli_args,
        )
        stdout_path, stderr_path = self._log_paths(run_dir)
        stdout_capture = _BoundedLogCapture(stdout_path)
        stderr_capture = _BoundedLogCapture(stderr_path)
        cancelled_during_spawn = False
        try:
            spawn_task = asyncio.create_task(
                asyncio.create_subprocess_exec(
                    *cmd,
                    cwd=str(effective_cwd),
                    stdin=subprocess.DEVNULL,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                    **self._process_group_kwargs(),
                )
            )
            try:
                process = await asyncio.shield(spawn_task)
            except asyncio.CancelledError:
                cancelled_during_spawn = True
                process = await spawn_task
        except BaseException:
            stdout_capture.close()
            stderr_capture.close()
            raise

        assert process.stdout is not None
        assert process.stderr is not None
        drain_tasks = [
            asyncio.create_task(_drain_async_stream(process.stdout, stdout_capture)),
            asyncio.create_task(_drain_async_stream(process.stderr, stderr_capture)),
        ]
        drain_future = asyncio.gather(*drain_tasks)
        wait_task = asyncio.create_task(process.wait())

        try:
            if cancelled_during_spawn:
                raise asyncio.CancelledError

            try:
                returncode = await asyncio.wait_for(
                    asyncio.shield(wait_task),
                    timeout=self.timeout,
                )
            except TimeoutError:
                await self._terminate_async_process_tree(process, wait_task)
                await asyncio.shield(drain_future)
                reason = f"backtest timed out after {self.timeout:g} seconds"
                return self._finalize_captures(
                    run_dir,
                    returncode=_TIMEOUT_EXIT_CODE,
                    stdout_capture=stdout_capture,
                    stderr_capture=stderr_capture,
                    stderr_message=reason,
                    timed_out=True,
                    reason="timeout",
                )

            await asyncio.shield(drain_future)
            elapsed = time.time() - started_at
            console.print(f"[blue]Runner: subprocess finished in {elapsed:.2f}s[/blue]")
            return self._finalize_captures(
                run_dir,
                returncode=returncode,
                stdout_capture=stdout_capture,
                stderr_capture=stderr_capture,
            )
        except asyncio.CancelledError:
            cleanup_task = asyncio.create_task(
                self._finalize_async_cancellation(
                    run_dir,
                    process=process,
                    wait_task=wait_task,
                    drain_future=drain_future,
                    stdout_capture=stdout_capture,
                    stderr_capture=stderr_capture,
                )
            )
            while True:
                try:
                    await asyncio.shield(cleanup_task)
                    break
                except asyncio.CancelledError:
                    if cleanup_task.done():
                        raise
            raise
