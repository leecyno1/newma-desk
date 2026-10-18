"""Same-session price checks for the previous limit-up cohort."""
from statistics import median

from .research import iso_date
from .service import finite_number

DAILY_FIELDS = "ts_code,trade_date,close,pct_chg,amount"
LIMIT_FIELDS = "ts_code,trade_date,up_limit,down_limit"
SOURCE = "Tushare daily（未复权；成交额千元） / stk_limit（人民币元）"


def indexed_rows(rows, day, codes, fields):
    indexed, conflicts = {}, set()
    for row in rows:
        code = row.get("ts_code")
        if code not in codes:
            continue
        if iso_date(row.get("trade_date")) != day:
            conflicts.add(code)
            continue
        if code in indexed and any(indexed[code].get(key) != row.get(key) for key in fields):
            conflicts.add(code)
        indexed[code] = row
    return indexed, conflicts


def verify_cohort(cohort, day, daily, limits):
    codes = {row["code"] for row in cohort}
    prices, bad_prices = indexed_rows(daily.get("rows", []) if daily["status"] == "ready" else [], day, codes, ("close", "pct_chg", "amount"))
    bounds, bad_bounds = indexed_rows(limits.get("rows", []) if limits["status"] == "ready" else [], day, codes, ("up_limit", "down_limit"))
    result = []
    for stock in cohort:
        code = stock["code"]
        row = {"code": code, "status": "unavailable", "reason": "", "close": None, "pct": None,
               "amountYi": None, "upLimit": None, "downLimit": None}
        price, bound = prices.get(code, {}), bounds.get(code, {})
        close, amount = finite_number(price.get("close")), finite_number(price.get("amount"))
        up, down = finite_number(bound.get("up_limit")), finite_number(bound.get("down_limit"))
        if code in bad_prices:
            row.update(status="conflict", reason="日线日期或重复记录冲突")
        elif daily["status"] != "ready":
            row["reason"] = "同日日线请求失败；不展示旧行情"
        elif not price or close is None or close <= 0 or amount is None or amount < 0:
            row["reason"] = "缺少同日有效行情；不据此判为停牌"
        elif amount == 0:
            row.update(status="no_trade", reason="来源成交额为零；交易状态待核实")
        else:
            row.update(close=close, pct=finite_number(price.get("pct_chg")), amountYi=amount / 100000,
                       status="traded", reason="有同日成交；缺有效涨跌停价，不能核实封板")
            if code in bad_bounds:
                row.update(status="conflict", reason="涨跌停价日期或重复记录冲突")
            elif up is not None and down is not None and 0 < down < up:
                row.update(upLimit=up, downLimit=down)
                at_up, at_down = abs(close - up) < 1e-6, abs(close - down) < 1e-6
                kind = stock["outcome"]
                if close > up + 1e-6 or close < down - 1e-6:
                    row.update(status="conflict", reason="收盘价超出同日涨跌停价格范围")
                elif (kind == "U" and not at_up) or (kind == "D" and not at_down) or (kind in {"absent", "Z"} and at_up) or (kind == "absent" and at_down):
                    row.update(status="conflict", reason="同日收盘价格与三池分类不一致")
                else:
                    row.update(status="at_limit" if at_up else "below_limit", reason="")
        result.append(row)
    usable = [row for row in result if row["status"] in {"at_limit", "below_limit", "traded"}]
    returns = [row["pct"] for row in usable if row["pct"] is not None]
    return {"asOf": day, "source": SOURCE, "dailyStatus": daily["status"], "limitsStatus": limits["status"],
            "rows": result, "summary": {"total": len(result), "priced": len(usable), "returnCount": len(returns),
                "medianPct": median(returns) if returns else None,
                "belowLimit": sum(row["status"] == "below_limit" for row in result),
                "atLimit": sum(row["status"] == "at_limit" for row in result),
                "conflicts": sum(row["status"] == "conflict" for row in result),
                "unresolved": sum(row["status"] in {"unavailable", "no_trade", "traded"} for row in result)},
            "note": "只核对同日未复权收盘价与来源涨跌停价，不按10%/20%阈值推断。未封涨停不等于下跌；缺行情不等于停牌。未核验历史ST变动，不能解释样本进出。涨跌幅中位数仅基于有可用涨跌幅且无冲突的样本，不是可实现的策略收益。"}
