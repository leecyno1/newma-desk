import httpx
import pytest

from vibe_visualization_api.policy_analysis.documents import fetch_official_document, parse_official_document
from vibe_visualization_api.policy_analysis.service import build_policy_interpretation
from vibe_visualization_api.policy_analysis.store import PolicyStore
from vibe_visualization_api.policy_analysis.research import compare_documents, transmission_hypotheses


# Synthetic official-page structure, not a real policy or investment conclusion.
HTML = """<html><head><meta name="author" content="网站编辑"></head><body>
<nav>首页 投资入口</nav><table class="bd1">
<tr><td><b>发文机关：</b></td><td>测试机关</td><td>成文日期：</td><td>2026年09月19日</td></tr>
<tr><td>标题：</td><td colspan="3">测试政策条例</td></tr>
<tr><td>发文字号：</td><td>测试〔2026〕1号</td><td>发布日期：</td><td>2026年09月24日</td></tr>
</table><div id="UCAP-CONTENT"><script>不能作为正文</script>
<p>第一条 为加强政策研究工作，明确依法履行职责，制定本条例。相关观察结论仅用于测试，不能作为任何真实政策的解读依据。</p>
<p>第二条 到2027年完成测试目标，并参考2020年1月1日施行的其他文件。</p>
<p>第三条 本条例自2026年12月1日起施行。</p>
</div><footer>版权所有</footer></body></html>"""
URL = "https://www.gov.cn/zhengce/content/test.htm"


def test_document_excludes_navigation_and_distinguishes_dates():
    result = parse_official_document(HTML, URL)
    assert result["issuer"] == "测试机关"
    assert result["title"] == "测试政策条例"
    assert result["publishedAt"] == "2026-09-24"
    assert result["issuedAt"] == "2026-09-19"
    assert result["effectiveAt"] == "2026-12-01"
    assert "首页" not in result["text"] and "不能作为正文" not in result["text"]
    assert result["effectiveDateQuote"].startswith("第三条")


def test_targets_and_other_documents_are_not_effective_dates():
    result = parse_official_document(HTML.replace("本条例自2026年12月1日起施行。", "施行日期待明确。"), URL)
    assert result["effectiveAt"] is None
    assert result["effectiveDateQuote"] is None
    with pytest.raises(ValueError, match="未识别到官方正文"):
        parse_official_document("<nav>只有导航没有正文</nav>", URL)


@pytest.mark.asyncio
async def test_redirect_to_non_official_host_is_not_fetched():
    calls = []
    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://127.0.0.1/private"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="官方来源"):
            await fetch_official_document(URL, client=client)
    assert calls == [URL]


@pytest.mark.asyncio
async def test_official_fetch_and_failed_fetch_preserve_saved_versions(tmp_path):
    store = PolicyStore(tmp_path / "policy.db")
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, text=HTML, headers={"content-type": "text/html; charset=utf-8"}),
    )) as client:
        document = await fetch_official_document(URL, client=client)
    first = store.save_document("test", document)
    assert store.save_document("test", {**document, "fetchedAt": "2026-10-13T12:00:00+00:00"})["revision"] == first["revision"]
    second = store.save_document("test", {**document, "text": document["text"].replace("2027年", "2028年")})
    assert second["revision"] != first["revision"]
    assert len(store.document_versions("test")) == 2
    assert "text" not in store.document_summaries()["test"]
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(503))) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await fetch_official_document(URL, client=client)
    assert store.document_versions("test")[0]["revision"] == second["revision"]


def test_assessment_is_not_fact_and_future_documents_are_not_history():
    event = {"id": "test", "title": "测试政策", "date": "2026-09-01", "summary": "官方摘要",
             "sourceUrl": URL, "rationale": ["规则判断"], "marketScope": [], "documentType": "formal-policy"}
    future = {**event, "id": "future", "date": "2026-10-01"}
    interpretation = build_policy_interpretation(event, [future])
    assert interpretation["impactAnalysis"]["facts"] == ["官方摘要"]
    assert interpretation["assessment"]["rationale"] == ["规则判断"]
    assert not interpretation["historicalComparison"]["matchedPolicies"]


def test_text_comparison_does_not_substitute_summary_or_truncated_text():
    before = parse_official_document(HTML, URL)
    after = parse_official_document(HTML.replace("2027年", "2028年"), URL)
    result = compare_documents(after, before, relation="same-page-revision")
    assert result["status"] == "available" and result["changeCount"] == 1
    assert "2027年" in result["changes"][0]["before"][0]
    assert "2028年" in result["changes"][0]["after"][0]
    assert result["relation"] == "same-page-revision"
    assert compare_documents(after, None)["status"] == "unavailable"
    assert compare_documents({**after, "truncated": True}, before)["status"] == "unavailable"


def test_transmission_is_anchored_in_body_not_summary():
    document = parse_official_document(HTML.replace("加强政策研究工作", "加强人工智能与算力研究工作"), URL)
    document["revision"] = 7
    rows = transmission_hypotheses(document)
    technology = next(row for row in rows if row["id"] == "technology")
    assert technology["status"] == "hypothesis" and technology["reviewStatus"] == "unreviewed"
    assert technology["documentRevision"] == 7
    assert technology["evidence"][0]["quote"] in document["text"]
    assert technology["indicators"] and technology["invalidation"]
    assert not transmission_hypotheses(None)


@pytest.mark.asyncio
async def test_gov_discovery_uses_official_index_when_rsshub_fails():
    from vibe_visualization_api.policy_analysis.collector import collect_policy_feeds
    from vibe_visualization_api.policy_analysis.service import OFFICIAL_SOURCES
    def handler(request):
        if request.url.host == "rsshub.local":
            return httpx.Response(503)
        assert str(request.url) == "https://www.gov.cn/zhengce/zuixin/ZUIXINZHENGCE.json"
        return httpx.Response(200, json=[{"TITLE": "测试政策通知", "URL": URL, "DOCRELPUBTIME": "2026-09-24"}])
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        events, state = await collect_policy_feeds([OFFICIAL_SOURCES[0]], "http://rsshub.local", 1, client)
    assert state["status"] == "ready"
    assert "JSON" in state["feeds"][0]["reason"]
    assert events[0]["sourceUrl"] == URL
    assert "正文尚未读取" in events[0]["summary"]


def test_sector_framework_is_not_strategic_due_to_referenced_authority():
    from vibe_visualization_api.policy_analysis.collector import assess_policy
    assert assess_policy("铁路科技创新规划通知", "依据国务院条例推进工作")[0] == 2


def test_import_document_persists_and_interpretation_uses_body(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from vibe_visualization_api.main import create_app
    from vibe_visualization_api.config import Settings
    async def fetch(url):
        return parse_official_document(HTML, URL)
    monkeypatch.setattr("vibe_visualization_api.policy_analysis.routes.fetch_official_document", fetch)
    with TestClient(create_app(Settings(database_path=tmp_path / "policy.db"))) as client:
        result = client.post("/api/policy-analysis/import", json={"url": URL})
        assert result.status_code == 200
        identity = result.json()["event"]["id"]
        document = client.get(f"/api/policy-analysis/events/{identity}/document").json()
        assert document["text"] and document["revision"]
        report = client.post(f"/api/policy-analysis/events/{identity}/interpretation").json()
        assert report["impactAnalysis"]["basis"] == "official-text-excerpts"
        assert report["reviewStatus"] == "unreviewed"
        events = client.get("/api/policy-analysis?as_of=2026-10-13").json()["events"]
        event = next(item for item in events if item["id"] == identity)
        assert event["lifecycleStage"] == "published"  # Dec 1 is not effective in October.
        events = client.get("/api/policy-analysis?as_of=2026-12-02").json()["events"]
        event = next(item for item in events if item["id"] == identity)
        assert event["lifecycleStage"] == "effective"
        assert event["lifecycleBasis"] == "official-effective-date"
