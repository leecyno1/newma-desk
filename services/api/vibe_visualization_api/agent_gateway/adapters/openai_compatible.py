import json
from collections.abc import AsyncIterator

import httpx

from vibe_visualization_api.agent_gateway.models import (
    AdapterEvent,
    AgentTaskCreate,
)
from vibe_visualization_api.config import Settings


class OpenAICompatibleAdapter:
    id = "openai-compatible"

    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient | None = None,
    ):
        self._settings = settings
        self._client = client
        self._endpoint = f"{settings.openai_base_url}/chat/completions"
        self._timeout = httpx.Timeout(settings.agent_timeout_seconds)

    async def capabilities(self) -> list[str]:
        return ["chat", "module.explain", "module.generate-view"]

    async def run(
        self,
        request: AgentTaskCreate,
    ) -> AsyncIterator[AdapterEvent]:
        yield AdapterEvent(type="progress", data={"message": "calling model"})

        api_key = self._settings.openai_api_key.get_secret_value()
        if not api_key:
            yield AdapterEvent(
                type="failed",
                data={
                    "code": "missing_api_key",
                    "error": "Agent provider is not configured",
                },
            )
            return

        payload = {
            "model": self._settings.openai_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are the Agent Gateway for a modular visualization "
                        "workspace. Answer the requested module task."
                    ),
                },
                {
                    "role": "user",
                    "content": self._user_message(request),
                },
            ],
        }
        client = self._client or httpx.AsyncClient(
            timeout=self._timeout,
            follow_redirects=False,
        )
        owns_client = self._client is None
        try:
            response = await client.post(
                self._endpoint,
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
                timeout=self._timeout,
                follow_redirects=False,
            )
        except httpx.TimeoutException:
            yield self._failed(
                "upstream_timeout",
                "Agent provider timed out",
            )
            return
        except httpx.RequestError:
            yield self._failed(
                "upstream_unavailable",
                "Agent provider is unavailable",
            )
            return
        finally:
            if owns_client:
                await client.aclose()

        if response.status_code in {401, 403}:
            yield self._failed(
                "upstream_authentication_failed",
                "Agent provider authentication failed",
            )
            return
        if response.status_code == 429:
            yield self._failed(
                "upstream_rate_limited",
                "Agent provider rate limit exceeded",
            )
            return
        if response.status_code >= 500:
            yield self._failed(
                "upstream_unavailable",
                "Agent provider is unavailable",
            )
            return
        if not 200 <= response.status_code < 300:
            yield self._failed(
                "upstream_rejected",
                "Agent provider rejected the request",
            )
            return

        content = self._response_content(response)
        if content is None:
            yield self._failed(
                "invalid_upstream_response",
                "Agent provider returned an invalid response",
            )
            return
        yield AdapterEvent(type="completed", data={"answer": content})

    async def cancel(self, task_id: str) -> None:
        return None

    @staticmethod
    def _user_message(request: AgentTaskCreate) -> str:
        return json.dumps(
            {
                "moduleId": request.module_id,
                "capability": request.capability,
                "prompt": request.prompt,
                "context": request.context,
                "input": request.input,
            },
            ensure_ascii=False,
            sort_keys=True,
        )

    @staticmethod
    def _failed(code: str, error: str) -> AdapterEvent:
        return AdapterEvent(type="failed", data={"code": code, "error": error})

    @staticmethod
    def _response_content(response: httpx.Response) -> str | None:
        try:
            body = response.json()
            choices = body.get("choices")
            message = choices[0].get("message")
            content = message.get("content")
        except (AttributeError, IndexError, TypeError, ValueError):
            return None
        return content if isinstance(content, str) else None
