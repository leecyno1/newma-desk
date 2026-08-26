import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from video_finance_evidence import (
    build_eastmoney_valuation_rows,
    build_relative_series,
    build_southbound_flow,
    build_valuation_rows,
    claim_evidence_item,
    configure_matplotlib_font,
    parse_eastmoney_quote,
    parse_tencent_kline,
)


def test_relative_series_uses_common_dates_and_normalizes_each_series_to_100():
    prices = pd.DataFrame(
        {
            "^HSTECH": [10.0, 11.0, 12.0, 13.0],
            "^IXIC": [20.0, None, 22.0, 21.0],
        },
        index=pd.to_datetime(["2026-06-01", "2026-06-02", "2026-06-03", "2026-06-04"]),
    )

    payload = build_relative_series(prices, {"^HSTECH": "恒生科技", "^IXIC": "纳斯达克"})

    assert payload["dates"] == ["2026-06-01", "2026-06-03", "2026-06-04"]
    assert payload["series"][0]["values"][0] == 100.0
    assert payload["series"][1]["values"][0] == 100.0
    assert payload["series"][0]["values"][-1] == 130.0
    assert payload["series"][1]["values"][-1] == 105.0


def test_relative_series_calculates_requested_common_session_windows():
    prices = pd.DataFrame(
        {
            "A": [10.0, 11.0, 12.0, 13.0, 14.0, 15.0],
            "B": [20.0, 19.0, 18.0, 17.0, 16.0, 15.0],
        },
        index=pd.date_range("2026-07-01", periods=6, freq="D"),
    )

    payload = build_relative_series(prices, {"A": "上涨", "B": "下跌"}, window_sessions=[2, 5, 8])

    assert [item["sessions"] for item in payload["window_returns"]] == [2, 5]
    assert payload["window_returns"][0]["returns"] == [
        {"ticker": "A", "name": "上涨", "return_pct": 15.385},
        {"ticker": "B", "name": "下跌", "return_pct": -11.765},
    ]


def test_valuation_rows_keep_same_provider_metrics_and_report_missing_fields():
    info = {
        "0700.HK": {"shortName": "Tencent", "forwardPE": 14.2, "trailingPE": 19.1, "currency": "HKD"},
        "META": {"shortName": "Meta", "forwardPE": 23.4, "trailingPE": 25.0, "currency": "USD"},
        "9988.HK": {"shortName": "Alibaba", "forwardPE": None, "trailingPE": 17.8, "currency": "HKD"},
        "AMZN": {"shortName": "Amazon", "forwardPE": 31.2, "trailingPE": 34.1, "currency": "USD"},
    }
    pairs = [
        {"company": "0700.HK", "peer": "META", "label": "腾讯 vs Meta"},
        {"company": "9988.HK", "peer": "AMZN", "label": "阿里 vs Amazon"},
    ]

    payload = build_valuation_rows(info, pairs, fetched_at="2026-07-11T10:00:00+08:00")

    assert payload["rows"][0]["company_forward_pe"] == 14.2
    assert payload["rows"][0]["peer_forward_pe"] == 23.4
    assert payload["rows"][0]["forward_pe_ratio"] == 0.607
    assert payload["status"] == "partial"
    assert payload["missing"] == [{"ticker": "9988.HK", "field": "forwardPE"}]


def test_claim_evidence_item_points_to_machine_readable_data_not_only_png():
    asset = {
        "id": "valuation-table",
        "kind": "valuation_comparison",
        "status": "ok",
        "json_path": "/tmp/valuation.json",
        "csv_path": "/tmp/valuation.csv",
        "png_path": "/tmp/valuation.png",
        "source": "Yahoo Finance via yfinance",
        "fetched_at": "2026-07-11T10:00:00+08:00",
    }

    item = claim_evidence_item(asset, rows=["0700.HK", "META"])

    assert item["relation"] == "direct"
    assert item["authenticity"] == "real_data"
    assert item["source_locator"]["json_path"] == "/tmp/valuation.json"
    assert item["source_locator"]["rows"] == ["0700.HK", "META"]


def test_parse_tencent_kline_extracts_daily_close_with_dates():
    payload = {
        "code": 0,
        "data": {
            "hkHSTECH": {
                "day": [
                    ["2026-07-08", "4525.77", "4731.02", "4774.20", "4525.77", "140456880834"],
                    ["2026-07-09", "4744.97", "4731.56", "4832.00", "4678.80", "133855376226"],
                ]
            }
        },
    }

    series = parse_tencent_kline(payload, "hkHSTECH")

    assert series.index.strftime("%Y-%m-%d").tolist() == ["2026-07-08", "2026-07-09"]
    assert series.tolist() == [4731.02, 4731.56]


def test_southbound_flow_uses_buy_minus_sell_and_builds_cumulative_net():
    frame = pd.DataFrame(
        {
            "trade_date": ["20260708", "20260709", "20260710"],
            "buy_amount": [519.77, 511.14, 467.50],
            "sell_amount": [449.46, 478.66, 500.94],
        }
    )

    payload = build_southbound_flow(frame)

    assert payload["dates"] == ["2026-07-08", "2026-07-09", "2026-07-10"]
    assert payload["net_amount"] == [70.31, 32.48, -33.44]
    assert payload["cumulative_net_amount"] == [70.31, 102.79, 69.35]


def test_chart_font_configuration_selects_an_installed_cjk_font():
    selected = configure_matplotlib_font(["Hiragino Sans GB", "Heiti SC", "Arial Unicode MS"])

    assert selected in {"Hiragino Sans GB", "Heiti SC", "Arial Unicode MS"}


def test_parse_eastmoney_quote_scales_pe_fields_using_provider_precision():
    payload = {
        "data": {
            "f43": 460200,
            "f57": "00700",
            "f58": "腾讯控股",
            "f116": 4_184_375_996_197.8,
            "f117": 4_184_375_996_197.8,
            "f152": 2,
            "f162": 0,
            "f163": 1861,
            "f164": 1592,
            "f167": 329,
        }
    }

    quote = parse_eastmoney_quote(payload, "116.00700")

    assert quote["price"] == 460.2
    assert quote["pe_dynamic"] is None
    assert quote["pe_static"] == 18.61
    assert quote["pe_ttm"] == 15.92
    assert quote["pb"] == 3.29


def test_eastmoney_valuation_rows_compare_same_provider_ttm_pe():
    quotes = {
        "116.00700": {"ticker": "00700", "name": "腾讯控股", "pe_ttm": 15.92},
        "105.META": {"ticker": "META", "name": "Meta Platforms", "pe_ttm": 24.07},
    }

    payload = build_eastmoney_valuation_rows(
        quotes,
        [{"company_secid": "116.00700", "peer_secid": "105.META", "label": "腾讯 vs Meta"}],
        fetched_at="2026-07-11T15:00:00+08:00",
    )

    assert payload["status"] == "ok"
    assert payload["metric"] == "PE (TTM)"
    assert payload["rows"][0]["company_pe_ttm"] == 15.92
    assert payload["rows"][0]["peer_pe_ttm"] == 24.07
    assert payload["rows"][0]["pe_ttm_ratio"] == 0.661
