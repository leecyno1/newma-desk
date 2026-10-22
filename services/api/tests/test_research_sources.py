import ipaddress
from io import BytesIO

import httpx
import pytest

from vibe_visualization_api import research_sources as sources
from vibe_visualization_api.data_services.client import UnsafeServiceUrl
from tests.mod_storage.test_routes import client, _manifest, _publish, _session_headers
from pypdf import PdfWriter
from pypdf.generic import NameObject, DictionaryObject, DecodedStreamObject


HTML = """<html><head><title>Official supplier statement</title><meta property="article:published_time" content="2026-08-01T09:00:00Z"></head>
<body><nav>ignore navigation</nav><article><h1>Supplier disclosure</h1><p>Alpha supplies optical components to Beta. The disclosure does not quantify dependency or future revenue.</p><script>malicious()</script></article></body></html>"""


@pytest.fixture
def public_dns(monkeypatch):
    def resolve(host, port):
        if host == "issuer.example":
            return {ipaddress.ip_address("93.184.215.14")}
        raise UnsafeServiceUrl("not public")
    monkeypatch.setattr(sources, "public_host_addresses", resolve)


@pytest.mark.asyncio
async def test_reads_plain_source_with_pinned_ip_sni_and_exact_quote(public_dns):
    def respond(request):
        assert request.url.host == "93.184.215.14"
        assert request.headers["host"] == "issuer.example"
        assert request.extensions["sni_hostname"] == "issuer.example"
        assert "authorization" not in request.headers and "cookie" not in request.headers
        return httpx.Response(200, headers={"content-type": "text/html"}, text=HTML)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        result = await sources.read_source(sources.SourceRead(url="https://issuer.example/story#p1", quote="Alpha supplies optical components to Beta.", asOf="2026-07-31"), client=http)
    assert result["status"] == "readable"
    assert result["quoteMatch"] == "found"
    assert result["claimVerified"] is False
    assert result["afterCutoff"] is True
    assert result["publishedAt"] == "2026-08-01"
    assert "malicious" not in result["text"] and "navigation" not in result["text"]
    assert result["paragraphs"][1]["locator"] == "网页提取段落 2"
    assert result["finalUrl"].startswith("https://issuer.example/")


@pytest.mark.asyncio
@pytest.mark.parametrize("status,expected", [(404,"not_found"),(410,"not_found"),(403,"restricted"),(429,"restricted"),(500,"unavailable")])
async def test_http_failures_do_not_become_readable(public_dns,status,expected):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(status))) as http:
        result = await sources.read_source(sources.SourceRead(url="https://issuer.example/"), client=http)
    assert result["status"] == expected
    assert result["claimVerified"] is False
    assert result["paragraphs"] == []


@pytest.mark.asyncio
async def test_rechecks_redirects_and_never_connects_to_private_network(public_dns):
    calls=[]
    def respond(request):
        calls.append(str(request.url))
        return httpx.Response(302,headers={"location":"http://127.0.0.1/admin"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        result = await sources.read_source(sources.SourceRead(url="https://issuer.example/"), client=http)
    assert result["status"] == "blocked"
    assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("url",["file:///etc/passwd","http://127.0.0.1/","https://user:secret@issuer.example/","http://issuer.example:8911/","http://localhost/","http://[::1]/","http://169.254.169.254/"])
async def test_rejects_unsafe_destinations_before_request(public_dns,url):
    def respond(_):
        pytest.fail("unsafe destination must not be requested")
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        assert (await sources.read_source(sources.SourceRead(url=url),client=http))["status"]=="blocked"


@pytest.mark.asyncio
async def test_limits_type_size_and_does_not_infer_publication_date(public_dns):
    for headers, text, expected in [
        ({"content-type":"application/pdf"},"%PDF-test","unreadable"),
        ({"content-type":"text/html"},"x"*(sources.MAX_BYTES+1),"too_large"),
        ({"content-type":"text/html"},"<title>404 - Page not found</title><main>"+"text"*30+"</main>","not_found"),
        ({"content-type":"text/html"},"<title>Just a moment</title>","restricted"),
        ({"content-type":"text/plain"},"A real source paragraph without any publication metadata. "*3,"readable"),
    ]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _:httpx.Response(200,headers=headers,text=text))) as http:
            result=await sources.read_source(sources.SourceRead(url="https://issuer.example/",quote="nonexistent wording",asOf="2026-01-01"),client=http)
        assert result["status"]==expected
        if expected=="readable":
            assert result["publishedAt"] is None
            assert result["afterCutoff"] is None
            assert result["quoteMatch"]=="not_found"


def test_endpoint_requires_current_mod_session_and_read_permission(client,monkeypatch):
    async def read(body):
        return {"status":"restricted","claimVerified":False,"sourceUrl":body.url}
    monkeypatch.setattr(sources,"read_source",read)
    manifest=_manifest();manifest["permissions"].append("analysis.read");_publish(client,manifest)
    endpoint="/api/mods/research-notes/sources/read";body={"url":"https://issuer.example/"}
    assert client.post(endpoint,json=body).status_code==401
    headers=_session_headers(client)
    assert client.post(endpoint,json=body,headers=headers).json()["status"]=="restricted"
    assert client.post(endpoint,json=body,headers={**headers,"X-Newma-Desk-Instance-Id":"other"}).status_code==403
    assert client.post("/api/mods/another-module/sources/read",json=body,headers=headers).status_code==403
    manifest["version"]="1.1.0";manifest["permissions"].remove("analysis.read");_publish(client,manifest)
    assert client.post(endpoint,json=body,headers=headers).status_code==403
    assert client.post(endpoint,json=body,headers=_session_headers(client)).status_code==403


def pdf_fixture(*texts, encrypted=False):
    writer = PdfWriter()
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
    for text in texts:
        page = writer.add_blank_page(width=600, height=800)
        if text:
            page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
            stream = DecodedStreamObject()
            stream.set_data(f'BT /F1 12 Tf 50 700 Td ({text}) Tj ET'.encode())
            page[NameObject('/Contents')] = stream
    writer.add_metadata({'/Title': 'Synthetic source fixture', '/CreationDate': 'D:20260801000000'})
    if encrypted:
        writer.encrypt('test-only')
    output = BytesIO(); writer.write(output)
    return output.getvalue()


@pytest.mark.asyncio
async def test_pdf_worker_preserves_physical_pages_and_never_uses_creation_date(public_dns):
    document = pdf_fixture('Cover is not disclosure evidence.', 'Alpha supplies optics to Beta. No dependency ratio is disclosed.', '', 'Future plans are not contracts.')
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, headers={'content-type': 'application/pdf'}, content=document))) as http:
        result = await sources.read_source(sources.SourceRead(url='https://issuer.example/report.pdf', pageStart=2, pageCount=2, quote='Alpha supplies optics to Beta.', asOf='2026-07-01'), client=http)
    assert result['status'] == 'readable' and result['quoteMatch'] == 'found'
    assert result['pageCount'] == 4 and result['readPages'] == [2, 3]
    assert result['textLayerMissingPages'] == [3] and result['nextPage'] == 4
    assert result['partialDocument'] is True
    assert result['paragraphs'][0]['page'] == 2
    assert 'PDF 物理第 2 页' in result['text'] and 'Cover' not in result['text']
    assert result['publishedAt'] is None and result['afterCutoff'] is None and result['claimVerified'] is False


@pytest.mark.asyncio
async def test_pdf_empty_encrypted_bad_range_and_binary_signature(public_dns):
    for content, mime, start, expected in [
        (pdf_fixture(''), 'application/pdf', 1, 'no_text'),
        (pdf_fixture('secret', encrypted=True), 'application/pdf', 1, 'encrypted'),
        (pdf_fixture('valid'), 'application/pdf', 2, 'page_out_of_range'),
        (b'<html>not a pdf</html>', 'application/octet-stream', 1, 'unsupported'),
        (pdf_fixture('A short genuine text layer.'), 'application/octet-stream', 1, 'readable'),
    ]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, headers={'content-type': mime}, content=content))) as http:
            result = await sources.read_source(sources.SourceRead(url='https://issuer.example/report', pageStart=start), client=http)
        assert result['status'] == expected
        assert result['claimVerified'] is False


@pytest.mark.asyncio
async def test_cancelled_pdf_worker_is_killed_and_reaped(monkeypatch):
    import asyncio
    class Process:
        returncode = None
        killed = False
        waited = False
        async def communicate(self, _):
            raise asyncio.CancelledError
        def kill(self):
            self.killed = True
        async def wait(self):
            self.waited = True
            self.returncode = -9
    process = Process()
    async def spawn(*args, **kwargs):
        return process
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', spawn)
    with pytest.raises(asyncio.CancelledError):
        await sources.read_pdf(b'%PDF-', 1, 10)
    assert process.killed and process.waited


@pytest.mark.asyncio
async def test_pdf_quote_crosses_display_block_without_added_spaces(public_dns):
    content = pdf_fixture('x' * 1495 + 'AlphaBetaGamma ' + 'x' * 100)
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, headers={'content-type':'application/pdf'}, content=content))) as http:
        result = await sources.read_source(sources.SourceRead(url='https://issuer.example/report', quote='AlphaBetaGamma'), client=http)
    assert len(result['paragraphs']) == 2
    assert result['quoteMatch'] == 'found'


def test_archive_sources_use_session_scope_and_only_adopted_filing_text(client):
    from tests.research_archive.test_research_archive_routes import _put_document
    manifest = _manifest(); manifest['permissions'].append('analysis.read'); _publish(client, manifest)
    note = {'reportId':'report-one','text':'Adopted original filing text, not an investment conclusion.',
            'pdfPage':9,'pdfPageCount':100,'readPages':[9],'confirmedAt':'2026-08-01T00:00:00Z',
            'truncated':True,'contentOrigin':'pdf-text'}
    source = {'id':'source-one','label':'Discussion','kind':'filing','status':'available','periodEnd':'2025-12-31',
              'basis':'annual','url':'https://issuer.example/report.pdf','discussion':note}
    value = {'workbooks':[{'id':'book-one','mode':'reported','updatedAt':'2026-08-02T00:00:00Z',
             'security':{'name':'Synthetic issuer'},'headline':'private judgment',
             'sourceMaterials':[source, {**source,'id':'stale','status':'stale'},
                 {**source,'id':'manual','discussion':{**note,'contentOrigin':'manual'}},
                 {**source,'id':'unadopted','discussion':{**note,'confirmedAt':None}},
                 {**source,'id':'note','discussion':None,'capitalNote':note}]},
             {'id':'preview','mode':'preview','sourceMaterials':[source]}]}
    _put_document(client,module_id='earnings-workbench',namespace='earnings-workbench',key='workbooks',value=value,user_id='user-a',workspace_id='workspace-a')
    endpoint='/api/mods/research-notes/sources/archive'
    assert client.get(endpoint).status_code==401
    headers=_session_headers(client)
    response=client.get(endpoint,headers={**headers,'X-User-Id':'other','X-Workspace-Id':'other'})
    assert response.status_code==200
    result=response.json()
    assert result['revision']==1 and len(result['materials'])==2
    assert result['materials'][0]['text']==note['text'] and result['materials'][0]['pdfPage']==9
    assert result['materials'][0]['truncated'] is True
    assert 'headline' not in result['materials'][0] and 'publishedAt' not in result['materials'][0]
    assert result['materials'][1]['section']=='capitalNote'
    for options in [{'workspace_id':'other'}, {'user_id':'other'}]:
        assert client.get(endpoint,headers=_session_headers(client,**options)).json()['materials']==[]
    assert client.get(endpoint,headers=headers).json()['revision']==1
    manifest['version']='1.1.0';manifest['permissions'].remove('analysis.read');_publish(client,manifest)
    assert client.get(endpoint,headers=headers).status_code==403
    assert client.get(endpoint,headers=_session_headers(client)).status_code==403


@pytest.mark.parametrize('module_id', ['instock-stock-research', 'instock-research-book'])
def test_company_review_handoff_is_scoped_latest_and_excludes_model_payloads(client, module_id):
    from tests.research_archive.test_research_archive_routes import _put_document
    manifest = _manifest(module_id); manifest['permissions'].append('analysis.read'); _publish(client, manifest)
    endpoint = f'/api/mods/{module_id}/sources/chain-reviews'
    target = {'theme':'test-chain', 'market':'CN', 'source':{'id':'upstream'}, 'target':{'id':'downstream'}}
    first = {'id':'first', 'target':target, 'decision':'supported', 'note':'old opinion'}
    latest = {**first, 'id':'latest', 'decision':'contradicted', 'note':'saved refutation',
              'agentAssistance':{'originalResponse':{'raw':'unnecessary private model response'}}}
    unrelated = {**latest, 'id':'unrelated', 'target':{**target, 'theme':'other-private-topic'}}
    _put_document(client, module_id='instock-industry-chain', namespace='relation-reviews', key='records',
        value={'schemaVersion':1, 'entries':[first, latest, unrelated]}, user_id='user-a', workspace_id='workspace-a')
    body = {'theme':'test-chain','market':'CN','relations':[{'source':'upstream','target':'downstream'}]}
    assert client.post(endpoint, json=body).status_code == 401
    headers = _session_headers(client, module_id=module_id)
    response = client.post(endpoint, json=body, headers={**headers,'X-User-Id':'other','X-Workspace-Id':'other'})
    assert response.status_code == 200
    result = response.json()
    assert result['revision'] == 1
    assert result['book']['entries'] == [{key:value for key,value in latest.items() if key != 'agentAssistance'}]
    assert result['archive'] == {'status':'ready','revision':0,'materials':[]}
    for options in [{'user_id':'other'}, {'workspace_id':'other'}]:
        other = _session_headers(client,module_id=module_id,**options)
        assert client.post(endpoint,json=body,headers=other).json()['book']['entries'] == []
    assert client.post(endpoint,json={**body,'workspaceId':'workspace-a'},headers=headers).status_code == 422
    assert client.post(endpoint,json=body,headers={**headers,'X-Newma-Desk-Instance-Id':'other'}).status_code == 403
    assert client.post('/api/mods/instock-industry-chain/sources/chain-reviews',json=body,headers=headers).status_code == 403
    manifest['version']='1.1.0';manifest['permissions'].remove('analysis.read');_publish(client,manifest)
    assert client.post(endpoint,json=body,headers=headers).status_code == 403
    assert client.post(endpoint,json=body,headers=_session_headers(client,module_id=module_id)).status_code == 403


@pytest.mark.parametrize('module_id', ['instock-stock-research', 'instock-research-book'])
def test_company_review_handoff_rechecks_archives_and_does_not_hide_corrupt_books(client, monkeypatch, module_id):
    from tests.research_archive.test_research_archive_routes import _put_document
    from vibe_visualization_api.mod_storage.store import ModStorageCorruptError
    manifest = _manifest(module_id); manifest['permissions'].append('analysis.read'); _publish(client,manifest)
    endpoint=f'/api/mods/{module_id}/sources/chain-reviews'
    headers=_session_headers(client,module_id=module_id)
    body={'theme':'chain','market':'CN','relations':[{'source':'a','target':'b'}]}
    row={'id':'review','target':{'theme':'chain','market':'CN','source':{'id':'a'},'target':{'id':'b'}},
         'archiveSource':{'workbookId':'book','sourceId':'source','text':'original passage'}}
    _put_document(client,module_id='instock-industry-chain',namespace='relation-reviews',key='records',
                  value={'schemaVersion':1,'entries':[row]},user_id='user-a',workspace_id='workspace-a')
    def archive(**scope):
        assert scope == {'user_id':'user-a','workspace_id':'workspace-a'}
        return {'revision':7,'materials':[{'workbookId':'book','sourceId':'source','text':'changed passage'},
                                         {'workbookId':'unrelated','sourceId':'source','text':'private unrelated material'}]}
    monkeypatch.setattr(client.app.state.research_archive_service,'relation_inputs',archive)
    result=client.post(endpoint,json=body,headers=headers).json()
    assert result['archive']['materials'] == [{'workbookId':'book','sourceId':'source','text':'changed passage'}]
    assert result['book']['entries'][0]['archiveSource']['text'] == 'original passage'
    def unreadable(**_): raise ModStorageCorruptError('corrupt fixture')
    monkeypatch.setattr(client.app.state.research_archive_service,'relation_inputs',unreadable)
    assert client.post(endpoint,json=body,headers=headers).json()['archive']['status'] == 'unavailable'
    monkeypatch.setattr(client.app.state.mod_storage_store,'get',unreadable)
    assert client.post(endpoint,json=body,headers=headers).status_code == 503
