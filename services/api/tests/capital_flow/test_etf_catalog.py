import json
from datetime import date

import httpx
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from vibe_visualization_api.capital_flow.etf_catalog import ETFCatalog
from vibe_visualization_api.capital_flow.research import CapitalResearchService, ETF_SAMPLE
from vibe_visualization_api.capital_flow.routes import ETFWatchRequest, research_etf_watchlist
from vibe_visualization_api.capital_flow.store import CapitalHistoryStore
from vibe_visualization_api.config import Settings


@pytest.mark.asyncio
async def test_catalog_pagination_search_cache_and_expired_failure(tmp_path):
    offsets, fail = [], False
    def handler(request):
        payload = json.loads(request.content)
        assert payload["api_name"] == "etf_basic"
        offset = payload["params"]["offset"]; offsets.append(offset)
        if fail: return httpx.Response(503)
        return httpx.Response(200, json={"code": 0, "data": {"fields": ["ts_code", "csname", "index_code", "index_name"],
            "items": [["588000.SH", "华夏科创50ETF", "000688.SH", "科创50"]] if offset == 0 else [["512100.SH", "南方中证1000ETF", "000852.SH", "中证1000"]],
            "has_more": offset == 0}})
    store = CapitalHistoryStore(tmp_path / "catalog.sqlite")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        catalog = ETFCatalog("test-token", store, client=client)
        result = await catalog.search("科创")
        assert result["total"] == 2 and result["items"][0]["code"] == "588000.SH"
        assert (await catalog.search("512100"))["items"][0]["name"] == "南方中证1000ETF"
        assert offsets == [0, 2000]
        saved, _ = store.read("capital.etf-catalog.v1", "CN", "2000-01-01", "2000-01-01")
        store.save("capital.etf-catalog.v1", "CN", saved, start="2000-01-01", end="2000-01-01", status="ready", reason="", received_at="2020-01-01T00:00:00+00:00")
        fail = True
        result = await catalog.search("科创")
        assert result["status"] == "unavailable" and result["usingSaved"]
        assert result["items"][0]["code"] == "588000.SH"


@pytest.mark.asyncio
async def test_watchlist_validation_and_authoritative_names(monkeypatch):
    for items in ([], [{"code": "600519", "category": "宽基"}], [{"code": "588000.SH", "category": "自定义脚本"}], [{"code": "588000.SH"}] * 13):
        with pytest.raises(ValidationError): ETFWatchRequest(items=items)
    settings = Settings(tushare_token="test-token", _env_file=None)
    async def catalog(_self):
        return {"status": "ready", "items": [{"code": "588000.SH", "name": "目录确认的ETF名称"}]}
    async def research(_self, *, refresh, samples):
        assert samples == [("588000.SH", "目录确认的ETF名称", "宽基")]
        assert len(ETF_SAMPLE) == 8
        return {"ok": True}
    monkeypatch.setattr(ETFCatalog, "read", catalog)
    monkeypatch.setattr(CapitalResearchService, "research", research)
    assert await research_etf_watchlist(ETFWatchRequest(items=[{"code": "588000.SH", "category": "宽基"}]), settings=settings) == {"ok": True}
    for items in ([{"code": "588000.SH"}] * 2, [{"code": "600519.SH"}]):
        with pytest.raises(HTTPException) as caught:
            await research_etf_watchlist(ETFWatchRequest(items=items), settings=settings)
        assert caught.value.status_code == 422
    async def failed(_self): return {"status": "unavailable", "items": []}
    monkeypatch.setattr(ETFCatalog, "read", failed)
    with pytest.raises(HTTPException) as caught:
        await research_etf_watchlist(ETFWatchRequest(items=[{"code": "588000.SH"}]), settings=settings)
    assert caught.value.status_code == 503


@pytest.mark.asyncio
async def test_research_only_queries_selected_pool(tmp_path, monkeypatch):
    calls = []
    async def dataset(_self, _client, api, symbol, *_args, **_kwargs):
        calls.append((api, symbol))
        rows = [{"date": "2026-10-13", "is_open": "1"}, {"date": "2026-10-14", "is_open": "1"}] if api == "trade_cal" else (
            [{"date": "2026-10-13", "total_share": 100, "nav": 1}, {"date": "2026-10-14", "total_share": 110, "nav": 1}] if api == "etf_share_size" else [])
        return {"rows": rows, "status": "ready", "reason": "", "receivedAt": "2026-10-15T00:00:00Z", "usingSaved": False}
    monkeypatch.setattr(CapitalResearchService, "_dataset", dataset)
    result = await CapitalResearchService("test", CapitalHistoryStore(tmp_path / "history.sqlite"), today=date(2026, 10, 15)).research(samples=[("588000.SH", "科创50ETF", "宽基")])
    assert result["coverage"]["etfTotal"] == 1
    assert result["etfs"][0]["summary"]["flow1dYi"] == .001
    assert result["groups"][0]["count"] == 1
    assert [symbol for api, symbol in calls if api == "etf_share_size"] == ["588000.SH"]
    assert "1只ETF" in result["notes"][0]
