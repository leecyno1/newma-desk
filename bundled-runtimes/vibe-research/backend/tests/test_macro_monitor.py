from datetime import date

from fastapi.testclient import TestClient
import pandas as pd

import app as app_module
import macro_monitor


client = TestClient(app_module.app)


def _standard(name: str, value: float, previous: float) -> pd.DataFrame:
    return pd.DataFrame([
        {"商品": name, "日期": "2026-06-30", "今值": previous, "预测值": previous, "前值": previous - 0.1},
        {"商品": name, "日期": "2026-07-31", "今值": value, "预测值": value - 0.1, "前值": previous},
        {"商品": name, "日期": "2026-08-31", "今值": None, "预测值": value, "前值": value},
    ])


def _fake_akshare(function_name: str, **kwargs):
    frames = {
        "macro_china_pmi_yearly": _standard("中国官方制造业PMI", 51.2, 49.8),
        "macro_china_gdp_yearly": _standard("中国GDP年率报告", 5.2, 5.0),
        "macro_china_cpi_yearly": _standard("中国CPI年率报告", 2.0, 1.8),
        "macro_china_ppi_yearly": _standard("中国PPI年率报告", -1.0, -1.5),
        "macro_china_m2_yearly": _standard("中国M2货币供应年率报告", 8.5, 8.0),
        "macro_china_industrial_production_yoy": _standard("中国规模以上工业增加值年率报告", 6.2, 5.8),
        "macro_china_exports_yoy": _standard("中国以美元计算出口年率报告", 7.0, 5.0),
        "macro_china_lpr": pd.DataFrame([
            {"TRADE_DATE": "2026-06-20", "LPR1Y": 3.1, "LPR5Y": 3.6},
            {"TRADE_DATE": "2026-07-20", "LPR1Y": 3.0, "LPR5Y": 3.5},
        ]),
        "macro_usa_cpi_yoy": pd.DataFrame([
            {"时间": "2026-06-01", "发布日期": "2026-07-14", "现值": 3.0, "前值": 3.2},
            {"时间": "2026-07-01", "发布日期": "2026-08-12", "现值": None, "前值": 3.0},
        ]),
        "macro_usa_unemployment_rate": pd.DataFrame([
            {"时间": "2026-06-01", "发布日期": "2026-07-03", "现值": 4.1, "前值": 4.2},
            {"时间": "2026-07-01", "发布日期": "2026-08-07", "现值": 4.2, "前值": 4.1},
        ]),
    }
    if function_name == "news_economic_baidu":
        requested = kwargs["date"]
        release = f"{requested[:4]}-{requested[4:6]}-{requested[6:]}"
        return pd.DataFrame([{
            "日期": release,
            "时间": "09:30",
            "地区": "中国",
            "事件": "制造业 PMI 公布",
            "公布": None,
            "预期": 50.5,
            "前值": 50.2,
            "重要性": 2,
        }])
    return frames[function_name]


def test_macro_monitor_builds_regime_and_calendar(monkeypatch):
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    monkeypatch.setattr(macro_monitor.astock, "akshare_parallel_call", _fake_akshare)
    macro_monitor._CACHE.clear()

    feed = macro_monitor.build_macro_monitor(7, today=date(2026, 8, 3))

    assert feed["schemaVersion"] == "newma-desk.macro-monitor.v1"
    assert len(feed["indicators"]) == 10
    assert feed["regime"]["growth"]["signal"] == "positive"
    assert feed["regime"]["inflation"]["signal"] == "positive"
    assert feed["regime"]["liquidity"]["signal"] == "positive"
    assert feed["events"][0]["source"]["id"] == "baidu-economic-calendar"
    assert any(
        gap["reason"] == "optional_fmp_provider_not_configured"
        for gap in feed["gaps"]
    )
    assert next(
        item for item in feed["indicators"] if item["id"] == "cn-pmi"
    )["nextReleaseDate"] == "2026-08-31"


def test_macro_monitor_reports_partial_indicator_failures(monkeypatch):
    def partial(function_name: str, **kwargs):
        if function_name == "macro_china_ppi_yearly":
            raise RuntimeError("upstream unavailable")
        return _fake_akshare(function_name, **kwargs)

    monkeypatch.delenv("FMP_API_KEY", raising=False)
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    monkeypatch.setattr(macro_monitor.astock, "akshare_parallel_call", partial)
    macro_monitor._CACHE.clear()

    feed = macro_monitor.build_macro_monitor(1, today=date(2026, 8, 3))

    source = next(
        item for item in feed["sources"]
        if item["id"] == "public-macro-aggregators"
    )
    assert source["status"] == "partial"
    assert any(
        gap == {"capability": "cn-ppi-yoy", "reason": "source_unavailable"}
        for gap in feed["gaps"]
    )


def test_tushare_monthly_series_uses_latest_period():
    config = next(item for item in macro_monitor._INDICATORS if item["id"] == "cn-cpi-yoy")
    series = next(item for item in macro_monitor._TUSHARE_SERIES if item["id"] == "cn-cpi-yoy")

    indicator = macro_monitor._normalize_tushare_series(config, series, [
        {"month": "202607", "nt_yoy": 0.5},
        {"month": "202606", "nt_yoy": 1.0},
    ], date(2026, 8, 22))

    assert indicator is not None
    assert indicator["period"] == "2026-07"
    assert indicator["value"] == 0.5
    assert indicator["previous"] == 1.0
    assert indicator["freshness"] == {"status": "fresh", "ageDays": 22}
    assert indicator["dateBasis"] == "period"


def test_tushare_calendar_prefers_explicit_actual():
    config = next(item for item in macro_monitor._INDICATORS if item["id"] == "cn-industrial-production-yoy")
    series = next(item for item in macro_monitor._TUSHARE_CALENDAR_SERIES if item["id"] == "cn-industrial-production-yoy")

    indicator = macro_monitor._normalize_tushare_calendar_series(config, series, [
        {"date": "20260715", "country": "economic_activity", "event": "中国规模以上工业增加值年率(同比)", "value": 5.3, "pre_value": 4.5, "fore_value": 4.7},
        {"date": "20260817", "country": "中国", "event": "中国规模以上工业增加值年率(%)(年度)(七月)", "value": None, "pre_value": "5.3%", "fore_value": None},
        {"date": "20260817", "country": "economic_activity", "event": "中国规模以上工业增加值年率(同比)", "value": 4.5, "pre_value": 5.3, "fore_value": 5.0},
    ], date(2026, 8, 22))

    assert indicator is not None
    assert indicator["value"] == 4.5
    assert indicator["previous"] == 5.3
    assert indicator["releaseDate"] == "2026-08-17"
    assert indicator["freshness"] == {"status": "fresh", "ageDays": 5}


def test_macro_monitor_endpoint_contract(monkeypatch):
    monkeypatch.setattr(
        macro_monitor,
        "build_macro_monitor",
        lambda days: {
            "schemaVersion": macro_monitor.SCHEMA_VERSION,
            "horizon": {"start": "2026-08-03", "end": "2026-08-10", "days": days},
            "regime": {},
            "indicators": [],
            "events": [],
            "sources": [],
            "gaps": [],
            "disclaimer": "test",
        },
    )

    response = client.get("/api/macro-monitor?days=14")

    assert response.status_code == 200
    assert response.json()["data"]["schemaVersion"] == macro_monitor.SCHEMA_VERSION
    assert response.json()["data"]["horizon"]["days"] == 14


def test_liquidity_loader_returns_grouped_indicators_and_baseline(monkeypatch):
    frames = {
        "macro_china_shibor_all": pd.DataFrame([
            {"日期": "2026-08-16", "O/N-定价": 1.44, "1W-定价": 1.46, "3M-定价": 1.48},
            {"日期": "2026-08-17", "O/N-定价": 1.40, "1W-定价": 1.42, "3M-定价": 1.45},
            {"日期": "2026-08-18", "O/N-定价": 1.36, "1W-定价": 1.38, "3M-定价": 1.43},
        ]),
        "macro_china_money_supply": pd.DataFrame([
            {"月份": "2026-05", "货币和准货币(M2)-同比增长": 6.8, "货币(M1)-同比增长": 2.8},
            {"月份": "2026-06", "货币和准货币(M2)-同比增长": 7.0, "货币(M1)-同比增长": 3.0},
            {"月份": "2026-07", "货币和准货币(M2)-同比增长": 7.7, "货币(M1)-同比增长": 4.0},
        ]),
        "macro_china_new_financial_credit": pd.DataFrame([
            {"月份": "2026-05", "当月": 900},
            {"月份": "2026-06", "当月": 1100},
            {"月份": "2026-07", "当月": 1200},
        ]),
        "macro_china_market_margin_sh": pd.DataFrame([
            {"日期": "2026-08-15", "融资融券余额": 980_000_000_000},
            {"日期": "2026-08-16", "融资融券余额": 990_000_000_000},
            {"日期": "2026-08-17", "融资融券余额": 1_000_000_000_000},
        ]),
        "macro_china_market_margin_sz": pd.DataFrame([
            {"日期": "2026-08-15", "融资融券余额": 480_000_000_000},
            {"日期": "2026-08-16", "融资融券余额": 490_000_000_000},
            {"日期": "2026-08-17", "融资融券余额": 500_000_000_000},
        ]),
        "macro_stock_finance": pd.DataFrame([
            {"月份": "2026-05", "募集资金": 180},
            {"月份": "2026-06", "募集资金": 200},
            {"月份": "2026-07", "募集资金": 220},
        ]),
    }

    monkeypatch.setattr(
        macro_monitor.astock,
        "akshare_parallel_call",
        lambda function_name, **_: frames[function_name],
    )
    macro_monitor._CACHE.clear()

    result = macro_monitor._load_liquidity(date(2026, 8, 18))

    assert [group["id"] for group in result["groups"]] == ["quantity", "price", "transmission"]
    assert result["coverage"] == {"available": 9, "total": 9, "asOf": "2026-08-18"}
    assert {item["id"] for item in result["forecast"]["items"]} == {
        "cn-m2-yoy", "cn-m1-yoy", "cn-m2-m1-spread", "cn-new-social-financing",
        "cn-shibor-on", "cn-shibor-1w", "cn-shibor-3m", "cn-margin-balance", "cn-equity-financing",
    }


def test_liquidity_loader_degrades_when_one_source_fails(monkeypatch):
    def partial(function_name, **_):
        if function_name == "macro_china_money_supply":
            raise RuntimeError("money supply unavailable")
        return pd.DataFrame([{"日期": "2026-08-18", "O/N-定价": 1.36, "1W-定价": 1.38, "3M-定价": 1.43}]) if function_name == "macro_china_shibor_all" else None

    monkeypatch.setattr(macro_monitor.astock, "akshare_parallel_call", partial)
    macro_monitor._CACHE.clear()

    result = macro_monitor._load_liquidity(date(2026, 8, 18))

    assert result["coverage"]["available"] == 3
    assert [group["id"] for group in result["groups"] if group["indicators"]] == ["price"]


def test_liquidity_forecast_handles_insufficient_history():
    result = macro_monitor._liquidity_forecast([
        {"id": "short", "name": "短序列", "change": None, "effect": "supportive", "history": [{"value": 1.0}]},
    ])

    assert result["items"] == []
    assert result["signal"] == "mixed"
