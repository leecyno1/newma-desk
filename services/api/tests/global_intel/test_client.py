import httpx
import pytest

from vibe_visualization_api.global_intel.client import (
    GlobalIntelClient,
    GlobalIntelUnavailable,
)


class OneShotAsyncStream(httpx.AsyncByteStream):
    async def __aiter__(self):
        yield b'data: {"status":"ok"}\n\n'


@pytest.mark.asyncio
async def test_client_loads_json_from_managed_upstream() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://127.0.0.1:8501/api/overview"
        return httpx.Response(200, json={"timestamp": "2026-08-09T12:00:00Z"})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = GlobalIntelClient("http://127.0.0.1:8501/", client=http_client)

    try:
        payload = await client.get_json("/api/overview")
    finally:
        await http_client.aclose()

    assert payload == {"timestamp": "2026-08-09T12:00:00Z"}


@pytest.mark.asyncio
async def test_client_rejects_non_object_payload() -> None:
    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=["invalid"])
        )
    )
    client = GlobalIntelClient("http://127.0.0.1:8501", client=http_client)

    try:
        with pytest.raises(GlobalIntelUnavailable):
            await client.get_json("/api/static")
    finally:
        await http_client.aclose()


@pytest.mark.asyncio
async def test_client_forwards_event_stream_bytes() -> None:
    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                stream=OneShotAsyncStream(),
                headers={"Content-Type": "text/event-stream"},
            )
        )
    )
    client = GlobalIntelClient("http://127.0.0.1:8501", client=http_client)

    try:
        chunks = [chunk async for chunk in client.stream("/api/stream")]
    finally:
        await http_client.aclose()

    assert b"".join(chunks) == b'data: {"status":"ok"}\n\n'
