import json

import httpx
import pytest

from vibe_visualization_api.config import Settings
from vibe_visualization_api.model_gateway.adapters.anthropic import (
    AnthropicModelAdapter,
)
from vibe_visualization_api.model_gateway.errors import ModelGatewayError
from vibe_visualization_api.model_gateway.models import ModelResponseCreate


@pytest.mark.asyncio
async def test_anthropic_adapter_uses_native_messages_api() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["key"] = request.headers.get("x-api-key")
        captured["version"] = request.headers.get("anthropic-version")
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"content": [{"type": "text", "text": "Claude 回答"}]},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = AnthropicModelAdapter(
        Settings(
            anthropic_base_url="https://claude.example.test/v1",
            anthropic_api_key="anthropic-secret",
            anthropic_model="claude-test",
        ),
        client=client,
    )
    try:
        response = await adapter.complete(
            ModelResponseCreate(
                module_id="market-daily",
                prompt="解释行情",
            )
        )
    finally:
        await client.aclose()

    assert response.answer == "Claude 回答"
    assert response.adapter == "anthropic"
    assert captured["url"] == "https://claude.example.test/v1/messages"
    assert captured["key"] == "anthropic-secret"
    assert captured["version"] == "2023-06-01"
    assert captured["payload"]["model"] == "claude-test"


@pytest.mark.asyncio
async def test_anthropic_adapter_requires_server_side_key() -> None:
    adapter = AnthropicModelAdapter(Settings(anthropic_api_key=""))

    with pytest.raises(ModelGatewayError) as captured:
        await adapter.complete(ModelResponseCreate(prompt="hello"))

    assert captured.value.code == "missing_api_key"
