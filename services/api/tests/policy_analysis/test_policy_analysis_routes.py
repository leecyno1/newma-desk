from fastapi.testclient import TestClient

import httpx
import pytest

from vibe_visualization_api.main import create_app
from vibe_visualization_api.policy_analysis.collector import collect_policy_feeds, parse_policy_feed


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
    assert all(item["sourceUrl"].startswith("https://") for item in payload["events"])
    assert payload["collector"]["status"] == "not-configured"


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
