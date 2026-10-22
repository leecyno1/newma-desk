from datetime import date
from unittest.mock import Mock

import pytest
import requests
from fastapi.testclient import TestClient

import app as app_module
import market_scan_daily as daily
import market_terminal
import market


@pytest.fixture(autouse=True)
def isolated_scan(monkeypatch):
    daily._CACHE.clear()
    market_terminal._SCAN_CACHE.clear()
    monkeypatch.setenv("TUSHARE_TOKEN", "test-only")
    monkeypatch.delenv("VR_CN_SCAN_SOURCE", raising=False)
    yield
    daily._CACHE.clear()
    market_terminal._SCAN_CACHE.clear()


@pytest.fixture
def tables(monkeypatch):
    records = {
        "trade_cal": [{"cal_date": "20261019", "is_open": 1, "pretrade_date": "20261016"}],
        "stock_basic": [
            {"ts_code": code, "name": code, "industry": "测试", "list_date": listing}
            for code, listing in [("000001.SZ", "20000101"), ("600000.SH", "20000101"),
                                  ("920001.BJ", "20200101"), ("200001.SZ", "20000101"),
                                  ("600001.SH", "20261020")]
        ],
        "daily": [
            {"ts_code": code, "trade_date": "20261019", "close": 10, "pct_chg": 0,
             "change": 0, "vol": 12, "amount": amount, "open": 9, "high": 11,
             "low": 9, "pre_close": 10}
            for code, amount in [("000001.SZ", 100), ("600000.SH", 200)]
        ],
        "daily_basic": [{"ts_code": "000001.SZ", "trade_date": "20261019", "pe": 0,
                         "pb": 1.2, "turnover_rate": 0, "volume_ratio": 1,
                         "total_mv": 123, "circ_mv": 100}],
        "index_member_all": [{"ts_code": "000001.SZ", "l1_code": "801780.SI",
                              "l1_name": "银行", "l2_code": "801783.SI",
                              "l2_name": "股份制银行Ⅱ", "in_date": "20210101",
                              "out_date": None, "is_new": "Y"}],
    }
    calls = []

    def request(token, api, params, fields, **kwargs):
        calls.append((api, params))
        rows = records[api]
        start = params.get("offset", 0)
        return rows[start:start + params.get("limit", len(rows))]

    monkeypatch.setattr(daily, "_request", request)
    return records, calls


def test_daily_snapshot_units_dates_missing_and_a_share_scope(tables):
    result = daily._load_snapshot("test-only", date(2026, 10, 19))
    first, second = result["items"]
    assert first["amount"] == 100_000
    assert first["marketCap"] == 1_230_000
    assert first["volume"] == 12  # hands, same CN volume convention as Eastmoney
    assert first["changePct"] == first["turnoverPct"] == first["pe"] == 0
    assert second["pe"] is None
    assert second["marketCap"] is None
    assert result["asOf"] == "2026-10-19T15:00:00+08:00"
    assert result["receivedAt"] != result["asOf"]
    assert result["coverage"]["listedCount"] == 3  # no B share or future listing
    assert result["coverage"]["missingQuoteCount"] == 1
    assert result["coverage"]["basicCount"] == 1
    assert result["coverage"]["realtime"] is False


def test_daily_breadth_uses_entire_quote_snapshot_not_ranked_top(monkeypatch):
    items = [{"changePct": 1, "industryL1": "银行", "industryClassification": {
        "taxonomy": "sw2021", "l1Code": "801780.SI"}} for _ in range(205)]
    items += [{"changePct": change, "industryL1": "银行", "industryClassification": {
        "taxonomy": "sw2021", "l1Code": "801780.SI"}} for change in (-1, 0, None)]
    items += [{"changePct": 2, "industryL1": "", "industryClassification": {}}]
    monkeypatch.setattr(daily, "_daily_snapshot", lambda: {"items": items,
        "asOf": "2026-10-21T15:00:00+08:00", "receivedAt": "2026-10-22T09:40:00+08:00",
        "coverage": {"listedCount": 210, "quoteCount": 209, "missingQuoteCount": 1}})
    result = daily.daily_market_breadth()
    assert result["sentiment"]["up"] == 206
    assert result["sentiment"]["down"] == result["sentiment"]["flat"] == 1
    assert result["sentiment"]["zt"] is None
    assert result["sentiment"]["date"] == "2026-10-21"
    breadth = result["industryBreadth"]
    row = breadth["top"][0]
    assert row["up_count"] == 205 and row["flat_count"] == 1
    assert row["observed_count"] == 207 and row["missing_change_count"] == 1
    assert row["change_pct"] == pytest.approx(204 / 207)
    assert row["change_method"] == "equal_weight_member_daily_pct"
    assert breadth["coverage"]["missingClassificationCount"] == 1
    assert breadth["coverage"]["missingChangeCount"] == 1
    assert breadth["coverage"]["quoteCount"] == 209
    assert breadth["data_state"] == "partial" and breadth["point_in_time"] is False


def test_daily_breadth_overview_and_industry_share_day_without_live_mix(monkeypatch, tables):
    snapshot = daily._load_snapshot("test-only", date(2026, 10, 19))
    monkeypatch.setattr(daily, "_daily_snapshot", lambda: snapshot)
    monkeypatch.setenv("VR_CN_SCAN_SOURCE", "tushare-daily")
    monkeypatch.setattr(market, "_sentiment", lambda: pytest.fail("不得混用实时情绪"))
    monkeypatch.setattr(market, "_sectors", lambda: [])
    market._CACHE.clear()
    try:
        overview = market.get_overview()
        assert overview["sentiment"]["date"] == "2026-10-19"
        assert overview["sentiment"]["flat"] == 2
        assert overview["sectors"] == []  # 广度不是资金净流入
        ranking = TestClient(app_module.app).get("/api/industry?top=5").json()["data"]
        assert ranking["top"] == overview["industryBreadth"]["top"]
        assert ranking["coverage"]["quoteCount"] == 2
    finally:
        market._CACHE.clear()


def test_failed_daily_breadth_never_switches_classification_or_live_date(monkeypatch):
    monkeypatch.setenv("VR_CN_SCAN_SOURCE", "tushare-daily")
    def fail():
        raise daily.DailyScanUnavailable("来源失败")
    monkeypatch.setattr(daily, "daily_market_breadth", fail)
    monkeypatch.setattr(market, "_sentiment", lambda: pytest.fail("不得自动切源"))
    monkeypatch.setattr(market, "_sectors", lambda: [])
    market._CACHE.clear()
    try:
        result = market.get_overview()
        assert result["industryBreadth"]["data_state"] == "unavailable"
        assert result["sentiment"] == {}
        assert TestClient(app_module.app).get("/api/industry").status_code == 502
    finally:
        market._CACHE.clear()


def test_paging_collects_all_rows_before_ranking(monkeypatch, tables):
    monkeypatch.setattr(daily, "_PAGE_SIZE", 2)
    result = daily._load_snapshot("test-only", date(2026, 10, 19))
    assert len(result["items"]) == 2
    assert [p["offset"] for api, p in tables[1] if api == "stock_basic"] == [0, 2, 4]
    assert [p["offset"] for api, p in tables[1] if api == "daily"] == [0, 2]


def test_mixed_trade_dates_are_not_joined(tables):
    tables[0]["daily_basic"][0]["trade_date"] = "20261016"
    with pytest.raises(daily.DailyScanUnavailable, match="不同交易日"):
        daily._load_snapshot("test-only", date(2026, 10, 19))


def test_duplicate_page_cannot_be_reported_complete(monkeypatch):
    monkeypatch.setattr(daily, "_PAGE_SIZE", 1)
    monkeypatch.setattr(daily, "_request", lambda *args: [{"ts_code": "000001.SZ"}])
    with pytest.raises(daily.DailyScanUnavailable, match="分页证券重复"):
        daily._table("test-only", "stock_basic", {}, "ts_code")


def test_weekend_uses_previous_trading_day(tables):
    tables[0]["trade_cal"][0] = {"cal_date": "20261018", "is_open": 0, "pretrade_date": "20261016"}
    for api in ("daily", "daily_basic"):
        for row in tables[0][api]:
            row["trade_date"] = "20261016"
    result = daily._load_snapshot("test-only", date(2026, 10, 18))
    assert result["coverage"]["tradeDate"] == "2026-10-16"


def test_empty_daily_is_not_empty_market_success(tables):
    tables[0]["daily"].clear()
    with pytest.raises(daily.DailyScanUnavailable, match="不能视为市场没有候选"):
        daily._load_snapshot("test-only", date(2026, 10, 19))


def test_ranking_drops_missing_not_zero_and_reuses_one_snapshot(monkeypatch, tables):
    snapshot = daily._load_snapshot("test-only", date(2026, 10, 19))
    loads = []
    monkeypatch.setattr(daily, "_load_snapshot", lambda *args: loads.append(1) or snapshot)
    pe = daily.scan_daily_quotes(sort="pe", order="asc")
    amount = daily.scan_daily_quotes(sort="amount")
    assert len(loads) == 1
    assert [row["symbol"] for row in pe["items"]] == ["000001"]
    assert pe["items"][0]["pe"] == 0
    assert pe["coverage"]["missingSortCount"] == 1
    assert amount["items"][0]["symbol"] == "600000"
    # A caller editing its rows must not corrupt the cached source snapshot.
    pe["items"][0]["price"] = 999
    assert daily.scan_daily_quotes(sort="pe")["items"][0]["price"] == 10


def test_failed_load_does_not_cache_success(monkeypatch):
    def fail(*args):
        raise daily.DailyScanUnavailable("测试不可用")
    monkeypatch.setattr(daily, "_load_snapshot", fail)
    with pytest.raises(daily.DailyScanUnavailable):
        daily.scan_daily_quotes()
    assert not daily._CACHE


@pytest.mark.parametrize("configured", ["tushare-daily", "invalid-source"])
def test_explicit_configuration_never_silently_uses_eastmoney(monkeypatch, configured):
    monkeypatch.setenv("VR_CN_SCAN_SOURCE", configured)
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    monkeypatch.setattr(market_terminal.astock, "em_get", lambda *a, **k: pytest.fail("silent fallback"))
    response = TestClient(app_module.app).get("/api/market-terminal/scan?market=CN")
    assert response.status_code == 502
    assert "TUSHARE_TOKEN" in response.text if configured == "tushare-daily" else "VR_CN_SCAN_SOURCE" in response.text


def test_route_selects_daily_provider_only_for_cn(monkeypatch, tables):
    snapshot = daily._load_snapshot("test-only", date(2026, 10, 19))
    monkeypatch.setattr(daily, "_load_snapshot", lambda *a: snapshot)
    monkeypatch.setenv("VR_CN_SCAN_SOURCE", "tushare-daily")
    response = TestClient(app_module.app).get("/api/market-terminal/scan?market=CN&sort=pe&order=asc")
    assert response.status_code == 200
    assert response.json()["data"]["source"] == "tushare-daily"
    assert response.json()["data"]["coverage"]["rankableCount"] == 1
    # This setting does not redirect HK/US to an A-share provider.
    empty_market = Mock()
    empty_market.json.return_value = {"rc": 0, "data": {"total": 0, "diff": []}}
    monkeypatch.setattr(market_terminal.astock, "em_get", lambda *a, **k: empty_market)
    assert market_terminal.scan_market_quotes("HK")["source"].startswith("eastmoney")


def test_transport_failure_does_not_expose_credentials(monkeypatch):
    def fail(*args, **kwargs):
        assert args[0] == "https://api.tushare.pro"
        assert kwargs["json"]["token"] == "secret-token"
        raise requests.ConnectionError("secret-token in request detail")
    monkeypatch.setattr(daily.requests, "post", fail)
    with pytest.raises(daily.DailyScanUnavailable) as caught:
        daily._request("secret-token", "daily", {}, "ts_code")
    assert "secret-token" not in str(caught.value)


def test_scan_uses_security_membership_not_basic_industry_name(tables):
    result = daily._load_snapshot("test-only", date(2026, 10, 19))
    first, second = result["items"]
    assert first["industry"] == "测试"  # original label is retained, not renamed
    assert first["industryL1"] == "银行"
    assert first["industryL2"] == "股份制银行Ⅱ"
    assert first["industryClassification"]["source"] == "tushare.index_member_all"
    assert first["industryClassification"]["inDate"] == "2021-01-01"
    assert second["industryL1"] == second["industryL2"] == ""
    assert second["industryClassification"]["taxonomy"] == "tushare_stock_basic"
    assert result["coverage"]["industryMembershipCount"] == 1
    assert result["coverage"]["missingIndustryMembershipCount"] == 1
    assert result["coverage"]["industryMembershipPointInTime"] is False


def test_membership_unavailable_does_not_discard_valid_prices(monkeypatch, tables):
    original = daily._request
    def request(token, api, params, fields, **kwargs):
        if api == "index_member_all":
            raise daily.DailyScanUnavailable("Tushare index_member_all 不可用")
        return original(token, api, params, fields, **kwargs)
    monkeypatch.setattr(daily, "_request", request)
    result = daily._load_snapshot("test-only", date(2026, 10, 19))
    assert len(result["items"]) == 2
    assert result["coverage"]["industryMembershipState"] == "unavailable"
    assert result["coverage"]["industryMembershipCount"] == 0
    assert all(not row["industryL1"] for row in result["items"])


@pytest.mark.parametrize("changes", [
    {"in_date": "20261020"}, {"in_date": "invalid"},
    {"out_date": "20261018"}, {"is_new": "N"},
])
def test_noncurrent_or_future_membership_is_not_applied(tables, changes):
    tables[0]["index_member_all"][0].update(changes)
    result = daily._load_snapshot("test-only", date(2026, 10, 19))
    assert result["items"][0]["industryL1"] == ""
    assert result["coverage"]["industryMembershipCount"] == 0
