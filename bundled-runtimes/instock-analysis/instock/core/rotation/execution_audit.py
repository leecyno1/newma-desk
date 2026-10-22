"""Audit frozen continuous rotation plans, never select using future fills."""

import pandas as pd

from instock.core.market_data_provider import MarketDataError
from instock.core.validation.execution import audit_open_bar


def execution_summary(rows):
    checks = [check for row in rows for check in row.get("execution_checks", [])]
    states = [row.get("execution_evidence_state", "legacy") for row in rows]
    state = ("unavailable" if not rows else "unresolved" if "unresolved" in states
             else "theoretical" if "theoretical" in states else "legacy" if "legacy" in states else "checked")
    return {"state": state, "planned_legs": len(checks),
            "price_volume_verified_legs": sum(check["bar_verified"] for check in checks),
            "paired_limit_legs": sum(check["state"] != "unverified" for check in checks),
            "adverse_limit_legs": sum(check["state"] == "adverse" for check in checks),
            "missing_limit_legs": sum(check["state"] == "unverified" for check in checks),
            "unresolved_periods": states.count("unresolved"),
            "theoretical_periods": states.count("theoretical"), "fill_guaranteed": False}


class RotationExecutionAudit:
    def __init__(self, provider, frames, start, end):
        self.provider, self.start, self.end = provider, start, end
        self.bars = {code: {pd.Timestamp(row["date"]).strftime("%Y-%m-%d"): row
                           for row in frame.to_dict("records")} for code, frame in frames.items()}
        self.feeds, self.limits = {}, {}

    def _load(self, symbol):
        if symbol in self.feeds:
            return
        try:
            loader = getattr(self.provider, "get_execution_prices", None)
            feed = loader(symbol, self.start, self.end) if loader else {
                "status": "unavailable", "reason": "当前数据源尚未接入历史限价"}
        except MarketDataError:
            feed = {"status": "unavailable", "reason": "历史限价请求失败，未用复权行情替代"}
        self.limits[symbol] = ({row["date"]: row for row in feed.get("rows", [])}
                               if feed.get("status") in {"ready", "partial"} else {})
        self.feeds[symbol] = {"symbol": symbol, **{key: feed.get(key) for key in ("status", "reason", "feeds")}}

    def apply(self, rows):
        """Initial buy; switches sell old + buy new; holds/final marks are not fills.

        Failed execution poisons all subsequent capital, even when the frozen
        desired portfolio later converges. No replacement or cash imputation.
        Missing limits leave explicitly theoretical returns, never certification.
        Each ensemble must be audited from its own original, unaudited plan.
        """
        output, previous, broken, theoretical = [], "CASH", False, False
        for source in rows:
            row = dict(source)
            symbol, day = row.get("symbol"), row["entry_date"]
            checks = []
            if symbol is None or row.get("switched") is None:
                broken = True
            elif symbol != previous:
                for code, side in ((previous, "sell"), (symbol, "buy")):
                    if code in {None, "CASH"}:
                        continue
                    self._load(code)
                    evidence = audit_open_bar(self.bars.get(code, {}).get(day, {}),
                        limit=self.limits[code].get(day), side=side)
                    checks.append({"symbol": code, "date": day, "side": side,
                        **evidence["limit_check"], "bar_verified": evidence["reason"] not in {
                            "missing_open", "missing_volume", "zero_volume"},
                        "execution_issue": evidence["reason"]})
            issue = next((check["execution_issue"] for check in checks if check["execution_issue"]), None)
            broken = broken or bool(issue)
            theoretical = theoretical or any(check["state"] == "unverified" for check in checks)
            row["execution_checks"] = checks
            row["execution_evidence_state"] = "unresolved" if broken else "theoretical" if theoretical else "checked"
            if broken:
                row.update(gross_return=None, net_return=None, transaction_cost=None)
                row["decision_issue"] = issue or row.get("decision_issue") or "prior_execution_unresolved"
            output.append(row)
            previous = symbol
        return output
