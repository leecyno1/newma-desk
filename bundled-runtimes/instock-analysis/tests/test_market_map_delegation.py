"""Synthetic request identities only; no live accounts or data providers."""
from concurrent.futures import ThreadPoolExecutor
import json
from types import SimpleNamespace

import pytest

from instock.core.analysis_scope import analysis_scope, analysis_session, desk_scope
from instock.core.market_data_provider import NewmaDeskMarketDataProvider, MarketDataError
from instock.core.workbench import MarketMapEngine
from test_market_map import MapProvider


def test_concurrent_market_map_workers_keep_each_request_identity():
    def run(owner):
        scope = analysis_scope.set(desk_scope(owner, 'workspace'))
        session = analysis_session.set(('synthetic-' + owner, 'instance-' + owner))
        identities = []
        class Provider(MapProvider):
            def get_stock_scan(self, **kwargs):
                identities.append((analysis_scope.get(), analysis_session.get()))
                return super().get_stock_scan(**kwargs)
        try:
            result = MarketMapEngine(Provider()).analyze(capacity=500)
            assert len(identities) == 6
            assert all(identity == (desk_scope(owner, 'workspace'), ('synthetic-' + owner, 'instance-' + owner)) for identity in identities)
            assert 'synthetic-' not in json.dumps(result)
        finally:
            analysis_session.reset(session)
            analysis_scope.reset(scope)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(run, ('alice', 'bob')))
    assert analysis_session.get() is None


def test_delegate_uses_only_request_signature_on_fixed_loopback(monkeypatch):
    monkeypatch.setenv('INSTOCK_DESK_SCOPE_URL', 'http://127.0.0.1:18911/api/mods/runtime/instock-scope')
    calls = []
    class Transport:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, **kwargs):
            assert self.trust_env is False
            calls.append((url, kwargs))
            return SimpleNamespace(status_code=200)
    monkeypatch.setattr('instock.core.market_data_provider.requests.Session', Transport)
    provider = NewmaDeskMarketDataProvider('http://unrelated.example/api', token='unused-process-token')
    scope = analysis_scope.set(desk_scope('alice', 'workspace'))
    session = analysis_session.set(('synthetic-alice', 'instance-alice'))
    try:
        provider._request_capability('market.scan', '/ignored', {'market': 'CN'}, headers={'Authorization': 'must-not-forward', 'Cookie': 'must-not-forward'})
        assert calls[0][0] == 'http://127.0.0.1:18911/api/mods/runtime/instock-data'
        assert calls[0][1]['headers'] == {'Authorization': 'Bearer synthetic-alice', 'X-Newma-Desk-Instance-Id': 'instance-alice'}
        assert calls[0][1]['allow_redirects'] is False
        with pytest.raises(MarketDataError, match='未回退'):
            provider._get('http://unrelated.example/api')
    finally:
        analysis_session.reset(session)
        analysis_scope.reset(scope)


def test_cloud_without_request_identity_cannot_use_process_token(monkeypatch):
    monkeypatch.setenv('INSTOCK_REQUIRE_DESK_SESSION', '1')
    provider = NewmaDeskMarketDataProvider('http://127.0.0.1:18911/api/research', token='unused-process-token')
    monkeypatch.setattr('instock.core.market_data_provider.requests.post', lambda *a, **k: pytest.fail('unexpected direct request'))
    with pytest.raises(MarketDataError, match='缺少请求级'):
        provider._request_capability('market.scan', '/ignored', {}, headers={})
    with pytest.raises(MarketDataError, match='未回退'):
        provider._post('http://127.0.0.1:18911/api')
