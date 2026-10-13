from types import SimpleNamespace
import pytest
import requests
from fastapi.testclient import TestClient
import astock
import app as app_module

ANN_ID = 'AN202608141827994407'

def payload(**overrides):
    return {'success': 1, 'data': {
        'art_code': ANN_ID, 'security': [{'stock': '600519'}],
        'notice_title': '合成半年报', 'notice_date': '2026-08-15 00:00:00',
        'notice_content': '营业收入 123 亿元。', 'page_size': 2,
        'attach_url': 'https://pdf.dfcfw.com/pdf/test.pdf', **overrides,
    }}

def mock_response(monkeypatch, value):
    def get(url, **kwargs):
        assert url == 'https://np-cnotice-stock.eastmoney.com/api/content/ann'
        assert kwargs['params']['art_code'] == ANN_ID
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: value)
    monkeypatch.setattr(requests, 'get', get)

def test_reads_provider_transcription_not_pdf_and_bounds_text(monkeypatch):
    mock_response(monkeypatch, payload(notice_content='文'*60001))
    result=astock.announcement_text('600519',ANN_ID)
    assert result['date']=='2026-08-15'
    assert result['segmentCount']==2
    assert result['truncated'] is True and len(result['text'])==60000
    assert result['contentOrigin']=='provider-transcription'
    assert result['retrievedAt'].endswith('Z')

@pytest.mark.parametrize('overrides', [
    {'security': [{'stock': '000001'}]}, {'art_code': 'AN000000000000'}, {'notice_content': ''},
])
def test_rejects_wrong_security_id_or_missing_content(monkeypatch, overrides):
    mock_response(monkeypatch,payload(**overrides))
    with pytest.raises(ValueError): astock.announcement_text('600519',ANN_ID)

def test_route_rejects_url_and_invalid_segment_without_fetch(monkeypatch):
    calls=[]
    monkeypatch.setattr(astock,'announcement_text',lambda *args: calls.append(args))
    client=TestClient(app_module.app)
    assert client.get('/api/announcement-text',params={'code':'600519','announcementId':'https://localhost/secret'}).status_code==422
    assert client.get('/api/announcement-text',params={'code':'600519','announcementId':ANN_ID,'segment':0}).status_code==422
    assert not calls
