import json
import socket

import httpx
import pytest

from vibe_visualization_api.data_services.client import (
    DataServiceClient,
    UnknownServiceCapability,
    UnsafeServiceUrl,
    UpstreamServiceError,
    validate_service_url,
)
from vibe_visualization_api.data_services.models import (
    DataServiceDescriptor,
    ServiceCapability,
)


@pytest.fixture
def market_service() -> DataServiceDescriptor:
    return DataServiceDescriptor(
        id="market-data",
        base_url="http://127.0.0.1:9000/api",
        transport="rest",
        allowed_hosts=["127.0.0.1"],
        auth_secret="MARKET_DATA_TOKEN",
        capabilities={
            "market.indices": ServiceCapability(
                method="GET",
                path="/indices",
                input_schema="MarketIndicesInput",
                output_schema="MarketIndicesOutput",
                permission="market.read",
            ),
            "market.overview": ServiceCapability(
                method="POST",
                path="/overview",
                input_schema="MarketOverviewInput",
                output_schema="MarketOverviewOutput",
                permission="market.read",
            ),
        },
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data",
        "http://127.0.0.1:9000/private",
        "http://10.0.0.1/private",
        "http://[::1]/private",
        "file:///etc/passwd",
        "javascript:alert(1)",
    ],
)
def test_client_rejects_unsafe_targets(url: str) -> None:
    with pytest.raises(UnsafeServiceUrl):
        validate_service_url(url, public_mode=True)


def test_public_mode_rejects_hostname_resolving_to_private_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def private_dns(*args: object, **kwargs: object):
        return [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("192.168.1.10", 443),
            )
        ]

    monkeypatch.setattr(socket, "getaddrinfo", private_dns)

    with pytest.raises(UnsafeServiceUrl):
        validate_service_url("https://market.example.test/api", public_mode=True)


def test_local_mode_requires_descriptor_host_allowlist() -> None:
    with pytest.raises(UnsafeServiceUrl):
        validate_service_url(
            "http://127.0.0.1:9000/api/indices",
            public_mode=False,
            allowed_hosts=[],
        )

    validate_service_url(
        "http://127.0.0.1:9000/api/indices",
        public_mode=False,
        allowed_hosts=["127.0.0.1"],
    )


@pytest.mark.asyncio
async def test_client_invokes_only_registered_method_and_path(
    market_service: DataServiceDescriptor,
) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["method"] = request.method
        captured["authorization"] = request.headers.get("authorization")
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"breadth": 0.63})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = DataServiceClient(
        public_mode=False,
        secret_resolver=lambda name: (
            "server-data-secret" if name == "MARKET_DATA_TOKEN" else None
        ),
        client=http_client,
    )

    try:
        result = await client.invoke(
            market_service,
            "market.overview",
            {"date": "2026-07-20"},
        )
    finally:
        await http_client.aclose()

    assert result == {"breadth": 0.63}
    assert captured == {
        "url": "http://127.0.0.1:9000/api/overview",
        "method": "POST",
        "authorization": "Bearer server-data-secret",
        "payload": {"date": "2026-07-20"},
    }


@pytest.mark.asyncio
async def test_client_uses_query_parameters_for_registered_get(
    market_service: DataServiceDescriptor,
) -> None:
    requested_url = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requested_url
        requested_url = str(request.url)
        return httpx.Response(200, json={"items": []})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = DataServiceClient(
        public_mode=False,
        secret_resolver=lambda name: "token",
        client=http_client,
    )

    try:
        await client.invoke(
            market_service,
            "market.indices",
            {"market": "cn"},
        )
    finally:
        await http_client.aclose()

    assert requested_url == "http://127.0.0.1:9000/api/indices?market=cn"


@pytest.mark.asyncio
async def test_unknown_capability_never_reaches_network(
    market_service: DataServiceDescriptor,
) -> None:
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = DataServiceClient(
        public_mode=False,
        secret_resolver=lambda name: "token",
        client=http_client,
    )

    try:
        with pytest.raises(UnknownServiceCapability):
            await client.invoke(market_service, "market.missing", {})
    finally:
        await http_client.aclose()

    assert called is False


@pytest.mark.asyncio
async def test_client_does_not_follow_upstream_redirects(
    market_service: DataServiceDescriptor,
) -> None:
    urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        return httpx.Response(
            302,
            headers={"Location": "http://169.254.169.254/latest/meta-data"},
        )

    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )
    client = DataServiceClient(
        public_mode=False,
        secret_resolver=lambda name: "token",
        client=http_client,
    )

    try:
        with pytest.raises(UpstreamServiceError):
            await client.invoke(market_service, "market.indices", {})
    finally:
        await http_client.aclose()

    assert urls == ["http://127.0.0.1:9000/api/indices"]
