from datetime import date
from io import BytesIO
import json

from fastapi.testclient import TestClient
import pandas as pd
import pytest

import app as app_module
import macro_monitor


client = TestClient(app_module.app)


@pytest.fixture(autouse=True)
def offline_macro_sources(monkeypatch):
    monkeypatch.setattr(macro_monitor, "_eastmoney_indicator", lambda *_: None)
    monkeypatch.setattr(macro_monitor, "_bls_unemployment_indicator", lambda *_: None)
    monkeypatch.setattr(macro_monitor, "_fred_unemployment_indicator", lambda *_: None)
    monkeypatch.setattr(macro_monitor, "_fred_cpi_indicator", lambda *_: None)
    monkeypatch.setattr(macro_monitor, "_tushare_client", lambda: None)
    macro_monitor._CACHE.clear()


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


def test_calendar_does_not_promote_previous_or_forecast_to_actual():
    config = next(item for item in macro_monitor._INDICATORS if item["id"] == "cn-industrial-production-yoy")
    series = macro_monitor._TUSHARE_CALENDAR_SERIES[0]
    rows = [{"date": "20260817", "country": "中国", "event": "中国规模以上工业增加值年率(同比)",
             "value": None, "pre_value": "5.3%", "fore_value": "5.0%"}]
    assert macro_monitor._normalize_tushare_calendar_series(config, series, rows, date(2026, 9, 9)) is None
    rows[0]["value"] = 0
    assert macro_monitor._normalize_tushare_calendar_series(config, series, rows, date(2026, 9, 9))["value"] == 0


def test_calendar_primary_paginates_full_range_and_caches_complete_result(monkeypatch):
    calls = []
    first = [{"date": "20260910", "time": "10:00", "country": "economic_activity", "currency": "CNY", "event": f"中国测试事件 {n}"} for n in range(100)]

    class CalendarClient:
        def query(self, api, **params):
            calls.append((api, params))
            return pd.DataFrame(first if params["offset"] == 0 else [
                {"date": "20261008", "event": "美国测试事件", "currency": "USD"},
                {"date": "20261010", "event": "范围外事件"},
            ])

    monkeypatch.setattr(macro_monitor, "_tushare_client", CalendarClient)
    monkeypatch.setattr(macro_monitor, "_fmp_events", lambda *_: pytest.fail("primary works; do not call FMP"))
    today = date(2026, 9, 9)
    events, sources, gaps = macro_monitor._load_calendar(today, 30)
    assert len(events) == 101
    assert events[-1]["date"] == "2026-10-08"
    assert events[0]["region"] == "中国"
    assert events[0]["importance"] == "unknown"
    assert sources[0]["coverage"]["queriedDays"] == 31
    assert sources[0]["coverage"]["missingDates"] == []
    assert len(sources) == 1 and gaps == []
    assert [params["offset"] for _, params in calls] == [0, 100]
    assert calls[0] == ("eco_cal", {"start_date": "20260909", "end_date": "20261009", "limit": 100, "offset": 0})
    macro_monitor._load_calendar(today, 30)
    assert len(calls) == 2


def test_calendar_does_not_claim_complete_query_when_pagination_repeats():
    class RepeatingClient:
        def query(self, *_args, **_params):
            return pd.DataFrame([{"date": "20260910", "event": f"event {n}"} for n in range(100)])

    with pytest.raises(ValueError, match="分页未推进"):
        macro_monitor._tushare_events(RepeatingClient(), date(2026, 9, 9), 30)


def test_calendar_normalization_preserves_units_and_labels_rule_ratings():
    today = date(2026, 9, 9)
    row = {"date": "20260909", "time": "20:30", "currency": "USD", "country": "employment",
           "event": "美国失业率", "value": "0%", "pre_value": "4.1%", "fore_value": "4.2%"}
    event = macro_monitor._calendar_event(row, "test", "test", "https://example.com", today)
    assert event["region"] == "美国"
    assert event["time"] == "20:30"
    assert event["actual"] == 0 and event["actualText"] == "0%"
    assert event["forecast"] == 4.2 and event["forecastText"] == "4.2%"
    assert event["previousText"] == "4.1%"
    assert event["status"] == "released" and event["importance"] == "high"
    assert event["importanceBasis"]["kind"] == "rule"
    assert event["importanceBasis"]["ruleId"] == "employment"
    future = macro_monitor._calendar_event({**row, "date": "20260910"}, "test", "test", "https://example.com", today)
    assert future["actual"] is None and future["actualText"] is None
    assert future["status"] == "scheduled"
    conflict = macro_monitor._calendar_event({**row, "event": "澳大利亚进口月率", "country": "中国", "currency": "AUD"},
                                             "test", "test", "https://example.com", today)
    assert conflict["region"] == "地区待核验"
    assert conflict["regionGroup"] == "UNKNOWN"
    assert conflict["regionBasis"]["titleRegion"] == "澳大利亚"
    assert conflict["regionBasis"]["reportedRegion"] == "中国"
    assert conflict["source"]["reportedCountry"] == "中国"


def test_calendar_regions_separate_economic_areas_and_quarantine_conflicts():
    cases = [
        ({"country": "香港"}, "中国香港失业率", "HK", "HK"),
        ({"country": "confidence_index"}, "印度尼西亚零售销售", "ID", "OTHER"),
        ({"country": "central_banks"}, "巴西跨境资本流动", "BR", "OTHER"),
        ({"country": "United Kingdom"}, "CPI", "GB", "EU"),
        ({"地区": "欧洲", "国家": "挪威"}, "CPI", "NO", "EU"),
        ({"country": "US", "currency": "USD"}, "国际能源署(IEA)月报", "GLOBAL", "OTHER"),
        ({"country": "employment", "currency": "USD"}, "未注明地区的就业数据", None, "UNKNOWN"),
        ({"country": "西班牙", "currency": "EUR"}, "以色列消费者信心指数", None, "UNKNOWN"),
    ]
    for row, title, code, group in cases:
        region = macro_monitor._calendar_region(row, title)
        assert (region["regionCode"], region["regionGroup"]) == (code, group)
    conflict = macro_monitor._calendar_region({"country": "西班牙"}, "以色列消费者信心指数")
    assert conflict["regionBasis"] == {"kind": "conflict", "titleRegion": "以色列", "reportedRegion": "西班牙",
                                      "reason": "标题与来源地区不一致，保留双方口径，等待核验"}


def test_calendar_keeps_explicit_offsets_but_never_invents_timezone_or_midnight():
    today = date(2026, 9, 10)
    base = {"date": "20260910", "event": "美国失业率"}
    def event(row):
        return macro_monitor._calendar_event({**base, **row}, "test", "test", "https://example.com", today)
    naive = event({"time": "20:30"})
    assert naive["time"] == "20:30"
    assert naive["timeBasis"]["kind"] == "unconfirmed" and naive["timeBasis"]["timestamp"] is None
    for raw_date, raw_time, clock, stamp, zone in [
        ("2026-09-10T20:30:00+08:00", None, "20:30", "2026-09-10T20:30:00+08:00", "UTC+08:00"),
        ("2026-09-10T08:30:00-04:00", "08:30", "08:30", "2026-09-10T08:30:00-04:00", "UTC-04:00"),
        ("20260910", "8:30Z", "08:30", "2026-09-10T08:30:00+00:00", "UTC+00:00"),
    ]:
        row = event({"date": raw_date, "time": raw_time})
        assert row["time"] == clock
        assert row["timeBasis"]["timestamp"] == stamp and row["timeBasis"]["timeZone"] == zone
        assert row["source"]["reportedDate"] == raw_date
    for raw_time in [None, float("nan"), "待定", "全天", "25:70"]:
        row = event({"time": raw_time})
        assert row["time"] is None and row["timeBasis"]["kind"] == "date-only"
        assert row["timeBasis"]["timestamp"] is None
    midnight = event({"time": "00:00"})
    assert midnight["time"] == "00:00" and midnight["timeBasis"]["kind"] == "unconfirmed"


def test_calendar_does_not_merge_different_offsets_or_disputed_regions():
    base = {"date": "20260910", "event": "以色列消费者信心指数", "currency": "EUR"}
    rows = [{**base, "time": clock, "country": "以色列"} for clock in ["08:30+08:00", "08:30-04:00", "08:30"]]
    rows += [{**base, "time": "08:30", "country": country} for country in ["西班牙", "南非"]]
    events = macro_monitor._calendar_rows(rows, "test", "test", "https://example.com", date(2026, 9, 10), 0)
    assert len(events) == 5 and len({event["id"] for event in events}) == 5
    assert len({event["evidenceId"] for event in events}) == 5
    assert all(event["recordCount"] == 1 for event in events)


def test_calendar_ratings_are_bounded_and_source_ratings_take_priority():
    rate = macro_monitor._calendar_importance
    for title, region in [("美联储利率决议", "美国"), ("欧洲央行利率决议(九月)", "欧元区"),
                          ("美国核心CPI月率(%)(月度)(八月)", "美国"), ("中国GDP年率(第二季度)", "中国"),
                          ("英国央行利率决议(九月)", "英国"), ("中国央行贷款市场报价利率(LPR)(九月)", "中国")]:
        level, basis = rate(title, region, None)
        assert level == "high" and basis["kind"] == "rule"
        assert basis["version"] == "1" and basis["reason"]
    assert rate("美国Markit制造业PMI(九月)", "美国", None)[0] == "medium"
    for title in ["美国测试事件", "美国消费者通胀预期", "亚特兰大联储GDPNow经济增长预测", "美国CPI新闻访谈", "美国3年期国债拍卖利率"]:
        assert rate(title, "美国", None)[0] == "unknown"
    level, basis = rate("美国失业率", "美国", "Low")
    assert level == "low" and basis == {"kind": "source", "sourceValue": "Low", "reason": "沿用日历来源评级"}


def test_calendar_merges_percent_variants_and_preserves_whole_records():
    base = {"date": "20260910", "time": "20:15", "currency": "EUR", "event": "欧元区欧洲央行边际借贷利率", "pre_value": "2.65"}
    rows = [base, {**base, "event": base["event"] + "（％）", "pre_value": "2.650%", "value": "2.8%"}]
    event, = macro_monitor._calendar_rows(rows, "test", "test", "https://example.com", date(2026, 9, 10), 7)
    assert event["recordCount"] == 2 and event["conflictFields"] == []
    assert event["actualText"] == "2.8%" and event["previousText"] == "2.650%"
    assert [record["title"] for record in event["records"]] == [row["event"] for row in rows]
    assert event["records"][0]["actual"] is None


def test_calendar_does_not_merge_different_periods_units_or_definitions():
    titles = ["美国消费信贷", "美国消费信贷(美元)(七月)", "美国消费信贷(美元)(八月)",
              "美国消费信贷(亿美元)(七月)", "美国CPI年率", "美国CPI月率", "美国核心CPI年率",
              "美国GDP季率初值", "美国GDP季率终值", "美国失业率(%)", "美国失业率(百分点)"]
    base = {"date": "20260910", "time": "20:30", "currency": "USD"}
    rows = [{**base, "event": title} for title in titles]
    rows += [{**rows[0], "time": "21:00"}, {**rows[0], "date": "20260911"}, {**rows[0], "currency": "EUR"}]
    events = macro_monitor._calendar_rows(rows, "test", "test", "https://example.com", date(2026, 9, 10), 7)
    assert len(events) == len(rows) and len({event["id"] for event in events}) == len(rows)
    assert all(event["recordCount"] == 1 for event in events)


def test_calendar_conflicts_are_visible_and_values_are_not_spliced():
    base = {"date": "20260910", "time": "20:30", "currency": "USD", "event": "美国失业率", "pre_value": "4.1%", "impact": "High"}
    rows = [{**base, "value": "4.2%"}, {**base, "value": "4.3%", "fore_value": "4.4%", "impact": "Low"}]
    event, = macro_monitor._calendar_rows(rows, "test", "test", "https://example.com", date(2026, 9, 10), 0)
    assert event["conflictFields"] == ["actual", "importance"]
    assert event["importance"] == "unknown" and event["importanceBasis"]["kind"] == "unknown"
    assert event["recordCount"] == 2 and len(event["records"]) == 2
    assert event["actualText"] == "4.3%" and event["forecastText"] == "4.4%"
    rows[1]["value"] = None
    rows[1]["impact"] = "High"
    event, = macro_monitor._calendar_rows(rows, "test", "test", "https://example.com", date(2026, 9, 10), 0)
    assert event["actualText"] == "4.2%" and event["forecastText"] is None
    assert event["importance"] == "high" and event["importanceBasis"]["kind"] == "source"


def test_calendar_fallback_exposes_failed_and_unqueried_dates_without_hiding_low_events(monkeypatch):
    monkeypatch.delenv("FMP_API_KEY", raising=False)

    def fetch(_function, *, date):
        if date == "20260912":
            raise TimeoutError("source timeout")
        if date == "20260913":
            return pd.DataFrame()
        return pd.DataFrame([
            {"日期": date, "事件": "低重要性事件", "地区": "美国", "重要性": 1.0, "公布": 9},
            {"日期": "20261010", "事件": "接口返回范围外事件", "重要性": 3},
        ])

    monkeypatch.setattr(macro_monitor.astock, "akshare_parallel_call", fetch)
    events, sources, gaps = macro_monitor._load_calendar(date(2026, 9, 9), 30)
    coverage = sources[-1]["coverage"]
    assert len(events) == 13
    assert all(event["importance"] == "low" for event in events)
    assert events[1]["actual"] is None
    assert coverage["requestedDays"] == 31 and coverage["queriedDays"] == 14
    assert len(coverage["missingDates"]) == 17
    assert "2026-09-12" in coverage["missingDates"] and "2026-10-09" in coverage["missingDates"]
    assert coverage["emptyDates"] == ["2026-09-13"]
    assert coverage["status"] == "partial"
    assert any(gap["capability"] == "economic-calendar-horizon" for gap in gaps)


def test_empty_primary_calendar_is_queried_not_unavailable(monkeypatch):
    class EmptyClient:
        def query(self, *_args, **_params):
            return pd.DataFrame()

    monkeypatch.setattr(macro_monitor, "_tushare_client", EmptyClient)
    events, sources, gaps = macro_monitor._load_calendar(date(2026, 9, 9), 7)
    assert events == [] and gaps == []
    assert sources[0]["status"] == "empty"
    assert sources[0]["coverage"]["queriedDays"] == 8
    assert sources[0]["coverage"]["missingDates"] == []
    assert len(sources[0]["coverage"]["emptyDates"]) == 8


def test_fmp_is_used_when_primary_fails_and_keeps_range_bounded(monkeypatch):
    class FailedClient:
        def query(self, *_args, **_params):
            raise RuntimeError("calendar unavailable")

    monkeypatch.setattr(macro_monitor, "_tushare_client", FailedClient)
    monkeypatch.setenv("FMP_API_KEY", "test-key")
    monkeypatch.setattr(macro_monitor, "_fmp_events", lambda *_: [
        {"date": "2026-09-10 14:00:00", "event": "CPI", "country": "US", "impact": "High", "estimate": "2.5%"},
        {"date": "2026-10-10", "event": "Outside", "country": "US"},
    ])
    events, sources, _ = macro_monitor._load_calendar(date(2026, 9, 9), 30)
    assert len(events) == 1 and events[0]["region"] == "美国"
    assert events[0]["importance"] == "high" and events[0]["forecastText"] == "2.5%"
    assert [source["status"] for source in sources] == ["unavailable", "ok"]
    assert sources[-1]["coverage"]["queriedDays"] == 31


def test_standard_and_lpr_pick_latest_released_value_regardless_of_row_order():
    today = date(2026, 9, 9)
    config = macro_monitor._INDICATORS[0]
    rows = [
        {"日期": "2026-08-31", "今值": 49.8, "前值": 49.2},
        {"日期": "2026-09-30", "今值": 55, "前值": 49.8},
        {"日期": "2026-07-31", "今值": 49.2, "前值": 50.3},
        {"日期": "未知", "今值": 99},
    ]
    result = macro_monitor._normalize_standard_indicator(config, rows, today)
    assert result["period"] == "2026-08-31"
    assert result["value"] == 49.8
    assert [item["value"] for item in result["history"]] == [49.2, 49.8]
    lpr = macro_monitor._normalize_lpr_indicator(config, [
        {"TRADE_DATE": "2026-09-20", "LPR1Y": 1},
        {"TRADE_DATE": "2026-08-20", "LPR1Y": 3},
        {"TRADE_DATE": "2026-07-20", "LPR1Y": 3.1},
    ], today)
    assert lpr["period"] == "2026-08-20"
    assert lpr["previous"] == 3.1


def test_statistical_period_not_database_update_controls_freshness():
    config = macro_monitor._INDICATORS[0]
    result = macro_monitor._normalize_tushare_series(config, macro_monitor._TUSHARE_SERIES[0], [
        {"month": "202508", "pmi010000": 49.4, "update_time": "2026-09-09"},
        {"month": "202609", "pmi010000": 99, "update_time": "2026-09-09"},
    ], date(2026, 9, 9))
    assert result["period"] == "2025-08"
    assert result["freshness"] == {"status": "stale", "ageDays": 374}


def test_gdp_labels_cumulative_and_single_quarter_series_separately():
    config = next(item for item in macro_monitor._INDICATORS if item["id"] == "cn-gdp-yoy")
    series = next(item for item in macro_monitor._TUSHARE_SERIES if item["id"] == "cn-gdp-yoy")
    result = macro_monitor._normalize_tushare_series(config, series, [
        {"quarter": "2026Q1", "gdp_yoy": 5}, {"quarter": "2026Q2", "gdp_yoy": 4.7},
    ], date(2026, 9, 9))
    assert result["name"] == "中国 GDP 累计同比"
    assert result["previous"] == 5
    assert config["name"] == "中国 GDP 单季同比"
    assert "累计同比" in macro_monitor._build_regime([result])["growth"]["summary"]


# Keep a reference to exercise the adapter while the remaining tests stay offline.
_eastmoney_indicator = macro_monitor._eastmoney_indicator
_bls_unemployment_indicator = macro_monitor._bls_unemployment_indicator
_fred_unemployment_indicator = macro_monitor._fred_unemployment_indicator
_fred_cpi_indicator = macro_monitor._fred_cpi_indicator


@pytest.mark.parametrize("explicit_proxy", [False, True])
def test_public_request_preserves_local_bypass_without_losing_system_proxy(monkeypatch, explicit_proxy):
    proxies = {"no": "127.0.0.1,localhost,::1"}
    if explicit_proxy:
        proxies["https"] = "http://configured-proxy.test:8080"
    monkeypatch.setattr(macro_monitor.http_request, "getproxies", lambda: proxies)
    monkeypatch.setattr(macro_monitor.http_request, "getproxies_macosx_sysconf",
                        lambda: {"https": "http://system-proxy.test:7890"}, raising=False)
    calls = []

    class Opener:
        def open(self, request, *, timeout):
            return (request.full_url, timeout)

    def build_opener(handler):
        calls.append(handler.proxies)
        return Opener()

    monkeypatch.setattr(macro_monitor.http_request, "build_opener", build_opener)
    monkeypatch.setattr(macro_monitor, "urlopen", lambda request, *, timeout: (request.full_url, timeout))
    url = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
    assert macro_monitor._open_public_request(macro_monitor.Request(url), timeout=10) == (url, 10)
    assert calls == ([] if explicit_proxy else [{**proxies, "https": "http://system-proxy.test:7890"}])


def test_bls_uses_monthly_actuals_and_preserves_period_without_inventing_release(monkeypatch):
    requests = []

    def open_url(request, *, timeout):
        requests.append((request.full_url, json.loads(request.data), timeout))
        return BytesIO(json.dumps({"status": "REQUEST_SUCCEEDED", "Results": {"series": [
            {"seriesID": "LNS14000000", "data": [
                {"year": "2026", "period": "M07", "value": "4.2"},
                {"year": "2026", "period": "M13", "value": "99"},
                {"year": "2026", "period": "M09", "value": "99"},
                {"year": "2026", "period": "M08", "value": "4.1"},
                {"year": "2026", "period": "M06", "value": "-"},
            ]},
        ]}}).encode())

    monkeypatch.setattr(macro_monitor, "_open_public_request", open_url)
    config = next(item for item in macro_monitor._INDICATORS if item["id"] == "us-unemployment-rate")
    result = _bls_unemployment_indicator(config, date(2026, 9, 9))
    assert result["value"] == 4.1
    assert result["previous"] == 4.2
    assert result["period"] == "2026-08"
    assert result["releaseDate"] is None
    assert result["dateBasis"] == "period"
    assert result["freshness"] == {"status": "fresh", "ageDays": 9}
    assert result["source"]["seriesId"] == "LNS14000000"
    assert result["history"] == [{"period": "2026-07", "value": 4.2}, {"period": "2026-08", "value": 4.1}]
    stale = _bls_unemployment_indicator(config, date(2026, 12, 9))
    assert stale["freshness"]["status"] == "stale"
    assert stale["confidence"]["level"] == "low"
    assert len(requests) == 1
    assert requests[0][1] == {"seriesid": ["LNS14000000"], "startyear": "2025", "endyear": "2026"}
    assert requests[0][2] == 10


def test_bls_failed_response_is_not_treated_as_current_data(monkeypatch):
    monkeypatch.setattr(macro_monitor, "_open_public_request", lambda *_args, **_kwargs: BytesIO(
        b'{"status":"REQUEST_NOT_PROCESSED","message":["daily limit"]}'
    ))
    with pytest.raises(ValueError, match="BLS"):
        _bls_unemployment_indicator(macro_monitor._INDICATORS[-1], date(2026, 9, 9))


def test_fred_preserves_bls_definition_and_month_without_inventing_release(monkeypatch):
    requests = []
    def open_url(request, *, timeout):
        requests.append((request.full_url, timeout))
        return BytesIO(("\ufeffobservation_date,UNRATE\n2024-12-01,99\n2025-10-01,\n2026-06-01,.\n"
                        "2026-08-01,4.1\n2026-07-01,4.2\n2026-09-01,99\n2026-10-01,99\n").encode())
    monkeypatch.setattr(macro_monitor, "_open_public_request", open_url)
    config = next(item for item in macro_monitor._INDICATORS if item["id"] == "us-unemployment-rate")
    result = _fred_unemployment_indicator(config, date(2026, 9, 9))
    assert (result["value"], result["previous"], result["period"], result["asOf"]) == (4.1, 4.2, "2026-08", "2026-08")
    assert result["releaseDate"] is None and result["forecast"] is None and result["dateBasis"] == "period"
    assert result["freshness"] == {"status": "fresh", "ageDays": 9}
    assert result["source"]["seriesId"] == "UNRATE" and result["source"]["originalSeriesId"] == "LNS14000000"
    assert result["source"]["originalSource"] == "美国劳工统计局 BLS"
    assert result["source"]["seasonalAdjustment"] == "seasonally-adjusted"
    assert result["history"] == [{"period": "2026-07", "value": 4.2}, {"period": "2026-08", "value": 4.1}]
    cached = _fred_unemployment_indicator(config, date(2026, 9, 10))
    assert cached["freshness"]["ageDays"] == 10 and len(requests) == 1
    assert requests == [("https://fred.stlouisfed.org/graph/fredgraph.csv?id=UNRATE&cosd=2025-01-01&coed=2026-09-09", 10)]


@pytest.mark.parametrize("payload", [b"<html>Forbidden</html>", b"observation_date,UNRATENSA\n2026-08-01,4.1", b"observation_date,UNRATE\n2026-08-01,."])
def test_fred_rejects_error_pages_wrong_series_and_missing_values(monkeypatch, payload):
    monkeypatch.setattr(macro_monitor, "_open_public_request", lambda *_args, **_kwargs: BytesIO(payload))
    with pytest.raises(ValueError, match="FRED"):
        _fred_unemployment_indicator(macro_monitor._INDICATORS[-1], date(2026, 9, 9))
    assert not macro_monitor._CACHE


def test_fred_cpi_uses_same_month_index_for_yoy_without_inventing_release(monkeypatch):
    requests = []
    def open_url(request, *, timeout):
        requests.append((request.full_url, timeout))
        return BytesIO(("observation_date,CPIAUCNS\n"
                        "2025-07-01,320\n2025-08-01,322\n"
                        "2026-07-01,329.6\n2026-08-01,332\n"
                        "2026-09-01,.\n").encode())
    monkeypatch.setattr(macro_monitor, "_open_public_request", open_url)
    config = next(item for item in macro_monitor._INDICATORS if item["id"] == "us-cpi-yoy")
    result = _fred_cpi_indicator(config, date(2026, 9, 20))
    assert (result["period"], result["value"], result["previous"]) == ("2026-08", 3.1, 3.0)
    assert result["change"] == pytest.approx(0.1)
    assert result["releaseDate"] is None and result["dateBasis"] == "period"
    assert result["source"]["seriesId"] == "CPIAUCNS"
    assert result["source"]["originalSeriesId"] == "CUUR0000SA0"
    assert result["revisionStatus"] == "not-tracked"
    assert "发布日期和历史修订版本未由此公开 CSV 提供" in result["confidence"]["rationale"]
    assert len(requests) == 1 and "cosd=2024-01-01" in requests[0][0]


@pytest.mark.parametrize("payload", [b"<html>Forbidden</html>", b"observation_date,CPIAUCSL\n2026-08-01,332", b"observation_date,CPIAUCNS\n2026-08-01,."])
def test_fred_cpi_rejects_wrong_or_missing_index(monkeypatch, payload):
    monkeypatch.setattr(macro_monitor, "_open_public_request", lambda *_args, **_kwargs: BytesIO(payload))
    config = next(item for item in macro_monitor._INDICATORS if item["id"] == "us-cpi-yoy")
    with pytest.raises(ValueError, match="FRED"):
        _fred_cpi_indicator(config, date(2026, 9, 20))


@pytest.mark.parametrize("primary_available,bls_state,fred_state,expected", [
    (True, "fresh", "fresh", "fred-unemployment"),
    (True, "fresh", "failed", "tushare-eco-cal"),
    (False, "fresh", "fresh", "bls-unemployment"),
    (False, "failed", "fresh", "fred-unemployment"),
    (False, "stale", "fresh", "fred-unemployment"),
    (False, "failed", "failed", "jin10-macro"),
    (False, "failed", "stale", "fred-unemployment"),
])
def test_unemployment_source_chain_keeps_primary_and_handles_official_outage(monkeypatch, primary_available, bls_state, fred_state, expected):
    today = date(2026, 9, 9)
    config = next(item for item in macro_monitor._INDICATORS if item["id"] == "us-unemployment-rate")
    primary = macro_monitor._normalize_standard_indicator(config, [{"日期": "2026-09-04", "今值": 4.1}], today)
    primary["source"]["id"] = "tushare-eco-cal"
    calls = []

    def adapter(provider, state):
        def fetch(*_):
            calls.append(provider)
            if state == "failed":
                raise RuntimeError(f"{provider} HTTP 403")
            rows = [{"month": "202608" if state == "fresh" else "202604", "value": 4.1}]
            return macro_monitor._normalize_unemployment(config, rows, today, {
                "id": f"{provider}-unemployment", "fallbackReason": f"{provider} 实际值",
            })
        return fetch

    monkeypatch.setattr(macro_monitor, "_INDICATORS", (config,))
    monkeypatch.setattr(macro_monitor, "_load_tushare_indicators", lambda _: (
        {config["id"]: primary} if primary_available else {}, [], "ok",
    ))
    monkeypatch.setattr(macro_monitor, "_bls_unemployment_indicator", adapter("bls", bls_state))
    monkeypatch.setattr(macro_monitor, "_fred_unemployment_indicator", adapter("fred", fred_state))
    monkeypatch.setattr(macro_monitor.astock, "akshare_parallel_call", lambda *_: pd.DataFrame([
        {"日期": "2025-08-01", "今值": 4.2},
    ]))
    indicators, source, gaps = macro_monitor._load_indicators(today)
    fresh = primary_available or bls_state == "fresh" or fred_state == "fresh"
    assert calls == (["fred"] if primary_available else ["bls"] if bls_state == "fresh" else ["bls", "fred"])
    assert indicators[0]["source"]["id"] == expected
    assert source["coverage"]["fresh"] == int(fresh)
    assert bool(gaps) == (not fresh)
    if primary_available and fred_state == "failed":
        assert "fred HTTP 403" in source["error"]
    elif not primary_available and bls_state == "failed":
        assert "bls HTTP 403" in source["error"]
    elif not primary_available:
        assert indicators[0]["source"]["fallbackReason"] == f"{expected.split('-')[0]} 实际值"


def test_cpi_prefers_fred_bls_month_over_aggregator_release_date(monkeypatch):
    today = date(2026, 10, 6)
    config = next(item for item in macro_monitor._INDICATORS if item["id"] == "us-cpi-yoy")
    aggregated = macro_monitor._normalize_standard_indicator(config, [{"日期": "2026-09-11", "今值": 3.4}], today)
    official = macro_monitor._normalize_period_series(
        config, {"periodKey": "month", "valueKey": "value", "frequency": "month"},
        [{"month": "202608", "value": 3.4}], today,
        source={"id": "fred-cpi", "label": "FRED · BLS CPI-U", "url": "https://fred.stlouisfed.org/series/CPIAUCNS"},
    )
    monkeypatch.setattr(macro_monitor, "_INDICATORS", (config,))
    monkeypatch.setattr(macro_monitor, "_load_tushare_indicators", lambda _: ({}, [], "ok"))
    monkeypatch.setattr(macro_monitor, "_fred_cpi_indicator", lambda *_: official)
    monkeypatch.setattr(macro_monitor, "_eastmoney_indicator", lambda *_: aggregated)
    indicators, _, _ = macro_monitor._load_indicators(today)
    assert indicators[0]["source"]["id"] == "fred-cpi"
    assert indicators[0]["period"] == "2026-08" and indicators[0]["releaseDate"] is None


def test_cpi_keeps_aggregator_when_fred_is_unavailable(monkeypatch):
    today = date(2026, 10, 6)
    config = next(item for item in macro_monitor._INDICATORS if item["id"] == "us-cpi-yoy")
    aggregated = macro_monitor._normalize_standard_indicator(config, [{"日期": "2026-09-11", "今值": 3.4}], today)
    monkeypatch.setattr(macro_monitor, "_INDICATORS", (config,))
    monkeypatch.setattr(macro_monitor, "_load_tushare_indicators", lambda _: ({}, [], "ok"))
    monkeypatch.setattr(macro_monitor, "_fred_cpi_indicator", lambda *_: (_ for _ in ()).throw(ValueError("FRED unavailable")))
    monkeypatch.setattr(macro_monitor, "_eastmoney_indicator", lambda *_: aggregated)
    indicators, source, _ = macro_monitor._load_indicators(today)
    assert indicators[0]["source"]["id"] == "eastmoney-us-macro"
    assert "fred us-cpi-yoy" in source["error"]


def test_eastmoney_adapter_uses_bounded_monthly_actual_field(monkeypatch):
    requests = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"success": True, "result": {"data": [
                {"REPORT_DATE": "2026-08-01 00:00:00", "EXIT_BASE_SAME": 25, "EXIT_ACCUMULATE_SAME": 99},
                {"REPORT_DATE": "2026-07-01 00:00:00", "EXIT_BASE_SAME": 23.9},
            ]}}

    def get(url, *, params, timeout):
        requests.append((url, params, timeout))
        return Response()

    monkeypatch.setattr(macro_monitor.astock, "em_get", get)
    config = next(item for item in macro_monitor._INDICATORS if item["id"] == "cn-exports-yoy")
    result = _eastmoney_indicator(config, date(2026, 9, 9))
    assert result["value"] == 25
    assert result["previous"] == 23.9
    assert result["period"] == "2026-08"
    assert result["releaseDate"] is None
    assert result["dateBasis"] == "period"
    assert result["source"]["field"] == "EXIT_BASE_SAME"
    assert requests[0][1]["pageSize"] == "18"
    assert requests[0][2] == 10
    assert "cn-gdp-yoy" not in macro_monitor._EASTMONEY_SERIES


def test_loader_prefers_primary_then_fresh_fallback_and_marks_stale_coverage(monkeypatch):
    today = date(2026, 9, 9)
    primary = macro_monitor._normalize_standard_indicator(macro_monitor._INDICATORS[0], [
        {"日期": "2026-08-31", "今值": 49.8, "前值": 49.2},
    ], today)
    primary["source"]["id"] = "tushare-cn_pmi"
    monkeypatch.setattr(macro_monitor, "_load_tushare_indicators", lambda _: ({"cn-pmi": primary}, [], "ok"))
    fallback_calls, legacy_calls = [], []

    def fallback(config, today):
        fallback_calls.append(config["id"])
        item = macro_monitor._normalize_standard_indicator(config, [
            {"日期": "2026-08-31", "今值": 1, "前值": 0.5},
        ], today)
        item["source"]["id"] = "eastmoney-test"
        return item

    def legacy(function, **_):
        legacy_calls.append(function)
        if function == "macro_china_lpr":
            return pd.DataFrame([{"TRADE_DATE": "2026-08-20", "LPR1Y": 3}])
        return pd.DataFrame([{"日期": "2025-08-01", "今值": 4.2}])

    monkeypatch.setattr(macro_monitor, "_eastmoney_indicator", fallback)
    monkeypatch.setattr(macro_monitor.astock, "akshare_parallel_call", legacy)
    indicators, source, gaps = macro_monitor._load_indicators(today)
    assert "cn-pmi" not in fallback_calls
    assert "macro_china_pmi_yearly" not in legacy_calls
    assert "macro_china_cpi_yearly" not in legacy_calls
    assert next(item for item in indicators if item["id"] == "cn-cpi-yoy")["source"]["id"] == "eastmoney-test"
    assert source["status"] == "partial"
    assert source["coverage"]["stale"] == 2
    assert any(gap["capability"] == "cn-gdp-yoy" for gap in gaps)


def test_regime_excludes_stale_evidence_instead_of_using_it_as_current():
    stale = macro_monitor._normalize_standard_indicator(macro_monitor._INDICATORS[0], [
        {"日期": "2025-08-31", "今值": 49.4, "前值": 49.8},
    ], date(2026, 9, 9))
    result = macro_monitor._build_regime([stale])
    assert result["growth"]["signal"] == "unknown"
    assert result["overall"]["label"] == "数据不足，暂不判定"
    assert result["overall"]["evidenceIds"] == []
    assert result["confidence"]["score"] == 0


def test_regime_requires_comparable_chinese_pairs_and_keeps_us_as_context_only():
    def observation(indicator_id, value, previous):
        config = next(item for item in macro_monitor._INDICATORS if item["id"] == indicator_id)
        return {
            "id": indicator_id, "name": config["name"], "region": config["region"],
            "value": value, "previous": previous,
            "change": value - previous if previous is not None else None,
            "freshness": {"status": "fresh"}, "evidenceId": f"evidence:{indicator_id}",
        }

    indicators = [
        observation("cn-pmi", 51.0, 50.5),
        observation("cn-gdp-yoy", 5.0, 4.8),
        observation("cn-cpi-yoy", 1.0, 0.5),
        observation("cn-m2-yoy", 8.0, 7.5),
        observation("cn-industrial-production-yoy", 5.2, 4.5),
        observation("cn-exports-yoy", 7.0, 6.0),
        observation("cn-lpr-1y", 3.0, 3.1),
        observation("us-cpi-yoy", 3.0, 2.9),
        observation("us-unemployment-rate", 4.1, 4.0),
    ]
    regime = macro_monitor._build_regime(indicators)
    review = macro_monitor._decision_review(regime, [], [])

    assert regime["growth"]["signal"] == "positive"
    assert regime["inflation"]["signal"] == "unknown"
    assert regime["overall"]["label"] == "关键证据不足，暂不判定"
    assert regime["confidence"]["score"] == 0.9
    assert all(not any(name in evidence for name in ("us-", "industrial-production", "exports"))
               for evidence in regime["overall"]["evidenceIds"])
    assert review["adoption"] == "暂缓采纳，先补证"
    assert any("价格" in check for check in review["checks"])
    assert "美国指标是跨市场旁证" in review["scope"]

    without_lpr = macro_monitor._build_regime([item for item in indicators if item["id"] != "cn-lpr-1y"])
    assert without_lpr["liquidity"]["signal"] == "unknown"
    assert without_lpr["overall"]["label"] == "关键证据不足，暂不判定"


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


def test_liquidity_loader_returns_grouped_observations_without_forecast(monkeypatch):
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
    assert {item["id"] for item in result["assessment"]["items"]} == {
        "cn-m2-yoy", "cn-m1-yoy", "cn-shibor-on", "cn-shibor-1w", "cn-shibor-3m",
    }
    assert "forecast" not in result
    credit = next(item for item in result["indicators"] if item["id"] == "cn-new-rmb-loans")
    assert credit["name"] == "新增人民币贷款"
    assert not any(item["name"] == "新增社融" for item in result["indicators"])
    assert all("forecast" not in item for item in result["assessment"]["items"])


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


def test_liquidity_assessment_requires_fresh_comparable_observations():
    result = macro_monitor._liquidity_assessment([
        {"id": "cn-m2-yoy", "name": "M2 同比", "change": 1.0, "effect": "supportive", "period": "2026-07", "unit": "%", "freshness": {"status": "stale"}},
        {"id": "cn-new-social-financing", "name": "新增社融", "change": -100, "effect": "supportive", "period": "2026-07", "unit": "亿元", "freshness": {"status": "fresh"}},
    ])
    assert result["items"] == []
    assert result["signal"] == "mixed"


def test_liquidity_item_rejects_future_rows():
    item = macro_monitor._liquidity_item(
        item_id="cn-m2-yoy", name="M2 同比", unit="%",
        rows=[{"period": date(2026, 7, 1), "value": 7.0}, {"period": date(2026, 9, 1), "value": 9.0}],
        today=date(2026, 8, 18), source_id="test", source_label="test", source_url="https://example.com",
        max_age_days=55, effect="supportive",
    )
    assert item["value"] == 7.0 and item["previous"] is None
    assert len(item["history"]) == 1


def test_liquidity_does_not_call_one_exchange_a_whole_market(monkeypatch):
    def one_exchange(function_name, **_):
        if function_name == "macro_china_market_margin_sh":
            return pd.DataFrame([{"日期": "2026-08-18", "融资融券余额": 980_000_000_000}])
        return None
    monkeypatch.setattr(macro_monitor.astock, "akshare_parallel_call", one_exchange)
    macro_monitor._CACHE.clear()
    result = macro_monitor._load_liquidity(date(2026, 8, 18))
    assert "cn-margin-balance" not in {item["id"] for item in result["indicators"]}


def test_decision_review_degrades_when_dimensions_are_missing():
    regime = macro_monitor._build_regime([])
    review = macro_monitor._decision_review(regime, [], [{"capability": "official-primary-source-verification", "reason": "test"}])
    assert review["adoption"] == "暂缓采纳，先补证"
    assert review["supportingEvidence"] == []
    assert "增长" in review["checks"][0]
    assert review["nextReviewEvents"] == []


def test_decision_review_prioritizes_relevant_events_and_exposes_divergence():
    regime = {
        "overall": {"label": "过渡混合", "summary": "信号分化"},
        "confidence": {"score": 1},
        "growth": {"label": "增长", "signal": "mixed", "summary": "PMI 与 GDP 不一致", "evidenceIds": ["pmi"]},
        "inflation": {"label": "价格", "signal": "positive", "summary": "价格上行", "evidenceIds": ["cpi"]},
        "liquidity": {"label": "流动性", "signal": "negative", "summary": "价格偏紧", "evidenceIds": ["lpr"]},
    }
    events = [
        {"id": "ch", "date": "2026-10-06", "title": "瑞士失业率", "regionGroup": "EU", "status": "scheduled", "importance": "high", "evidenceId": "ch"},
        {"id": "us", "date": "2026-10-06", "title": "美国 PMI", "regionGroup": "US", "status": "scheduled", "importance": "medium", "importanceBasis": {"kind": "rule"}, "evidenceId": "us"},
    ]
    review = macro_monitor._decision_review(regime, events, [])
    assert review["nextReviewEvents"] == [{"id": "us", "date": "2026-10-06", "title": "美国 PMI", "importance": "medium", "ratingBasis": "rule", "evidenceId": "us"}]
    assert any("方向不一致" in item for item in review["counterEvidence"])
