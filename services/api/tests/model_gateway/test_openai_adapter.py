import json

import httpx
import pytest

from vibe_visualization_api.config import Settings
from vibe_visualization_api.model_gateway.adapters.openai_compatible import (
    OpenAICompatibleModelAdapter,
)
from vibe_visualization_api.model_gateway.errors import ModelGatewayError
from vibe_visualization_api.model_gateway.models import ModelResponseCreate


def _settings(**changes: object) -> Settings:
    values: dict[str, object] = {
        "openai_api_key": "server-secret-key",
        "openai_base_url": "https://models.example.test/v1",
        "openai_model": "gpt-5.6",
    }
    values.update(changes)
    return Settings(**values)


@pytest.mark.asyncio
async def test_openai_adapter_sends_server_auth_and_module_context() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("authorization")
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "异动解释"}}]},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = OpenAICompatibleModelAdapter(_settings(), client=client)
    try:
        response = await adapter.complete(
            ModelResponseCreate(
                module_id="market-daily",
                capability="market.explain",
                prompt="解释今天的异动",
                context={"securityCode": "600519"},
                input={"date": "2026-07-20"},
                model="gpt-5.6-mini",
            )
        )
    finally:
        await client.aclose()

    assert response.answer == "异动解释"
    assert response.adapter == "openai-compatible"
    assert response.model == "gpt-5.6-mini"
    assert captured["url"] == "https://models.example.test/v1/chat/completions"
    assert captured["authorization"] == "Bearer server-secret-key"
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["model"] == "gpt-5.6-mini"
    user_content = json.loads(payload["messages"][-1]["content"])
    assert user_content["moduleId"] == "market-daily"
    assert user_content["context"] == {"securityCode": "600519"}
    assert "server-secret-key" not in json.dumps(payload)


@pytest.mark.asyncio
async def test_openai_adapter_maps_authentication_failure_safely() -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                401,
                json={"error": {"message": "bad server-secret-key"}},
            )
        )
    )
    adapter = OpenAICompatibleModelAdapter(_settings(), client=client)
    try:
        with pytest.raises(ModelGatewayError) as captured:
            await adapter.complete(ModelResponseCreate(prompt="hello"))
    finally:
        await client.aclose()

    assert captured.value.code == "upstream_authentication_failed"
    assert "server-secret-key" not in captured.value.message


@pytest.mark.asyncio
async def test_openai_adapter_supports_local_endpoint_without_api_key() -> None:
    authorization: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        authorization.append(request.headers.get("authorization"))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "本地模型回答"}}]},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = OpenAICompatibleModelAdapter(
        _settings(openai_api_key="", openai_api_key_required=False),
        client=client,
    )
    try:
        response = await adapter.complete(ModelResponseCreate(prompt="hello"))
    finally:
        await client.aclose()

    assert response.answer == "本地模型回答"
    assert authorization == [None]


@pytest.mark.asyncio
async def test_openai_adapter_maps_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow upstream", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = OpenAICompatibleModelAdapter(_settings(), client=client)
    try:
        with pytest.raises(ModelGatewayError) as captured:
            await adapter.complete(ModelResponseCreate(prompt="hello"))
    finally:
        await client.aclose()

    assert captured.value.code == "upstream_timeout"


def test_settings_hide_model_and_agent_secrets() -> None:
    settings = _settings(
        hermes_webui_cookie="session=secret-cookie",
        hermes_webui_csrf_token="secret-csrf",
    )

    serialized = settings.model_dump_json()
    assert "server-secret-key" not in repr(settings)
    assert "server-secret-key" not in serialized
    assert "secret-cookie" not in serialized
    assert "secret-csrf" not in serialized
