import math

import numpy as np
import pandas as pd
import pytest

from instock.core.market_data_provider import MarketDataError, MarketDataProvider
from instock.core.rotation.etf_universe import SectorETF
from instock.core.rotation.rotation_experiment import (
    ROTATION_CONFIRMATION_POLICIES,
    ROTATION_WEIGHT_PROFILES,
    RotationExperiment,
)
from instock.core.rotation.rotation_engine import RotationEngine


UNIVERSE = (
    SectorETF("100001", "成长ETF", "成长", ("成长",), signal_code="100001"),
    SectorETF("100002", "银行ETF", "银行", ("银行",), signal_code="100002"),
    SectorETF("100003", "消费ETF", "消费", ("消费",), signal_code="100003"),
    SectorETF("100004", "地产ETF", "地产", ("地产",), signal_code="100004"),
)


def _bars(rate: float, size: int = 620, future_shock_at=None, shock=1.0) -> pd.DataFrame:
    dates = pd.bdate_range("2023-01-02", periods=size)
    rows = []
    price = 100.0
    for index, date in enumerate(dates):
        cycle = math.sin(index / 17) * 0.0015
        price *= 1 + rate + cycle
        adjusted = price * (shock if future_shock_at is not None and index >= future_shock_at else 1.0)
        rows.append({
            "date": date,
            "open": adjusted * (1 + math.sin(index / 7) * 0.001),
            "high": adjusted * 1.008,
            "low": adjusted * 0.992,
            "close": adjusted,
            "volume": 1_000_000 * (1 + math.sin(index / 9) * 0.08),
            "amount": adjusted * 1_000_000,
        })
    frame = pd.DataFrame(rows)
    frame.attrs.update({
        "data_source": "fixture",
        "data_endpoint": "/api/market-terminal/ohlcv",
        "adjust": "qfq",
    })
    return frame


class ExperimentProvider(MarketDataProvider):
    name = "fixture"

    def __init__(self, size=620, future_shock_at=None):
        self.calls = []
        self.frames = {
            "510300": _bars(0.0004, size),
            "100001": _bars(0.0018, size),
            "100002": _bars(0.0009, size, future_shock_at, 5.0),
            "100003": _bars(0.0002, size),
            "100004": _bars(-0.0004, size),
        }

    def get_kline(self, symbol, period="daily", limit=480, as_of=None):
        self.calls.append((symbol, period, limit, as_of))
        frame = self.frames[symbol]
        if as_of:
            frame = frame[frame["date"] <= pd.Timestamp(as_of)]
        result = frame.tail(limit).reset_index(drop=True).copy()
        result.attrs.update(frame.attrs)
        return result


def _reference_variant_trades(
    experiment,
    *,
    benchmark_frame,
    trade_frames,
    signal_frames,
    weights,
    window,
    rebalance_days,
    cost_bps,
):
    """Straightforward reference implementation used as an equivalence oracle."""

    engine = RotationEngine(
        experiment.provider,
        universe=experiment.universe,
        max_workers=experiment.max_workers,
        weights=weights,
    )
    dates = list(pd.to_datetime(benchmark_frame["date"]))
    trades = []
    held_symbol = None
    for position in range(max(window + 5, 125), len(dates) - rebalance_days - 1, rebalance_days):
        signal_date = dates[position]
        entry_date = dates[position + 1]
        exit_date = dates[position + 1 + rebalance_days]
        benchmark_slice = benchmark_frame[pd.to_datetime(benchmark_frame["date"]) <= signal_date]
        benchmark_metrics = engine._benchmark_metrics(benchmark_slice, window)
        raw_rows = []
        executable = {}
        period_returns = []
        for item in experiment.universe:
            trade_source = trade_frames.get(item.code)
            signal_source = signal_frames.get(item.code)
            if trade_source is None or signal_source is None:
                continue
            trade_slice = trade_source[pd.to_datetime(trade_source["date"]) <= signal_date]
            signal_slice = signal_source[pd.to_datetime(signal_source["date"]) <= signal_date]
            if len(trade_slice) < window + 1 or len(signal_slice) < window + 1:
                continue
            trade_lag = engine._session_lag(benchmark_slice["date"], trade_slice["date"].iloc[-1])
            signal_lag = engine._session_lag(benchmark_slice["date"], signal_slice["date"].iloc[-1])
            if trade_lag > engine.max_stale_sessions or signal_lag > engine.max_stale_sessions:
                continue
            entry_price = experiment._execution_price(trade_source, entry_date)
            exit_price = experiment._execution_price(trade_source, exit_date)
            if entry_price is None or exit_price is None:
                continue
            trade_slice = trade_slice.copy()
            trade_slice.attrs.update(trade_source.attrs)
            trade_slice.attrs["data_lag_sessions"] = trade_lag
            signal_slice = signal_slice.copy()
            signal_slice.attrs.update(signal_source.attrs)
            signal_slice.attrs["signal_lag_sessions"] = signal_lag
            raw_rows.append(engine._raw_metrics(
                item,
                signal_slice,
                benchmark_metrics,
                window,
                [],
                trade_frame=trade_slice,
                signal_mode=signal_source.attrs.get("rotation_signal_mode", "trade_asset"),
            ))
            executable[item.code] = (entry_price, exit_price)
            period_returns.append(exit_price / entry_price - 1)
        if len(raw_rows) < experiment._minimum_cross_section_size(len(experiment.universe)):
            continue
        rankings = engine._score_rows(raw_rows)
        leader = rankings[0]
        selected = experiment._select_with_buffer(rankings, held_symbol)
        switched = held_symbol != selected["code"]
        transaction_cost = 2 * cost_bps / 10_000 if switched else 0.0
        entry_price, exit_price = executable[selected["code"]]
        leader_entry_price, leader_exit_price = executable[leader["code"]]
        benchmark_entry = experiment._execution_price(benchmark_frame, entry_date)
        benchmark_exit = experiment._execution_price(benchmark_frame, exit_date)
        if benchmark_entry is None or benchmark_exit is None:
            continue
        gross_return = exit_price / entry_price - 1
        trades.append({
            "signal_date": signal_date.strftime("%Y-%m-%d"),
            "entry_date": entry_date.strftime("%Y-%m-%d"),
            "exit_date": exit_date.strftime("%Y-%m-%d"),
            "symbol": selected["code"],
            "name": selected["name"],
            "industry": selected["industry"],
            "signal_code": selected["signal_code"],
            "signal_name": selected["signal_name"],
            "signal_mode": selected["signal_mode"],
            "score": selected["total_score"],
            "current_leader_symbol": leader["code"],
            "current_leader_name": leader["name"],
            "current_leader_industry": leader["industry"],
            "current_leader_signal_code": leader["signal_code"],
            "current_leader_signal_name": leader["signal_name"],
            "current_leader_signal_mode": leader["signal_mode"],
            "current_leader_score": leader["total_score"],
            "current_leader_gross_return": (
                leader_exit_price / leader_entry_price - 1
            ),
            "switched": switched,
            "transaction_cost": transaction_cost,
            "gross_return": gross_return,
            "net_return": gross_return - transaction_cost,
            "benchmark_return": benchmark_exit / benchmark_entry - 1,
            "equal_weight_return": float(np.mean(period_returns)),
        })
        held_symbol = selected["code"]
    return trades


def test_rotation_experiment_returns_oos_parameter_surface_and_stress_tests():
    provider = ExperimentProvider()
    result = RotationExperiment(provider, universe=UNIVERSE, max_workers=2).run(
        benchmark="510300",
        rebalance_days=10,
        cost_bps=25,
    )

    assert result["engine"]["name"] == "instock-rotation-experiment"
    assert result["engine"]["version"] == "2.1.1"
    assert len(result["parameter_surface"]) == len(ROTATION_WEIGHT_PROFILES) * 3
    comparison = result["confirmation_comparison"]
    assert comparison["base_variant_id"] == result["selected_variant"]["id"]
    assert {row["id"] for row in comparison["policies"]} == set(ROTATION_CONFIRMATION_POLICIES)
    assert comparison["selected_policy"]["id"] == result["summary"]["selected_confirmation_policy"]
    assert comparison["oos_observation"]["post_hoc_only"] is True
    assert all(len(row["cost_sensitivity"]) == 3 for row in comparison["policies"])
    raw_policy = next(row for row in comparison["policies"] if row["id"] == "raw")
    assert raw_policy["out_of_sample"] == result["selected_variant"]["out_of_sample"]
    assert result["selected_variant"]["out_of_sample"]["trades"] >= 4
    assert result["rules"]["signal_timing"] == "signal_at_close_t_execute_next_session_open"
    assert result["rules"]["historical_industry_factor"] == "confirmation_only_no_lookahead"
    assert result["rules"]["historical_slow_factors"] == "excluded_without_point_in_time_evidence"
    assert result["rules"]["switch_score_gap"] == 5.0
    assert result["rules"]["hold_rank_limit"] == 3
    assert result["rules"]["transaction_cost"] == "charged_when_selected_etf_changes"
    assert result["selected_variant"]["qualification"]["state"] == "qualified"
    assert result["data_quality"]["state"] == "complete"
    assert result["data_quality"]["signal_state"] == "complete"
    assert result["data_quality"]["universe_coverage_pct"] == 100.0
    assert result["data_quality"]["index_signal_coverage_pct"] == 100.0
    assert result["data_quality"]["effective_signal_coverage_pct"] == 100.0
    assert result["data_quality"]["configured_factor_count"] == 7
    assert result["data_quality"]["active_factor_count"] == 5
    assert {row["horizon_sessions"] for row in result["prediction_diagnostics"]["out_of_sample"]["horizons"]} == {5, 10, 20}
    factor_effectiveness = result["prediction_diagnostics"]["factor_effectiveness"]
    assert factor_effectiveness["primary_horizon_sessions"] == 10
    assert len(factor_effectiveness["factors"]) == 7
    assert result["prediction_diagnostics"]["confidence_diagnostics"]["verdict"]["deployment"].startswith("shadow_only")
    assert result["parameter_ensemble"]["variant_count"] == 9
    assert result["parameter_ensemble"]["majority_threshold"] == 5
    assert result["parameter_ensemble"]["verdict"]["deployment"].startswith("shadow_only")
    online_consensus = result["parameter_ensemble"]["online_current_leader"]
    assert online_consensus["alignment"] == "same_as_online_snapshot_parameter_consensus"
    assert online_consensus["verdict"]["deployment"] == "observation_only_until_forward_validated"
    assert "development_holdout_has_been_reused_not_blind" in result["limitations"]
    assert result["snapshot"]["snapshot_id"].startswith("instock-rotation-experiment:")
    assert result["verdict"]["state"] == "insufficient_evidence"
    assert any("低于五年" in reason for reason in result["verdict"]["reasons"])
    assert all(call[2] == 800 for call in provider.calls)

    stress_returns = [row["total_return_pct"] for row in result["stress_tests"]]
    assert stress_returns == sorted(stress_returns, reverse=True)


def test_rotation_experiment_requires_broad_cross_section_for_31_industries():
    assert RotationExperiment._minimum_cross_section_size(4) == 4
    assert RotationExperiment._minimum_cross_section_size(31) == 24

    class SparseProvider(ExperimentProvider):
        def get_kline(self, symbol, period="daily", limit=480, as_of=None):
            if symbol == "100004":
                raise MarketDataError("fixture missing")
            return super().get_kline(symbol, period, limit, as_of)

    with pytest.raises(MarketDataError, match="有效 ETF 仅 3/4 个.*最低覆盖 4 个"):
        RotationExperiment(SparseProvider(), universe=UNIVERSE, max_workers=2)._load_frames(
            "510300", None
        )


def test_rotation_experiment_ranks_on_index_and_executes_etf_prices():
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

    class SplitProvider(ExperimentProvider):
        def __init__(self):
            super().__init__(size=360)
            self.frames.update({
                "100001": _bars(-0.0008, 360),
                "100002": _bars(0.0015, 360),
                "100003": _bars(0.0005, 360),
                "100004": _bars(-0.0002, 360),
            })
            self.signal_frames = {
                "S1.SI": _bars(0.0030, 360),
                "S2.SI": _bars(0.0010, 360),
                "S3.SI": _bars(0.0001, 360),
                "S4.SI": _bars(-0.0010, 360),
            }

        def get_signal_kline(self, symbol, period="daily", limit=480, as_of=None):
            frame = self.signal_frames[symbol]
            if as_of:
                frame = frame[frame["date"] <= pd.Timestamp(as_of)]
            result = frame.tail(limit).reset_index(drop=True).copy()
            result.attrs.update(frame.attrs)
            result.attrs["adjust"] = "none"
            return result

    experiment = RotationExperiment(SplitProvider(), universe=universe, max_workers=2)
    benchmark, trade_frames, signal_frames, failures, signal_failures = experiment._load_frames(
        "510300", None
    )
    trades = experiment._variant_trades(
        benchmark_frame=benchmark,
        trade_frames=trade_frames,
        signal_frames=signal_frames,
        weights=ROTATION_WEIGHT_PROFILES["balanced"],
        window=60,
        rebalance_days=10,
        cost_bps=25,
    )
    first = trades[0]
    trade_frame = trade_frames[first["symbol"]]
    expected_entry = experiment._execution_price(trade_frame, pd.Timestamp(first["entry_date"]))
    expected_exit = experiment._execution_price(trade_frame, pd.Timestamp(first["exit_date"]))

    assert failures == []
    assert signal_failures == []
    assert first["symbol"] == "100001"
    assert first["signal_code"] == "S1.SI"
    assert first["signal_mode"] == "industry_index"
    assert first["gross_return"] == pytest.approx(expected_exit / expected_entry - 1)


def test_rotation_experiment_accepts_same_industry_etf_signal_proxy():
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

    class PartialIndexProvider(ExperimentProvider):
        def __init__(self):
            super().__init__()
            self.signal_frames = {
                f"S{index}.SI": _bars(rate, 620)
                for index, rate in enumerate((0.0018, 0.0009, 0.0002, -0.0004), start=1)
            }

        def get_signal_kline(self, symbol, period="daily", limit=480, as_of=None):
            if symbol == "S4.SI":
                raise MarketDataError("index fixture failure")
            frame = self.signal_frames[symbol]
            if as_of:
                frame = frame[frame["date"] <= pd.Timestamp(as_of)]
            result = frame.tail(limit).reset_index(drop=True).copy()
            result.attrs.update(frame.attrs)
            result.attrs["adjust"] = "none"
            return result

    result = RotationExperiment(
        PartialIndexProvider(), universe=universe, max_workers=2
    ).run(benchmark="510300", rebalance_days=10, cost_bps=25)

    assert result["data_quality"]["signal_state"] == "partial"
    assert result["data_quality"]["index_signal_coverage_pct"] == 75.0
    assert result["data_quality"]["effective_signal_coverage_pct"] == 100.0
    assert result["verdict"]["state"] == "insufficient_evidence"
    assert not any("有效价格信号覆盖" in reason for reason in result["verdict"]["reasons"])


def test_rotation_experiment_skips_known_unsupported_index_symbols():
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

    class EtfProxyProvider(ExperimentProvider):
        signal_calls = 0

        def supports_signal_kline(self, symbol):
            return not symbol.endswith(".SI")

        def get_signal_kline(self, symbol, period="daily", limit=480, as_of=None):
            self.signal_calls += 1
            raise AssertionError("known unsupported signal must not be requested")

    provider = EtfProxyProvider()
    result = RotationExperiment(provider, universe=universe, max_workers=2).run(
        benchmark="510300", rebalance_days=10, cost_bps=25
    )

    assert provider.signal_calls == 0
    assert result["data_quality"]["state"] == "complete"
    assert result["data_quality"]["signal_state"] == "fallback"
    assert result["data_quality"]["configured_signal_proxy_count"] == len(universe)
    assert result["signal_failures"] == []


def test_confirmation_policy_excludes_heat_and_can_hold_cash_without_signal():
    rankings = [
        {"rank": 1, "code": "100001", "total_score": 80, "overheated": True, "rotation_signal": "领先过热"},
        {"rank": 2, "code": "100002", "total_score": 75, "overheated": False, "rotation_signal": "新晋观察"},
        {"rank": 3, "code": "100003", "total_score": 70, "overheated": False, "rotation_signal": "弱势回避"},
    ]

    cool = RotationExperiment._select_confirmation_policy(rankings, None, "exclude_overheated")
    confirmed = RotationExperiment._select_confirmation_policy(rankings, None, "confirmed_only")

    assert cool["code"] == "100002"
    assert confirmed is None


def test_rotation_experiment_keeps_top_three_incumbent_when_lead_is_small():
    rankings = [
        {"rank": 1, "code": "100001", "total_score": 72.0},
        {"rank": 2, "code": "100002", "total_score": 68.0},
        {"rank": 3, "code": "100003", "total_score": 65.0},
        {"rank": 4, "code": "100004", "total_score": 60.0},
    ]

    selected = RotationExperiment._select_with_buffer(rankings, "100002")

    assert selected["code"] == "100002"


def test_rotation_experiment_marks_losing_training_candidate_as_diagnostic_only():
    qualification = RotationExperiment._training_qualification({
        "total_return_pct": -4.28,
        "excess_return_pct": -16.88,
    })

    assert qualification["state"] == "diagnostic_only"
    assert qualification["checks"]["positive_total_return"] is False
    assert qualification["checks"]["positive_excess_return"] is False
    assert qualification["checks"]["majority_positive_training_blocks"] is True


@pytest.mark.parametrize("held_symbol", ["100002", "100004"])
def test_rotation_experiment_switches_when_lead_is_clear_or_incumbent_falls_out(held_symbol):
    rankings = [
        {"rank": 1, "code": "100001", "total_score": 72.0},
        {"rank": 2, "code": "100002", "total_score": 67.0},
        {"rank": 3, "code": "100003", "total_score": 65.0},
        {"rank": 4, "code": "100004", "total_score": 69.0},
    ]

    selected = RotationExperiment._select_with_buffer(rankings, held_symbol)

    assert selected["code"] == "100001"


def test_rotation_experiment_stress_cost_only_applies_when_position_changes():
    base_trade = {
        "gross_return": 0.10,
        "net_return": 0.10,
        "benchmark_return": 0.0,
        "equal_weight_return": 0.0,
    }

    held = RotationExperiment._stress_metrics(
        [{**base_trade, "switched": False}],
        rebalance_days=10,
        cost_bps=25,
    )
    switched = RotationExperiment._stress_metrics(
        [{**base_trade, "switched": True}],
        rebalance_days=10,
        cost_bps=25,
    )

    assert held["total_return_pct"] == 10.0
    assert switched["total_return_pct"] == 9.5


def test_parameter_ensemble_separates_buffered_state_from_online_current_leader():
    def row(buffered_symbol, current_symbol, current_return):
        return {
            "signal_date": "2026-01-05",
            "entry_date": "2026-01-06",
            "exit_date": "2026-01-20",
            "symbol": buffered_symbol,
            "name": buffered_symbol,
            "industry": buffered_symbol,
            "signal_code": buffered_symbol,
            "signal_name": buffered_symbol,
            "signal_mode": "trade_asset",
            "score": 70.0,
            "gross_return": 0.01,
            "benchmark_return": 0.0,
            "equal_weight_return": 0.0,
            "current_leader_symbol": current_symbol,
            "current_leader_name": current_symbol,
            "current_leader_industry": current_symbol,
            "current_leader_signal_code": current_symbol,
            "current_leader_signal_name": current_symbol,
            "current_leader_signal_mode": "trade_asset",
            "current_leader_score": 80.0,
            "current_leader_gross_return": current_return,
        }

    trade_sets = {
        "v1": [row("A", "B", 0.10)],
        "v2": [row("A", "B", 0.10)],
        "v3": [row("C", "C", -0.02)],
    }
    buffered = RotationExperiment._parameter_ensemble_trades(
        trade_sets, cost_bps=25, vote_source="buffered_selection"
    )
    online = RotationExperiment._parameter_ensemble_trades(
        trade_sets, cost_bps=25, vote_source="current_leader"
    )

    assert buffered[0]["symbol"] == "A"
    assert online[0]["symbol"] == "B"
    assert online[0]["gross_return"] == 0.10
    assert online[0]["selection_model"].endswith("current_leader")


def test_prediction_interval_uses_actual_non_overlapping_signals():
    effects = [
        {
            "available": True,
            "entry_date": "2026-01-01",
            "exit_date": "2026-01-11",
            "rank_ic": 0.1,
            "top3_minus_bottom3": 0.01,
            "top3_beat_benchmark": True,
        },
        {
            "available": True,
            "entry_date": "2026-01-06",
            "exit_date": "2026-01-16",
            "rank_ic": -0.1,
            "top3_minus_bottom3": -0.01,
            "top3_beat_benchmark": False,
        },
        {
            "available": True,
            "entry_date": "2026-01-11",
            "exit_date": "2026-01-21",
            "rank_ic": 0.2,
            "top3_minus_bottom3": 0.02,
            "top3_beat_benchmark": True,
        },
    ]

    summary = RotationExperiment._effect_summary(effects, horizon=10)

    assert summary["samples"] == 3
    assert summary["effective_non_overlapping_samples"] == 2
    assert summary["non_overlapping_top3_beat_benchmark_rate_pct"] == 50.0
    assert summary["non_overlapping_top3_beat_benchmark_rate_range_pct"] == [0.0, 100.0]
    assert summary["wilson_sample_policy"] == (
        "all_non_overlapping_phase_cohorts_conservative_envelope"
    )


def test_rotation_experiment_reuses_factors_across_weight_profiles(monkeypatch):
    experiment = RotationExperiment(ExperimentProvider(size=360), universe=UNIVERSE, max_workers=2)
    benchmark_frame, trade_frames, signal_frames, _, _ = experiment._load_frames("510300", None)
    rebalance_days = 10
    cost_bps = 25
    expected = {}
    for window in experiment.windows:
        expected[window] = {
            profile: _reference_variant_trades(
                experiment,
                benchmark_frame=benchmark_frame,
                trade_frames=trade_frames,
                signal_frames=signal_frames,
                weights=weights,
                window=window,
                rebalance_days=rebalance_days,
                cost_bps=cost_bps,
            )
            for profile, weights in ROTATION_WEIGHT_PROFILES.items()
        }

    raw_metric_calls = 0
    original_raw_metrics = RotationEngine._raw_metrics

    def counting_raw_metrics(self, *args, **kwargs):
        nonlocal raw_metric_calls
        raw_metric_calls += 1
        return original_raw_metrics(self, *args, **kwargs)

    monkeypatch.setattr(RotationEngine, "_raw_metrics", counting_raw_metrics)
    actual = {}
    for window in experiment.windows:
        actual[window] = experiment._window_trade_sets(
            benchmark_frame=benchmark_frame,
            trade_frames=trade_frames,
            signal_frames=signal_frames,
            weight_profiles=ROTATION_WEIGHT_PROFILES,
            window=window,
            rebalance_days=rebalance_days,
            cost_bps=cost_bps,
        )

    assert actual == expected
    assert raw_metric_calls == sum(
        len(actual[window]["balanced"]) * len(UNIVERSE)
        for window in experiment.windows
    )


def test_rotation_experiment_historical_ranking_does_not_see_future_shock():
    base = RotationExperiment(ExperimentProvider(), universe=UNIVERSE, max_workers=2)
    shocked = RotationExperiment(
        ExperimentProvider(future_shock_at=480),
        universe=UNIVERSE,
        max_workers=2,
    )
    base_benchmark, base_trade_frames, base_signal_frames, _, _ = base._load_frames("510300", None)
    shocked_benchmark, shocked_trade_frames, shocked_signal_frames, _, _ = shocked._load_frames("510300", None)
    kwargs = {
        "weights": ROTATION_WEIGHT_PROFILES["balanced"],
        "window": 60,
        "rebalance_days": 10,
        "cost_bps": 25,
    }
    base_trades = base._variant_trades(
        benchmark_frame=base_benchmark,
        trade_frames=base_trade_frames,
        signal_frames=base_signal_frames,
        **kwargs,
    )
    shocked_trades = shocked._variant_trades(
        benchmark_frame=shocked_benchmark,
        trade_frames=shocked_trade_frames,
        signal_frames=shocked_signal_frames,
        **kwargs,
    )
    cutoff = base_benchmark["date"].iloc[470].strftime("%Y-%m-%d")
    before_base = [(row["signal_date"], row["symbol"]) for row in base_trades if row["exit_date"] < cutoff]
    before_shock = [(row["signal_date"], row["symbol"]) for row in shocked_trades if row["exit_date"] < cutoff]

    assert before_base
    assert before_base == before_shock
    assert all(row["signal_date"] < row["entry_date"] < row["exit_date"] for row in base_trades)

    base_confirmation = base._confirmation_trade_sets(
        benchmark_frame=base_benchmark,
        trade_frames=base_trade_frames,
        signal_frames=base_signal_frames,
        **kwargs,
    )
    shocked_confirmation = shocked._confirmation_trade_sets(
        benchmark_frame=shocked_benchmark,
        trade_frames=shocked_trade_frames,
        signal_frames=shocked_signal_frames,
        **kwargs,
    )
    for policy in ROTATION_CONFIRMATION_POLICIES:
        before_base = [
            (row["signal_date"], row["symbol"])
            for row in base_confirmation[policy]
            if row["exit_date"] < cutoff
        ]
        before_shock = [
            (row["signal_date"], row["symbol"])
            for row in shocked_confirmation[policy]
            if row["exit_date"] < cutoff
        ]
        assert before_base == before_shock


def test_rotation_experiment_rejects_history_too_short_for_oos():
    experiment = RotationExperiment(
        ExperimentProvider(size=220),
        universe=UNIVERSE,
        max_workers=2,
    )

    with pytest.raises(MarketDataError, match="不足 260 根"):
        experiment.run()
