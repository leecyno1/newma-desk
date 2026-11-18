import asyncio
import logging
import sqlite3
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from world_intel_mcp.fetcher import Fetcher
from world_intel_mcp.cache import Cache


@pytest.mark.asyncio
@pytest.mark.parametrize('method', ['get_text', 'get_json'])
async def test_failed_requests_do_not_log_url_credentials_or_cached_key(method, caplog, monkeypatch):
    secret = 'synthetic-secret-for-test'
    url = f'https://example.test/path/{secret}?token={secret}'
    request = httpx.Request('GET', url)
    response = httpx.Response(403, request=request)
    client = Mock(is_closed=False)
    client.get = AsyncMock(side_effect=httpx.HTTPStatusError(f'failed for {url}', request=request, response=response))
    cache = Mock()
    cache.get.return_value = None
    cache.get_stale.return_value = {'cached': True}
    breaker = Mock()
    breaker.is_available.return_value = True
    fetcher = Fetcher(cache, breaker, client=client, max_retries=1)
    monkeypatch.setattr('world_intel_mcp.fetcher.asyncio.sleep', AsyncMock())
    caplog.set_level(logging.DEBUG, logger='world-intel-mcp.fetcher')

    result = await getattr(fetcher, method)(url, 'test-source')

    assert result == {'cached': True}
    assert client.get.await_count == 2
    breaker.record_failure.assert_called_once_with('test-source')
    assert secret not in caplog.text
    assert url not in caplog.text
    assert 'test-source' in caplog.text
    assert '403' in caplog.text


def test_cache_write_failure_does_not_log_sensitive_key(tmp_path, caplog, monkeypatch):
    cache = Cache(tmp_path / 'cache.db')
    conn = Mock()
    conn.execute.side_effect = sqlite3.OperationalError('write failed')
    monkeypatch.setattr(cache, '_get_conn', lambda: conn)
    caplog.set_level(logging.WARNING, logger='world-intel-mcp.cache')
    try:
        cache.set('https://example.test/synthetic-secret-for-test', {}, 60)
        assert 'synthetic-secret-for-test' not in caplog.text
        assert 'Cache write failed' in caplog.text
    finally:
        cache.close()


@pytest.mark.asyncio
async def test_http_library_logs_are_scoped_to_fetcher_requests(tmp_path, caplog):
    secret = 'synthetic-request-secret'
    async def response(request):
        await asyncio.sleep(0)
        return httpx.Response(200, json={'ok': True})
    cache = Cache(tmp_path / 'cache.db')
    breaker = Mock()
    breaker.is_available.return_value = True
    transport = httpx.MockTransport(response)
    caplog.set_level(logging.DEBUG, logger='httpx')
    try:
        async with httpx.AsyncClient(transport=transport) as client:
            fetcher = Fetcher(cache, breaker, client=client)
            result, other = await asyncio.gather(
                fetcher.get_json(f'https://example.test/{secret}', 'test'),
                client.get('https://example.test/other-request'),
            )
        assert result == {'ok': True} and other.status_code == 200
        assert secret not in caplog.text
        assert 'other-request' in caplog.text
    finally:
        cache.close()


@pytest.mark.asyncio
async def test_automatic_cache_keys_do_not_store_url_or_params(tmp_path):
    secret = 'synthetic-cache-secret'
    cache = Cache(tmp_path / 'cache.db')
    breaker = Mock()
    breaker.is_available.return_value = True
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={'ok': True}))) as client:
        fetcher = Fetcher(cache, breaker, client=client)
        try:
            await fetcher.get_json(f'https://example.test/{secret}', 'test', params={'token': secret})
            keys = [row[0] for row in cache._get_conn().execute('SELECT key FROM cache')]
            assert len(keys) == 1
            assert all(secret not in key for key in keys)
        finally:
            cache.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('expired', [False, True])
async def test_legacy_cache_remains_readable_without_rewriting(tmp_path, expired):
    cache = Cache(tmp_path / 'cache.db')
    url = 'https://example.test/synthetic-legacy-secret'
    old_key = f'test:{url}:None'
    cache.set(old_key, {'old': True}, -1 if expired else 60)
    breaker = Mock()
    breaker.is_available.return_value = False
    fetcher = Fetcher(cache, breaker)
    try:
        assert await fetcher.get_json(url, 'test') == {'old': True}
        assert [row[0] for row in cache._get_conn().execute('SELECT key FROM cache')] == [old_key]
    finally:
        cache.close()


@pytest.mark.asyncio
async def test_real_http_transport_debug_does_not_log_request_secrets(tmp_path, caplog):
    secret = 'synthetic-transport-secret'
    async def serve(reader, writer):
        await reader.readuntil(b'\r\n\r\n')
        writer.write(b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok')
        await writer.drain()
        writer.close()
        await writer.wait_closed()
    server = await asyncio.start_server(serve, '127.0.0.1', 0)
    port = server.sockets[0].getsockname()[1]
    cache = Cache(tmp_path / 'cache.db')
    breaker = Mock()
    breaker.is_available.return_value = True
    caplog.set_level(logging.DEBUG, logger='httpcore')
    caplog.set_level(logging.INFO, logger='httpx')
    fetcher = Fetcher(cache, breaker)
    try:
        assert await fetcher.get_text(f'http://127.0.0.1:{port}/{secret}', 'test', headers={'Authorization': f'Bearer {secret}'}) == 'ok'
        assert secret not in caplog.text
    finally:
        await fetcher.close()
        cache.close()
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_new_automatic_keys_cache_separately_and_keep_stale_fallback(tmp_path):
    cache = Cache(tmp_path / 'cache.db')
    breaker = Mock()
    breaker.is_available.return_value = True
    calls = []
    def response(request):
        calls.append(request)
        return httpx.Response(200, json={'value': request.url.params['value']})
    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
        fetcher = Fetcher(cache, breaker, client=client, max_retries=0)
        try:
            url = 'https://example.test/data'
            assert await fetcher.get_json(url, 'test', params={'value': 'one'}) == {'value': 'one'}
            assert await fetcher.get_json(url, 'test', params={'value': 'one'}) == {'value': 'one'}
            assert await fetcher.get_json(url, 'test', params={'value': 'two'}) == {'value': 'two'}
            assert len(calls) == 2
            cache._get_conn().execute('UPDATE cache SET expires_at = 0')
            cache._get_conn().commit()
            breaker.is_available.return_value = False
            assert await fetcher.get_json(url, 'test', params={'value': 'one'}) == {'value': 'one'}
        finally:
            cache.close()
