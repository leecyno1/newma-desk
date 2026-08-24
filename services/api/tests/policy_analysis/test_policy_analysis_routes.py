import asyncio
import json

from fastapi.testclient import TestClient

import httpx
import pytest

from vibe_visualization_api.main import create_app
from vibe_visualization_api.agent_gateway.models import AgentTask, AgentTaskCreate
from vibe_visualization_api.policy_analysis.collector import (
    assess_policy,
    classify_document_type,
    classify_lifecycle,
    extract_policy_entities,
    is_policy_document,
    clean_policy_text,
    collect_policy_feeds,
    parse_policy_feed,
)
from vibe_visualization_api.policy_analysis.store import PolicyStore
from vibe_visualization_api.policy_analysis.refresher import PolicyRefreshService
from vibe_visualization_api.policy_analysis.service import compare_policy_events


def test_policy_dashboard_exposes_calendar_sources_and_levels(tmp_path):
    from vibe_visualization_api.config import Settings

    app = create_app(Settings(database_path=tmp_path / "policy.db"))
    with TestClient(app) as client:
        response = client.get("/api/policy-analysis?as_of=2026-08-15")
    assert response.status_code == 200
    payload = response.json()
    assert payload["schemaVersion"] == "newma-desk.policy-analysis.v1"
    assert {item["level"] for item in payload["events"]} == {1, 2, 3}
    assert any(item["id"] == "pbc" for item in payload["sources"])
    assert next(item for item in payload["sources"] if item["id"] == "stats")["rssHubPath"]
    assert all(item["sourceUrl"].startswith("https://") for item in payload["events"])
    assert all("lifecycleStage" in item for item in payload["events"])
    assert all("relatedPolicyIds" in item for item in payload["events"])
    assert all("entities" in item and "comparison" in item for item in payload["events"])
    assert payload["summary"]["lifecycle"]["scheduled"] >= 1
    assert set(payload["summary"]["lifecycle"]) == {
        "scheduled", "solicitation", "published", "effective",
        "amended", "adjusted", "repealed", "expired",
    }
    assert payload["collector"]["status"] == "not-configured"
    with TestClient(app) as client:
        refresh_response = client.post("/api/policy-analysis/refresh")
    assert refresh_response.status_code == 200


def test_policy_assessment_can_be_reviewed_through_api(tmp_path):
    from vibe_visualization_api.config import Settings

    app = create_app(Settings(database_path=tmp_path / "policy.db"))
    with TestClient(app) as client:
        dashboard = client.get("/api/policy-analysis?as_of=2026-08-15").json()
        event_id = dashboard["events"][0]["id"]
        response = client.patch(
            f"/api/policy-analysis/events/{event_id}/assessment",
            json={"level": 2, "note": "研究员复核"},
        )
    assert response.status_code == 200
    assert response.json()["level"] == 2
    assert response.json()["assessmentStatus"] == "reviewed"
    assert response.json()["assessmentConfidence"] == 1


def test_published_policy_can_be_interpreted_with_safe_fallback(tmp_path):
    from vibe_visualization_api.config import Settings

    app = create_app(Settings(database_path=tmp_path / "policy.db"))
    with TestClient(app) as client:
        dashboard = client.get("/api/policy-analysis?as_of=2026-08-15").json()
        event = next(item for item in dashboard["events"] if item["status"] == "published")
        response = client.post(
            f"/api/policy-analysis/events/{event['id']}/interpretation"
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["policyId"] == event["id"]
    assert payload["mode"] == "rule-fallback"
    assert payload["impactAnalysis"]["facts"]
    assert payload["transcriptComparison"]["status"] == "unavailable"


def test_published_policy_prefers_declared_agent_action(tmp_path):
    from vibe_visualization_api.config import Settings

    app = create_app(Settings(database_path=tmp_path / "policy.db"))
    repository = app.state.resolve_module_repository()
    draft = repository.create_draft(
        {
            "id": "policy-interpretation",
            "schemaVersion": "1.1",
            "actions": {
                "policy.interpret": {
                    "binding": {"type": "agent"},
                }
            },
        }
    )
    repository.publish("policy-interpretation", draft.revision)
    captured = {}

    class _FakeAgentService:
        async def create(self, request, *, workspace_id):
            captured["request"] = request
            captured["workspace_id"] = workspace_id
            return AgentTask(id="policy-task", status="queued", request=request)

        async def get(self, task_id):
            request = captured["request"].model_copy(
                update={"adapter": "minimax-cli", "model": "MiniMax-M3"}
            )
            return AgentTask(
                id=task_id,
                status="completed",
                request=request,
                result={
                    "answer": json.dumps(
                        {
                            "impactAnalysis": {
                                "facts": ["Agent 事实"],
                                "inferences": ["Agent 推断"],
                                "uncertainties": ["Agent 不确定性"],
                            },
                            "historicalComparison": {
                                "matchedPolicies": [],
                                "added": [],
                                "removed": [],
                                "shared": [],
                                "note": "Agent 历史对比",
                            },
                            "transcriptComparison": {
                                "status": "unavailable",
                                "basis": "summary",
                                "note": "缺少两份官方正文",
                            },
                        },
                        ensure_ascii=False,
                    ),
                    "agentId": "minimax-cli",
                },
            )

        async def cancel(self, task_id):
            raise AssertionError(f"不应取消已完成任务 {task_id}")

        async def shutdown(self):
            return None

    app.state.agent_task_service = _FakeAgentService()
    with TestClient(app) as client:
        dashboard = client.get("/api/policy-analysis?as_of=2026-08-15").json()
        event = next(item for item in dashboard["events"] if item["status"] == "published")
        response = client.post(
            f"/api/policy-analysis/events/{event['id']}/interpretation",
            headers={"X-User-Id": "policy-user", "X-Workspace-Id": "policy-workspace"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "ai"
    assert payload["adapter"] == "minimax-cli"
    assert payload["model"] == "MiniMax-M3"
    assert payload["impactAnalysis"]["facts"] == ["Agent 事实"]
    assert captured["request"].module_id == "policy-interpretation"
    assert captured["request"].capability == "policy.interpret"
    assert captured["request"].profile == "batch"
    assert captured["request"].command_profile == "batch"
    assert captured["request"].memory_scope == "task"
    assert captured["workspace_id"] == "policy-workspace"


def test_policy_agent_shape_is_normalized_for_the_page(tmp_path):
    from vibe_visualization_api.config import Settings

    app = create_app(Settings(database_path=tmp_path / "policy.db"))
    repository = app.state.resolve_module_repository()
    draft = repository.create_draft({
        "id": "policy-interpretation",
        "schemaVersion": "1.1",
        "actions": {"policy.interpret": {"binding": {"type": "agent"}}},
    })
    repository.publish("policy-interpretation", draft.revision)

    class _Agent:
        async def create(self, request, *, workspace_id):
            return AgentTask(id="policy-shape", status="queued", request=request)

        async def get(self, task_id):
            request = AgentTaskCreate(
                user_id="local-user", module_id="policy-interpretation",
                capability="policy.interpret", profile="batch",
                memory_scope="task", prompt="shape", input={},
            )
            return AgentTask(
                id=task_id, status="completed", request=request,
                result={"answer": json.dumps({
                    "impactAnalysis": {"facts": ["事实"], "inferences": [], "uncertainties": []},
                    "historicalComparison": {"status": "unavailable", "conclusion": "没有历史样本"},
                    "transcriptComparison": {"status": "unavailable", "reason": "缺少正文"},
                }, ensure_ascii=False)},
            )

        async def cancel(self, task_id):
            return None

        async def shutdown(self):
            return None

    app.state.agent_task_service = _Agent()
    with TestClient(app) as client:
        dashboard = client.get("/api/policy-analysis?as_of=2026-08-15").json()
        event = next(item for item in dashboard["events"] if item["status"] == "published")
        payload = client.post(
            f"/api/policy-analysis/events/{event['id']}/interpretation"
        ).json()

    assert payload["historicalComparison"]["matchedPolicies"] == []
    assert payload["historicalComparison"]["added"] == []
    assert payload["historicalComparison"]["note"] == "没有历史样本"
    assert payload["transcriptComparison"]["note"] == "缺少正文"


def test_policy_agent_partial_object_lists_are_kept_as_ai_output(tmp_path):
    from vibe_visualization_api.config import Settings

    app = create_app(Settings(database_path=tmp_path / "policy.db"))
    repository = app.state.resolve_module_repository()
    draft = repository.create_draft({
        "id": "policy-interpretation",
        "schemaVersion": "1.1",
        "actions": {"policy.interpret": {"binding": {"type": "agent"}}},
    })
    repository.publish("policy-interpretation", draft.revision)

    class _Agent:
        async def create(self, request, *, workspace_id):
            return AgentTask(id="policy-partial", status="queued", request=request)

        async def get(self, task_id):
            request = AgentTaskCreate(
                user_id="local-user", module_id="policy-interpretation",
                capability="policy.interpret", profile="batch",
                memory_scope="task", prompt="partial", input={},
            )
            return AgentTask(
                id=task_id, status="completed", request=request,
                result={"answer": (
                    '{"impactAnalysis":{"facts":[{"field":"操作量","value":"950亿元",'
                    '"source":"官方摘要"}],"inferences":[{"sector":"债券","direction":"偏支持",'
                    '"reasoning":"逆回购投放"}],"risks":[{"description":"缺少到期量"}]}}'
                    ',"historicalComparison":{"status":"unavailable","note":"没有历史样本"}'
                    ',"transcriptComparison":{"status":"unavailable","reason":"缺少正文"}}'
                )},
            )

        async def cancel(self, task_id):
            return None

        async def shutdown(self):
            return None

    app.state.agent_task_service = _Agent()
    with TestClient(app) as client:
        dashboard = client.get("/api/policy-analysis?as_of=2026-08-15").json()
        event = next(item for item in dashboard["events"] if item["status"] == "published")
        payload = client.post(
            f"/api/policy-analysis/events/{event['id']}/interpretation"
        ).json()

    assert payload["mode"] == "ai"
    assert payload["impactAnalysis"]["facts"] == ["操作量：950亿元（官方摘要）"]
    assert payload["impactAnalysis"]["inferences"] == ["债券 · 偏支持：逆回购投放"]
    assert payload["impactAnalysis"]["uncertainties"] == ["缺少到期量"]
    assert payload["historicalComparison"]["matchedPolicies"] == []
    assert payload["historicalComparison"]["note"] == "没有历史样本"
    assert payload["transcriptComparison"]["status"] == "unavailable"
    assert payload["transcriptComparison"]["note"] == "缺少正文"


def test_scheduled_policy_cannot_be_interpreted(tmp_path):
    from vibe_visualization_api.config import Settings

    app = create_app(Settings(database_path=tmp_path / "policy.db"))
    with TestClient(app) as client:
        dashboard = client.get("/api/policy-analysis?as_of=2026-08-15").json()
        event = next(item for item in dashboard["events"] if item["status"] == "scheduled")
        response = client.post(
            f"/api/policy-analysis/events/{event['id']}/interpretation"
        )
    assert response.status_code == 409


def test_policy_feed_keeps_official_link_and_scores_level():
    source = {"id": "pbc", "name": "中国人民银行", "url": "https://www.pbc.gov.cn/", "categories": ["货币政策"]}
    events = parse_policy_feed("""<?xml version="1.0"?><rss><channel><item>
      <title>中国人民银行决定降低存款准备金率</title>
      <link>https://www.pbc.gov.cn/example.html</link>
      <pubDate>Fri, 15 Aug 2026 08:00:00 GMT</pubDate>
      <description>政策原文摘要</description>
    </item></channel></rss>""", source)
    assert events[0]["sourceUrl"] == "https://www.pbc.gov.cn/example.html"
    assert events[0]["level"] == 3
    assert events[0]["certainty"] == "official"
    assert events[0]["assessmentStatus"] == "machine"
    assert events[0]["documentType"] == "formal-policy"


def test_general_government_news_is_not_treated_as_policy():
    assert not is_policy_document("某同志遗体火化", "政务新闻", "gov")
    assert is_policy_document("国务院关于印发人工智能行动方案的通知", "政策原文", "gov")


def test_policy_assessment_does_not_treat_every_decision_as_strategic():
    level, confidence, rationale = assess_policy(
        "国家发展改革委关于修改部分行政规范性文件的决定"
    )
    assert level == 2
    assert confidence >= 0.6
    assert any("规则" in item for item in rationale)


def test_policy_document_type_reduces_false_strategic_level():
    title = "中共中央政治局召开经济工作会议并发表重要讲话"
    document_type = classify_document_type(title)
    level, _, rationale = assess_policy(
        title,
        document_type=document_type,
    )
    assert document_type == "meeting-speech"
    assert level == 2
    assert any("不直接视为战略级" in item for item in rationale)


def test_policy_lifecycle_classification_links_related_documents():
    stage, key = classify_lifecycle("一图读懂《工业绿色低碳发展“十五五”规划》", "policy-interpretation")
    formal_stage, formal_key = classify_lifecycle("《工业绿色低碳发展“十五五”规划》", "formal-policy")
    assert stage == "published"
    assert formal_stage == "published"
    assert key == formal_key
    assert classify_lifecycle("关于修订某办法的决定", "formal-policy")[0] == "amended"
    assert classify_lifecycle("关于调整某项政策的通知", "formal-policy")[0] == "adjusted"
    assert classify_lifecycle("关于废止某办法的决定", "formal-policy")[0] == "repealed"
    assert classify_lifecycle("关于某办法失效的公告", "formal-policy")[0] == "expired"
    assert classify_lifecycle("关于修订某办法公开征求意见", "formal-policy")[0] == "solicitation"
    assert classify_document_type("《工业绿色低碳发展规划》解读") == "policy-interpretation"


def test_policy_summary_is_plain_text():
    assert clean_policy_text("<p>支持 <b>科技创新</b></p><table><tr><td>扩大投资</td></tr></table>") == (
        "支持 科技创新 扩大投资"
    )


def test_statistics_source_keeps_macro_category():
    source = {"id": "stats", "categories": ["宏观数据"]}
    from vibe_visualization_api.policy_analysis.collector import classify_policy

    category, scope = classify_policy("工业企业利润数据解读", "文化产业企业数据", source)
    assert category == "宏观数据"
    assert "商品" in scope


def test_policy_entities_are_rule_based_and_tradable_subjects_are_explicit():
    entities = extract_policy_entities("医药ETF与医疗服务政策", "ETF代码512010与医药行业")
    by_name = {item["displayName"]: item for item in entities}
    assert by_name["医药ETF"]["canonicalId"] == "etf:CN:512010"
    assert by_name["医药生物"]["source"] == "rule"
    assert by_name["医药生物"]["confidence"] < 1


def test_policy_comparison_is_explicitly_summary_based():
    previous = {"id": "old", "title": "制造业补贴办法", "summary": "补贴100亿元"}
    current = {"id": "new", "title": "制造业补贴办法修订", "summary": "补贴120亿元并强化监管"}
    result = compare_policy_events(current, previous)
    assert result["basis"] == "title-summary"
    assert "120亿元" in result["added"]
    assert "100亿元" in result["removed"]
    assert "制造业" in result["shared"]


@pytest.mark.asyncio
async def test_policy_collector_reports_failed_sources_without_hiding_success():
    sources = [
        {"id": "ok", "name": "正常源", "url": "https://example.gov.cn", "categories": ["综合"], "rssHubPath": "/ok"},
        {"id": "bad", "name": "失败源", "url": "https://example.gov.cn", "categories": ["综合"], "rssHubPath": "/bad"},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/bad":
            return httpx.Response(502)
        return httpx.Response(200, text="""<rss><channel><item><title>政策通知</title>
          <link>https://example.gov.cn/policy/1</link><pubDate>Fri, 15 Aug 2026 08:00:00 GMT</pubDate>
        </item></channel></rss>""")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        events, status = await collect_policy_feeds(sources, "http://rsshub.local", 1, client)
    assert len(events) == 1
    assert status["status"] == "degraded"
    assert [item["status"] for item in status["feeds"]] == ["ok", "failed"]


def test_policy_store_preserves_events_and_source_success_across_failures(tmp_path):
    store = PolicyStore(tmp_path / "policy.db")
    event = {
        "id": "feed-csrc-1", "title": "资本市场管理办法",
        "date": "2026-08-15", "institution": "中国证监会",
        "category": "资本市场", "level": 2, "status": "published",
        "certainty": "official", "summary": "规范市场运行。",
        "rationale": ["涉及行业规则"], "sourceUrl": "https://www.csrc.gov.cn/1",
        "marketScope": ["A股"], "assessmentConfidence": 0.7,
        "assessmentStatus": "machine", "contentHash": "hash-1",
    }
    store.upsert_events([event])
    store.record_source_runs(
        [{"sourceId": "csrc", "status": "ok", "items": 1}],
        "2026-08-15T08:00:00+00:00",
    )
    store.record_source_runs(
        [{"sourceId": "csrc", "status": "failed", "items": 0, "reason": "timeout"}],
        "2026-08-16T08:00:00+00:00",
    )

    assert store.list_events()[0]["title"] == "资本市场管理办法"
    assert store.source_runs()["csrc"]["lastSuccessAt"] == "2026-08-15T08:00:00+00:00"
    assert store.source_runs()["csrc"]["reason"] == "timeout"


def test_policy_assessment_review_is_persisted_and_not_overwritten(tmp_path):
    store = PolicyStore(tmp_path / "policy.db")
    event = {
        "id": "feed-csrc-review", "title": "资本市场管理办法",
        "date": "2026-08-15", "institution": "中国证监会",
        "category": "资本市场", "level": 2, "status": "published",
        "certainty": "official", "summary": "规范市场运行。",
        "rationale": ["机器初筛"], "sourceUrl": "https://www.csrc.gov.cn/review",
        "marketScope": ["A股"], "assessmentConfidence": 0.7,
        "assessmentStatus": "machine", "contentHash": "hash-review",
    }
    store.upsert_events([event])
    reviewed = store.review_assessment(event["id"], 3, "影响全市场")
    event.update(level=1, rationale=["机器刷新"], assessmentConfidence=0.5)
    store.upsert_events([event])

    persisted = store.list_events()[0]
    assert reviewed["assessmentStatus"] == "reviewed"
    assert persisted["level"] == 3
    assert persisted["assessmentConfidence"] == 1
    assert any("影响全市场" in item for item in persisted["rationale"])


@pytest.mark.asyncio
async def test_policy_refresher_runs_and_stops_cleanly(tmp_path, monkeypatch):
    calls = 0
    started = asyncio.Event()

    async def fake_dashboard(*args, **kwargs):
        nonlocal calls
        calls += 1
        started.set()
        return {}

    monkeypatch.setattr(
        "vibe_visualization_api.policy_analysis.refresher.policy_dashboard",
        fake_dashboard,
    )
    service = PolicyRefreshService(
        database_path=tmp_path / "policy.db",
        rsshub_base_url="http://rsshub.local",
        timeout_seconds=1,
        interval_seconds=300,
    )
    service.start()
    await asyncio.wait_for(started.wait(), timeout=1)
    await service.stop()

    assert calls == 1
