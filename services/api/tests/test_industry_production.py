import asyncio
from datetime import date

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from vibe_visualization_api import industry_production as production

URL = "https://www.stats.gov.cn/sj/zxfb/202609/t20260915_1965308.html"


def document():
    return '''<meta name="ArticleTitle" content="2026年8月份规模以上工业增加值增长5.2%">
    <meta name="PubDate" content="2026/09/15 10:00">
    <table><tr><td>指标</td><td>8月</td><td>1—8月</td></tr>
    <tr><td>绝对量</td><td>同比增长（%）</td><td>绝对量</td><td>同比增长（%）</td></tr>
    <tr><td>规模以上工业增加值</td><td>…</td><td>5.2</td><td>…</td><td>5.3</td></tr>
    <tr><td>主要行业增加值</td><td></td><td></td><td></td><td></td></tr>
    <tr><td>煤炭开采和洗选业</td><td>…</td><td>-5.6</td><td>…</td><td>0.8</td></tr>
    <tr><td>规模以上工业主要产品产量</td><td></td><td></td><td></td><td></td></tr>
    <tr><td>原煤（万吨）</td><td>36182</td><td>-7.7</td><td>306443</td><td>-3.3</td></tr>
    <tr><td>集成电路（亿块）</td><td>529</td><td>20.6</td><td>3860</td><td>22.3</td></tr>
    <tr><td>微型计算机设备（万台）</td><td>2075</td><td>-25.6</td><td>18683</td><td>-14.7</td></tr>
    <tr><td>移动通信手持机（万台）</td><td>10207</td><td>-18.0</td><td>87418</td><td>-5.6</td></tr>
    <tr><td>产品销售率（%）</td><td>96.8</td><td>-0.1（百分点）</td><td>96.2</td><td>0.1（百分点）</td></tr></table>'''


def parse(html):
    return production.parse_production(html, URL, "2026-08", today=date(2026, 10, 18))


def test_monthly_and_cumulative_metrics_are_separate_and_national_totals_excluded():
    data = parse(document() + document())
    assert len(data["metrics"]) == 5
    value_added, coal = data["metrics"][:2]
    assert value_added["monthValue"] is None
    assert value_added["monthYoy"] == -5.6
    assert value_added["cumulativeYoy"] == 0.8
    assert coal["unit"] == "万吨"
    assert coal["monthValue"] == 36182
    assert coal["cumulativeValue"] == 306443
    assert data["periodEnd"] == "2026-08-31"
    assert data["publishedAt"] == "2026-09-15"
    assert data["nationalSales"]["monthRate"] == 96.8
    assert data["nationalSales"]["monthYoyPp"] == -0.1
    assert data["nationalSales"]["cumulativeYoyPp"] == 0.1
    assert data["nationalSales"]["scope"] == "全国规模以上工业"


def test_national_sales_percentage_points_are_not_inferred_from_ambiguous_units():
    data = parse(document().replace("（百分点）", ""))
    assert data["nationalSales"]["monthYoyPp"] is None
    assert data["nationalSales"]["monthRate"] == 96.8
    assert parse(document().replace("产品销售率（%）", "产品销售率（元）"))["nationalSales"] is None


@pytest.mark.parametrize("old,new", [("8月份", "7月份"), ("2026/09/15", "2026/11/15"), ("同比增长（%）", "环比增长（%）"), ("1—8月", "1—7月")])
def test_wrong_reporting_period_and_columns_are_rejected(old, new):
    with pytest.raises(ValueError):
        parse(document().replace(old, new))


def test_unknown_values_preserved_and_conflicting_duplicates_rejected():
    data = parse(document().replace("-7.7", "—").replace("-3.3", "0"))
    assert data["metrics"][1]["monthYoy"] is None
    assert data["metrics"][1]["raw"]["monthYoy"] == "—"
    assert data["metrics"][1]["cumulativeYoy"] == 0
    with pytest.raises(ValueError, match="冲突"):
        parse(document() + document().replace("-7.7", "-7.8"))


def test_unit_change_does_not_silently_relabel_product():
    data = parse(document().replace("原煤（万吨）", "原煤（亿吨）"))
    assert not any(item["name"] == "原煤" for item in data["metrics"])


def test_discovery_matches_requested_period_and_official_host():
    title = "2026年8月份规模以上工业增加值增长5.2%"
    html = f'<a href="{URL}">{title}</a><a href="https://evil.example/report">{title}</a><a href="{URL}">解读：{title}</a>'
    assert production.production_links(html, "2026-08") == [URL]
    assert production.production_links(html, "2026-07") == []


@pytest.mark.parametrize("mode", ["ok", "partial", "missing", "duplicate"])
def test_collect_reports_discovery_failures_and_never_substitutes_another_month(mode):
    def handler(request):
        url = str(request.url)
        if mode == "partial" and url.endswith("index_3.html"):
            return httpx.Response(503)
        if url == URL:
            return httpx.Response(200, text=document())
        title = "2026年8月份规模以上工业增加值增长5.2%" if mode != "missing" else "2026年7月份规模以上工业增加值增长4.5%"
        listing = f'<a href="{URL}">{title}</a>'
        if mode == "duplicate":
            listing += f'<a href="{URL.replace("1965308", "1965309")}">{title}</a>'
        return httpx.Response(200, text=listing)
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await production.collect_production(client, "2026-08")
    if mode in ("missing", "duplicate"):
        with pytest.raises(ValueError):
            asyncio.run(run())
    else:
        result = asyncio.run(run())
        assert result["sourceUrl"] == URL
        assert len(result["discoveryErrors"]) == (1 if mode == "partial" else 0)


def test_refresh_failure_does_not_return_cache_and_invalid_month_is_rejected(monkeypatch):
    app = FastAPI(); app.include_router(production.router)
    monkeypatch.setattr(production, "_cache", {"2026-08": (production.time.monotonic(), {"metrics": ["old"]})})
    async def failed(client, period):
        raise httpx.ReadTimeout("upstream timeout")
    monkeypatch.setattr(production, "collect_production", failed)
    with TestClient(app) as client:
        assert client.get("/api/industry-research/production?period=2026-08").json()["cached"] is True
        assert client.get("/api/industry-research/production?period=2026-13").status_code == 422
        response = client.get("/api/industry-research/production?period=2026-08&refresh=true")
        assert response.status_code == 502
        assert "metrics" not in response.json()
