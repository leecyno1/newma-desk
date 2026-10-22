import asyncio
from datetime import date

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from vibe_visualization_api import industry_prices as prices

URL = "https://www.stats.gov.cn/sj/zxfb/202609/t20260909_1965262.html"


def document():
    return '''<meta name="ArticleTitle" content="2026年8月份工业生产者出厂价格同比上涨3.8%">
    <meta name="PubDate" content="2026/09/09 09:30">
    <table><tr><td></td><td>环比涨跌幅（%）</td><td>同比涨跌幅（%）</td><td>1—8月同比涨跌幅（%）</td></tr>
    <tr><td>一、工业生产者出厂价格</td><td>0.4</td><td>3.8</td><td>2.0</td></tr>
    <tr><td>二、工业生产者购进价格</td><td>0.3</td><td>5.8</td><td>3.2</td></tr>
    <tr><td>燃料、动力类</td><td>1.4</td><td>9.8</td><td>3.0</td></tr>
    <tr><td>三、主要行业出厂价格</td><td></td><td></td><td></td></tr>
    <tr><td>煤炭开采和洗选业</td><td>2.8</td><td>26.6</td><td>7.6</td></tr>
    <tr><td>计算机、通信和其他电子设备制造业</td><td>0.6</td><td>5.3</td><td>1.8</td></tr></table>
    <p>2026年1月起，PPI以2025年为基期，权数有所调整。</p>'''


def parse(html):
    return prices.parse_prices(html, URL, "2026-08", today=date(2026, 10, 18))


def test_industry_output_prices_not_national_or_input_prices():
    data = parse(document() + document())
    assert len(data["metrics"]) == 2
    assert data["metrics"][0] == {"name": "煤炭开采和洗选业", "monthMom": 2.8, "monthYoy": 26.6,
                                  "yearToDateAverageYoy": 7.6, "raw": {"monthMom": "2.8", "monthYoy": "26.6", "yearToDateAverageYoy": "7.6"}}
    assert data["averagePeriod"] == "2026年1—8月平均"
    assert len(data["baseNotes"]) == 1
    assert "2025" in data["baseNotes"][0]


@pytest.mark.parametrize("old,new", [("8月份", "9月份"), ("1—8月", "1—9月"), ("2026/09/09", "2026/11/09"), ("环比涨跌幅（%）", "环比指数"), ("三、主要行业出厂价格", "三、主要行业购进价格")])
def test_mismatched_period_units_or_price_type_rejected(old, new):
    with pytest.raises(ValueError):
        parse(document().replace(old, new))


def test_missing_zero_and_conflicting_duplicates():
    data = parse(document().replace("26.6", "—").replace("2.8", "0"))
    assert data["metrics"][0]["monthYoy"] is None
    assert data["metrics"][0]["monthMom"] == 0
    with pytest.raises(ValueError, match="冲突"):
        parse(document() + document().replace("26.6", "26.7"))


@pytest.mark.parametrize("mode", ["ok", "partial", "newer_only", "duplicate"])
def test_discovery_matches_exact_month_not_latest(mode):
    title = "2026年8月份工业生产者出厂价格同比上涨3.8%"
    def handler(request):
        url = str(request.url)
        if url == URL:
            return httpx.Response(200, text=document())
        if mode == "partial" and url.endswith("index_4.html"):
            return httpx.Response(503)
        listing = f'<a href="{URL}">{title if mode != "newer_only" else title.replace("8月份", "9月份")}</a>'
        listing += f'<a href="https://evil.example/report">{title}</a>'
        if mode == "duplicate":
            listing += f'<a href="{URL.replace("1965262", "1965263")}">{title}</a>'
        return httpx.Response(200, text=listing)
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await prices.collect_prices(client, "2026-08")
    if mode in ("newer_only", "duplicate"):
        with pytest.raises(ValueError):
            asyncio.run(run())
    else:
        data = asyncio.run(run())
        assert data["periodEnd"] == "2026-08-31"
        assert len(data["discoveryErrors"]) == (1 if mode == "partial" else 0)


def test_refresh_failure_does_not_replace_with_cache(monkeypatch):
    app = FastAPI(); app.include_router(prices.router)
    monkeypatch.setattr(prices, "_cache", {"2026-08": (prices.time.monotonic(), {"metrics": ["old"]})})
    async def failed(client, period):
        raise httpx.ReadTimeout("timeout")
    monkeypatch.setattr(prices, "collect_prices", failed)
    with TestClient(app) as client:
        assert client.get("/api/industry-research/prices?period=2026-08").json()["cached"] is True
        assert client.get("/api/industry-research/prices?period=2026-13").status_code == 422
        response = client.get("/api/industry-research/prices?period=2026-08&refresh=true")
        assert response.status_code == 502
        assert "metrics" not in response.json()
