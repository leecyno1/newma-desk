"""Daily close + execution open risk, without changing rotation selection or fees."""

from __future__ import annotations

import math

import pandas as pd

from instock.core.validation.execution import valid_execution_price


def _prices(frame):
    return {
        pd.Timestamp(row["date"]).strftime("%Y-%m-%d"): row
        for row in frame.to_dict("records")
    }


def _drawdowns(points):
    peak, peak_index, worst, peak_at_worst, trough = 1.0, 0, 0.0, None, None
    for index, point in enumerate(points):
        nav = point["nav"]
        point["drawdown_pct"] = None
        if nav is None:
            continue
        if nav > peak:
            peak, peak_index = nav, index
        drawdown = max(0.0, (1 - nav / peak) * 100)
        point["drawdown_pct"] = drawdown
        if drawdown > worst:
            worst, peak_at_worst, trough = drawdown, peak_index, index
    recovery = None
    if trough is not None:
        high_water = points[peak_at_worst]["nav"]
        recovery = next((point["date"] for point in points[trough + 1:]
                         if point["nav"] is not None and point["nav"] >= high_water), None)
    return {
        "max_drawdown_pct": worst if any(point["nav"] is not None for point in points) else None,
        "peak_date": points[peak_at_worst]["date"] if peak_at_worst is not None else None,
        "trough_date": points[trough]["date"] if trough is not None else None,
        "recovery_date": recovery,
        "current_drawdown_pct": points[-1]["drawdown_pct"] if points else None,
    }


def _mark_path(periods, records, frames, calendar):
    points, issues = [], []
    base = 1.0
    observed_periods = observed_closes = expected_closes = 0
    if periods:
        points.append({"date": periods[0][0], "phase": "initial", "nav": base})
    for entry, exit_date in periods:
        period_start = len(points)
        row = records.get((entry, exit_date))
        sessions = [date for date in calendar if entry <= date < exit_date]
        expected_closes += len(sessions)
        prices = frames.get(row["symbol"], {}) if row else {}
        cost_known = row is not None and row.get("transaction_cost") is not None
        cost = float(row["transaction_cost"]) if cost_known else 0.0
        if row is not None and (row.get("symbol") is None or not cost_known):
            issues.append({"date": entry, "reason": row.get("decision_issue", "unresolved_decision")})
            base = None
        entry_price = valid_execution_price(prices.get(entry, {}).get("open"))
        if row is None:
            issues.append({"date": entry, "reason": "missing_holding_period"})
        elif row.get("symbol") is not None and cost_known:
            observed_periods += 1
        if entry_price is None:
            issues.append({"date": entry, "reason": "missing_entry_open"})
            base = None

        def mark(date, phase, price):
            value = valid_execution_price(price)
            if value is None:
                issues.append({"date": date, "reason": "missing_" + phase})
            nav = base * (value / entry_price - cost) if value is not None and base is not None else None
            if nav is not None and (not math.isfinite(nav) or nav < 0):
                issues.append({"date": date, "reason": "invalid_equity"})
                nav = None
            points.append({"date": date, "phase": phase, "nav": nav})
            return nav

        mark(entry, "entry_open", entry_price)
        for date in sessions:
            close = prices.get(date, {}).get("close")
            if valid_execution_price(close) is not None:
                observed_closes += 1
            mark(date, "close", close)
        end_nav = mark(exit_date, "exit_open", prices.get(exit_date, {}).get("open"))
        # Keep the existing additive cost convention exactly; never quietly replace
        # an execution ledger with today's revised prices.
        if end_nav is not None and row.get("net_return") is not None:
            expected = base * (1 + float(row["net_return"]))
            if not math.isclose(end_nav, expected, rel_tol=1e-8, abs_tol=1e-10):
                issues.append({"date": exit_date, "reason": "execution_return_mismatch"})
                # Revised/inconsistent prices cannot establish a drawdown lower
                # bound for the recorded trade either. Discard that segment.
                for point in points[period_start:]:
                    point["nav"] = None
                end_nav = None
        base = end_nav
    risk = _drawdowns(points)
    complete = bool(periods) and not issues and all(point["nav"] is not None for point in points)
    summary = {
        "state": "complete" if complete else "incomplete" if periods else "unavailable",
        "start_date": periods[0][0] if periods else None,
        "end_date": periods[-1][1] if periods else None,
        **{key: value if complete else None for key, value in risk.items()},
        "observed_max_drawdown_pct": risk["max_drawdown_pct"],
        "ending_nav": points[-1]["nav"] if points else None,
        "coverage": {
            "expected_periods": len(periods), "observed_periods": observed_periods,
            "expected_closes": expected_closes, "observed_closes": observed_closes,
        },
        "issues": issues,
    }
    return points, summary


def daily_rotation_risk(trades, *, trade_frames, benchmark_frame, expected_periods, sessions):
    """Value the selected OOS ledger on its full scheduled holding calendar.

    Missing closes break the curve. A missing holding period or execution price
    makes all subsequent strategy NAV unknown, not a fictional cash interval.
    """
    periods = [(str(entry), str(exit_date)) for entry, exit_date in expected_periods]
    benchmark_prices = _prices(benchmark_frame)
    calendar = [pd.Timestamp(day).strftime("%Y-%m-%d") for day in sessions]
    records = {(row["entry_date"], row["exit_date"]): row for row in trades}
    strategy, summary = _mark_path(periods, records,
                                   {code: _prices(frame) for code, frame in trade_frames.items()}, calendar)
    benchmark_records = {
        period: {"symbol": "benchmark", "transaction_cost": 0,
                 "net_return": records.get(period, {}).get("benchmark_return")}
        for period in periods
    }
    benchmark, benchmark_summary = _mark_path(periods, benchmark_records, {"benchmark": benchmark_prices}, calendar)
    curve = [{"date": row["date"], "phase": row["phase"],
              "strategy": row["nav"], "benchmark": reference["nav"],
              "strategy_drawdown_pct": row["drawdown_pct"],
              "benchmark_drawdown_pct": reference["drawdown_pct"]}
             for row, reference in zip(strategy, benchmark)]
    return {
        "sampling": "daily_close_and_execution_open",
        "cost_policy": "fixed_period_start_notional_round_trip_cost_at_entry",
        "selection_policy": "diagnostic_only_selected_variant_unchanged",
        "strategy": summary, "benchmark": benchmark_summary, "curve": curve,
    }
