from io import BytesIO
from types import SimpleNamespace
import pytest
import requests
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
from fastapi.testclient import TestClient
import astock
import app as app_module

ANN_ID = 'AN202608141827994407'


@pytest.fixture(autouse=True)
def clear_pdf_cache():
    astock._ANN_PDF_CACHE.clear()
    yield
    astock._ANN_PDF_CACHE.clear()


def pdf_bytes():
    writer = PdfWriter()
    page = writer.add_blank_page(300, 300)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
    stream = DecodedStreamObject()
    stream.set_data(b'BT /F1 12 Tf 30 250 Td (Revenue 123 million) Tj ET')
    page[NameObject('/Contents')] = stream
    writer.add_blank_page(300, 300)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def mock_pdf(monkeypatch, url='https://pdf.dfcfw.com/report.pdf'):
    payload = {'success': 1, 'data': {'art_code': ANN_ID, 'security': [{'stock': '600519'}], 'notice_title': 'PDF only', 'attach_url': url, 'notice_content': ''}}
    class Response:
        status_code = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def raise_for_status(self): pass
        def iter_content(self, size): yield pdf_bytes()
    def get(target, **kwargs):
        if target.endswith('/api/content/ann'):
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: payload)
        assert target == 'https://pdf.dfcfw.com/report.pdf'
        assert kwargs['allow_redirects'] is False
        return Response()
    monkeypatch.setattr(requests, 'get', get)


def test_reads_actual_physical_pages_without_requiring_transcription(monkeypatch):
    mock_pdf(monkeypatch)
    first = astock.announcement_pdf_page('600519', ANN_ID, 1)
    assert 'Revenue 123 million' in first['text']
    assert first['contentOrigin'] == 'pdf-text'
    assert first['pdfPage'] == 1 and first['pdfPageCount'] == 2
    blank = astock.announcement_pdf_page('600519', ANN_ID, 2)
    assert blank['text'] == '' and blank['pdfPage'] == 2
    with pytest.raises(ValueError, match='共 2 页'):
        astock.announcement_pdf_page('600519', ANN_ID, 3)


def test_rejects_attachment_outside_provider_host(monkeypatch):
    mock_pdf(monkeypatch, 'https://127.0.0.1/internal.pdf')
    with pytest.raises(ValueError, match='PDF 附件'):
        astock.announcement_pdf_page('600519', ANN_ID)


def test_pdf_route_page_and_source_validation(monkeypatch):
    mock_pdf(monkeypatch)
    client = TestClient(app_module.app)
    params = {'code': '600519', 'announcementId': ANN_ID}
    assert client.get('/api/announcement-pdf-page', params={**params, 'page': 1}).json()['data']['pdfPage'] == 1
    assert client.get('/api/announcement-pdf-page', params={**params, 'page': 0}).status_code == 422
    assert client.get('/api/announcement-pdf-page', params={**params, 'code': '000001'}).status_code == 422


def test_reuses_pdf_bytes_and_original_retrieval_time(monkeypatch):
    mock_pdf(monkeypatch)
    first = astock.announcement_pdf_page('600519', ANN_ID, 1)
    original_get = requests.get
    def metadata_only(url, **kwargs):
        assert url.endswith('/api/content/ann'), '翻页不应重复下载同一 PDF'
        return original_get(url, **kwargs)
    monkeypatch.setattr(requests, 'get', metadata_only)
    second = astock.announcement_pdf_page('600519', ANN_ID, 2)
    assert second['retrievedAt'] == first['retrievedAt']


def test_provider_html_challenge_is_not_read_or_cached_as_pdf(monkeypatch):
    mock_pdf(monkeypatch)
    monkeypatch.setitem(globals(), 'pdf_bytes', lambda: b'<script>provider verification</script>')
    with pytest.raises(astock.AnnouncementSourceUnavailable, match='本次未读取正文'):
        astock.announcement_pdf_page('600519', ANN_ID, 1)
    assert not astock._ANN_PDF_CACHE


@pytest.mark.parametrize('path', ['/api/announcement-pdf-page', '/api/equity-research/statement-evidence'])
def test_source_challenge_is_not_a_user_input_error(monkeypatch, path):
    mock_pdf(monkeypatch)
    monkeypatch.setitem(globals(), 'pdf_bytes', lambda: b'<script>provider verification</script>')
    response = TestClient(app_module.app).get(path, params={'code': '600519', 'announcementId': ANN_ID})
    assert response.status_code == 503
    assert '本次未读取正文' in response.json()['detail']
    assert not astock._ANN_PDF_CACHE


def test_explicit_cninfo_source_verifies_security_and_exact_attachment(monkeypatch):
    announcement = {'secCode':'300502', 'announcementId':'1225499406', 'announcementTitle':'2026年半年度报告',
                    'announcementTime':1787587200000, 'adjunctUrl':'finalpage/2026-08-25/1225499406.PDF'}
    def post(url, **kwargs):
        assert url == 'https://www.cninfo.com.cn/new/announcement/bulletin_detail'
        assert kwargs['params']['announceId'] == '1225499406'
        return SimpleNamespace(raise_for_status=lambda:None, json=lambda:{'announcement':announcement})
    monkeypatch.setattr(requests, 'post', post)
    monkeypatch.setattr(astock, '_announcement_pdf_bytes', lambda url:(pdf_bytes(), '2026-10-20T00:00:00Z'))
    metadata, url, reader, _ = astock._announcement_pdf_document('300502', '1225499406', 'cninfo')
    assert url == 'https://static.cninfo.com.cn/finalpage/2026-08-25/1225499406.PDF'
    assert metadata['notice_date'] == '2026-08-25' and len(reader.pages)==2
    with pytest.raises(ValueError, match='当前证券'):
        astock._announcement_pdf_document('600519', '1225499406', 'cninfo')
    announcement['adjunctUrl'] = 'https://example.com/1225499406.pdf'
    with pytest.raises(ValueError, match='编号一致'):
        astock._announcement_pdf_document('300502', '1225499406', 'cninfo')
    with pytest.raises(ValueError, match='编号无效'):
        astock._announcement_pdf_document('300502', ANN_ID, 'cninfo')
