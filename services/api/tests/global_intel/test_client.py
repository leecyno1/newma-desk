import gzip

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


@pytest.mark.asyncio
@pytest.mark.parametrize("content_type", [None, "text/html", "application/json"])
async def test_stream_rejects_non_sse_before_forwarding_body(content_type) -> None:
    class UnexpectedBody(httpx.AsyncByteStream):
        read = False
        closed = False

        async def __aiter__(self):
            self.read = True
            yield b"private upstream response"

        async def aclose(self):
            self.closed = True

    body = UnexpectedBody()
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(
        200, headers={"Content-Type": content_type} if content_type else {}, stream=body,
    ))) as http_client:
        client = GlobalIntelClient("http://127.0.0.1:8501", client=http_client)
        with pytest.raises(GlobalIntelUnavailable, match="invalid event stream"):
            _ = [chunk async for chunk in client.stream("/api/stream")]
    assert body.closed and not body.read


@pytest.mark.asyncio
async def test_stream_decodes_compressed_sse_and_bounds_idle_not_lifetime() -> None:
    event = 'data: {"source":"地震"}\n\n'.encode()

    class CompressedBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            compressed = gzip.compress(event)
            yield compressed[:10]
            yield compressed[10:]

    def handler(request):
        assert request.extensions["timeout"] == {"connect": 5.0, "read": 120.0, "write": 5.0, "pool": 5.0}
        assert request.headers["accept"] == "text/event-stream"
        return httpx.Response(200, headers={"Content-Type": "Text/Event-Stream; charset=utf-8", "Content-Encoding": "gzip"}, stream=CompressedBody())

    async with httpx.AsyncClient(timeout=None, transport=httpx.MockTransport(handler)) as http_client:
        client = GlobalIntelClient("http://127.0.0.1:8501", client=http_client)
        assert b"".join([chunk async for chunk in client.stream("/api/stream")]) == event


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["redirect", "timeout"])
async def test_stream_failure_does_not_retry_or_follow_redirect(failure) -> None:
    calls = []

    def handler(request):
        calls.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("private upstream address", request=request)
        return httpx.Response(302, headers={"Location": "http://other.invalid/"})

    async with httpx.AsyncClient(follow_redirects=True, transport=httpx.MockTransport(handler)) as http_client:
        client = GlobalIntelClient("http://127.0.0.1:8501", client=http_client)
        with pytest.raises(GlobalIntelUnavailable) as error:
            _ = [chunk async for chunk in client.stream("/api/stream")]
        assert "private upstream" not in str(error.value)
    assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,code", [
    (httpx.ReadTimeout, "world_stream_idle_timeout"),
    (httpx.ConnectError, "world_connection_failed"),
    (httpx.RemoteProtocolError, "world_stream_disconnected"),
])
async def test_stream_failure_preserves_partial_data_and_safe_reason(kind, code, caplog):
    class BrokenStream(httpx.AsyncByteStream):
        closed = False
        async def __aiter__(self):
            yield b'data: {"_done":1,"_total":48}\n\n'
            raise kind("private-token-internal-address")
        async def aclose(self):
            self.closed = True
    body = BrokenStream()
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(
        200, headers={"Content-Type": "text/event-stream"}, stream=body,
    ))) as transport:
        stream = GlobalIntelClient("http://127.0.0.1:8501", client=transport).stream("/api/stream")
        assert b'"_done":1' in await anext(stream)
        with pytest.raises(GlobalIntelUnavailable) as caught:
            await anext(stream)
        assert caught.value.code == code
    assert body.closed
    assert code in caplog.text
    assert "private-token-internal-address" not in caplog.text
