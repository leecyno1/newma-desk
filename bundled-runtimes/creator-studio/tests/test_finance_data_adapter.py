import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import finance_data_adapter as adapter
from build_stage3_draft import resolve_asset_specs


def test_build_kline_chart_spec_from_eastmoney_payload(monkeypatch):
    def fake_em_get_json(url, params=None, timeout=15):
        assert params["secid"] == "1.600519"
        return {
            "data": {
                "name": "贵州茅台",
                "klines": [
                    "2026-01-02,100,102,103,99,1000,100000,4,2,2,1.2",
                    "2026-01-03,102,105,106,101,1200,126000,5,2.94,3,1.4",
                ],
            }
        }

    monkeypatch.setattr(adapter, "em_get_json", fake_em_get_json)

    spec = adapter.build_kline_chart_spec(
        {
            "id": "moutai-close",
            "title": "贵州茅台收盘价",
            "claim_id": "claim-price",
            "section_id": "section-01",
            "metric_id": "close_price",
            "unit": "元/股",
            "symbols": [{"code": "600519", "label": "茅台"}],
            "start_date": "20260101",
            "end_date": "20260131",
        }
    )

    assert spec["id"] == "moutai-close"
    assert spec["labels"] == ["2026-01-02", "2026-01-03"]
    assert spec["datasets"][0]["label"] == "茅台"
    assert spec["datasets"][0]["data"] == [102.0, 105.0]
    assert spec["source"] == "东方财富 push2his K线"
    assert spec["claim_id"] == "claim-price"
    assert spec["meta"]["claim_id"] == "claim-price"
    assert spec["meta"]["metric_id"] == "close_price"
    assert spec["meta"]["unit"] == "元/股"
    assert spec["meta"]["data_quality"]["status"] == "pass"
    assert spec["meta"]["provenance"]["source"] == "东方财富 push2his K线"


def test_fetch_kline_falls_back_to_baidu(monkeypatch):
    def fail_eastmoney(*args, **kwargs):
        raise RuntimeError("eastmoney down")

    def fake_baidu(symbol, *, start_date, end_date, period="daily"):
        return {
            "code": "600519",
            "prefix": "sh",
            "secid": "baidu.600519",
            "name": "贵州茅台",
            "source": "baidu_gushitong_kline",
            "rows": [{"date": "2026-01-02", "close": 102.0}],
        }

    monkeypatch.setattr(adapter, "fetch_eastmoney_kline", fail_eastmoney)
    monkeypatch.setattr(adapter, "fetch_baidu_kline", fake_baidu)

    payload = adapter.fetch_kline("600519", start_date="20260101", end_date="20260131")

    assert payload["source"] == "baidu_gushitong_kline"
    assert payload["rows"][0]["close"] == 102.0


def test_global_market_request_uses_direct_yahoo_series(monkeypatch):
    def fake_global_market(symbol, *, start_date, end_date, interval="1d"):
        return {
            "code": "^GSPC",
            "name": "S&P 500",
            "source": "yahoo_chart_api",
            "rows": [
                {"date": "2026-01-02", "close": 5000.0},
                {"date": "2026-01-03", "close": 5050.0},
            ],
        }

    monkeypatch.setattr(adapter, "fetch_global_market_history", fake_global_market)

    spec = adapter.build_kline_chart_spec(
        {
            "kind": "global_market",
            "title": "标普500走势",
            "symbols": [{"ticker": "^GSPC", "label": "S&P 500"}],
            "start_date": "20260101",
            "end_date": "20260131",
        }
    )

    assert spec["source"] == "Yahoo Finance Chart API"
    assert spec["datasets"][0]["data"] == [5000.0, 5050.0]


def test_fetch_yahoo_chart_history_parses_and_caches_payload(monkeypatch, tmp_path):
    monkeypatch.setenv("DASHENG_FINANCE_CACHE_DIR", str(tmp_path))
    call_count = {"value": 0}

    def fake_urlopen_json(url, params=None, timeout=15):
        call_count["value"] += 1
        return {
            "chart": {
                "result": [
                    {
                        "meta": {"symbol": "^GSPC", "shortName": "S&P 500"},
                        "timestamp": [1767312000, 1767398400],
                        "indicators": {
                            "quote": [
                                {
                                    "open": [5000, 5010],
                                    "close": [5020, 5030],
                                    "high": [5030, 5040],
                                    "low": [4990, 5000],
                                    "volume": [10, 12],
                                }
                            ],
                            "adjclose": [{"adjclose": [5020, 5030]}],
                        },
                    }
                ]
            }
        }

    monkeypatch.setattr(adapter, "_urlopen_json", fake_urlopen_json)

    first = adapter.fetch_yahoo_chart_history({"ticker": "^GSPC"}, start_date="20260101", end_date="20260103")
    second = adapter.fetch_yahoo_chart_history({"ticker": "^GSPC"}, start_date="20260101", end_date="20260103")

    assert first["source"] == "yahoo_chart_api"
    assert first["rows"][0]["close"] == 5020.0
    assert second["rows"][1]["close"] == 5030.0
    assert call_count["value"] == 1


def test_economic_calendar_request_builds_impact_chart(monkeypatch):
    def fake_calendar(from_date, to_date, api_key=None):
        return [
            {"date": "2026-01-02", "country": "US", "event": "CPI", "impact": "High"},
            {"date": "2026-01-03", "country": "US", "event": "Retail Sales", "impact": "Medium"},
            {"date": "2026-01-04", "country": "EU", "event": "PMI", "impact": "Low"},
        ]

    monkeypatch.setattr(adapter, "fetch_fmp_economic_calendar", fake_calendar)

    spec = adapter.build_economic_calendar_chart_spec(
        {"kind": "economic_calendar", "from_date": "2026-01-01", "to_date": "2026-01-07", "countries": ["US"]}
    )

    assert spec["source"] == "FMP Economic Calendar"
    assert spec["labels"] == ["High", "Medium", "Low", "Other"]
    assert spec["datasets"][0]["data"] == [1, 1, 0, 0]
    assert spec["meta"]["event_count"] == 2
    assert spec["meta"]["data_quality"]["status"] == "pass"


def test_china_macro_preset_builds_chart_spec(monkeypatch):
    def fake_macro_report(report_name, page_size=1000):
        assert report_name == "RPT_ECONOMY_CPI"
        return [
            {"REPORT_DATE": "2026-01-01 00:00:00", "TIME": "2026年01月份", "NATIONAL_SAME": 0.5},
            {"REPORT_DATE": "2026-02-01 00:00:00", "TIME": "2026年02月份", "NATIONAL_SAME": 0.8},
        ]

    monkeypatch.setattr(adapter, "fetch_eastmoney_macro_report", fake_macro_report)

    spec = adapter.build_eastmoney_macro_chart_spec(
        {
            "id": "china-cpi",
            "kind": "china_macro",
            "preset": "china_cpi",
            "claim_id": "claim-cpi",
            "start_date": "20260101",
            "end_date": "20260228",
        }
    )

    assert spec["id"] == "china-cpi"
    assert spec["claim_id"] == "claim-cpi"
    assert spec["labels"] == ["2026-01-01", "2026-02-01"]
    assert spec["datasets"][0]["label"] == "CPI同比"
    assert spec["datasets"][0]["data"] == [0.5, 0.8]
    assert spec["meta"]["metric_id"] == "china_cpi"
    assert spec["meta"]["unit"] == "%"
    assert spec["meta"]["provenance"]["source_key"] == "RPT_ECONOMY_CPI"


def test_china_house_price_builds_city_series(monkeypatch):
    def fake_macro_report(report_name, page_size=1000):
        assert report_name == "RPT_ECONOMY_HOUSE_PRICE"
        return [
            {"REPORT_DATE": "2026-01-01 00:00:00", "CITY": "北京", "FIRST_COMHOUSE_SAME": 99.0},
            {"REPORT_DATE": "2026-02-01 00:00:00", "CITY": "北京", "FIRST_COMHOUSE_SAME": 99.2},
            {"REPORT_DATE": "2026-01-01 00:00:00", "CITY": "上海", "FIRST_COMHOUSE_SAME": 100.2},
            {"REPORT_DATE": "2026-02-01 00:00:00", "CITY": "上海", "FIRST_COMHOUSE_SAME": 100.4},
        ]

    monkeypatch.setattr(adapter, "fetch_eastmoney_macro_report", fake_macro_report)

    spec = adapter.build_eastmoney_macro_chart_spec(
        {
            "id": "house-price",
            "kind": "china_house_price",
            "preset": "china_house_price",
            "cities": ["北京", "上海"],
            "field": "FIRST_COMHOUSE_SAME",
        }
    )

    assert spec["labels"] == ["2026-01-01", "2026-02-01"]
    assert spec["datasets"][0]["label"] == "北京"
    assert spec["datasets"][0]["data"] == [-1.0, -0.8]
    assert spec["datasets"][1]["label"] == "上海"
    assert spec["datasets"][1]["data"] == [0.2, 0.4]
    assert spec["meta"]["transform"] == "delta_from_100"
    assert spec["meta"]["provenance"]["source_key"] == "RPT_ECONOMY_HOUSE_PRICE"


def test_resolve_asset_specs_expands_finance_chart_requests(monkeypatch):
    def fake_build_finance_chart_specs_with_report(requests):
        assert requests[0]["symbols"] == ["600519"]
        return {
            "chart_specs": [
                {
                    "id": "finance-chart",
                    "title": "金融数据图",
                    "type": "line",
                    "labels": ["2026-01-02"],
                    "datasets": [{"label": "收盘价", "data": [102]}],
                }
            ],
            "failures": [],
            "validation_report": {"status": "pass", "requested_count": 1, "generated_count": 1, "failure_count": 0},
        }

    monkeypatch.setattr("build_stage3_draft.build_finance_chart_specs_with_report", fake_build_finance_chart_specs_with_report)

    result = resolve_asset_specs(
        {
            "topic_id": "topic-finance",
            "title": "金融选题",
            "chart_needs": ["股价走势"],
            "finance_chart_requests": [{"kind": "kline", "symbols": ["600519"]}],
        },
        {"topic_id": "topic-finance", "claims": []},
        {},
    )

    assert result["asset_status"] == "complete"
    assert result["asset_missing"] == []
    assert result["chart_specs"][0]["id"] == "finance-chart"
    assert result["finance_chart_requests"][0]["symbols"] == ["600519"]
    assert result["finance_chart_failures"] == []
    assert result["data_validation"]["status"] == "pass"


def test_resolve_asset_specs_accepts_future_data_requests(monkeypatch):
    def fake_build_finance_chart_specs_with_report(requests):
        assert requests[0]["claim_id"] == "claim-data"
        return {
            "chart_specs": [
                {
                    "id": "data-chart",
                    "title": "未来数据结构图",
                    "type": "line",
                    "labels": ["2026-01-02"],
                    "datasets": [{"label": "指数", "data": [100]}],
                    "claim_id": "claim-data",
                }
            ],
            "failures": [],
            "validation_report": {"status": "pass", "requested_count": 1, "generated_count": 1, "failure_count": 0},
        }

    monkeypatch.setattr("build_stage3_draft.build_finance_chart_specs_with_report", fake_build_finance_chart_specs_with_report)

    result = resolve_asset_specs(
        {
            "topic_id": "topic-finance",
            "title": "金融选题",
            "data_requests": [
                {
                    "id": "data-chart",
                    "kind": "global_market",
                    "claim_id": "claim-data",
                    "symbols": [{"ticker": "^GSPC"}],
                }
            ],
        },
        {"topic_id": "topic-finance", "claims": []},
        {},
    )

    assert result["asset_status"] == "complete"
    assert result["finance_chart_requests"][0]["claim_id"] == "claim-data"
    assert result["chart_specs"][0]["claim_id"] == "claim-data"
    assert result["data_validation"]["generated_count"] == 1


def test_resolve_asset_specs_marks_partial_finance_failures_incomplete(monkeypatch):
    def fake_build_finance_chart_specs_with_report(requests):
        return {
            "chart_specs": [
                {
                    "id": "ok-chart",
                    "title": "成功图",
                    "type": "line",
                    "labels": ["2026-01-02"],
                    "datasets": [{"label": "收盘价", "data": [102]}],
                }
            ],
            "failures": [{"request_id": "missing-chart", "kind": "global_market", "reason": "Yahoo rate limit"}],
            "validation_report": {"status": "fail", "requested_count": 2, "generated_count": 1, "failure_count": 1},
        }

    monkeypatch.setattr("build_stage3_draft.build_finance_chart_specs_with_report", fake_build_finance_chart_specs_with_report)

    result = resolve_asset_specs(
        {
            "topic_id": "topic-finance",
            "title": "金融选题",
            "finance_chart_requests": [
                {"id": "ok-chart", "kind": "kline", "symbols": ["600519"]},
                {"id": "missing-chart", "kind": "global_market", "symbols": [{"ticker": "^GSPC"}]},
            ],
        },
        {"topic_id": "topic-finance", "claims": []},
        {},
    )

    assert result["asset_status"] == "incomplete"
    assert result["asset_missing"] == ["finance_chart_specs"]
    assert result["finance_chart_failures"][0]["request_id"] == "missing-chart"
    assert result["data_validation"]["status"] == "fail"
