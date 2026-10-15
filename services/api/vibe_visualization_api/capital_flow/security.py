from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx

from vibe_visualization_api.capital_flow.research import CapitalResearchService, baseline, window_sum
from vibe_visualization_api.capital_flow.sectors import sector_summary
from vibe_visualization_api.capital_flow.service import finite_number


DC_FIELDS = "ts_code,trade_date,name,net_amount,net_amount_rate,buy_elg_amount,buy_lg_amount"
ORDER_FIELDS = "ts_code,trade_date,buy_lg_amount,sell_lg_amount,buy_elg_amount,sell_elg_amount"


def yi(row, field, divisor):
    value = finite_number(row.get(field))
    return value / divisor if value is not None else None


def security_analysis(flows, daily, factors, margins, sessions, *, source="moneyflow_dc") -> dict:
    indexes = [{row["date"]: row for row in rows} for rows in (flows, daily, factors, margins)]
    points = []
    for index, day in enumerate(sessions):
        flow, price, factor, margin = [rows.get(day, {}) for rows in indexes]
        def difference(buy, sell):
            values = [yi(flow, field, 10000) for field in (buy, sell)]
            return values[0] - values[1] if all(value is not None for value in values) else None
        large = yi(flow, "buy_lg_amount", 10000) if source == "moneyflow_dc" else difference("buy_lg_amount", "sell_lg_amount")
        extra = yi(flow, "buy_elg_amount", 10000) if source == "moneyflow_dc" else difference("buy_elg_amount", "sell_elg_amount")
        net = yi(flow, "net_amount", 10000) if source == "moneyflow_dc" else large + extra if large is not None and extra is not None else None
        amount, close, adj = yi(price, "amount", 100000), finite_number(price.get("close")), finite_number(factor.get("adj_factor"))
        adjusted = close * adj if close is not None and close > 0 and adj is not None and adj > 0 else None
        previous = points[-1] if index else {}
        old_adjusted = previous.get("adjustedValue")
        balance, buy, repay = [yi(margin, field, 1e8) for field in ("rzye", "rzmre", "rzche")]
        margin_net = buy - repay if buy is not None and repay is not None else None
        balance_change = balance - previous["balanceYi"] if balance is not None and previous.get("balanceYi") is not None else None
        residual = (balance_change - margin_net) * 1e8 if balance_change is not None and margin_net is not None else None
        points.append({"date": day, "net": net, "largeYi": large, "extraYi": extra,
            "amountYi": amount, "netSharePct": net / amount * 100 if net is not None and amount and amount > 0 else None,
            "sourceSharePct": finite_number(flow.get("net_amount_rate")) if source == "moneyflow_dc" else None,
            "close": close, "adjFactor": adj, "adjustedValue": adjusted,
            "adjustedPct": (adjusted / old_adjusted - 1) * 100 if adjusted is not None and old_adjusted else None,
            "factorChanged": bool(adj and previous.get("adjFactor") and adj != previous["adjFactor"]),
            "balanceYi": balance, "marginBuyYi": buy, "marginRepayYi": repay, "marginNetYi": margin_net,
            "balanceChangeYi": balance_change, "marginResidualYuan": round(residual, 2) if residual is not None else None})

    # Reuse the established strict-session windows and streak, not a second scoring system.
    order = sector_summary([{**point, "pct": None} for point in points], sessions)
    order.pop("price5dPct"); order.pop("price20dPct")
    def price_change(days):
        window = points[-days - 1:]
        return round((window[-1]["adjustedValue"] / window[0]["adjustedValue"] - 1) * 100, 4) if len(window) == days + 1 and all(point["adjustedValue"] is not None for point in window) else None
    def share(field, days):
        numerator = window_sum(points, sessions, field, days)
        denominator = window_sum(points, sessions, "amountYi", days)
        return round(numerator / denominator * 100, 4) if numerator is not None and denominator and denominator > 0 else None
    for days in (1, 5, 20):
        order[f"share{days}dPct"] = share("net", days)
    leverage = {f"net{days}dYi": window_sum(points, sessions, "marginNetYi", days) for days in (1, 5, 20)}
    for days in (5, 20):
        window = points[-days - 1:]
        leverage[f"balanceChange{days}dYi"] = round(window[-1]["balanceYi"] - window[0]["balanceYi"], 4) if len(window) == days + 1 and all(point["balanceYi"] is not None for point in window) else None
    leverage.update(baseline=baseline(points, sessions, "balanceYi"), buyShare5dPct=share("marginBuyYi", 5),
        reconciliationChecked=sum(point["marginResidualYuan"] is not None for point in points[-20:]),
        reconciliationConflicts=sum(abs(point["marginResidualYuan"]) > 1 for point in points[-20:] if point["marginResidualYuan"] is not None))
    return {"points": points, "order": order, "leverage": leverage,
            "price": {"change5dPct": price_change(5), "change20dPct": price_change(20),
                      "method": "close × adj_factor 比值，处理除权；不是含税费的策略回报",
                      "factorChanges20d": sum(point["factorChanged"] for point in points[-20:])}}


def observations(analysis, feeds, calendar_ready):
    ready = {key: row["status"] == "ready" and not row["usingSaved"] for key, row in feeds.items()}
    results = []
    net, change = analysis["order"]["net5dYi"], analysis["price"]["change5dPct"]
    if calendar_ready and all(ready[key] for key in ("orders", "daily", "factors")) and net is not None and change is not None:
        label = "上涨伴随大额订单净卖出" if change > 0 and net < 0 else "下跌伴随大额订单净买入" if change < 0 and net > 0 else "资金与价格方向一致" if net * change > 0 else "资金或价格方向持平"
        results.append({"id": "order-price", "title": label, "detail": f"同一5交易日：大额订单净额 {net:.4f} 亿元，复权价格变化 {change:+.2f}%；只作观察，不证明吸筹或出货。"})
    else:
        results.append({"id": "order-price", "title": "资金价格对照待核验", "detail": "订单、行情、复权因子或交易日历不齐备/更新失败，不给出背离判断。"})
    leverage = analysis["leverage"]
    if calendar_ready and all(ready[key] for key in ("margin", "daily", "factors")) and change is not None and leverage["balanceChange5dYi"] is not None:
        title = "下跌期间融资余额增加" if change < 0 and leverage["balanceChange5dYi"] > 0 else "融资与价格分开观察"
        results.append({"id": "leverage-price", "title": title, "detail": f"5日融资余额变化 {leverage['balanceChange5dYi']:+.4f} 亿元；融资增加不是上涨预测，余额需与买入、偿还勾稽。"})
    if leverage["reconciliationConflicts"]:
        results.append({"id": "margin-conflict", "title": "融资余额存在勾稽差异", "detail": f"最近20日中 {leverage['reconciliationConflicts']} 日余额变化与买入减偿还相差超过1元，核对交易所原始数据及调整。"})
    return results


class SecurityResearchService(CapitalResearchService):
    async def research(self, code, *, refresh=False):
        suffix = "SH" if code.startswith("6") else "BJ" if code.startswith(("4", "8", "92")) else "SZ"
        symbol = f"{code}.{suffix}"
        client = self.client or httpx.AsyncClient(timeout=18, trust_env=False)
        try:
            calendar, flow, daily, factors, margin = await asyncio.gather(
                self._dataset(client, "trade_cal", "SSE", {"exchange": "SSE", "is_open": "1"}, "cal_date,is_open", "cal_date", refresh=refresh),
                self._dataset(client, "moneyflow_dc", symbol, {"ts_code": symbol}, DC_FIELDS, refresh=refresh),
                # Capacity research requests fewer daily fields; independent cache prevents mutual overwrite.
                self._dataset(client, "daily", symbol, {"ts_code": symbol}, "ts_code,trade_date,close,vol,amount", refresh=refresh, cache_key="daily:security"),
                self._dataset(client, "adj_factor", symbol, {"ts_code": symbol}, "ts_code,trade_date,adj_factor", refresh=refresh),
                self._dataset(client, "margin_detail", symbol, {"ts_code": symbol}, "ts_code,trade_date,rzye,rzmre,rzche,rqye,rzrqye", refresh=refresh),
            )
            source, fallback_reason = "moneyflow_dc", ""
            if flow["status"] != "ready" and not flow["rows"]:
                fallback_reason = flow["reason"] or "东财接口成功但未返回记录"
                flow = await self._dataset(client, "moneyflow", symbol, {"ts_code": symbol}, ORDER_FIELDS, refresh=refresh)
                source = "moneyflow"
            sessions = sorted({row["date"] for row in calendar["rows"] if str(row.get("is_open")) == "1"})
            feeds = {"orders": flow, "daily": daily, "factors": factors, "margin": margin}
            rows = [[row for row in feed["rows"] if row.get("ts_code") == symbol] for feed in feeds.values()]
            result = security_analysis(*rows, sessions, source=source)
            feeds = {key: {"api": source if key == "orders" else {"daily": "daily", "factors": "adj_factor", "margin": "margin_detail"}[key],
                          **{field: feed[field] for field in ("status", "reason", "usingSaved", "receivedAt")},
                          "asOf": max((row["date"] for row in rows[index]), default=None), "count": len(rows[index])}
                     for index, (key, feed) in enumerate(feeds.items())}
            expected = sessions[-1] if sessions else None
            return {"schemaVersion": "newma-desk.security-research.v1", "code": code, "symbol": symbol,
                    "generatedAt": datetime.now(timezone.utc).isoformat(), "expectedDate": expected, "currency": "CNY", "unit": "亿元",
                    "source": f"Tushare {source}", "fallbackReason": fallback_reason,
                    "calendar": {"status": calendar["status"], "reason": calendar["reason"], "dates": sessions},
                    "feeds": feeds, **result, "observations": observations(result, feeds, calendar["status"] == "ready" and not calendar["usingSaved"]),
                    "notes": ["东财个股资金万元÷10000，注意不同于板块资金的元口径；大额订单不是机构账户",
                              "备用 moneyflow 使用大单及特大单买卖差，不使用 net_mf_amount；不同供应商历史不拼接",
                              "daily 成交额千元÷100000；资金净额/同期成交额为相对强度，不是机构持仓占比",
                              "固定交易日1/5/20窗口；停牌或数据缺失不补零、不跨日补复权因子",
                              "融资金额元÷1亿；融资余额变化与买入减偿还逐日勾稽；空结果不能证明不属于两融标的",
                              "前60日分位只是历史位置；龙虎榜是事件披露，含单日/多日口径，不与其他资金相加"]}
        finally:
            if self.client is None:
                await client.aclose()
