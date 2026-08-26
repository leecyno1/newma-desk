import math
from datetime import datetime, timedelta

import pandas as pd

from instock.core.market_data_provider import MarketDataError, MarketDataProvider
from instock.core.rotation.etf_universe import (
    DEFAULT_SECTOR_ETFS,
    SW_2021_L1_INDUSTRIES,
    SectorETF,
)
from instock.core.rotation.rotation_engine import RotationEngine


UNIVERSE = (
    SectorETF("100001", "成长ETF", "成长", ("成长",), signal_code="100001"),
    SectorETF("100002", "银行ETF", "银行", ("银行",), signal_code="100002"),
    SectorETF("100003", "消费ETF", "消费", ("消费",), signal_code="100003"),
    SectorETF("100004", "地产ETF", "地产", ("地产",), signal_code="100004"),
)


def _bars(rate: float, size: int = 145) -> pd.DataFrame:
    rows = []
    for index in range(size):
        close = 100 * ((1 + rate) ** index) * (1 + math.sin(index / 8) * 0.002)
        volume = 1_000_000 * (1 + math.sin(index / 5) * 0.04)
        rows.append({
            "date": datetime(2025, 1, 1) + timedelta(days=index),
            "open": close * 0.997,
            "high": close * 1.008,
            "low": close * 0.992,
            "close": close,
            "volume": volume,
            "amount": volume * close,
        })
    return pd.DataFrame(rows)


class FixtureProvider(MarketDataProvider):
    name = "fixture"

    def __init__(self, fail_code=None, fail_industry=False, lag_code=None, lag_sessions=0):
        self.fail_code = fail_code
        self.fail_industry = fail_industry
        self.lag_code = lag_code
        self.lag_sessions = lag_sessions
        self.industry_calls = 0
        self.overview_calls = 0
        self.kline_as_of = []
        self.frames = {
            "510300": _bars(0.0005),
            "100001": _bars(0.0030),
            "100002": _bars(0.0012),
            "100003": _bars(0.0001),
            "100004": _bars(-0.0012),
        }

    def get_kline(self, symbol, period="daily", limit=480, as_of=None):
        if symbol == self.fail_code:
            raise MarketDataError("fixture failure")
        frame = self.frames[symbol]
        if as_of:
            frame = frame[frame["date"] <= pd.Timestamp(as_of)]
        frame = frame.tail(limit).reset_index(drop=True).copy()
        if symbol == self.lag_code and self.lag_sessions:
            frame = frame.iloc[:-self.lag_sessions].reset_index(drop=True)
        frame.attrs["data_source"] = self.name
        frame.attrs["data_endpoint"] = "/api/market-terminal/ohlcv"
        frame.attrs["adjust"] = "qfq"
        frame.attrs["as_of_mode"] = "client_filter" if as_of else "latest"
        self.kline_as_of.append((symbol, as_of))
        return frame

    def get_industry_ranking(self, top=50):
        self.industry_calls += 1
        if self.fail_industry:
            raise MarketDataError("industry unavailable")
        rows = [
            {"rank": 1, "name": "成长", "change_pct": 2.0, "up_count": 8, "down_count": 2, "code": "A"},
            {"rank": 20, "name": "银行", "change_pct": 0.4, "up_count": 6, "down_count": 4, "code": "B"},
            {"rank": 60, "name": "消费", "change_pct": -0.2, "up_count": 4, "down_count": 6, "code": "C"},
            {"rank": 100, "name": "地产", "change_pct": -2.0, "up_count": 1, "down_count": 9, "code": "D"},
        ]
        return {"top": rows[:2], "bottom": rows[2:], "total": 100}

    def get_market_overview(self):
        self.overview_calls += 1
        return {
            "sentiment": {
                "up": 3405, "down": 1664, "flat": 128,
                "breadth": "偏强", "speculation": "亢奋",
            },
            "sectors": [],
            "updated": "2026-08-04 17:07",
        }


def test_rotation_engine_ranks_strong_relative_momentum_first():
    result = RotationEngine(FixtureProvider(), universe=UNIVERSE, max_workers=2).analyze(60, "510300")

    assert result["data_state"] == "complete"
    assert result["engine"]["version"] == "2.1.1"
    assert result["universe_standard"] == "申万行业分类标准（2021版）一级行业"
    assert result["proxy_count"] == 0
    assert result["successful_count"] == 4
    assert result["stale_count"] == 0
    assert result["adjust"] == "qfq"
    assert result["etfs"][0]["code"] == "100001"
    assert result["etfs"][0]["momentum_20d"] > result["etfs"][1]["momentum_20d"]
    assert result["summary"]["leading_industry"] == "成长"
    assert result["summary"]["market_breadth"] == "偏强"
    assert result["market_breadth"]["state"] == "available"
    assert result["market_breadth"]["up"] == 3405
    assert result["market_breadth"]["up_ratio"] > 60
    assert result["etfs"][0]["sector_fund_flow"]["state"] == "unavailable"
    assert any("Desk 市场宽度为偏强" in item for item in result["insight"]["evidence"])
    assert result["insight"] == result["etfs"][0]["insight"]
    assert all(row["name"] in row["insight"]["headline"] for row in result["etfs"])
    runner_up = result["etfs"][1]
    assert f"排名第{runner_up['rank']}" in runner_up["insight"]["headline"]
    assert any(runner_up["name"] in item for item in runner_up["insight"]["evidence"])
    assert runner_up["insight"]["headline"] != result["insight"]["headline"]
    assert len(result["rotation_history"]) == 20
    assert result["rotation_history"][-1]["leader"]["code"] == "100001"
    assert result["summary"]["leader_streak_days"] == 20
    assert result["summary"]["rotation_changes_20d"] == 0
    assert result["summary"]["rotation_environment"] == "趋势延续"
    assert result["summary"]["leader_signal"] == "确认领先"
    assert result["summary"]["signal_distribution"] == {
        "counts": {"确认领先": 2, "新晋观察": 1, "弱势回避": 1},
        "confirmed_count": 2,
        "overheated_count": 0,
        "avoid_count": 1,
        "candidate_count": 4,
    }
    assert result["etfs"][0]["trend_state"] == "多头"
    assert result["etfs"][0]["persistence_score"] == 100
    assert result["etfs"][0]["top3_days_20d"] == 20
    assert result["etfs"][0]["rotation_signal"] == "确认领先"
    assert result["confirmation_method"].startswith("轮动确认使用近20日")
    assert result["industry_rankings"][0]["score"] == result["etfs"][0]["total_score"]
    assert result["industry_rankings"][0]["sector_fund_flow"]["score_effect"] == "confirmation_only"
    assert result["industry_rankings"][0]["proxy_type"] == "direct"
    assert all(row["proxy_type"] == "direct" for row in result["etfs"])
    assert result["signal_state"] == "complete"
    assert result["signal_fallback_count"] == 0
    assert result["factor_model"]["configured_factor_count"] == 7
    assert result["factor_model"]["active_factor_count"] == 5
    assert result["factor_model"]["industry_breadth_role"] == "confirmation_only"
    assert result["parameter_consensus"]["model_count"] == 9
    assert result["parameter_consensus"]["majority_threshold"] == 5
    assert result["parameter_consensus"]["winner"]["code"] == "100001"
    assert result["parameter_consensus"]["state"] == "strict_majority"
    assert result["parameter_consensus"]["signal"] == "参数一致"
    shadow = result["parameter_consensus"]["shadow_state"]
    assert shadow["lifecycle_state"] == "bootstrap"
    assert shadow["new_signal"] is True
    assert shadow["model_count"] == 9
    assert shadow["winner"]["code"] == "100001"
    assert result["summary"]["shadow_signal"] == "影子初始化"
    assert result["summary"]["predictive_signal"] == "观察"
    assert result["etfs"][0]["parameter_vote_count"] >= 5
    assert set(result["factor_model"]["inactive_slow_factors"]) == {
        "valuation", "fundamental_quality",
    }
    assert all(
        {"momentum", "relative_strength", "trend", "volume_continuity",
         "crowding_reversal", "valuation", "fundamental_quality"}
        <= set(row["factor_scores"])
        for row in result["etfs"]
    )


def test_rotation_engine_activates_point_in_time_slow_factors_at_broad_coverage():
    provider = FixtureProvider()
    as_of = provider.frames["510300"]["date"].iloc[-1].strftime("%Y-%m-%d")
    slow_factors = {
        "as_of": as_of,
        "source": "desk-point-in-time-fixture",
        "items": {
            item.code: {
                "valuation_percentile": 20 + index * 10,
                "fundamental_quality_score": 80 - index * 5,
            }
            for index, item in enumerate(UNIVERSE)
        },
    }

    result = RotationEngine(provider, universe=UNIVERSE, max_workers=2).analyze(
        60, "510300", slow_factors=slow_factors
    )

    assert result["factor_model"]["state"] == "complete"
    assert result["factor_model"]["active_factor_count"] == 7
    assert result["factor_model"]["coverage"] == {
        "valuation": 100.0,
        "fundamental_quality": 100.0,
    }
    assert all(row["factor_availability"]["valuation"] for row in result["etfs"])
    assert all(row["factor_availability"]["fundamental_quality"] for row in result["etfs"])
    assert all(row["slow_factor_source"] == "desk-point-in-time-fixture" for row in result["etfs"])


def test_rotation_engine_attaches_sector_fund_flow_as_confirmation_only():
    class FundFlowProvider(FixtureProvider):
        def get_market_overview(self):
            overview = super().get_market_overview()
            overview["sectors"] = [
                {
                    "name": "成长",
                    "pct": 2.1,
                    "net": 12.5,
                    "inflow": 30.0,
                    "outflow": 17.5,
                    "firms": 20,
                },
                {
                    "name": "银行",
                    "pct": -0.2,
                    "net": -3.2,
                    "inflow": 8.0,
                    "outflow": 11.2,
                    "firms": 40,
                },
            ]
            return overview

    baseline = RotationEngine(
        FixtureProvider(), universe=UNIVERSE, max_workers=2
    ).analyze(60, "510300")
    result = RotationEngine(
        FundFlowProvider(), universe=UNIVERSE, max_workers=2
    ).analyze(60, "510300")

    assert [row["total_score"] for row in result["etfs"]] == [
        row["total_score"] for row in baseline["etfs"]
    ]
    flow = result["etfs"][0]["sector_fund_flow"]
    assert {key: flow[key] for key in (
        "state", "name", "net", "inflow", "outflow", "direction",
        "unit", "source", "score_effect",
    )} == {
        "state": "available",
        "name": "成长",
        "net": 12.5,
        "inflow": 30.0,
        "outflow": 17.5,
        "direction": "inflow",
        "unit": "亿元",
        "source": "desk_market_overview",
        "score_effect": "confirmation_only",
    }
    assert flow["persistence"]["label"] == "积累中"
    assert result["summary"]["leading_sector_flow_net"] == 12.5
    assert any("仅作确认，不改变综合分" in item for item in result["insight"]["evidence"])
    assert result["effective_signal_coverage_pct"] == 100.0
    assert result["insight"]["headline"]


def test_rotation_engine_uses_distinct_saved_days_for_fund_flow_persistence():
    class FundFlowProvider(FixtureProvider):
        def get_market_overview(self):
            overview = super().get_market_overview()
            overview["sectors"] = [{"name": "成长", "net": 12.5, "inflow": 30, "outflow": 17.5}]
            return overview

    def record(as_of, net):
        return {
            "as_of": as_of,
            "flows": [{"industry": "成长", "net": net}],
        }

    current_as_of = FundFlowProvider().frames["510300"]["date"].iloc[-1]
    previous_dates = [
        (current_as_of - pd.Timedelta(days=offset)).strftime("%Y-%m-%d")
        for offset in range(1, 5)
    ]
    history = [
        record(previous_dates[0], 8.0),
        record(previous_dates[0], -99.0),
        record(previous_dates[1], 5.0),
        record(previous_dates[2], -2.0),
        record(previous_dates[3], 3.0),
    ]
    result = RotationEngine(
        FundFlowProvider(), universe=UNIVERSE, max_workers=2
    ).analyze(60, "510300", fund_flow_history=history)

    persistence = result["etfs"][0]["sector_fund_flow"]["persistence"]
    assert persistence == {
        "state": "available",
        "reason": None,
        "observed_days": 5,
        "window_days": 5,
        "inflow_days": 4,
        "outflow_days": 1,
        "neutral_days": 0,
        "net_sum": 26.5,
        "direction": "inflow",
        "label": "持续流入",
        "as_of_dates": [
            current_as_of.strftime("%Y-%m-%d"),
            *previous_dates,
        ],
        "source": "sector_fund_flow_history",
        "score_effect": "confirmation_only",
    }
    assert persistence["observed_days"] == len(persistence["as_of_dates"])
    assert any("行业资金日度账本确认" in item for item in result["insight"]["evidence"])


def test_rotation_engine_marks_fund_flow_persistence_as_accumulating():
    class FundFlowProvider(FixtureProvider):
        def get_market_overview(self):
            overview = super().get_market_overview()
            overview["sectors"] = [{"name": "成长", "net": 12.5}]
            return overview

    result = RotationEngine(
        FundFlowProvider(), universe=UNIVERSE, max_workers=2
    ).analyze(60, "510300")

    persistence = result["etfs"][0]["sector_fund_flow"]["persistence"]
    assert persistence["state"] == "unavailable"
    assert persistence["label"] == "积累中"
    assert persistence["observed_days"] == 1
    assert not any("行业资金日度账本确认" in item for item in result["insight"]["evidence"])


def test_default_sector_etf_universe_covers_all_sw_2021_level_1_industries():
    codes = {item.code for item in DEFAULT_SECTOR_ETFS}
    industries = tuple(item.industry for item in DEFAULT_SECTOR_ETFS)

    assert len(DEFAULT_SECTOR_ETFS) == 31
    assert len(codes) == len(DEFAULT_SECTOR_ETFS)
    assert industries == SW_2021_L1_INDUSTRIES
    assert sum(item.proxy_type != "direct" for item in DEFAULT_SECTOR_ETFS) == 6
    assert all(item.proxy_note for item in DEFAULT_SECTOR_ETFS if item.proxy_type != "direct")
    assert len({item.resolved_signal_code for item in DEFAULT_SECTOR_ETFS}) == 31
    assert all(item.resolved_signal_code.endswith(".SI") for item in DEFAULT_SECTOR_ETFS)


def test_rotation_engine_uses_industry_index_for_price_signal():
    universe = tuple(
        SectorETF(
            item.code,
            item.name,
            item.industry,
            item.industry_aliases,
            signal_code=f"S{index}.SI",
            signal_name=f"{item.industry}指数",
        )
        for index, item in enumerate(UNIVERSE, start=1)
    )

    class IndexSignalProvider(FixtureProvider):
        def __init__(self, fail_signal=None):
            super().__init__(fail_industry=True)
            self.fail_signal = fail_signal
            self.signal_frames = {
                "S1.SI": _bars(-0.0010),
                "S2.SI": _bars(0.0002),
                "S3.SI": _bars(0.0008),
                "S4.SI": _bars(0.0035),
            }

        def get_signal_kline(self, symbol, period="daily", limit=480, as_of=None):
            if symbol == self.fail_signal:
                raise MarketDataError("index fixture failure")
            frame = self.signal_frames[symbol]
            if as_of:
                frame = frame[frame["date"] <= pd.Timestamp(as_of)]
            frame = frame.tail(limit).reset_index(drop=True).copy()
            frame.attrs.update({
                "data_source": self.name,
                "data_endpoint": "/api/market-terminal/ohlcv",
                "adjust": "none",
            })
            return frame

    result = RotationEngine(
        IndexSignalProvider(), universe=universe, max_workers=2
    ).analyze(60, "510300")

    assert result["etfs"][0]["code"] == "100004"
    assert result["etfs"][0]["signal_code"] == "S4.SI"
    assert result["etfs"][0]["signal_mode"] == "industry_index"
    assert result["etfs"][0]["signal_adjust"] == "none"
    assert result["signal_state"] == "complete"
    assert result["index_signal_count"] == 4


def test_rotation_engine_falls_back_to_etf_when_industry_index_fails():
    universe = tuple(
        SectorETF(
            item.code,
            item.name,
            item.industry,
            item.industry_aliases,
            signal_code=f"S{index}.SI",
            signal_name=f"{item.industry}指数",
        )
        for index, item in enumerate(UNIVERSE, start=1)
    )

    class PartialSignalProvider(FixtureProvider):
        def get_signal_kline(self, symbol, period="daily", limit=480, as_of=None):
            if symbol == "S2.SI":
                raise MarketDataError("index fixture failure")
            rate = {"S1.SI": 0.003, "S3.SI": 0.001, "S4.SI": -0.001}[symbol]
            frame = _bars(rate).tail(limit).reset_index(drop=True)
            frame.attrs.update({"adjust": "none", "data_endpoint": "/api/market-terminal/ohlcv"})
            return frame

    result = RotationEngine(
        PartialSignalProvider(), universe=universe, max_workers=2
    ).analyze(60, "510300")
    bank = next(row for row in result["etfs"] if row["code"] == "100002")

    assert result["signal_state"] == "partial"
    assert result["index_signal_count"] == 3
    assert result["signal_fallback_count"] == 1
    assert result["effective_signal_count"] == 4
    assert result["effective_signal_coverage_pct"] == 100.0
    assert result["failures"] == []
    assert result["signal_failures"][0]["signal_code"] == "S2.SI"
    assert bank["signal_mode"] == "etf_fallback"
    assert bank["signal_code"] == "100002"


def test_rotation_engine_skips_known_unsupported_index_symbols():
    universe = tuple(
        SectorETF(
            item.code,
            item.name,
            item.industry,
            item.industry_aliases,
            signal_code=f"S{index}.SI",
        )
        for index, item in enumerate(UNIVERSE, start=1)
    )

    class EtfProxyProvider(FixtureProvider):
        signal_calls = 0

        def supports_signal_kline(self, symbol):
            return not symbol.endswith(".SI")

        def get_signal_kline(self, symbol, period="daily", limit=480, as_of=None):
            self.signal_calls += 1
            raise AssertionError("known unsupported signal must not be requested")

    provider = EtfProxyProvider()
    result = RotationEngine(provider, universe=universe, max_workers=2).analyze(60, "510300")

    assert provider.signal_calls == 0
    assert result["signal_state"] == "fallback"
    assert result["signal_fallback_count"] == len(universe)
    assert result["configured_signal_proxy_count"] == len(universe)
    assert result["signal_failures"] == []
    assert result["data_state"] == "complete"
    assert result["signal_policy"] == "same_industry_etf_proxy"


def test_rotation_confirmation_distinguishes_acceleration_overheat_and_defense():
    rank_paths = {
        "A": [6, 6, 5, 4, 3, 1],
        "B": [2, 2, 2, 2, 2, 2],
        "C": [1, 1, 1, 1, 1, 3],
        "D": [3, 3, 3, 3, 4, 4],
        "E": [4, 4, 4, 5, 5, 5],
        "F": [5, 5, 6, 6, 6, 6],
    }
    rows = []
    for rank, code in enumerate(rank_paths, start=1):
        defensive = code == "C"
        rows.append({
            "rank": rank,
            "code": code,
            "total_score": 90 - rank * 5,
            "trend_state": "空头" if defensive else "多头",
            "momentum_20d": -2.0 if defensive else 12.0,
            "relative_20d": -1.0 if defensive else 5.0,
            "distance_ma20": 9.0 if code in {"B", "D"} else 3.0,
            "factor_scores": {"risk_penalty": 50.0},
        })
    history = [
        {
            "rankings": [
                {"code": code, "rank": path[index]}
                for code, path in rank_paths.items()
            ]
        }
        for index in range(6)
    ]

    RotationEngine._attach_rotation_confirmation(rows, history)

    assert rows[0]["rotation_signal"] == "加速上行"
    assert rows[0]["rank_change_5d"] == 5
    assert rows[1]["rotation_signal"] == "领先过热"
    assert rows[1]["overheated"] is True
    assert rows[2]["rotation_signal"] == "相对防御"
    assert rows[3]["rotation_signal"] == "过热观察"


def test_rotation_engine_degrades_when_one_etf_and_industry_fail():
    provider = FixtureProvider(fail_code="100004", fail_industry=True)
    result = RotationEngine(provider, universe=UNIVERSE, max_workers=2).analyze(40, "510300")

    assert result["data_state"] == "partial"
    assert result["successful_count"] == 3
    assert result["failures"][0]["code"] == "100004"
    assert any("行业广度" in warning for warning in result["warnings"])
    assert all(row["factor_scores"]["industry"] == 50 for row in result["etfs"])


def test_rotation_engine_marks_small_data_lag_and_uses_benchmark_as_of():
    provider = FixtureProvider(lag_code="100002", lag_sessions=1)
    result = RotationEngine(provider, universe=UNIVERSE, max_workers=2).analyze(60, "510300")

    bank = next(row for row in result["etfs"] if row["code"] == "100002")
    assert result["as_of"] == provider.frames["510300"]["date"].iloc[-1].strftime("%Y-%m-%d")
    assert result["stale_count"] == 1
    assert bank["data_lag_sessions"] == 1
    assert bank["is_stale"] is True
    assert result["data_state"] == "partial"
    assert any("行情较基准滞后" in warning for warning in result["warnings"])


def test_rotation_engine_excludes_etf_beyond_stale_limit():
    provider = FixtureProvider(lag_code="100004", lag_sessions=4)
    result = RotationEngine(provider, universe=UNIVERSE, max_workers=2).analyze(60, "510300")

    assert result["successful_count"] == 3
    assert {row["code"] for row in result["etfs"]} == {"100001", "100002", "100003"}
    assert result["failures"][0]["code"] == "100004"
    assert "行情滞后 4 个交易日" in result["failures"][0]["error"]


def test_rotation_engine_historical_as_of_avoids_current_industry_snapshot():
    provider = FixtureProvider()
    as_of = provider.frames["510300"]["date"].iloc[-20].strftime("%Y-%m-%d")

    result = RotationEngine(provider, universe=UNIVERSE, max_workers=2).analyze(
        60, "510300", as_of
    )

    assert result["requested_as_of"] == as_of
    assert result["as_of"] == as_of
    assert provider.industry_calls == 0
    assert provider.overview_calls == 0
    assert all(value == as_of for _, value in provider.kline_as_of)
    assert all(row["factor_scores"]["industry"] == 50 for row in result["etfs"])
    assert result["snapshot"]["freshness"]["state"] == "historical"
    assert result["snapshot"]["freshness"]["resolution"] == "exact"
    assert result["parameter_consensus"]["shadow_state"]["lifecycle_state"] == (
        "historical_disabled"
    )
    assert result["parameter_consensus"]["shadow_state"]["models"] == []
    assert any("不复用当前行业广度" in warning for warning in result["warnings"])
    assert all(
        row["sector_fund_flow"]["persistence"]["reason"] == "historical_as_of_isolated"
        for row in result["etfs"]
    )


def test_rotation_engine_latest_mode_keeps_legacy_provider_signature_compatible():
    class LegacyFixtureProvider(FixtureProvider):
        def get_kline(self, symbol, period="daily", limit=480):
            return super().get_kline(symbol, period, limit)

    result = RotationEngine(
        LegacyFixtureProvider(), universe=UNIVERSE, max_workers=2
    ).analyze(40, "510300")

    assert result["successful_count"] == len(UNIVERSE)


def test_rotation_shadow_schedule_covers_bootstrap_hold_rebalance_and_gap_reset():
    dates = pd.bdate_range("2026-01-05", periods=30)
    frame = pd.DataFrame({"date": dates})
    bootstrap = RotationEngine._shadow_schedule(frame.iloc[:10], None, enabled=True)

    assert bootstrap["lifecycle_state"] == "bootstrap"
    assert bootstrap["new_signal"] is True
    assert bootstrap["next_rebalance_in_sessions"] == 10

    previous = {
        "strategy_id": RotationEngine.shadow_strategy_id,
        "as_of": dates[5].strftime("%Y-%m-%d"),
        "last_rebalance_date": dates[5].strftime("%Y-%m-%d"),
        "models": [{"id": "balanced-w60", "selected_code": "100001"}],
    }
    holding = RotationEngine._shadow_schedule(frame.iloc[:12], previous, enabled=True)
    rebalanced = RotationEngine._shadow_schedule(frame.iloc[:16], previous, enabled=True)
    reset = RotationEngine._shadow_schedule(frame.iloc[:26], previous, enabled=True)

    assert holding["lifecycle_state"] == "holding"
    assert holding["sessions_since_rebalance"] == 6
    assert holding["next_rebalance_in_sessions"] == 4
    assert holding["new_signal"] is False
    assert rebalanced["lifecycle_state"] == "rebalanced"
    assert rebalanced["last_rebalance_date"] == dates[15].strftime("%Y-%m-%d")
    assert rebalanced["new_signal"] is True
    assert reset["lifecycle_state"] == "reinitialized_after_gap"
    assert reset["new_signal"] is True

    same_day = dict(previous)
    same_day["as_of"] = dates[11].strftime("%Y-%m-%d")
    same_day_result = RotationEngine._shadow_schedule(
        frame.iloc[:12], same_day, enabled=True
    )
    assert same_day_result["lifecycle_state"] == "same_day"
    assert same_day_result["new_signal"] is False


def test_rotation_shadow_selection_uses_buffer_and_forces_missing_switch():
    rankings = [
        {"code": "A", "rank": 1, "total_score": 90.0},
        {"code": "B", "rank": 2, "total_score": 86.0},
        {"code": "C", "rank": 3, "total_score": 82.0},
    ]

    selected, action = RotationEngine._select_shadow_position(
        rankings, "B", "rebalanced"
    )
    assert selected["code"] == "B"
    assert action == "hold_buffer"

    rankings[1]["total_score"] = 85.0
    selected, action = RotationEngine._select_shadow_position(
        rankings, "B", "rebalanced"
    )
    assert selected["code"] == "A"
    assert action == "switch"

    selected, action = RotationEngine._select_shadow_position(
        rankings, "MISSING", "holding"
    )
    assert selected["code"] == "A"
    assert action == "forced_switch_unavailable"
