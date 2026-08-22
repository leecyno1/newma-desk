from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from threading import Event
from typing import Any

from vibe_visualization_api.creator_studio.registry import (
    CreatorStudioUnavailableError,
)


class CreatorControlAdapter:
    """Adapter for the existing media project's allowlisted control commands."""

    def __init__(self, workspace: Path):
        self.workspace = workspace.expanduser().resolve()
        self.script = self.workspace / "scripts" / "newma_creator_control.py"
        workspace_python = self.workspace / ".venv" / "bin" / "python"
        self.python = workspace_python if workspace_python.is_file() else Path(sys.executable)

    def _invoke(
        self,
        command: str,
        *command_args: str,
        payload: dict[str, Any] | None = None,
        timeout: int = 30,
        allow_failure: bool = False,
    ) -> dict[str, Any]:
        if not self.script.is_file():
            raise CreatorStudioUnavailableError(
                f"Creator Studio control adapter unavailable: {self.script}"
            )
        result = subprocess.run(
            [str(self.python), str(self.script), command, *command_args],
            cwd=self.workspace,
            input=json.dumps(payload, ensure_ascii=False) if payload is not None else None,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise CreatorStudioUnavailableError(
                "Creator Studio control adapter returned invalid JSON"
            ) from error
        if not allow_failure and (result.returncode != 0 or payload.get("status") == "failed"):
            raise CreatorStudioUnavailableError(
                str(payload.get("error") or result.stderr or "control adapter failed")
            )
        return payload

    def detect_capabilities(self) -> dict[str, Any]:
        return self._invoke("detect-capabilities", timeout=20)

    def approve_gate(
        self, run_id: str, stage: str, selected_ids: list[str] | None = None
    ) -> dict[str, Any]:
        """Review gate approve 联动：把 media 侧阶段 gate 文件状态翻 approved。

        gate 文件缺失（missing）属正常业务结果，不视为失败。
        selected_ids 非空时写入选题 gate（selected_topics.json）的选择结果。
        """
        args = ["--run-id", run_id, "--stage", stage]
        if selected_ids:
            args += ["--selected-ids", ",".join(selected_ids)]
        return self._invoke(
            "approve-gate",
            *args,
            timeout=20,
            allow_failure=True,
        )

    def test_agent(self, agent_id: str, bin_override: str = "") -> dict[str, Any]:
        """Invoke a short hello prompt via the specified agent to verify it works."""
        args = [
            "--agent", agent_id,
            "--prompt", "Reply with exactly: AGENT_TEST_OK",
            "--timeout", "30",
            "--workdir", str(self.workspace),
        ]
        if bin_override.strip():
            args.extend(["--bin-override", bin_override.strip()])
        # A failed CLI check is a usable result for the settings page; it should
        # not turn into a transport-level HTTP 500/503.
        return self._invoke(
            "invoke-cli",
            *args,
            timeout=45,
            allow_failure=True,
        )

    def marketplace(self) -> dict[str, Any]:
        return self._invoke("marketplace", timeout=30)

    def marketplace_asset(self, asset_path: str) -> Path:
        candidate = (self.workspace / asset_path).resolve()
        try:
            candidate.relative_to(self.workspace)
        except ValueError as error:
            raise FileNotFoundError(asset_path) from error
        if candidate.suffix.lower() not in {
            ".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".mp4", ".webm",
        } or not candidate.is_file():
            raise FileNotFoundError(asset_path)
        return candidate

    @staticmethod
    def _terminate(process: subprocess.Popen[str]) -> None:
        try:
            if os.name != "nt":
                os.killpg(process.pid, signal.SIGTERM)
            else:
                process.terminate()
            process.wait(timeout=1)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            if process.poll() is None:
                if os.name != "nt":
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
                process.wait(timeout=1)

    def run_node(
        self,
        request: dict[str, Any],
        *,
        cancel_event: Event | None = None,
    ) -> dict[str, Any]:
        if not self.script.is_file():
            raise CreatorStudioUnavailableError(
                f"Creator Studio control adapter unavailable: {self.script}"
            )
        started = time.monotonic()
        with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as stdout_file:
            with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as stderr_file:
                process = subprocess.Popen(
                    [str(self.python), str(self.script), "run-node"],
                    cwd=self.workspace,
                    stdin=subprocess.PIPE,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    text=True,
                    start_new_session=os.name != "nt",
                )
                assert process.stdin is not None
                try:
                    process.stdin.write(json.dumps(request, ensure_ascii=False))
                    process.stdin.close()
                except BrokenPipeError:
                    pass
                deadline = started + int(request.get("timeout_seconds") or 3600)
                while process.poll() is None:
                    if cancel_event is not None and cancel_event.wait(0.1):
                        self._terminate(process)
                        return {
                            "status": "cancelled",
                            "progress": 0,
                            "duration_ms": round((time.monotonic() - started) * 1000),
                            "logs": [{"message": "节点执行已取消。"}],
                        }
                    if time.monotonic() >= deadline:
                        self._terminate(process)
                        return {
                            "status": "failed",
                            "progress": 0,
                            "duration_ms": round((time.monotonic() - started) * 1000),
                            "error": "Creator node execution timed out",
                            "logs": [{"message": "节点执行超时。"}],
                        }
                    time.sleep(0.05)
                stdout_file.seek(0)
                stderr_file.seek(0)
                stdout = stdout_file.read()
                stderr = stderr_file.read()

        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as error:
            raise CreatorStudioUnavailableError(
                str(stderr or "Creator Studio control adapter returned invalid JSON")
            ) from error
        if not isinstance(payload, dict):
            raise CreatorStudioUnavailableError(
                "Creator Studio control adapter returned invalid payload"
            )
        if process.returncode != 0 and payload.get("status") != "failed":
            payload["status"] = "failed"
            payload["error"] = payload.get("error") or stderr or "control adapter failed"
        return payload

    def launch_editor(self, request: dict[str, Any]) -> dict[str, Any]:
        return self._invoke(
            "launch-editor",
            payload=request,
            timeout=40,
            allow_failure=True,
        )
