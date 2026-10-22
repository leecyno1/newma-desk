"""Website-bound stock reads use the same published action grants as local Desk."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.test_website_auth import COOKIE, TOKEN, DESK_ORIGIN, USER, WORKSPACE, make_app
from vibe_visualization_api.config import Settings
from vibe_visualization_api.main import create_app
from vibe_visualization_api.data_services.models import DataServiceDescriptor
from vibe_visualization_api.data_services.registry import DataServiceRegistry

MOD = 'instock-market-workbench'
ENDPOINT = '/api/mods/runtime/instock-scope'


@pytest.fixture
def stock_website(tmp_path):
    app = create_app(Settings(runtime_dir=tmp_path, database_path=tmp_path / 'stock.db',
        website_auth_enabled=True, enable_domain_suites=False, mod_admission_allowlist=MOD))
    authority = make_app()
    app.state.website_auth.post = authority.state.website_auth.post
    root = Path(__file__).resolve().parents[4]
    service = DataServiceDescriptor.model_validate_json((root / 'integrations/instock-analysis/data-service.json').read_text())
    app.state.data_service_registry = DataServiceRegistry([service])
    suite = json.loads((root / 'mods/instock-market-suite/suite.json').read_text())
    page = next(page for page in suite['pages'] if page['id'] == MOD)
    manifest = {**suite['manifest'], **page['manifest'], 'id': MOD, 'name': page['name'], 'version': suite['version'],
        'entry': {'type': 'external', 'url': 'https://c10375.runtime.drlemon.cc:10445/mods/market-workbench'}}
    with TestClient(app, base_url=DESK_ORIGIN, client=('127.0.0.1', 1234)) as client:
        client.cookies.set(COOKIE, TOKEN)
        origin = {'Origin': DESK_ORIGIN}
        draft = client.post('/api/mods/drafts', headers=origin, json=manifest)
        assert draft.status_code == 201, draft.text
        assert client.post(f'/api/mods/{MOD}/revisions/{draft.json()["revision"]}/publish', headers=origin).status_code == 200
        result = client.post(f'/api/mods/{MOD}/sessions', headers=origin, json={'instanceId': 'stock-one', 'workspaceId': WORKSPACE})
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
