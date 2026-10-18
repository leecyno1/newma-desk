import importlib.util
import io
import json
from datetime import datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.models import DataApiProject, DataApiRequest, Message, ContactPredictionEvent, ContactPredictionEvaluation, ContactScoreSnapshot
from app.routers import developer
from app.services import public_data, public_data_media
from test_project_data_api import api, HEADERS

ADMIN = {'X-Deepsee-Admin': '1'}
PAYLOAD = {'name': '测试项目', 'scopes': ['messages:read'], 'requests_per_minute': 100}


@pytest.fixture
def admin(api):
    _, _, app = api
    app.include_router(developer.router)
    return peer_client(app, '127.0.0.1')


def peer_client(app, host):
    async def transport(scope, receive, send):
        scope['client'] = (host, 12345)
        await app(scope, receive, send)
    return TestClient(transport, base_url='http://127.0.0.1')


def test_managed_key_lifecycle_and_private_audit(api, admin, monkeypatch):
    client, factory, _ = api
    monkeypatch.setattr(settings, 'DATA_API_CLIENTS', None)
    created = admin.post('/api/developer/projects', headers=ADMIN, json=PAYLOAD)
    assert created.status_code == 201
    token = created.json()['token']; project = created.json()['data']
    auth = {'Authorization': f'Bearer {token}'}
    assert client.get('/api/v1/messages?q=private-search', headers=auth).status_code == 200
    assert client.get('/api/v1/contacts', headers=auth).status_code == 403
    listing = admin.get('/api/developer/projects', headers=ADMIN).text
    logs = admin.get('/api/developer/requests', headers=ADMIN).text
    assert token not in listing + logs and 'token_digest' not in listing
    assert 'private-search' not in logs and '403' in logs and '200' in logs
    with factory() as db:
        row = db.get(DataApiProject, project['id'])
        assert row.token_digest != token and len(row.token_digest) == 64
        assert db.query(DataApiRequest).count() == 2
    rotated = admin.post(f'/api/developer/projects/{project["id"]}/rotate', headers=ADMIN).json()['token']
    assert client.get('/api/v1/messages', headers=auth).status_code == 401
    auth = {'Authorization': f'Bearer {rotated}'}
    assert client.get('/api/v1/messages', headers=auth).status_code == 200
    assert admin.delete(f'/api/developer/projects/{project["id"]}', headers=ADMIN).status_code == 204
    assert client.get('/api/v1/messages', headers=auth).status_code == 401


@pytest.mark.parametrize('headers', [{}, {**ADMIN, 'Origin':'https://evil.example'},
    {**ADMIN, 'Host':'evil.example'}, {**ADMIN, 'X-Forwarded-For':'127.0.0.1'},
    {**ADMIN, 'Sec-Fetch-Site':'cross-site'}])
def test_local_admin_rejects_unsafe_context(admin, headers):
    assert admin.post('/api/developer/projects', headers=headers, json=PAYLOAD).status_code == 403


def test_local_admin_rejects_remote_peer(api, admin):
    _, _, app = api
    remote = peer_client(app, '192.168.1.2')
    assert remote.get('/api/developer/projects', headers=ADMIN).status_code == 403


def test_project_permission_edit_and_rate_limit(api, admin):
    client, _, _ = api
    created = admin.post('/api/developer/projects', headers=ADMIN, json=PAYLOAD).json()
    auth = {'Authorization': f'Bearer {created["token"]}'}
    project_id = created['data']['id']
    changed = {**PAYLOAD, 'scopes':['contacts:read'], 'requests_per_minute':2, 'enabled':True}
    assert admin.put(f'/api/developer/projects/{project_id}', headers=ADMIN, json=changed).status_code == 200
    assert client.get('/api/v1/messages', headers=auth).status_code == 403
    assert client.get('/api/v1/contacts', headers=auth).status_code == 200
    assert client.get('/api/v1/contacts', headers=auth).status_code == 429
    logs = admin.get('/api/developer/requests', params={'project_id':project_id}, headers=ADMIN).json()['data']
    assert [row['status'] for row in logs] == [429, 200, 403]


def test_grouped_search_scope_and_pagination(api, monkeypatch):
    client, _, _ = api
    monkeypatch.setattr(public_data, 'snapshot_rows', lambda db, source: [{'id':'1', 'title':'公司新闻'}])
    result = client.get('/api/v1/search', params={'q':'公司', 'sources':'messages,news', 'limit':1}, headers=HEADERS)
    assert result.status_code == 200
    groups = result.json()['data']
    assert [g['source'] for g in groups] == ['messages', 'news']
    assert groups[0]['data'][0]['sender_name'] == '研究员备注'
    assert groups[1]['meta']['coverage'] == 'local_snapshot'
    news = {'Authorization':'Bearer news-only-project-key-123456789'}
    assert [g['source'] for g in client.get('/api/v1/search?q=公司', headers=news).json()['data']] == ['news']
    assert client.get('/api/v1/search?q=公司&sources=messages', headers=news).status_code == 403
    assert client.get('/api/v1/search?q=公司&sources=unknown', headers=HEADERS).status_code == 422
    assert client.get('/api/v1/search?q=%25&sources=messages', headers=HEADERS).json()['data'][0]['data'][0]['id'] == 1


def test_scorecard_uses_saved_evidence_without_raw_text(api):
    client, factory, _ = api
    empty = client.get('/api/v1/contacts/wx_a/scorecard', headers=HEADERS).json()['data']
    assert empty['accuracy_score'] is None and empty['evidence']['status'] == 'unrated'
    with factory() as db:
        event = ContactPredictionEvent(contact_id='wx_a', source_message_id=1, source_time=datetime.now()-timedelta(days=100),
            asset_type='stock', asset_code='600000', asset_name='示例', direction='bullish', event_kind='stock_recommendation',
            is_actionable=True, raw_text='secret original message', normalized_text='推荐买入', benchmark_code='000300')
        event.evaluations.append(ContactPredictionEvaluation(horizon_code='1m', direction_hit=True,
            absolute_return=.1, excess_return=.05, entry_price=10, evaluation_price=11, meta={'secret':'do-not-export'}))
        db.add(event)
        db.add(ContactScoreSnapshot(contact_id='wx_a', accuracy_score=80, sample_size=1, hit_rate_overall=1))
        db.commit()
    response = client.get('/api/v1/contacts/wx_a/scorecard', headers=HEADERS)
    assert response.status_code == 200
    assert 'secret' not in response.text and 'normalized_text' not in response.text
    score = response.json()['data']
    assert score['evidence']['verified_samples'] == 1 and score['accuracy_score'] == 80
    assert score['predictions'][0]['evaluations'][0]['entry_price'] == 10
    assert client.get('/api/v1/contacts/missing/scorecard', headers=HEADERS).status_code == 404


class MediaResponse:
    def __init__(self, code=200, content_type='image/png', location=None):
        self.status_code = code; self.closed = False
        self.headers = {'content-type':content_type, 'location':location or ''}
    def close(self): self.closed = True
    def iter_content(self, chunk_size): yield b'fake-media'


def test_attachment_permissions_and_retained_download(api, admin, monkeypatch):
    client, factory, _ = api
    monkeypatch.setattr(settings, 'CHATLOG_HTTP_BASE', 'http://127.0.0.1:5031')
    with factory() as db:
        db.get(Message, 2).media_url = 'http://127.0.0.1:5031/image/example'; db.commit()
    response = MediaResponse()
    monkeypatch.setattr(public_data_media.requests, 'get', lambda *args, **kwargs: response)
    downloaded = client.get('/api/v1/messages/2/attachment', headers=HEADERS)
    assert downloaded.status_code == 200 and downloaded.content == b'fake-media'
    assert downloaded.headers['X-RateLimit-Limit'] == '120'
    assert 'attachment;' in downloaded.headers['content-disposition'] and response.closed
    key = admin.post('/api/developer/projects', headers=ADMIN, json=PAYLOAD).json()['token']
    assert client.get('/api/v1/messages/2/attachment', headers={'Authorization':f'Bearer {key}'}).status_code == 403
    assert client.get('/api/v1/messages/1/attachment', headers=HEADERS).status_code == 404


@pytest.mark.parametrize('url', ['https://evil.example/image/a', 'http://127.0.0.1:5031/image/../secret',
    'http://127.0.0.1:5031/image/a?key=secret', 'http://127.0.0.1:5031/image/%2e%2e/secret'])
def test_attachment_rejects_untrusted_urls(monkeypatch, url):
    monkeypatch.setattr(settings, 'CHATLOG_HTTP_BASE', 'http://127.0.0.1:5031')
    assert not public_data_media.retained_url(url)


def test_attachment_rejects_external_redirect(api, monkeypatch):
    client, factory, _ = api
    monkeypatch.setattr(settings, 'CHATLOG_HTTP_BASE', 'http://127.0.0.1:5031')
    with factory() as db:
        db.get(Message, 2).media_url = 'http://127.0.0.1:5031/image/example'; db.commit()
    response = MediaResponse(302, location='https://evil.example/file')
    monkeypatch.setattr(public_data_media.requests, 'get', lambda *args, **kwargs: response)
    assert client.get('/api/v1/messages/2/attachment', headers=HEADERS).status_code == 502 and response.closed


@pytest.fixture
def cli():
    path = Path(__file__).parents[1] / 'scripts/deepsee.py'
    spec = importlib.util.spec_from_file_location('deepsee_cli', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def test_cli_uses_project_api_and_env(cli, monkeypatch, capsys):
    monkeypatch.setenv('DEEPSEE_API_KEY', 'test-cli-key')
    class Opener:
        def open(self, request, timeout):
            assert request.headers['Authorization'] == 'Bearer test-cli-key'
            assert '/api/v1/search?q=' in request.full_url
            return io.BytesIO(b'{"data":[]}')
    monkeypatch.setattr(cli, 'build_opener', lambda *args: Opener())
    assert cli.main(['search', '半导体']) == 0
    output = capsys.readouterr(); assert json.loads(output.out) == {'data':[]} and not output.err


def test_cli_fails_safely_and_does_not_overwrite(cli, monkeypatch, capsys, tmp_path):
    monkeypatch.delenv('DEEPSEE_API_KEY', raising=False)
    assert cli.main(['capabilities']) == 2
    monkeypatch.setenv('DEEPSEE_API_KEY', 'never-print-test-key')
    assert cli.main(['--base', 'http://remote.example/api/v1', 'capabilities']) == 2
    class Opener:
        def open(self, request, timeout): return io.BytesIO(b'media')
    monkeypatch.setattr(cli, 'build_opener', lambda *args: Opener())
    output = tmp_path / 'media'; output.write_bytes(b'original')
    assert cli.main(['attachment', '1', '--output', str(output)]) == 1
    assert output.read_bytes() == b'original'
    assert 'never-print-test-key' not in capsys.readouterr().err
