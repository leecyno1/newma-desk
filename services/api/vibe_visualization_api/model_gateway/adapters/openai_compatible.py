import json

import httpx

from vibe_visualization_api.config import Settings
from vibe_visualization_api.model_gateway.errors import ModelGatewayError
from vibe_visualization_api.model_gateway.models import (
    ModelResponse,
    ModelResponseCreate,
)


class OpenAICompatibleModelAdapter:
    id = "openai-compatible"

    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient | None = None,
    ):
        self._settings = settings
        self._client = client
        self._endpoint = f"{settings.openai_base_url}/chat/completions"
        self._timeout = httpx.Timeout(settings.model_timeout_seconds)
        self._fallback_models = tuple(
            model.strip()
            for model in settings.openai_fallback_models.split(",")
            if model.strip()
        )

    async def capabilities(self) -> list[str]:
        return ["chat", "module.explain", "module.generate-view"]

    async def complete(self, request: ModelResponseCreate) -> ModelResponse:
        api_key = self._settings.openai_api_key.get_secret_value()
        if self._settings.openai_api_key_required and not api_key:
            raise ModelGatewayError(
                "missing_api_key",
                "Model provider is not configured",
                503,
            )

        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        client = self._client or httpx.AsyncClient(
            timeout=self._timeout,
            follow_redirects=False,
        )
        owns_client = self._client is None
        try:
            models = self._candidate_models(request)
            for index, model in enumerate(models):
                has_fallback = index + 1 < len(models)
                payload = {
                    "model": model,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a model connected to a modular "
                                "visualization workspace. Answer only the "
                                "requested module task."
                            ),
                        },
                        {
                            "role": "user",
                            "content": self._user_message(request),
                        },
                    ],
                }
                try:
                    response = await client.post(
                        self._endpoint,
                        headers=headers,
                        json=payload,
                        timeout=self._timeout,
                        follow_redirects=False,
                    )
                except httpx.TimeoutException as error:
                    raise ModelGatewayError(
                        "upstream_timeout",
                        "Model provider timed out",
                        504,
                    ) from error
                except httpx.RequestError as error:
                    raise ModelGatewayError(
                        "upstream_unavailable",
                        "Model provider is unavailable",
                        502,
                    ) from error

                if response.status_code in {429} or response.status_code >= 500:
                    if has_fallback:
                        continue
                return self._model_response(response, model)
        finally:
            if owns_client:
                await client.aclose()

        raise ModelGatewayError(
            "upstream_unavailable",
            "Model provider is unavailable",
            502,
        )

    def _candidate_models(self, request: ModelResponseCreate) -> tuple[str, ...]:
        primary = request.model or self._settings.openai_model
        if request.model is not None:
            return (primary,)
        return tuple(dict.fromkeys((primary, *self._fallback_models)))

    def _model_response(
        self,
        response: httpx.Response,
        model: str,
    ) -> ModelResponse:
        if response.status_code in {401, 403}:
            raise ModelGatewayError(
                "upstream_authentication_failed",
                "Model provider authentication failed",
                502,
            )
        if response.status_code == 429:
            raise ModelGatewayError(
                "upstream_rate_limited",
                "Model provider rate limit exceeded",
                502,
            )
        if response.status_code >= 500:
            raise ModelGatewayError(
                "upstream_unavailable",
                "Model provider is unavailable",
                502,
            )
        if not 200 <= response.status_code < 300:
            raise ModelGatewayError(
                "upstream_rejected",
                "Model provider rejected the request",
                502,
            )

        content = self._response_content(response)
        if content is None:
            raise ModelGatewayError(
                "invalid_upstream_response",
                "Model provider returned an invalid response",
                502,
            )
        return ModelResponse(answer=content, adapter=self.id, model=model)

    @staticmethod
    def _user_message(request: ModelResponseCreate) -> str:
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
    def _response_content(response: httpx.Response) -> str | None:
        try:
            body = response.json()
            choices = body.get("choices")
            message = choices[0].get("message")
            content = message.get("content")
        except (AttributeError, IndexError, TypeError, ValueError):
            return None
        return content if isinstance(content, str) else None
