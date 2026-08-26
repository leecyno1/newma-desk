import json
import math
import warnings
from datetime import datetime, timedelta
from types import SimpleNamespace

import pandas as pd

import instock.core.indicator.czsc_analyzer as czsc_analyzer_module
from instock.core.czsc_analysis import run_czsc_analysis
from instock.core.indicator.czsc_analyzer import CZSCAnalyzer
from instock.core.strategy.czsc_strategy import (
    check_czsc_buy_strategy,
    check_czsc_comprehensive,
    check_czsc_consolidation_breakout,
    check_czsc_reversal_pattern,
    check_czsc_trend_following,
)


def _sample_bars(size=360):
    rows = []
    for index in range(size):
        close = 20 + math.sin(index / 7) * 2.4 + math.sin(index / 19) * 0.8 + index * 0.006
        open_ = close + math.sin(index * 1.7) * 0.18
        volume = 100000 + index * 100
        rows.append({
            "date": datetime(2024, 1, 1) + timedelta(days=index),
            "open": open_, "close": close,
            "high": max(open_, close) + 0.35,
            "low": min(open_, close) - 0.35,
            "volume": volume, "amount": volume * close,
        })
    return pd.DataFrame(rows)


def test_czsc_analysis_and_echarts_are_complete_and_serializable():
    analyzer = CZSCAnalyzer()
    result = analyzer.analyze_kline(_sample_bars(), symbol="TEST", freq="daily")

    assert result["success"] is True
    assert result["fx_list"]
    assert result["bi_list"]
    assert result["zs_list"]
    assert all(center["lower"] < center["upper"] for center in result["zs_list"])
    option = analyzer.get_echarts_option()
    assert {x["name"] for x in option["series"]} >= {"K线", "笔", "顶分型", "底分型", "成交量"}
    json.dumps(option, ensure_ascii=False)

    payload = analyzer.get_analysis_payload()
    assert payload["engine"]["name"] == "czsc"
    assert payload["engine"]["version"] == "0.10.12"
    assert payload["engine"]["analysis_model"] == "instock-czsc"
    assert payload["engine"]["analysis_version"] == "2.2.0"
    assert payload["engine"]["compatibility"] == {
        "production_version": "0.10.12",
        "tested_versions": ["0.10.12", "1.0.0rc8"],
        "installed_version": "0.10.12",
        "tested": True,
        "mode": "full",
        "official_signal_adapter": "czsc.signals-v0.10",
        "official_signals_available": True,
        "release_policy": "stable-pinned",
    }
    assert payload["summary"]["bi_count"] == len(payload["structure"]["strokes"])
    assert payload["signal_model"]["current_signals"] == "czsc_official"
    assert payload["signal_model"]["historical_markers_are_official"] is False
    assert payload["structure"]["official_signals"]
    assert payload["evidence"]["schema_version"] == "1.0"
    assert payload["evidence"]["structure_stability"]["heuristic"] is True
    assert payload["evidence"]["latest_structure_change"]["date"]
    assert payload["evidence"]["input_quality"]["state"] == "clean"
    assert payload["summary"]["structure_stability_score"] >= 0
    assert all(item["source"] == "czsc_official" for item in payload["structure"]["official_signals"])
    assert all(item["source"] == "instock_heuristic" for item in payload["structure"]["buy_points"] + payload["structure"]["sell_points"])
    assert payload["insight"]["headline"]
    assert payload["insight"]["key_levels"]
    assert payload["chart"]["series"]
    json.dumps(payload, ensure_ascii=False)


def test_missing_legacy_signal_namespace_degrades_to_structure_only(monkeypatch):
    monkeypatch.setattr(czsc_analyzer_module, "czsc_signals", None)
    monkeypatch.delattr(
        czsc_analyzer_module.czsc, "generate_czsc_signals", raising=False
    )

    analyzer = CZSCAnalyzer()
    result = analyzer.analyze_kline(_sample_bars(), symbol="TEST", freq="daily")
    payload = analyzer.get_analysis_payload()

    assert result["success"] is True
    assert payload["engine"]["compatibility"]["mode"] == "structure-only"
    assert payload["engine"]["compatibility"]["official_signals_available"] is False
    assert payload["structure"]["official_signals"] == []
    assert payload["signal_model"]["current_signals"] == "unavailable"
    assert payload["signal_model"]["fallback_current_signal"] == "instock_heuristic_v1"
    assert payload["summary"]["official_signal_status"] == "unavailable"
    assert any("官方信号适配器" in item for item in payload["insight"]["risk_flags"])


def test_rust_registry_adapter_executes_all_official_signal_rules(monkeypatch):
    captured = {}

    def fake_generate(bars, configs, *, init_n, df):
        captured.update({
            "bars": bars,
            "configs": configs,
            "init_n": init_n,
            "df": df,
        })
        return [{
            "日线_D1B_BUY1": "一买_5笔_任意_0",
            "日线_D1B_SELL1": "其他_任意_任意_0",
            "日线_D1W15T2_第二买卖点V240524": "二买_任意_任意_0",
            "日线_D1#SMA#34_BS2辅助V230320": "其他_任意_任意_0",
            "日线_D1#SMA#34_BS3辅助V230319": "三买_均线新高_任意_0",
            "日线_D1_三买辅助V230228": "其他_其他_任意_0",
            "日线_趋势跟随_BS辅助V240526": "其他_任意_任意_0",
        }]

    monkeypatch.setattr(czsc_analyzer_module, "czsc_signals", None)
    monkeypatch.setattr(
        czsc_analyzer_module.czsc, "generate_czsc_signals", fake_generate
    )

    analyzer = CZSCAnalyzer()
    result = analyzer.analyze_kline(_sample_bars(), symbol="TEST", freq="daily")
    payload = analyzer.get_analysis_payload()

    assert result["success"] is True
    assert payload["engine"]["compatibility"]["mode"] == "full"
    assert payload["engine"]["compatibility"]["official_signal_adapter"] == (
        "czsc.rust-registry-v1"
    )
    assert len(payload["structure"]["official_signals"]) == 7
    assert {item["signal"] for item in payload["structure"]["official_signals"] if item["active"]} == {
        "一买", "二买", "三买",
    }
    assert payload["signal_model"]["current_signals"] == "czsc_official"
    assert len(captured["configs"]) == 7
    assert captured["configs"][0] == {
        "name": "cxt_first_buy_V221126", "freq": "日线", "di": 1,
    }
    assert captured["init_n"] == len(captured["bars"]) - 1
    assert captured["df"] is False


def test_normalize_integer_amount_can_reconstruct_float_values_without_warning():
    data = _sample_bars(20)
    data["amount"] = 0

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        normalized = CZSCAnalyzer._normalize_data(data)

    assert normalized["amount"].dtype.kind == "f"
    assert (normalized["amount"] > 0).all()
    assert not [item for item in captured if issubclass(item.category, FutureWarning)]


def test_center_builder_rejects_inverted_price_overlap(monkeypatch):
    monkeypatch.setattr(
        "instock.core.indicator.czsc_analyzer.czsc.ZS",
        lambda _: SimpleNamespace(is_valid=True),
    )
    bis = [
        SimpleNamespace(high=447.715, low=365.714),
        SimpleNamespace(high=583.843, low=365.714),
        SimpleNamespace(high=583.843, low=490.130),
    ]

    assert CZSCAnalyzer._build_centers(bis) == []


def test_czsc_evidence_reports_normalization_and_large_calendar_gaps():
    data = _sample_bars(180).drop(index=range(80, 100)).reset_index(drop=True)
    data = pd.concat([data, data.iloc[[20]]], ignore_index=True)
    data.loc[len(data)] = data.iloc[0]
    data.loc[len(data) - 1, "date"] = None

    result = CZSCAnalyzer().analyze_kline(data, symbol="TEST", freq="daily")

    assert result["success"] is True
    quality = result["evidence"]["input_quality"]
    assert quality["state"] == "partial"
    assert quality["duplicate_dates_removed"] >= 1
    assert quality["invalid_required_rows"] >= 1
    assert quality["large_gap_count"] >= 1
    assert result["evidence"]["structure_stability"]["limitations"]


def test_short_history_czsc_keeps_structure_but_suppresses_directional_conclusion():
    class ShortProvider:
        name = "fixture"

        def get_kline(self, symbol, period="daily", limit=480, as_of=None):
            frame = _sample_bars(44)
            frame.attrs.update({
                "data_source": "fixture",
                "data_endpoint": "fixture://ohlcv",
                "adjust": "qfq",
            })
            return frame

    payload = run_czsc_analysis(
        ShortProvider(), symbol="300502", period="daily", bars=480
    )

    assert payload["actual_bars"] == 44
    assert payload["data_state"] == "partial"
    assert payload["conclusion_state"] == "insufficient_history"
    assert payload["insight"]["bias"] == "unknown"
    assert "仅 44 根 K 线" in payload["insight"]["headline"]
    assert payload["structure"]["fractals"]
    assert payload["snapshot"]["data_window"]["coverage"] == "partial"
    assert "insufficient_history_for_directional_conclusion" in (
        payload["snapshot"]["provenance"]["limitations"]
    )


def test_all_czsc_strategies_return_bool():
    data = _sample_bars()
    code_name = ("2025-12-31", "TEST")
    strategies = [
        check_czsc_comprehensive,
        check_czsc_buy_strategy,
        check_czsc_trend_following,
        check_czsc_reversal_pattern,
        check_czsc_consolidation_breakout,
    ]
    assert all(isinstance(check(code_name, data, None, 30), bool) for check in strategies)
