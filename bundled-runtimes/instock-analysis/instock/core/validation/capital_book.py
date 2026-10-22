"""Finite, independently funded sleeves on an exchange-session event clock."""

from collections import defaultdict
import math

import numpy as np
import pandas as pd

from instock.core.validation.execution import audit_open_bar, valid_execution_price
from instock.core.validation.metrics import round_metric


def simulate_sleeves(rows, frames, benchmark_frame, sessions, *, slots, cost_bps, execution_limits=None):
    """A signal reserves one sleeve; missing future prices never select a replacement.

    Each sleeve starts with 1/N capital, reinvests only its own proceeds, and may
    trade fractional units. Exit first, then enter in original signal order.
    Missing executions poison that sleeve's capital; missing marks only break
    the valuation path. Neither is treated as cash or a zero return.
    """
    prices = {code: {pd.Timestamp(row["date"]): row for row in frame.to_dict("records")}
              for code, frame in frames.items()}
    benchmark_prices = {pd.Timestamp(row["date"]): row for row in benchmark_frame.to_dict("records")}
    execution_limits = execution_limits or {}

    def quote(code, date, phase):
        return valid_execution_price(prices.get(code, {}).get(date, {}).get(phase))

    scheduled = defaultdict(list)
    ledger = []
    for row in rows:
        item = {"decision_date": row["decision_date"], "symbols": list(row["symbols"]),
                "entry_date": row["entry_date"], "exit_date": row["exit_date"],
                "state": "pending_entry", "slot": None, "entry_budget": None,
                "exit_proceeds": None, "cost": None, "issues": [], "execution_issues": []}
        ledger.append(item)
        if row["entry_index"] is not None:
            scheduled[row["entry_index"]].append((row, item))
    sleeves = [{"cash": 1 / slots, "position": None} for _ in range(slots)]
    curve, issues = [], []
    first = min(scheduled, default=None)
    last = max((row["exit_index"] if row["exit_index"] is not None else len(sessions) - 1
                for row in rows if row["entry_index"] is not None), default=None)
    fee_rate = cost_bps / 10000
    benchmark_entry = (valid_execution_price(benchmark_prices.get(sessions[first], {}).get("open"))
                       if first is not None else None)
    costs, cost_complete = 0.0, True
    max_active = 0

    def mark(date, phase, price_field):
        values, cash_values = [], []
        for sleeve in sleeves:
            pos = sleeve["position"]
            if pos is None:
                values.append(sleeve["cash"])
                cash_values.append(sleeve["cash"])
            else:
                marks = [quote(code, date, price_field) for code in pos["symbols"]]
                value = (sum(unit * price for unit, price in zip(pos["units"], marks))
                         if pos["units"] is not None and all(price is not None for price in marks) else None)
                values.append(value)
                cash_values.append(sleeve["cash"])
                for code, price in zip(pos["symbols"], marks):
                    if price is None:
                        issues.append({"date": date.strftime("%Y-%m-%d"), "symbol": code,
                                       "reason": f"missing_{price_field}_mark"})
        nav = sum(values) if all(value is not None for value in values) else None
        cash = sum(cash_values) if all(value is not None for value in cash_values) else None
        benchmark_price = valid_execution_price(benchmark_prices.get(date, {}).get(price_field))
        benchmark_nav = benchmark_price / benchmark_entry if benchmark_price is not None and benchmark_entry is not None else None
        curve.append({"date": date.strftime("%Y-%m-%d"), "phase": phase, "nav": nav,
                      "cash": cash, "benchmark_nav": benchmark_nav,
                      "active_sleeves": sum(sleeve["position"] is not None for sleeve in sleeves)})

    if first is not None:
        curve.append({"date": sessions[first].strftime("%Y-%m-%d"), "phase": "initial",
                      "nav": 1.0, "cash": 1.0, "benchmark_nav": 1.0 if benchmark_entry is not None else None,
                      "active_sleeves": 0})
        for index in range(first, last + 1):
            date = sessions[index]
            mark(date, "open_before_trades", "open")
            for sleeve in sleeves:
                pos = sleeve["position"]
                if pos is None or pos["exit_index"] != index:
                    continue
                item = pos["ledger"]
                evidence = [audit_open_bar(prices.get(code, {}).get(date, {}),
                            limit=execution_limits.get(code, {}).get(date), side="sell") for code in pos["symbols"]]
                exits = [bar["price"] for bar in evidence]
                item["execution_issues"].extend(
                    {"symbol": code, "date": date.strftime("%Y-%m-%d"), "side": "sell", "reason": bar["reason"]}
                    for code, bar in zip(pos["symbols"], evidence) if bar["reason"])
                gross = (sum(unit * price for unit, price in zip(pos["units"], exits))
                         if pos["units"] is not None and all(price is not None for price in exits) else None)
                sleeve["cash"] = gross * (1 - fee_rate) if gross is not None else None
                sleeve["position"] = None
                item["exit_proceeds"] = sleeve["cash"]
                if gross is None:
                    item["state"] = "unresolved"
                    item["cost"] = None
                    cost_complete = False
                    item["issues"].append("missing_exit_or_unknown_units")
                else:
                    exit_cost = gross * fee_rate
                    costs += exit_cost
                    item["cost"] += exit_cost
                    item["state"] = "closed"
            for row, item in scheduled[index]:
                free = next((i for i, sleeve in enumerate(sleeves) if sleeve["position"] is None), None)
                if free is None:
                    item["state"] = "skipped_capacity"
                    continue
                sleeve = sleeves[free]
                budget = sleeve["cash"]
                item.update(slot=free + 1, entry_budget=budget)
                evidence = [audit_open_bar(prices.get(code, {}).get(date, {}),
                            limit=execution_limits.get(code, {}).get(date), side="buy") for code in row["symbols"]]
                entries = [bar["price"] for bar in evidence]
                item["execution_issues"].extend(
                    {"symbol": code, "date": date.strftime("%Y-%m-%d"), "side": "buy", "reason": bar["reason"]}
                    for code, bar in zip(row["symbols"], evidence) if bar["reason"])
                units = None
                if budget is not None and all(price is not None for price in entries):
                    notional = budget / (1 + fee_rate)
                    units = [notional / len(entries) / price for price in entries]
                    item["cost"] = budget - notional
                    costs += item["cost"]
                    item["state"] = "open"
                else:
                    item["state"] = "unresolved"
                    item["issues"].append("missing_entry_open" if any(bar["reason"] == "missing_open" for bar in evidence)
                                          else "unverified_entry_volume" if any(bar["reason"] in {"missing_volume", "zero_volume"} for bar in evidence)
                                          else "unverified_entry_limit" if any(bar["reason"] for bar in evidence)
                                          else "unknown_sleeve_capital")
                    cost_complete = False
                # Unknown entry evidence is not proof that the cash was spent.
                sleeve["cash"] = 0.0 if units is not None else None
                sleeve["position"] = {"symbols": row["symbols"], "units": units,
                                      "exit_index": row["exit_index"], "ledger": item}
            max_active = max(max_active, sum(sleeve["position"] is not None for sleeve in sleeves))
            mark(date, "open_after_trades", "open")
            mark(date, "close", "close")

    complete = bool(curve) and all(row["nav"] is not None for row in curve)
    benchmark_complete = bool(curve) and all(row["benchmark_nav"] is not None for row in curve)
    observed_peak, observed_dd = None, 0.0
    for row in curve:
        nav = row["nav"]
        if nav is None:
            observed_peak = None
            row["drawdown_pct"] = None
        else:
            observed_peak = max(observed_peak if observed_peak is not None else nav, nav)
            row["drawdown_pct"] = (1 - nav / observed_peak) * 100
            observed_dd = max(observed_dd, row["drawdown_pct"])
    end = curve[-1] if curve else {}
    total = (end["nav"] - 1) * 100 if end.get("nav") is not None else None
    benchmark_return = ((end["benchmark_nav"] - 1) * 100
                        if end.get("benchmark_nav") is not None else None)
    closes = [row for row in curve if row["phase"] == "close"]
    # Close-to-close returns exclude the partial first trading day; no gap bridge.
    daily = np.array([right["nav"] / left["nav"] - 1 for left, right in zip(closes, closes[1:])]) if complete else np.array([])
    volatility = float(daily.std(ddof=0)) if len(daily) >= 2 else None
    sharpe = float(daily.mean() / volatility * math.sqrt(252)) if volatility is not None and volatility > 1e-12 else None
    active = (daily - np.array([right["benchmark_nav"] / left["benchmark_nav"] - 1
                               for left, right in zip(closes, closes[1:])])) if complete and benchmark_complete else np.array([])
    active_volatility = float(active.std(ddof=0)) if len(active) >= 2 else None
    information_ratio = float(active.mean() / active_volatility * math.sqrt(252)) if active_volatility is not None and active_volatility > 1e-12 else None
    return {
        "state": "complete" if complete else "incomplete" if curve else "unavailable",
        "benchmark_state": "complete" if benchmark_complete else "incomplete" if curve else "unavailable",
        "start_date": curve[0]["date"] if curve else None,
        "end_date": end.get("date"), "initial_nav": 1.0,
        "ending_nav": end.get("nav"), "ending_cash": end.get("cash"),
        "total_return_pct": round_metric(total) if total is not None else None,
        "benchmark_return_pct": round_metric(benchmark_return) if benchmark_return is not None else None,
        "excess_return_pct": round_metric(total - benchmark_return) if total is not None and benchmark_return is not None else None,
        "max_drawdown_pct": round_metric(observed_dd) if complete else None,
        "observed_drawdown_lower_bound_pct": round_metric(observed_dd) if curve else None,
        "annualized_volatility_pct": round_metric(volatility * math.sqrt(252) * 100) if volatility is not None else None,
        "sharpe": round_metric(sharpe) if sharpe is not None else None,
        "information_ratio": round_metric(information_ratio) if information_ratio is not None else None,
        "daily_return_observations": len(daily),
        "planned_signals": len(rows), "allocated_signals": sum(item["slot"] is not None for item in ledger),
        "skipped_signals": sum(item["state"] == "skipped_capacity" for item in ledger),
        "pending_signals": sum(item["state"] == "pending_entry" for item in ledger),
        "unresolved_signals": sum(item["state"] == "unresolved" for item in ledger),
        "open_sleeves": sum(sleeve["position"] is not None for sleeve in sleeves),
        "max_active_sleeves": max_active,
        "cost_pct_initial_capital": round_metric(costs * 100) if cost_complete and curve else None,
        "coverage": {"observed_marks": sum(row["nav"] is not None for row in curve if row["phase"] != "initial"),
                     "expected_marks": max(0, len(curve) - 1)},
        "ledger": ledger, "curve": curve, "issues": issues,
    }
