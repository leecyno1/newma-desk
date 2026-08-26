import math
from datetime import datetime, timedelta

import pandas as pd

from instock.core.market_data_provider import MarketDataError, MarketDataProvider
from instock.core.signals import TechnicalSignalCenterEngine, TechnicalSignalCenterError


def _bars(rate=0.002, size=280, final_change=None, volume_multiple=1.0):
    rows = []
    for index in range(size):
        close = 20 * ((1 + rate) ** index) * (1 + math.sin(index / 9) * 0.006)
        volume = 12_000_000 * (1 + math.sin(index / 7) * 0.05)
        rows.append({
            "date": datetime(2025, 1, 1) + timedelta(days=index),
            "open": close * 0.994,
            "high": close * 1.012,
            "low": close * 0.988,
            "close": close,
            "volume": volume,
            "amount": close * volume,
        })
    if final_change is not None:
        previous = rows[-2]["close"]
        close = previous * (1 + final_change)
        rows[-1].update({
            "open": previous * 1.005,
            "high": close * 1.01,
            "low": previous * 0.995,
            "close": close,
            "volume": rows[-2]["volume"] * volume_multiple,
            "amount": close * rows[-2]["volume"] * volume_multiple,
        })
    frame = pd.DataFrame(rows)
    frame.attrs.update({"data_source": "fixture-desk", "adjust": "qfq"})
    return frame


class FixtureProvider(MarketDataProvider):
    name = "fixture-desk"

    def __init__(self, fail_symbol=None):
        self.fail_symbol = fail_symbol
        self.frames = {
            "300502": _bars(final_change=0.045, volume_multiple=2.6),
            "000001": _bars(rate=0.0004),
            "600000": _bars(rate=-0.0012),
        }

    def get_kline(self, symbol, period="daily", limit=480, as_of=None):
        if symbol == self.fail_symbol:
            raise MarketDataError("kline unavailable")
        frame = self.frames[symbol].tail(limit).reset_index(drop=True).copy()
        frame.attrs.update(self.frames[symbol].attrs)
        return frame

    def get_stock_scan(self, *, sort="amount", order="desc", limit=50):
        return {
            "items": [
                {"symbol": "300502", "name": "新易盛", "industry": "通信", "price": 42, "change_pct": 4.5, "amount": 8e9, "turnover_pct": 7.2, "volume_ratio": 2.6, "market_cap": 80e9, "pe": 50, "pb": 8},
                {"symbol": "000001", "name": "平安银行", "industry": "银行", "price": 12, "change_pct": 0.4, "amount": 5e9, "turnover_pct": 1.1, "volume_ratio": 1.0, "market_cap": 220e9, "pe": 7, "pb": 0.8},
                {"symbol": "600000", "name": "浦发银行", "industry": "银行", "price": 9, "change_pct": -1.2, "amount": 3e9, "turnover_pct": 0.8, "volume_ratio": 0.9, "market_cap": 180e9, "pe": 6, "pb": 0.7},
            ],
            "source": self.name,
            "as_of": "2026-08-11T15:00:00+08:00",
            "coverage": {"requested": limit, "returned": 3},
        }

    def get_liquidity_scan(self, *, limit=50):
        result = self.get_stock_scan(sort="amount", order="desc", limit=limit)
        result["coverage"].update({
            "scope": "full_market_top20_plus_market_cap_pool",
            "sort_basis": "amount_top20_then_marketCap",
        })
        return result


class DragonTigerProvider(FixtureProvider):
    def __init__(self, packet=None, error=None):
        super().__init__()
        self.packet = packet
        self.error = error

    def get_dragon_tiger_evidence(self, symbol):
        if self.error:
            raise MarketDataError(self.error)
        return self.packet or {"records": [], "institution": {}}


class ShortHistoryProvider(FixtureProvider):
    def __init__(self):
        super().__init__()
        self.frames["688825"] = _bars(size=13)
        self.frames["688825"].attrs.update({
            "upstream_source": "desk-tushare",
            "upstream_has_more": False,
        })

    def get_stock_scan(self, *, sort="amount", order="desc", limit=50):
        result = super().get_stock_scan(sort=sort, order=order, limit=limit)
        result["items"].append({
            "symbol": "688825",
            "name": "长鑫科技",
            "industry": "电子",
            "price": 118,
            "change_pct": 3.2,
            "amount": 4e9,
            "turnover_pct": 12.5,
            "volume_ratio": 1.8,
            "market_cap": 120e9,
            "pe": 0,
            "pb": 12,
        })
        return result


class CrossMarketProvider(FixtureProvider):
    def __init__(self):
        super().__init__()
        self.frames["00700.HK"] = _bars(rate=0.0011)

    def get_kline(self, symbol, period="daily", limit=480, as_of=None):
        if symbol == "00700.HK":
            frame = self.frames[symbol].tail(limit).reset_index(drop=True).copy()
            frame.attrs.update(self.frames[symbol].attrs)
            return frame
        return super().get_kline(symbol, period=period, limit=limit, as_of=as_of)

    def get_candidate_universe(self, *, markets=("CN",), per_scan_limit=200):
        items = []
        if "CN" in markets:
            items.extend(self.get_stock_scan(limit=per_scan_limit)["items"])
        if "HK" in markets:
            items.append({
                "symbol": "00700",
                "market": "HK",
                "name": "腾讯控股",
                "industry": "互联网",
                "price": 600,
                "change_pct": 1.1,
                "amount": 9e9,
                "turnover_pct": 0.8,
                "volume_ratio": 1.2,
                "market_cap": 5e12,
                "pe": 25,
                "pb": 4,
            })
        return {
            "items": items,
            "source": self.name,
            "as_of": "2026-08-11T15:00:00+08:00",
            "coverage": {
                "scope": "desk_multi_scan_union",
                "sort_basis": "eight_scan_axes",
            },
        }


class BroadFailureProvider(FixtureProvider):
    def get_candidate_universe(self, *, markets=("CN",), per_scan_limit=200):
        raise MarketDataError("broad scan unavailable")


class WidePrefilterProvider(FixtureProvider):
    def get_candidate_universe(self, *, markets=("CN",), per_scan_limit=200):
        items = []
        for index in range(35):
            symbol = f"60{index:04d}"
            items.append({
                "symbol": symbol,
                "market": "CN",
                "name": f"样本{index}",
                "industry": "样本行业",
                "price": 10,
                "change_pct": 1,
                "amount": 1e9,
                "turnover_pct": 2,
                "volume_ratio": 1.2,
                "market_cap": 1e10,
                "pe": 5 if index == 34 else 50,
                "pb": 2,
                "scan_rank_score": 35 - index,
            })
        return {
            "items": items,
            "source": self.name,
            "as_of": "2026-08-11T15:00:00+08:00",
            "coverage": {"scope": "desk_multi_scan_union", "sort_basis": "eight_scan_axes"},
        }

    def get_kline(self, symbol, period="daily", limit=480, as_of=None):
        return _bars().tail(limit).reset_index(drop=True)


class FundamentalProvider(FixtureProvider):
    def __init__(self, *, missing=False):
        super().__init__()
        self.missing = missing
        self.comparison_calls = []
        self.snapshot_calls = []

    def get_equity_comparison(self, symbols, *, refresh=False):
        self.comparison_calls.append((list(symbols), refresh))
        rows = [{
            "identity": {"symbol": "300502"},
            "metrics": {
                "roePct": 18,
                "revenueGrowthPct": 20,
                "netProfitGrowthPct": 25,
            },
        }]
        if not self.missing:
            rows.append({
                "identity": {"symbol": "000001"},
                "metrics": {
                    "roePct": 11,
                    "revenueGrowthPct": 8,
                    "netProfitGrowthPct": 12,
                },
            })
        return {"rows": rows, "errors": [], "generatedAt": "2026-08-11T18:00:00+08:00"}

    def get_equity_snapshot(self, symbol, *, refresh=False):
        self.snapshot_calls.append((symbol, refresh))
        if self.missing:
            raise MarketDataError("fundamental unavailable")
        return {
            "generatedAt": "2026-08-11T18:00:00+08:00",
            "comparisonProfile": {"metrics": {
                "roePct": 9,
                "revenueGrowthPct": 5,
                "netProfitGrowthPct": -2,
            }},
        }


def test_signal_center_unifies_indicators_patterns_and_ten_legacy_strategies():
    result = TechnicalSignalCenterEngine(FixtureProvider(), max_workers=2).analyze(
        universe_size=30, bars=260
    )

    assert result["engine"]["name"] == "instock-technical-signal-center"
    assert result["data_state"] == "complete"
    assert len(result["catalog"]["strategies"]) == 10
    assert {item["id"] for item in result["catalog"]["strategies"]} == {
        "volume_rise", "ma_bull", "parking_apron", "backtrace_ma250",
        "breakthrough_platform", "low_backtrace_increase", "turtle_trade",
        "high_tight_flag", "climax_limitdown", "low_atr_growth",
    }
    row = next(item for item in result["rows"] if item["symbol"] == "300502")
    assert set(row["indicators"]) >= {"macd", "macd_signal", "rsi", "kdj_k", "atr_pct", "cci", "mfi", "obv"}
    assert set(row["indicator_signals"]) == {"buy", "sell"}
    assert len(row["strategies"]) == 10
    assert any(item["id"] == "volume_rise" and item["state"] == "active" for item in row["strategies"])
    assert row["technical_score"] > 50
    assert result["coverage"]["scan_scope"] == "full_market_top20_plus_market_cap_pool"
    assert result["coverage"]["scan_sort_basis"] == "amount_top20_then_marketCap"
    assert "signal_pool_uses_turnover_top20_then_market_cap_fill" in result["limitations"]
    assert result["snapshot"]["analysis"]["name"] == "instock-technical-signal-center"


def test_high_tight_flag_requires_positive_institutional_net_buy():
    strategies = [{
        "id": "high_tight_flag", "state": "needs_evidence",
        "evidence": ["价格形态前置条件已满足"], "missing": ["机构龙虎榜证据"],
    }]
    provider = DragonTigerProvider({
        "records": [{"date": "2026-08-15", "reason": "日涨幅偏离"}],
        "institution": {"net_amt": 700},
        "source": "capability:capital.dragon-tiger",
    })
    error = TechnicalSignalCenterEngine(provider)._confirm_high_tight_flag(
        "300502", "CN", strategies
    )

    assert error == ""
    assert strategies[0]["state"] == "active"
    assert strategies[0]["external_evidence"]["institution_net_cny_10k"] == 700


def test_high_tight_flag_does_not_use_ordinary_dragon_tiger_net_buy():
    strategies = [{
        "id": "high_tight_flag", "state": "needs_evidence",
        "evidence": [], "missing": ["机构龙虎榜证据"],
    }]
    provider = DragonTigerProvider({
        "records": [{"date": "2026-08-15", "net_buy": 700}],
        "institution": {"net_amt": 0},
    })

    TechnicalSignalCenterEngine(provider)._confirm_high_tight_flag(
        "300502", "CN", strategies
    )

    assert strategies[0]["state"] == "inactive"
    assert "未形成净买确认" in strategies[0]["evidence"][-1]


def test_high_tight_flag_keeps_evidence_gap_when_dragon_tiger_fails():
    strategies = [{
        "id": "high_tight_flag", "state": "needs_evidence",
        "evidence": [], "missing": ["机构龙虎榜证据"],
    }]
    error = TechnicalSignalCenterEngine(
        DragonTigerProvider(error="dragon tiger unavailable")
    )._confirm_high_tight_flag("300502", "CN", strategies)

    assert error == "dragon tiger unavailable"
    assert strategies[0]["state"] == "needs_evidence"
    assert strategies[0]["missing"] == ["机构龙虎榜证据读取失败"]


def test_signal_center_exposes_unavailable_long_window_rule_without_faking_signal():
    result = TechnicalSignalCenterEngine(FixtureProvider(), max_workers=2).analyze(
        universe_size=30, bars=120
    )
    row = result["rows"][0]
    annual = next(item for item in row["strategies"] if item["id"] == "backtrace_ma250")

    assert annual["state"] == "unavailable"
    assert annual["missing"] == ["至少 250 根日线"]
    assert "long_window_strategies_partial" in result["limitations"]


def test_signal_center_keeps_partial_results_when_one_symbol_fails():
    result = TechnicalSignalCenterEngine(
        FixtureProvider(fail_symbol="600000"), max_workers=2
    ).analyze(universe_size=30, bars=260)

    assert result["data_state"] == "partial"
    assert result["coverage"]["analyzed_count"] == 2
    assert result["failures"] == [{"symbol": "600000", "market": "CN", "error": "kline unavailable"}]


def test_signal_center_places_new_listing_in_watchlist_without_marking_data_failure():
    result = TechnicalSignalCenterEngine(
        ShortHistoryProvider(), max_workers=2
    ).analyze(universe_size=30, bars=260)

    assert result["data_state"] == "complete"
    assert result["coverage"]["analyzed_count"] == 3
    assert result["coverage"]["failed_count"] == 0
    assert result["coverage"]["short_history_watch_count"] == 1
    assert result["failures"] == []
    assert result["short_history_watchlist"] == [{
        "symbol": "688825",
        "market": "CN",
        "name": "长鑫科技",
        "industry": "电子",
        "reason": "short_history_watch",
        "required_bars": 80,
        "available_bars": 13,
        "data_start": "2025-01-01",
        "data_end": "2025-01-13",
        "history_source": "desk-tushare",
        "history_has_more": False,
        "message": "有效日线不足 80 根（实际 13），暂列短历史观察",
    }]
    assert "short_history_securities_excluded_from_ranking" in result["limitations"]
    assert "partial_kline_coverage" not in result["limitations"]


def test_signal_center_rejects_unknown_window():
    try:
        TechnicalSignalCenterEngine(FixtureProvider()).analyze(universe_size=30, bars=200)
    except TechnicalSignalCenterError as exc:
        assert "120、260" in str(exc)
    else:
        raise AssertionError("expected TechnicalSignalCenterError")


def test_signal_center_applies_hard_rules_and_reports_exclusions():
    result = TechnicalSignalCenterEngine(FixtureProvider(), max_workers=2).analyze(
        universe_size=30,
        bars=260,
        filters={
            "bias": "bullish",
            "min_technical_score": 65,
            "required_strategies": ["volume_rise"],
        },
    )

    assert [row["symbol"] for row in result["matched_rows"]] == ["300502"]
    assert result["screening_coverage"] == {
        "before_rules": 3,
        "after_market_rules": 3,
        "deep_pool_count": 3,
        "analyzed_count": 3,
        "after_fundamental_rules": 3,
        "after_rules": 1,
        "excluded_by_rules": 2,
    }
    assert result["coverage"]["matched_count"] == 1
    assert {row["symbol"] for row in result["excluded_by_rules"]} == {"000001", "600000"}
    assert all(row["reasons"] for row in result["excluded_by_rules"])


def test_signal_center_supports_combined_cn_hk_universe():
    result = TechnicalSignalCenterEngine(CrossMarketProvider(), max_workers=2).analyze(
        universe_size=30,
        bars=260,
        market="CN_HK",
        universe_mode="broad",
    )

    assert {row["market"] for row in result["rows"]} == {"CN", "HK"}
    assert next(row for row in result["rows"] if row["market"] == "HK")["symbol"] == "00700"
    assert result["screening_model"]["market"] == "CN_HK"
    assert result["snapshot"]["parameters"]["market"] == "CN_HK"


def test_signal_center_falls_back_to_quick_pool_when_broad_scan_is_unavailable():
    result = TechnicalSignalCenterEngine(BroadFailureProvider(), max_workers=2).analyze(
        universe_size=30,
        bars=260,
        market="CN",
        universe_mode="broad",
    )

    assert result["data_state"] == "partial"
    assert result["coverage"]["requested_universe_mode"] == "broad"
    assert result["coverage"]["effective_universe_mode"] == "quick"
    assert result["coverage"]["broad_fallback_reason"] == "broad scan unavailable"
    assert "broad_universe_unavailable_quick_fallback" in result["limitations"]


def test_market_rules_filter_the_broad_pool_before_deep_kline_selection():
    result = TechnicalSignalCenterEngine(WidePrefilterProvider(), max_workers=2).analyze(
        universe_size=30,
        bars=120,
        filters={"max_pe": 10},
    )

    assert [row["symbol"] for row in result["rows"]] == ["600034"]
    assert result["coverage"]["broad_eligible_count"] == 35
    assert result["coverage"]["market_prefilter_count"] == 1
    assert result["coverage"]["eligible_count"] == 1
    assert result["coverage"]["market_prefilter_excluded_count"] == 34
    assert all(row["stage"] == "market_prefilter" for row in result["excluded_by_rules"])


def test_market_rules_can_return_an_empty_result_without_api_error():
    result = TechnicalSignalCenterEngine(FixtureProvider(), max_workers=2).analyze(
        universe_size=30,
        bars=260,
        filters={"industries": ["不存在行业"]},
    )

    assert result["rows"] == []
    assert result["coverage"]["market_prefilter_count"] == 0
    assert result["coverage"]["analyzed_count"] == 0
    assert result["coverage"]["excluded_by_rules_count"] == 3


def test_deep_pool_priority_follows_active_market_filter():
    rows = [
        {
            "symbol": "600001", "market": "CN", "amount": 9e9,
            "market_cap": 9e11, "scan_rank_score": 9,
            "scan_memberships": ["marketCap:desc"],
            "scan_membership_scores": {"marketCap:desc": 1.0},
        },
        {
            "symbol": "600002", "market": "CN", "amount": 1e9,
            "market_cap": 1e10, "scan_rank_score": 1,
            "scan_memberships": ["marketCap:asc"],
            "scan_membership_scores": {"marketCap:asc": 1.0},
        },
    ]

    selected = TechnicalSignalCenterEngine._select_deep_pool(
        rows, 1, ("CN",), {"max_market_cap": 2e10}
    )

    assert [row["symbol"] for row in selected] == ["600002"]
    assert TechnicalSignalCenterEngine._deep_pool_selection_basis({
        "max_market_cap": 2e10,
        "max_pe": 20,
    }) == ["marketCap:asc", "pe:asc"]


def test_fundamentals_are_not_requested_without_fundamental_rules():
    provider = FundamentalProvider()
    result = TechnicalSignalCenterEngine(provider, max_workers=2).analyze(
        universe_size=30,
        bars=260,
    )

    assert result["coverage"]["fundamental_requested"] is False
    assert provider.comparison_calls == []
    assert provider.snapshot_calls == []


def test_fundamental_rules_run_after_kline_and_filter_each_metric():
    provider = FundamentalProvider()
    result = TechnicalSignalCenterEngine(provider, max_workers=2).analyze(
        universe_size=30,
        bars=260,
        filters={
            "min_roe_pct": 12,
            "min_revenue_growth_pct": 10,
            "min_net_profit_growth_pct": 15,
        },
        refresh=True,
    )

    assert [row["symbol"] for row in result["rows"]] == ["300502"]
    assert result["rows"][0]["fundamentals"]["roe_pct"] == 18
    assert provider.comparison_calls == [(["300502", "000001", "600000"], True)]
    assert provider.snapshot_calls == [("600000", True)]
    assert result["coverage"]["fundamental_evaluated_count"] == 3
    assert result["coverage"]["fundamental_available_count"] == 3
    assert result["coverage"]["fundamental_excluded_count"] == 2
    assert {row["stage"] for row in result["excluded_by_rules"]} == {"fundamental_rules"}
    assert any("营收增长" in reason for row in result["excluded_by_rules"] for reason in row["reasons"])
    assert any("净利润增长" in reason for row in result["excluded_by_rules"] for reason in row["reasons"])


def test_missing_fundamentals_are_explicitly_excluded():
    provider = FundamentalProvider(missing=True)
    result = TechnicalSignalCenterEngine(provider, max_workers=2).analyze(
        universe_size=30,
        bars=260,
        filters={"min_roe_pct": 10},
    )

    assert [row["symbol"] for row in result["rows"]] == ["300502"]
    excluded = [row for row in result["excluded_by_rules"] if row["stage"] == "fundamental_rules"]
    assert {row["symbol"] for row in excluded} == {"000001", "600000"}
    assert all(row["reasons"] == ["ROE数据缺失"] for row in excluded)
    assert result["coverage"]["fundamental_failed_count"] == 2
    assert "partial_fundamental_coverage" in result["limitations"]
