import json

import httpx
import pytest

from vibe_visualization_api.agent_gateway.adapters.openai_compatible import (
    OpenAICompatibleAdapter,
)
from vibe_visualization_api.agent_gateway.models import AgentTaskCreate
from vibe_visualization_api.config import Settings


async def _events(
    adapter: OpenAICompatibleAdapter,
    request: AgentTaskCreate,
):
    return [event async for event in adapter.run(request)]


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
            json={"choices": [{"message": {"role": "assistant", "content": "异动解释"}}]},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = OpenAICompatibleAdapter(_settings(), client=client)
    request = AgentTaskCreate(
        module_id="market-daily",
        capability="market.explain",
        prompt="解释今天的异动",
        context={"securityCode": "600519"},
        input={"date": "2026-07-20"},
    )

    try:
        events = await _events(adapter, request)
    finally:
        await client.aclose()

    assert [event.type for event in events] == ["progress", "completed"]
    assert events[-1].data == {"answer": "异动解释"}
    assert captured["url"] == "https://models.example.test/v1/chat/completions"
    assert captured["authorization"] == "Bearer server-secret-key"
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["model"] == "gpt-5.6"
    user_message = payload["messages"][-1]
    assert user_message["role"] == "user"
    user_content = json.loads(user_message["content"])
    assert user_content == {
        "moduleId": "market-daily",
        "capability": "market.explain",
        "prompt": "解释今天的异动",
        "context": {"securityCode": "600519"},
        "input": {"date": "2026-07-20"},
    }
    assert "server-secret-key" not in json.dumps(payload)


@pytest.mark.asyncio
async def test_openai_adapter_maps_401_to_safe_failed_event() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"error": {"message": "bad server-secret-key"}},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = OpenAICompatibleAdapter(_settings(), client=client)

    try:
        events = await _events(adapter, AgentTaskCreate(prompt="hello"))
    finally:
        await client.aclose()

    assert [event.type for event in events] == ["progress", "failed"]
    assert events[-1].data == {
        "code": "upstream_authentication_failed",
        "error": "Agent provider authentication failed",
    }
    assert "server-secret-key" not in json.dumps(events[-1].model_dump(mode="json"))


@pytest.mark.asyncio
async def test_openai_adapter_maps_timeout_to_failed_event() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow upstream", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = OpenAICompatibleAdapter(_settings(), client=client)

    try:
        events = await _events(adapter, AgentTaskCreate(prompt="hello"))
    finally:
        await client.aclose()

    assert events[-1].type == "failed"
    assert events[-1].data == {
        "code": "upstream_timeout",
        "error": "Agent provider timed out",
    }


@pytest.mark.asyncio
async def test_openai_adapter_fails_safely_when_key_is_missing() -> None:
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = OpenAICompatibleAdapter(
        _settings(openai_api_key=""),
        client=client,
    )

    try:
        events = await _events(adapter, AgentTaskCreate(prompt="hello"))
    finally:
        await client.aclose()

    assert called is False
    assert events[-1].data == {
        "code": "missing_api_key",
        "error": "Agent provider is not configured",
    }


@pytest.mark.asyncio
async def test_openai_adapter_rejects_malformed_success_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = OpenAICompatibleAdapter(_settings(), client=client)

    try:
        events = await _events(adapter, AgentTaskCreate(prompt="hello"))
    finally:
        await client.aclose()

    assert events[-1].type == "failed"
    assert events[-1].data == {
        "code": "invalid_upstream_response",
        "error": "Agent provider returned an invalid response",
    }


@pytest.mark.asyncio
async def test_openai_adapter_does_not_follow_redirects() -> None:
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(
            302,
            headers={"Location": "https://redirect.example.test/collect"},
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )
    adapter = OpenAICompatibleAdapter(_settings(), client=client)

    try:
        events = await _events(adapter, AgentTaskCreate(prompt="hello"))
    finally:
        await client.aclose()

    assert requested_urls == ["https://models.example.test/v1/chat/completions"]
    assert events[-1].data == {
        "code": "upstream_rejected",
        "error": "Agent provider rejected the request",
    }


@pytest.mark.asyncio
async def test_openai_adapter_capabilities_are_provider_neutral() -> None:
    adapter = OpenAICompatibleAdapter(_settings())

    assert await adapter.capabilities() == [
        "chat",
        "module.explain",
        "module.generate-view",
    ]


def test_settings_hide_the_server_api_key() -> None:
    settings = _settings()

    assert "server-secret-key" not in repr(settings)
    assert "server-secret-key" not in settings.model_dump_json()
