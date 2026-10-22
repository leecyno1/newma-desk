"""Website-bound stock reads use the same published action grants as local Desk."""
import json
from pathlib import Path

import pytest
import httpx
from fastapi.testclient import TestClient

from tests.test_website_auth import COOKIE, TOKEN, DESK_ORIGIN, USER, WORKSPACE, make_app
from vibe_visualization_api.config import Settings
from vibe_visualization_api.main import create_app
from vibe_visualization_api.data_services.models import DataServiceDescriptor
from vibe_visualization_api.data_services.registry import DataServiceRegistry
from vibe_visualization_api.data_services.client import DataServiceClient

MOD = 'instock-market-workbench'
ENDPOINT = '/api/mods/runtime/instock-scope'


@pytest.fixture
def stock_website(tmp_path, request):
    mod = getattr(request, 'param', MOD)
    app = create_app(Settings(runtime_dir=tmp_path, database_path=tmp_path / 'stock.db',
        website_auth_enabled=True, enable_domain_suites=False, mod_admission_allowlist=mod))
    authority = make_app()
    app.state.website_auth.post = authority.state.website_auth.post
    root = Path(__file__).resolve().parents[4]
    service = DataServiceDescriptor.model_validate_json((root / 'integrations/instock-analysis/data-service.json').read_text())
    market = DataServiceDescriptor.model_validate_json((root / 'integrations/vibe-research/data-service.json').read_text())
    market.auth_secret = None
    app.state.data_service_registry = DataServiceRegistry([service, market])
    app.state.market_calls = []
    app.state.market_status = 200
    def upstream(request):
        app.state.market_calls.append(request)
        return httpx.Response(app.state.market_status, json={'data': {'items': [], 'source': 'synthetic'}})
    app.state.data_service_client = DataServiceClient(public_mode=False,
        transport_factory=lambda: httpx.MockTransport(upstream))
    suite = json.loads((root / 'mods/instock-market-suite/suite.json').read_text())
    page = next(page for page in suite['pages'] if page['id'] == MOD)
    manifest = {**suite['manifest'], **page['manifest'], 'id': MOD, 'name': page['name'], 'version': suite['version'],
        'entry': {'type': 'external', 'url': 'https://c10375.runtime.drlemon.cc:10445/mods/market-workbench'}}
    if mod == 'instock-market-map':
        definition = json.loads((root / 'mods/instock-market-map/mod.json').read_text())
        manifest = {**definition['manifest'], 'id': mod, 'name': definition['name'], 'version': definition['version'],
            'entry': {'type': 'external', 'url': 'https://c10375.runtime.drlemon.cc:10445/mods/market-map'}}
    with TestClient(app, base_url=DESK_ORIGIN, client=('127.0.0.1', 1234)) as client:
        client.cookies.set(COOKIE, TOKEN)
        origin = {'Origin': DESK_ORIGIN}
        draft = client.post('/api/mods/drafts', headers=origin, json=manifest)
        assert draft.status_code == 201, draft.text
        assert client.post(f'/api/mods/{mod}/revisions/{draft.json()["revision"]}/publish', headers=origin).status_code == 200
        result = client.post(f'/api/mods/{mod}/sessions', headers=origin, json={'instanceId': 'stock-one', 'workspaceId': WORKSPACE})
        assert result.status_code == 201, result.text
        client.cookies.clear()
        yield client, authority, {'Authorization': 'Bearer ' + result.json()['accessToken'], 'X-Newma-Desk-Instance-Id': 'stock-one'}


def test_stock_website_gate_requires_binding_and_preserves_authoritative_owner(stock_website):
    client, authority, headers = stock_website
    target = {'method': 'GET', 'path': '/api/v1/analysis-history'}
    assert client.post(ENDPOINT, json=target).status_code == 401
    client.cookies.set(COOKIE, TOKEN)
    assert client.post(ENDPOINT, headers={'Origin': DESK_ORIGIN}, json=target).status_code == 401
    client.cookies.clear()
    assert client.post(ENDPOINT, headers={**headers, 'X-User-Id': 'forged', 'X-Workspace-Id': 'forged'}, json=target).status_code == 403
    result = client.post(ENDPOINT, headers=headers, json=target)
    assert result.status_code == 200, result.text
    assert result.headers['cache-control'] == 'private, no-store'
    assert result.json() == {'userId': USER, 'workspaceId': WORKSPACE}
    assert client.post(ENDPOINT, headers={**headers, 'X-Newma-Dock-Instance-Id': 'wrong'}, json=target).status_code == 403
    authority.state.revoked = True
    client.app.state.website_auth.cache.clear()
    assert client.post(ENDPOINT, headers=headers, json=target).status_code == 401


def test_stock_rejects_other_entry_and_unadmitted_page(stock_website):
    client, _, headers = stock_website
    for path in ('/api/v1/research-books', '/api/v1/stock-research/dossiers', '/api/v1/industry-chain/research'):
        assert client.post(ENDPOINT, headers=headers, json={'method': 'GET', 'path': path}).status_code == 403
    client.app.state.resolve_module_repository()._allowed_module_ids = frozenset({'other'})
    assert client.post(ENDPOINT, headers=headers, json={'method': 'GET', 'path': '/api/v1/analysis-history'}).status_code == 403


DEPENDENCY = '/api/mods/runtime/instock-data'
SCAN = {'capability': 'market.scan', 'parameters': {'market': 'CN', 'sort': 'marketCap', 'order': 'desc', 'limit': 100}}


@pytest.mark.parametrize('stock_website', ['instock-market-map'], indirect=True)
def test_market_map_delegation_uses_registered_read_only_provider(stock_website):
    client, _, headers = stock_website
    result = client.post(DEPENDENCY, headers=headers, json=SCAN)
    assert result.status_code == 200, result.text
    assert result.headers['cache-control'] == 'private, no-store'
    call = client.app.state.market_calls[-1]
    assert call.method == 'GET' and call.url.path.endswith('/market-terminal/scan')
    assert dict(call.url.params) == {**SCAN['parameters'], 'limit': '100'}
    assert 'authorization' not in call.headers and 'cookie' not in call.headers
    assert 'x-newma-desk-instance-id' not in call.headers
    result = client.post(DEPENDENCY, headers=headers, json={'capability': 'market.quotes', 'parameters': {'symbols': 'CN:600519,CN:000001'}})
    assert result.status_code == 200, result.text
    assert client.app.state.market_calls[-1].url.path.endswith('/market-terminal/quotes')
    client.app.state.market_status = 401
    assert client.post(DEPENDENCY, headers=headers, json=SCAN).status_code == 502
    assert len(client.app.state.market_calls) == 3  # no anonymous retry


@pytest.mark.parametrize('stock_website', ['instock-market-map'], indirect=True)
def test_market_map_delegation_checks_binding_and_revocation(stock_website):
    client, authority, headers = stock_website
    assert client.post(DEPENDENCY, json=SCAN).status_code == 401
    client.cookies.set(COOKIE, TOKEN)
    assert client.post(DEPENDENCY, headers={'Origin': DESK_ORIGIN}, json=SCAN).status_code == 401
    client.cookies.clear()
    remote = TestClient(client.app, base_url=DESK_ORIGIN, client=('192.0.2.10', 1234))
    try:
        assert remote.post(DEPENDENCY, headers={**headers, 'Origin': DESK_ORIGIN}, json=SCAN).status_code == 403
    finally:
        remote.close()
    authority.state.revoked = True
    client.app.state.website_auth.cache.clear()
    assert client.post(DEPENDENCY, headers=headers, json=SCAN).status_code == 401
    assert not client.app.state.market_calls


@pytest.mark.parametrize('stock_website', ['instock-market-map'], indirect=True)
def test_market_map_dependency_parameters_and_current_admission(stock_website):
    client, _, headers = stock_website
    for override in ({'sort': []}, {'order': {}}, {'limit': True}, {'limit': 500}, {'market': 'US'}, {'sort': 'pe'}, {'url': 'http://other'}):
        assert client.post(DEPENDENCY, headers=headers, json={**SCAN, 'parameters': {**SCAN['parameters'], **override}}).status_code == 422
    for symbols in ('US:AAPL', 'CN:600519&token=x', ','.join(['CN:600519'] * 51)):
        assert client.post(DEPENDENCY, headers=headers, json={'capability': 'market.quotes', 'parameters': {'symbols': symbols}}).status_code == 422
    assert client.post(DEPENDENCY, headers=headers, json={'capability': 'market.ohlcv', 'parameters': {}}).status_code == 422
    service = client.app.state.data_service_registry.get('market-data')
    service.capabilities['market.scan'].method = 'POST'
    assert client.post(DEPENDENCY, headers=headers, json=SCAN).status_code == 503
    client.app.state.resolve_module_repository()._allowed_module_ids = frozenset({'other'})
    assert client.post(DEPENDENCY, headers=headers, json=SCAN).status_code == 403
    assert not client.app.state.market_calls


def test_other_stock_page_does_not_gain_market_map_dependency(stock_website):
    client, _, headers = stock_website
    assert client.post(DEPENDENCY, headers=headers, json=SCAN).status_code == 403
    assert not client.app.state.market_calls


@pytest.mark.parametrize('stock_website', ['instock-market-map'], indirect=True)
def test_market_map_old_revision_cannot_delegate_after_republish(stock_website):
    client, _, headers = stock_website
    manifest = client.app.state.resolve_module_repository().get_published('instock-market-map').manifest
    client.cookies.set(COOKIE, TOKEN)
    origin = {'Origin': DESK_ORIGIN}
    draft = client.post('/api/mods/drafts', headers=origin, json=manifest)
    assert draft.status_code == 201, draft.text
    published = client.post(f'/api/mods/instock-market-map/revisions/{draft.json()["revision"]}/publish', headers=origin)
    assert published.status_code == 200, published.text
    client.cookies.clear()
    assert client.post(DEPENDENCY, headers=headers, json=SCAN).status_code == 403
    assert not client.app.state.market_calls


@pytest.mark.parametrize('stock_website', ['instock-market-map'], indirect=True)
def test_market_map_uses_existing_internal_research_transport(stock_website):
    from tests.data_services.test_internal_research import upstream
    from vibe_visualization_api.data_services.internal_research import InternalResearch
    client, _, headers = stock_website
    service = client.app.state.data_service_registry.get('market-data')
    research = upstream()
    transport = InternalResearch(str(service.base_url), service.capabilities.values())
    transport.bind(research, 'synthetic-internal-key')
    client.app.state.data_service_client = DataServiceClient(public_mode=False, transport_factory=transport.transport)
    result = client.post(DEPENDENCY, headers=headers, json=SCAN)
    assert result.status_code == 200, result.text
    assert research.state.calls == [('GET', 'market-terminal/scan', {**SCAN['parameters'], 'limit': '100'})]
