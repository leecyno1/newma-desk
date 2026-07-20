import json

import httpx

from vibe_visualization_api.config import Settings
from vibe_visualization_api.model_gateway.errors import ModelGatewayError
from vibe_visualization_api.model_gateway.models import (
    ModelResponse,
    ModelResponseCreate,
)


class AnthropicModelAdapter:
    id = "anthropic"

    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient | None = None,
    ):
        self._settings = settings
        self._client = client
        self._endpoint = f"{settings.anthropic_base_url}/messages"
        self._timeout = httpx.Timeout(settings.model_timeout_seconds)

    async def capabilities(self) -> list[str]:
        return ["chat", "module.explain", "module.generate-view"]

    async def complete(self, request: ModelResponseCreate) -> ModelResponse:
        api_key = self._settings.anthropic_api_key.get_secret_value()
        if not api_key:
            raise ModelGatewayError(
                "missing_api_key",
                "Anthropic model provider is not configured",
                503,
            )
        model = request.model or self._settings.anthropic_model
        payload = {
            "model": model,
            "max_tokens": self._settings.anthropic_max_tokens,
            "system": (
                "You are a model connected to a modular visualization "
                "workspace. Answer only the requested module task."
            ),
            "messages": [
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "moduleId": request.module_id,
                            "capability": request.capability,
                            "prompt": request.prompt,
                            "context": request.context,
                            "input": request.input,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                }
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
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": self._settings.anthropic_version,
                },
                json=payload,
                timeout=self._timeout,
                follow_redirects=False,
            )
        except httpx.TimeoutException as error:
            raise ModelGatewayError(
                "upstream_timeout",
                "Anthropic model provider timed out",
                504,
            ) from error
        except httpx.RequestError as error:
            raise ModelGatewayError(
                "upstream_unavailable",
                "Anthropic model provider is unavailable",
                502,
            ) from error
        finally:
            if owns_client:
                await client.aclose()

        if response.status_code in {401, 403}:
            raise ModelGatewayError(
                "upstream_authentication_failed",
                "Anthropic model provider authentication failed",
                502,
            )
        if response.status_code == 429:
            raise ModelGatewayError(
                "upstream_rate_limited",
                "Anthropic model provider rate limit exceeded",
                502,
            )
        if not 200 <= response.status_code < 300:
            raise ModelGatewayError(
                "upstream_unavailable",
                "Anthropic model provider is unavailable",
                502,
            )
        answer = self._response_content(response)
        if answer is None:
            raise ModelGatewayError(
                "invalid_upstream_response",
                "Anthropic model provider returned an invalid response",
                502,
            )
        return ModelResponse(answer=answer, adapter=self.id, model=model)

    @staticmethod
    def _response_content(response: httpx.Response) -> str | None:
        try:
            body = response.json()
            content = body.get("content")
            text_parts = [
                part.get("text")
                for part in content
                if isinstance(part, dict)
                and part.get("type") == "text"
                and isinstance(part.get("text"), str)
            ]
        except (AttributeError, TypeError, ValueError):
            return None
        answer = "".join(text_parts).strip()
        return answer or None
