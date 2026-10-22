import asyncio
from datetime import date

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from vibe_visualization_api import industry_capacity as capacity

URL = "https://www.stats.gov.cn/sj/zxfb/202607/t20260715_1964130.html"


def document():
    return '''<meta name="ArticleTitle" content="2026年二季度全国规模以上工业产能利用率为73.0%">
    <meta name="PubDate" content="2026/07/15 10:00">
    <table><tr><td>行业</td><td>二季度</td><td>上半年</td></tr>
    <tr><td>产能利用率（%）</td><td>比上年同期增减（百分点）</td><td>产能利用率（%）</td><td>比上年同期增减（百分点）</td></tr>
    <tr><td>工业</td><td>73.0</td><td>-1.0</td><td>73.3</td><td>-0.7</td></tr>
    <tr><td>制造业</td><td>73.5</td><td>-0.8</td><td>73.7</td><td>-0.5</td></tr>
    <tr><td>其中：煤炭开采和洗选业</td><td>61.2</td><td>-8.1</td><td>63.6</td><td>-7.0</td></tr>
    <tr><td>计算机、通信和其他电子设备制造业</td><td>78.7</td><td>1.4</td><td>77.2</td><td>1.1</td></tr></table>'''


def parse(html):
    return capacity.parse_capacity(html, URL, "2026-06", today=date(2026, 10, 18))


def test_official_quarter_ytd_pp_and_scope_are_distinct():
    result = parse(document() * 2)
    assert result["coverage"] == 2
    assert len(result["metrics"]) == 4
    assert result["periodEnd"] == "2026-06-30"
    assert result["quarterPeriod"] == "2026年二季度"
    assert result["yearToDatePeriod"] == "2026年上半年"
    coal = result["metrics"][2]
    assert coal["name"] == "煤炭开采和洗选业"
    assert coal["scope"] == "industry"
    assert coal["quarterRate"] == 61.2
    assert coal["quarterYoyPp"] == -8.1
    assert coal["yearToDateRate"] == 63.6
    assert result["metrics"][1]["scope"] == "group"


@pytest.mark.parametrize("old,new", [("二季度", "三季度"), ("上半年", "前三季度"), ("百分点", "%"), ("2026/07/15", "2026/11/15")])
def test_wrong_period_units_and_future_publication_rejected(old, new):
    with pytest.raises(ValueError):
        parse(document().replace(old, new))


def test_missing_zero_and_conflicting_duplicate_values():
    result = parse(document().replace("61.2", "—").replace("-8.1", "0"))
    assert result["metrics"][2]["quarterRate"] is None
    assert result["metrics"][2]["raw"]["quarterRate"] == "—"
    assert result["metrics"][2]["quarterYoyPp"] == 0
    with pytest.raises(ValueError, match="冲突"):
        parse(document() + document().replace("61.2", "62.2"))


def test_discovery_requires_matching_quarter_and_official_host():
    title = "2026年二季度全国规模以上工业产能利用率为73.0%"
    html = f'<a href="{URL}">{title}</a><a href="https://evil.example/r">{title}</a>'
    assert capacity.capacity_links(html, "2026-06") == [URL]
    assert capacity.capacity_links(html, "2026-09") == []


@pytest.mark.parametrize("mode", ["ready", "partial", "missing", "duplicate"])
def test_collection_does_not_substitute_other_quarters(mode):
    def handler(request):
        url = str(request.url)
        if url == URL:
            return httpx.Response(200, text=document())
        if mode == "partial" and url.endswith("index_3.html"):
            return httpx.Response(503)
        title = "2026年二季度全国规模以上工业产能利用率为73.0%"
        if mode == "missing":
            title = title.replace("二季度", "三季度")
        html = f'<a href="{URL}">{title}</a>'
        if mode == "duplicate":
            html += f'<a href="{URL.replace("1964130", "1964131")}">{title}</a>'
        return httpx.Response(200, text=html)
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await capacity.collect_capacity(client, "2026-06")
    if mode in ("missing", "duplicate"):
        with pytest.raises(ValueError, match="唯一匹配"):
            asyncio.run(run())
    else:
        result = asyncio.run(run())
        assert result["periodEnd"] == "2026-06-30"
        assert len(result["discoveryErrors"]) == (1 if mode == "partial" else 0)


def test_refresh_failure_clears_response_and_non_quarter_query_is_rejected(monkeypatch):
    app = FastAPI(); app.include_router(capacity.router)
    monkeypatch.setattr(capacity, "_cache", {"2026-06": (capacity.time.monotonic(), {"metrics": ["old"]})})
    async def failed(client, period):
        raise httpx.ReadTimeout("upstream timeout")
    monkeypatch.setattr(capacity, "collect_capacity", failed)
    with TestClient(app) as client:
        assert client.get("/api/industry-research/capacity?period=2026-06").json()["cached"] is True
        assert client.get("/api/industry-research/capacity?period=2026-08").status_code == 422
        response = client.get("/api/industry-research/capacity?period=2026-06&refresh=true")
        assert response.status_code == 502
        assert "metrics" not in response.json()
