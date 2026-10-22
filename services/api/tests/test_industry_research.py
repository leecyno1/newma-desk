import asyncio
from datetime import date

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from vibe_visualization_api import industry_research as research


def document(profit_yoy="51.6", *, duplicate=False):
    table = f"""<table><tr><td>行　业</td><td>营业收入</td><td>营业成本</td><td>利润总额</td></tr>
    <tr><td>金额（亿元）同比增长（%）</td></tr>
    <tr><td>总计</td><td>1000</td><td>10</td><td>800</td><td>8</td><td>100</td><td>20</td></tr>
    <tr><td>煤炭开采和洗选业</td><td>200</td><td>10.4</td><td>150</td><td>4.1</td><td>30</td><td>{profit_yoy}</td></tr>
    <tr><td>开采专业及辅助性活动</td><td>100</td><td>-2</td><td>90</td><td>-3</td><td>5</td><td>0</td></tr></table>"""
    return '<meta name="ArticleTitle" content="2026年1—8月份全国规模以上工业企业利润增长15.7%"><meta name="PubDate" content="2026/09/28 09:30">' + table * (2 if duplicate else 1)


def parse(html):
    return research.parse_publication(html, "https://www.stats.gov.cn/sj/zxfb/202609/t20260928_1965425.html", today=date(2026, 10, 18))


def test_official_units_ratios_and_duplicate_mobile_table():
    data = parse(document(duplicate=True))
    assert data["periodEnd"] == "2026-08-31"
    assert data["publishedAt"] == "2026-09-28"
    assert data["coverage"]["industries"] == 2
    coal, auxiliary = data["rows"]
    assert coal["profitMargin"] == 15
    assert coal["costRatio"] == 75
    assert coal["quadrant"] == "expansion"
    assert auxiliary["quadrant"] == "boundary"


def operations_table():
    headers = ["分组", "营业收入利润率", "每百元营业收入中的成本", "每百元营业收入中的费用", "每百元资产实现的营业收入", "人均营业收入", "资产负债率", "产成品存货周转天数", "应收账款平均回收期"]
    units = ["（%）", "（元）", "（元）", "（元）", "（万元/人）", "（%）", "（天）", "（天）"]
    def tr(items):
        return "<tr>" + "".join(f"<td>{value}</td>" for value in items) + "</tr>"
    rows = [tr(headers), tr(["1-8月"] * 3 + ["8月末"] * 5), tr(units)]
    for name in ["总计", "其中：采矿业", "制造业", "电力、热力、燃气及水生产和供应业", "其中：私营企业"]:
        rows.append(tr([name, "5.66", "85.07", "8.35", "72.4", "192.2", "58.5", "21.3", "72.2"]))
    return "<table>" + "".join(rows) + "</table>"


def test_operations_scope_dedup_units_and_official_yoy():
    paragraph = "<p>8月末，规模以上工业企业产成品存货周转天数为21.3天，同比增加0.6天；应收账款平均回收期为72.2天，同比减少0.9天。</p>"
    result = parse(document() + operations_table() * 2 + paragraph)["operations"]
    assert result["status"] == "ready"
    assert len(result["rows"]) == 4  # ownership groups overlap; do not include them
    national = result["rows"][0]
    assert national["inventoryDays"] == 21.3
    assert national["receivableDays"] == 72.2
    assert national["expensePer100Revenue"] == 8.35
    assert national["inventoryDaysYoyChange"] == 0.6
    assert national["receivableDaysYoyChange"] == -0.9
    assert "inventoryDaysYoyChange" not in result["rows"][1]
    assert result["periodEnd"] == "2026-08-31"
    assert result["scope"] == "全国及工业三大门类，不是41个细分行业"
    wrong_period = parse(document() + operations_table() + paragraph.replace("8月末", "7月末"))
    assert wrong_period["operations"]["rows"][0]["inventoryDaysYoyChange"] is None


def test_missing_or_unrecognized_operations_never_blocks_financial_table():
    assert parse(document())["operations"]["status"] == "unavailable"
    missing = parse(document() + operations_table().replace("<td>21.3</td>", "<td>—</td>"))
    assert missing["operations"]["rows"][0]["inventoryDays"] is None
    for table in [operations_table().replace("（天）", "（月）"), operations_table() + operations_table().replace("21.3", "22.3")]:
        result = parse(document() + table)
        assert result["operations"]["status"] == "unavailable"
        assert result["operations"]["rows"] == []
        assert len(result["rows"]) == 2


@pytest.mark.parametrize("raw", ["—", "-", "注1", "亏损", "nan", "inf"])
def test_missing_and_non_comparable_growth_is_not_zero(raw):
    data = parse(document(raw))
    assert data["rows"][0]["profitYoy"] is None
    assert data["rows"][0]["raw"]["profitYoy"] == raw
    assert data["rows"][0]["quadrant"] == "unknown"
    assert data["coverage"]["comparable"] == 1


def test_zero_revenue_does_not_produce_a_margin():
    data = parse(document().replace("<td>200</td>", "<td>0</td>"))
    assert data["rows"][0]["profitMargin"] is None
    assert data["rows"][0]["costRatio"] is None


def test_conflicting_mobile_values_are_rejected():
    with pytest.raises(ValueError, match="冲突"):
        parse(document() + document("52.0"))


@pytest.mark.parametrize("old,new", [("亿元", "万元"), ("同比增长", "环比增长"), ("2026/09/28", "2026/11/28"), ("行　业", "分组")])
def test_wrong_units_period_or_table_are_rejected(old, new):
    with pytest.raises(ValueError):
        parse(document().replace(old, new))


def test_discovery_only_accepts_official_statistical_release():
    title = "2026年1—8月份全国规模以上工业企业利润增长15.7%"
    path = "./202609/t20260928_1965425.html"
    html = f'<a href="{path}">{title}</a><a href="{path}">{title}</a><a href="https://evil.example/file">{title}</a><a href="//www.stats.gov.cn.evil.example/file">{title}</a><a href="{path}">解读：{title}</a>'
    assert research.publication_links(html) == ["https://www.stats.gov.cn/sj/zxfb/202609/t20260928_1965425.html"]


@pytest.mark.parametrize("page", [0, 1, 3])
def test_latest_report_can_move_beyond_first_listing_page(page):
    latest = "https://www.stats.gov.cn/sj/zxfb/202609/t20260928_1965425.html"
    prior = "https://www.stats.gov.cn/sj/zxfb/202608/t20260827_1965126.html"
    pages = [research.INDEX, *(research.INDEX + f"index_{i}.html" for i in range(1, 4))]
    requested = []
    def handler(request):
        url = str(request.url)
        requested.append(url)
        if url == latest:
            return httpx.Response(200, text=document())
        if url == pages[page]:
            title = "2026年1—8月份全国规模以上工业企业利润增长15.7%"
            return httpx.Response(200, text=f'<a href="{prior}">{title}</a><a href="{latest}">{title}</a>')
        return httpx.Response(200, text="<a>其他统计发布</a>")
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await research.collect(client)
    result = asyncio.run(run())
    assert result["sourceUrl"] == latest
    assert result["periodEnd"] == "2026-08-31"
    assert result["discoveryPages"] == pages[:page + 1]
    assert requested == [*pages[:page + 1], latest]
    assert "不保证完整历史" in result["discovery"]


@pytest.mark.parametrize("failure", ["empty", "listing", "document", "parse"])
def test_latest_discovery_is_bounded_and_never_falls_back_to_an_older_report(failure):
    latest = "https://www.stats.gov.cn/sj/zxfb/202609/t20260928_1965425.html"
    requested = []
    def handler(request):
        url = str(request.url)
        requested.append(url)
        if url == research.INDEX:
            return httpx.Response(200, text="其他统计发布")
        if failure == "empty":
            return httpx.Response(200, text="其他统计发布")
        if failure == "listing" or (failure == "document" and url == latest):
            return httpx.Response(503)
        if url == latest:
            return httpx.Response(200, text="unrecognized")
        return httpx.Response(200, text=f'<a href="{latest}">2026年1—8月份全国规模以上工业企业利润增长15.7%</a>')
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await research.collect(client)
    with pytest.raises((ValueError, httpx.HTTPStatusError)):
        asyncio.run(run())
    assert len(requested) == {"empty": 4, "listing": 2, "document": 3, "parse": 3}[failure]


@pytest.mark.parametrize("revenue,profit,expected", [(1, 1, "expansion"), (1, -1, "pressure"), (-1, 1, "repair"), (-1, -1, "contraction"), (0, 1, "boundary"), (None, 1, "unknown")])
def test_growth_structure_is_not_an_investment_score(revenue, profit, expected):
    assert research.quadrant(revenue, profit) == expected


def test_refresh_failure_does_not_return_cached_success(monkeypatch):
    app = FastAPI()
    app.include_router(research.router)
    monkeypatch.setattr(research, "_cache", (research.time.monotonic(), {"rows": ["old"]}))
    async def failed(client):
        raise httpx.ReadTimeout("upstream timeout")
    monkeypatch.setattr(research, "collect", failed)
    with TestClient(app) as client:
        assert client.get("/api/industry-research").json()["cached"] is True
        response = client.get("/api/industry-research?refresh=true")
    assert response.status_code == 502
    assert "rows" not in response.json()


def test_old_publication_is_explicitly_stale():
    data = research.parse_publication(document(), "test", today=date(2026, 12, 1))
    assert data["freshness"] == "stale"


def test_annual_publication_uses_december_not_current_month():
    html = document().replace("2026年1—8月份", "2025年").replace("2026/09/28", "2026/01/28")
    result = parse(html)
    assert result["periodEnd"] == "2025-12-31"
    assert result["period"] == "2025年1—12月"
    link = '<a href="./202601/t20260128_1000000.html">2025年全国规模以上工业企业利润增长1%</a>'
    assert len(research.publication_links(link)) == 1


@pytest.mark.parametrize("failure", [None, "listing", "document", "parse", "all"])
def test_history_discovery_parallel_dedup_and_partial_failures(failure):
    latest = "https://www.stats.gov.cn/sj/zxfb/202609/t20260928_1965425.html"
    prior = "https://www.stats.gov.cn/sj/zxfb/202608/t20260827_1965126.html"
    title = "2026年1—8月份全国规模以上工业企业利润增长15.7%"
    def handler(request):
        url = str(request.url)
        if failure == "all" or (failure == "listing" and url.endswith("index_3.html")) or (failure == "document" and url == prior):
            return httpx.Response(503)
        if url == latest:
            return httpx.Response(200, text=document())
        if url == prior:
            return httpx.Response(200, text="unrecognized" if failure == "parse" else document().replace("1—8月份", "1—7月份").replace("2026/09/28", "2026/08/27"))
        # Repeated links across pagination and mobile markup must not duplicate releases.
        return httpx.Response(200, text=f'<a href="{latest}">{title}</a><a href="{prior}">{title}</a>')
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await research.collect_history(client)
    if failure == "all":
        with pytest.raises(ValueError, match="未取得"):
            asyncio.run(run())
    else:
        result = asyncio.run(run())
        assert len(result["publications"]) == (1 if failure in ("document", "parse") else 2)
        assert result["status"] == ("partial" if failure else "complete")
        assert len(result["errors"]) == (1 if failure else 0)
        assert result["publications"][0]["periodEnd"] == "2026-08-31"
        assert len(result["discoveryPages"]) == 4
        assert "无前视" in result["scope"]


def test_history_refresh_failure_never_returns_old_evidence(monkeypatch):
    app = FastAPI()
    app.include_router(research.router)
    monkeypatch.setattr(research, "_history_cache", (research.time.monotonic(), {"publications": [{"cached": False}]}))
    async def failed(client):
        raise ValueError("没有历史原文")
    monkeypatch.setattr(research, "collect_history", failed)
    with TestClient(app) as client:
        assert client.get("/api/industry-research/history").json()["publications"][0]["cached"] is True
        response = client.get("/api/industry-research/history?refresh=true")
        assert response.status_code == 502
        assert "publications" not in response.json()
    assert research._history_cache[1]["publications"][0]["cached"] is False
