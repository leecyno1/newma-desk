from __future__ import annotations

import json
import threading
import time
from typing import Any
from urllib.parse import urlparse

import requests


class DeskAgentError(RuntimeError):
    """Desk Agent task failed or returned an unusable result."""


class DeskAgentClient:
    """Small synchronous client for stateless Deepsee batch work.

    The gateway owns CLI discovery and model selection. Deepsee only submits a
    task and waits for its result, so the legacy model path remains independent
    and can be used as a fallback.
    """

    _slots = threading.BoundedSemaphore(3)

    def __init__(
        self,
        base_url: str,
        *,
        module_id: str = "deepsee-news",
        adapter: str = "",
        model: str = "",
        command_profile: str = "batch",
        token: str = "",
        timeout_seconds: int = 180,
        poll_seconds: float = 0.4,
    ) -> None:
        self.base_url = str(base_url or "").strip().rstrip("/")
        self.module_id = str(module_id or "deepsee-news").strip()
        self.adapter = str(adapter or "").strip()
        self.model = str(model or "").strip()
        self.command_profile = str(command_profile or "batch").strip()
        self.token = str(token or "").strip()
        self.timeout_seconds = max(10, min(900, int(timeout_seconds or 180)))
        self.poll_seconds = max(0.15, min(2.0, float(poll_seconds or 0.4)))

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "DeskAgentClient | None":
        raw = config.get("desk_agent") if isinstance(config, dict) else None
        if not isinstance(raw, dict) or not bool(raw.get("enabled")):
            return None
        base_url = str(raw.get("base_url") or "").strip()
        if not base_url:
            return None
        return cls(
            base_url,
            module_id=str(raw.get("module_id") or "deepsee-news"),
            adapter=str(raw.get("adapter") or ""),
            model=str(raw.get("model") or ""),
            command_profile=str(raw.get("command_profile") or "batch"),
            token=str(raw.get("token") or ""),
            timeout_seconds=int(raw.get("timeout_seconds") or 180),
        )

    def summarize(
        self,
        messages: list[dict[str, Any]],
        prompt_messages: list[dict[str, str]],
        *,
        module_id: str = "",
        capability: str = "deepsee.news.batch-analyze",
        operation: str = "message-summary",
    ) -> str:
        if not self.base_url:
            raise DeskAgentError("Desk Agent 地址未配置")
        payload = {
            "moduleId": str(module_id or self.module_id).strip(),
            "capability": capability,
            "profile": "batch",
            "commandProfile": self.command_profile,
            "memoryScope": "task",
            "prompt": self._prompt(prompt_messages),
            # The prompt already contains the message bodies. Only send IDs in
            # module input so the local CLI does not receive every body twice.
            "input": {
                "itemIds": [str(item.get("id") or "") for item in messages],
            },
            "context": {
                "source": "deepsee",
                "operation": operation,
                "stateless": True,
            },
        }
        if self.adapter:
            payload["adapter"] = self.adapter
        if self.model:
            payload["model"] = self.model
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        deadline = time.monotonic() + self.timeout_seconds
        task_id = ""
        terminal = False
        with self._slots:
            try:
                response = requests.post(
                    f"{self.base_url}/api/agent/tasks",
                    json=payload,
                    headers=headers,
                    timeout=min(20, self.timeout_seconds),
                    **self._request_options(),
                )
                response.raise_for_status()
                task = response.json()
                task_id = str(task.get("id") or "").strip()
                if not task_id:
                    raise DeskAgentError("Desk Agent 未返回任务 ID")
                while time.monotonic() < deadline:
                    current = requests.get(
                        f"{self.base_url}/api/agent/tasks/{task_id}",
                        headers=headers,
                        timeout=min(10, self.timeout_seconds),
                        **self._request_options(),
                    )
                    current.raise_for_status()
                    body = current.json()
                    status = str(body.get("status") or "").lower()
                    if status == "completed":
                        terminal = True
                        result = body.get("result") or {}
                        answer = result.get("answer") or result.get("message")
                        if isinstance(answer, str) and answer.strip():
                            return answer.strip()
                        raise DeskAgentError("Desk Agent 返回为空")
                    if status in {"failed", "cancelled"}:
                        terminal = True
                        detail = body.get("error") or (body.get("result") or {}).get("error")
                        raise DeskAgentError(str(detail or f"任务{status}"))
                    time.sleep(self.poll_seconds)
            except DeskAgentError:
                if task_id and not terminal:
                    self._cancel_task(task_id, headers)
                raise
            except requests.RequestException as exc:
                if task_id and not terminal:
                    self._cancel_task(task_id, headers)
                raise DeskAgentError(f"Desk Agent 请求失败: {exc}") from exc
            except Exception:
                if task_id and not terminal:
                    self._cancel_task(task_id, headers)
                raise
        if task_id and not terminal:
            self._cancel_task(task_id, headers)
        raise DeskAgentError("Desk Agent 任务超时")

    def _cancel_task(self, task_id: str, headers: dict[str, str]) -> None:
        try:
            requests.post(
                f"{self.base_url}/api/agent/tasks/{task_id}/cancel",
                headers=headers,
                timeout=5,
                **self._request_options(),
            )
        except requests.RequestException:
            pass

    def _request_options(self) -> dict[str, Any]:
        host = urlparse(self.base_url).hostname
        if host in {"127.0.0.1", "localhost", "::1"}:
            return {"proxies": {"http": None, "https": None, "socks": None}}
        return {}

    @staticmethod
    def _prompt(prompt_messages: list[dict[str, str]]) -> str:
        parts: list[str] = []
        for item in prompt_messages:
            role = str(item.get("role") or "user").upper()
            content = str(item.get("content") or "").strip()
            if content:
                parts.append(f"{role}:\n{content}")
        parts.append("只返回符合要求的 JSON，不要代码块，不要解释。")
        return "\n\n".join(parts)
