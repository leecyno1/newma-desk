"""Real cycle declaration and Website-bound sessions, without real logins/products."""
import json
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

from tests.test_website_auth import COOKIE, TOKEN, DESK_ORIGIN, USER, WORKSPACE, make_app
from vibe_visualization_api.config import Settings
from vibe_visualization_api.main import create_app

ENDPOINT = "/api/mods/runtime/cycle-scope"
MOD = "seven-cycle-research"


@pytest.fixture
def cycle(tmp_path):
    app = create_app(Settings(runtime_dir=tmp_path, database_path=tmp_path / "cycle.db",
                              website_auth_enabled=True, enable_domain_suites=False, mod_admission_allowlist=MOD))
    authority = make_app()
    app.state.website_auth.post = authority.state.website_auth.post
    client = TestClient(app, base_url=DESK_ORIGIN, client=("127.0.0.1", 1234))
    client.cookies.set(COOKIE, TOKEN)
    origin = {"Origin": DESK_ORIGIN}
    root = Path(__file__).resolve().parents[4]
    definition = json.loads((root / "mods" / MOD / "mod.json").read_text())
    manifest = {**definition['manifest'], 'id': MOD, 'name': definition['name'], 'version': definition['version'],
                'entry': {'type': 'external', 'url': 'https://c10375.runtime.drlemon.cc:10445/'}}
    draft = client.post('/api/mods/drafts', headers=origin, json=manifest)
    assert draft.status_code == 201, draft.text
    assert client.post(f'/api/mods/{MOD}/revisions/{draft.json()["revision"]}/publish', headers=origin).status_code == 200
    result = client.post(f'/api/mods/{MOD}/sessions', headers=origin, json={'instanceId': 'cycle-one', 'workspaceId': WORKSPACE})
    assert result.status_code == 201, result.text
    client.cookies.clear()
    headers = {'Authorization': 'Bearer ' + result.json()['accessToken'], 'X-Newma-Desk-Instance-Id': 'cycle-one'}
    yield client, authority, headers
    client.close()


@pytest.mark.parametrize('name', ['market-surface', 'cycle-research', 'asset-statistics', 'forecast-extension', 'data-calibration'])
def test_current_page_snapshots_require_bound_signed_session(cycle, name):
    client, _, headers = cycle
    target = {'method': 'GET', 'path': f'/data/{name}.json', 'query': ''}
    assert client.post(ENDPOINT, json=target).status_code == 401
    client.cookies.set(COOKIE, TOKEN)
    assert client.post(ENDPOINT, headers={'Origin': DESK_ORIGIN}, json=target).status_code == 401
    client.cookies.clear()
    result = client.post(ENDPOINT, headers=headers, json=target)
    assert result.status_code == 200, result.text
    assert result.json() == {'userId': USER, 'workspaceId': WORKSPACE}
    assert result.headers['cache-control'] == 'private, no-store'


def test_only_displayed_attribution_query_and_no_arbitrary_products(cycle):
    client, _, headers = cycle
    target = {'method': 'GET', 'path': '/v1/assets/商品::原油/attribution', 'query': 'horizon=12'}
    assert client.post(ENDPOINT, headers=headers, json=target).status_code == 200
    for changes in ({'path': '/v1/assets'}, {'path': '/v1/assets/one/mapping'}, {'path': '/data/deployment.json'},
                    {'path': '/data/../private.json'}, {'path': '/v1/assets/a%2fb/attribution'},
                    {'path': '/v1/assets/a\\b/attribution'}, {'query': 'horizon=6'},
                    {'query': 'horizon=12&run_id=other'}, {'query': 'horizon=12&horizon=6'}):
        assert client.post(ENDPOINT, headers=headers, json={**target, **changes}).status_code == 403
    assert client.post(ENDPOINT, headers=headers, json={**target, 'method': 'POST'}).status_code == 422
    assert client.post(ENDPOINT, headers=headers, json={**target, 'extra': 'untrusted'}).status_code == 422


def test_current_permissions_revision_admission_and_website_revocation(cycle):
    client, authority, headers = cycle
    target = {'method': 'GET', 'path': '/data/cycle-research.json'}
    assert client.post(ENDPOINT, headers={**headers, 'X-Newma-Desk-Instance-Id': 'wrong'}, json=target).status_code == 403
    service = client.app.state.mod_session_service
    for mod, permissions in [('industry-prosperity', ['analysis.read']), (MOD, [])]:
        token, _ = service.issue(instance_id='cycle-one', module_id=mod, user_id=USER, workspace_id=WORKSPACE,
                                 revision=1, actions=[], permissions=permissions)
        client.app.state.website_auth.bind(service.validate(token), TOKEN)
        assert client.post(ENDPOINT, headers={**headers, 'Authorization': 'Bearer ' + token}, json=target).status_code == 403
    repo = client.app.state.resolve_module_repository()
    original = repo.get_published
    for revision, permissions in [(99, ['analysis.read']), (1, [])]:
        repo.get_published = lambda _: SimpleNamespace(revision=revision, manifest={'permissions': permissions})
        assert client.post(ENDPOINT, headers=headers, json=target).status_code == 403
    repo.get_published = original
    repo._allowed_module_ids = frozenset({'other'})
    assert client.post(ENDPOINT, headers=headers, json=target).status_code == 403
    repo._allowed_module_ids = frozenset({MOD})
    authority.state.revoked = True
    client.app.state.website_auth.cache.clear()
    assert client.post(ENDPOINT, headers=headers, json=target).status_code == 401


def test_only_loopback_validator_may_omit_browser_origin(cycle):
    client, _, headers = cycle
    target = {'method': 'GET', 'path': '/data/cycle-research.json'}
    external = TestClient(client.app, base_url=DESK_ORIGIN, client=('198.51.100.5', 1234))
    assert external.post(ENDPOINT, headers=headers, json=target).status_code == 403
    assert external.post(ENDPOINT, headers={**headers, 'Origin': 'https://evil.example'}, json=target).status_code == 403


def test_native_runtime_checks_real_desk_gate_before_reading(cycle, monkeypatch):
    client, authority, headers = cycle
    root = Path(__file__).resolve().parents[4]
    spec = importlib.util.spec_from_file_location('cycle_access_contract', root / 'bundled-runtimes/seven-cycle/src/seven_cycle_platform/api/desk_access.py')
    access = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(access)
    monkeypatch.setenv('SEVEN_CYCLE_DESK_SCOPE_URL', 'http://127.0.0.1:8911' + ENDPOINT)
    native = FastAPI()
    reads = []

    @native.get('/data/cycle-research.json')
    @native.get('/v1/cycles/current')
    def product():
        reads.append('read')
        return {'source': 'synthetic-contract-test'}

    access.install_desk_access(native)
    native.state.cycle_desk_verifier = lambda endpoint, token, instance, target: client.post(
        ENDPOINT, headers={'Authorization': token, 'X-Newma-Desk-Instance-Id': instance}, json=target,
    ).status_code
    with TestClient(native) as browser:
        assert browser.get('/data/cycle-research.json').status_code == 401
        assert reads == []
        result = browser.get('/data/cycle-research.json', headers=headers)
        assert result.status_code == 200
        assert result.json() == {'source': 'synthetic-contract-test'}
        assert result.headers['cache-control'] == 'private, no-store'
        assert browser.get('/v1/cycles/current', headers=headers).status_code == 403
        authority.state.revoked = True
        client.app.state.website_auth.cache.clear()
        assert browser.get('/data/cycle-research.json', headers=headers).status_code == 401
        assert reads == ['read']
