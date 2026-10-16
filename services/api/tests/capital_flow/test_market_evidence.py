import json
from datetime import date, timedelta

import httpx
import pytest

from vibe_visualization_api.capital_flow.market_evidence import MarketEvidenceService, policy_candidates


def event(key="bank", **changes):
    return {"id": key, "title": "银行政策", "date": "2026-09-15", "status": "published",
            "sourceUrl": "https://www.gov.cn/policy/test", "firstSeenAt": "2026-10-01T00:00:00+00:00",
            "entities": [{"type": "industry", "displayName": "银行", "evidence": "银行", "source": "rule"}], **changes}


def test_policy_explicit_entity_and_publication_dates_not_title_or_calendar():
    events = [event(), event("future", date="2026-10-01"), event("calendar", status="scheduled"),
              event("title-only", entities=[]), event("concept", entities=[{"type": "concept", "displayName": "银行"}]),
              event("unsafe", sourceUrl="javascript:alert(1)"), event("old", date="2025-01-01"),
              event("document-future"), event("etf", entities=[{"type": "security", "assetType": "etf", "symbol": "512800"}])]
    docs = {"document-future": {"publishedAt": "2026-09-22"}, "bank": {"publishedAt": "2026-09-16", "status": "ready"}}
    result = policy_candidates(events, docs, code="512800.SH", aliases=["银行"], as_of=date(2026, 9, 21))
    assert {item["id"] for item in result["items"]} == {"bank", "etf"}
    assert result["items"][0]["dateBasis"] == "已保存正文发布日期"
    assert result["items"][0]["publishedDate"] == "2026-09-16"
    assert all(item["timingLabel"] == "复盘日后入库，仅供事后参考" for item in result["items"])
    assert not result["pointInTimeVerified"]


def test_explicit_alias_and_missing_data_are_not_zero_or_positive_evidence():
    result = policy_candidates([event(entities=[{"type": "industry", "displayName": "证券"}])], {},
        code="512070.SH", aliases=["非银金融", "证券", "保险"], as_of=date(2026, 9, 21))
    assert result["matchedCount"] == 1
    assert result["items"][0]["documentStatus"] == "missing"
    assert "待核验" in result["items"][0]["dateBasis"]


@pytest.mark.asyncio
async def test_etf_reuses_capital_formula_respects_cutoff_and_failed_refresh(tmp_path):
    fail = False
    calls = []
    days = [(date(2026, 9, 1) + timedelta(days=i)).isoformat() for i in range(22)]
    def respond(request):
        body = json.loads(request.content); api = body["api_name"]; calls.append(body)
        if fail and api != "trade_cal":
            return httpx.Response(503)
        fields = body["fields"].split(",")
        if api == "etf_basic":
            rows = [{"ts_code": "512800.SH", "csname": "目录银行ETF", "index_code": "399986.SZ", "index_name": "中证银行"}]
        elif api == "trade_cal":
            rows = [{"cal_date": day.replace("-", ""), "is_open": 1} for day in days]
        elif api == "etf_share_size":
            rows = [{"trade_date": day.replace("-", ""), "ts_code": "512800.SH", "total_share": 10000 + i * 100,
                     "nav": 2, "total_size": 0} for i, day in enumerate(days)]
        else:
            rows = []
        return httpx.Response(200, json={"code": 0, "data": {"fields": fields, "items": [[row.get(field) for field in fields] for row in rows]}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        service = MarketEvidenceService("test", tmp_path / "evidence.sqlite", client=client)
        result = await service.research("512800.SH", date(2026, 9, 21), "银行", ["银行"])
        assert result["catalog"]["item"]["indexCode"] == "399986.SZ"
        assert result["etf"]["asOf"] == "2026-09-21"  # Sep 22 data must not leak
        window = result["etf"]["windows"]["5"]
        assert window["current"] and window["flowYi"] == pytest.approx(.1)
        assert window["strengthPct"] == pytest.approx(.1 / 2.3 * 100)
        assert result["policies"]["matchedCount"] == 0
        assert all(body["params"]["end_date"] == "20260921" for body in calls if body["api_name"] != "etf_basic")
        fail = True
        degraded = await service.research("512800.SH", date(2026, 9, 21), "银行", ["银行"], refresh=True)
        assert not degraded["etf"]["current"]
        assert not degraded["etf"]["windows"]["5"]["current"]
