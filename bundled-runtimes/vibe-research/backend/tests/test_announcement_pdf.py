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
    with pytest.raises(ValueError, match='本次未读取正文'):
        astock.announcement_pdf_page('600519', ANN_ID, 1)
    assert not astock._ANN_PDF_CACHE
