"""使用真实公开持仓、行情、估值和财务数据计算 Barra 风格描述子。

这里不计算因子收益、协方差矩阵或特异风险，因此不是完整 Barra 风险模型。
"""
import math
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd

from lib.holding_weight_validation import (
    INVALID_WEIGHT_SCALE,
    MIN_STYLE_COVERAGE,
    fund_nav_weight,
    validate_fund_nav_weights,
)


FACTOR_META = {
    "SIZE": {"label": "规模", "unit": "cny_100m", "field": "market_cap_cny_100m"},
    "BTOP": {"label": "价值（账面市值比）", "unit": "multiple", "field": "book_to_price"},
    "BETA": {"label": "市场 Beta", "unit": "multiple", "field": "beta"},
    "MOMENTUM": {"label": "12-1 个月动量", "unit": "ratio", "field": "momentum_12_1"},
    "RESVOL": {"label": "残差波动率", "unit": "ratio", "field": "residual_volatility"},
    "LIQUIDITY": {"label": "平均换手率", "unit": "ratio", "field": "turnover_rate"},
    "LEVERAGE": {"label": "资产负债率", "unit": "ratio", "field": "debt_to_assets"},
    "GROWTH": {"label": "季度收入/利润增长", "unit": "ratio", "field": "growth"},
}
class HoldingStyleFactorService:
    """计算公开持仓加权的风格描述子。"""

    _stock_cache: Dict[tuple[str, str], Dict[str, Optional[float]]] = {}
    _market_return_cache: Dict[str, pd.Series] = {}

    def __init__(self, data_service: Any, market_benchmark: str = "000300.SH"):
        self.data_service = data_service
        self.market_benchmark = market_benchmark

    def analyze(self, holdings: List[Dict[str, Any]], quarter: str) -> Dict[str, Any]:
        weight_validation = validate_fund_nav_weights(holdings)
        if weight_validation.status == INVALID_WEIGHT_SCALE:
            return {
                "status": "insufficient_evidence",
                "source": "invalid_weight_scale_gate",
                "quarter": quarter,
                "descriptors": [],
                "holdings_count": len(holdings),
                "holdings_disclosed_weight": 0.0,
                "weight_validation": weight_validation.as_dict(),
                "missing_items": ["持仓基金净值权重超出 0-100% 或合计超过 100%，已阻止进入风格描述子计算。"],
            }
        period_end = self._quarter_end(quarter)
        weighted_holdings = []
        total_disclosed_weight = 0.0
        for holding in holdings:
            weight = self._fund_nav_weight(holding)
            code = str(holding.get("stock_code") or "").strip().upper()
            if weight is None or weight <= 0:
                continue
            total_disclosed_weight += weight
            if not self._supported_stock_code(code):
                continue
            weighted_holdings.append({"stock_code": code, "weight": weight})

        disclosed_weight = sum(item["weight"] for item in weighted_holdings)
        excluded_weight = max(0.0, total_disclosed_weight - disclosed_weight)
        if not weighted_holdings or disclosed_weight <= 0:
            return {
                "status": "insufficient_evidence",
                "source": "evidence_gate",
                "quarter": quarter,
                "descriptors": [],
                "holdings_count": 0,
                "holdings_disclosed_weight": round(total_disclosed_weight, 6),
                "model_eligible_weight": 0.0,
                "cross_market_excluded_weight": round(total_disclosed_weight, 6),
                "weight_validation": weight_validation.as_dict(),
                "missing_items": [
                    (
                        f"公开持仓合计覆盖基金净值的 {total_disclosed_weight:.1%}，"
                        "但当前 Barra 描述子模型没有可计算的 A 股持仓；港股等跨市场持仓尚未纳入。"
                    )
                    if total_disclosed_weight > 0
                    else "缺少以基金净值为分母的 A 股持仓权重。"
                ],
            }
        if disclosed_weight < MIN_STYLE_COVERAGE:
            if excluded_weight > 0:
                coverage_message = (
                    f"公开持仓合计覆盖基金净值的 {total_disclosed_weight:.1%}，"
                    f"其中当前模型可计算的 A 股持仓为 {disclosed_weight:.1%}；"
                    f"港股等跨市场持仓 {excluded_weight:.1%} 尚未纳入 A 股 Barra 描述子。"
                )
            else:
                coverage_message = f"公开持仓仅覆盖基金净值的 {disclosed_weight:.1%}。"
            return {
                "status": "insufficient_evidence",
                "source": "fund_portfolio_disclosure_gate",
                "quarter": quarter,
                "descriptors": [],
                "holdings_count": len(weighted_holdings),
                "holdings_disclosed_weight": round(total_disclosed_weight, 6),
                "model_eligible_weight": round(disclosed_weight, 6),
                "cross_market_excluded_weight": round(excluded_weight, 6),
                "weight_validation": weight_validation.as_dict(),
                "missing_items": [
                    coverage_message
                    + " "
                    f"低于 {MIN_STYLE_COVERAGE:.0%} 最低门槛，不输出基金整体风格画像。"
                ],
            }

        stock_codes = [item["stock_code"] for item in weighted_holdings]
        descriptors = self._load_stock_descriptors(stock_codes, period_end)
        factors = []
        missing_items = []
        if excluded_weight > 0:
            missing_items.append(
                f"公开持仓合计覆盖基金净值的 {total_disclosed_weight:.1%}；"
                f"港股等跨市场持仓 {excluded_weight:.1%} 未纳入当前 A 股 Barra 描述子。"
            )
        for factor, meta in FACTOR_META.items():
            field = meta["field"]
            covered = [
                (item["weight"], descriptors.get(item["stock_code"], {}).get(field))
                for item in weighted_holdings
            ]
            covered = [(weight, value) for weight, value in covered if self._number(value) is not None]
            covered_weight = sum(weight for weight, _ in covered)
            if covered_weight <= 0:
                missing_items.append(f"{meta['label']}描述子数据缺失")
                continue
            exposure = sum(weight * float(value) for weight, value in covered) / covered_weight
            factors.append({
                "factor": factor,
                "label": meta["label"],
                "exposure": round(exposure, 6),
                "unit": meta["unit"],
                "descriptor_coverage": round(covered_weight / disclosed_weight, 6),
                "fund_nav_coverage": round(covered_weight, 6),
            })
            if covered_weight / disclosed_weight < 0.8:
                missing_items.append(f"{meta['label']}描述子仅覆盖已披露持仓的 {covered_weight / disclosed_weight:.1%}")

        if not factors:
            return {
                "status": "insufficient_evidence",
                "source": "tushare.real_inputs",
                "quarter": quarter,
                "descriptors": [],
                "holdings_count": len(weighted_holdings),
                "holdings_disclosed_weight": round(total_disclosed_weight, 6),
                "model_eligible_weight": round(disclosed_weight, 6),
                "cross_market_excluded_weight": round(excluded_weight, 6),
                "weight_validation": weight_validation.as_dict(),
                "missing_items": missing_items or ["持仓股票行情、估值和财务数据不足。"],
            }

        missing_items.insert(0, "未接入因子收益、因子协方差矩阵和特异风险，当前是公开持仓风格描述子，不是完整 Barra 风险模型。")
        return {
            "status": "partial_evidence",
            "source": "tushare.fund_portfolio+daily+adj_factor+daily_basic+fina_indicator",
            "quarter": quarter,
            "market_benchmark": self.market_benchmark,
            "as_of_date": period_end,
            "descriptors": factors,
            "holdings_count": len(weighted_holdings),
            "holdings_disclosed_weight": round(total_disclosed_weight, 6),
            "model_eligible_weight": round(disclosed_weight, 6),
            "cross_market_excluded_weight": round(excluded_weight, 6),
            "weight_validation": weight_validation.as_dict(),
            "missing_items": list(dict.fromkeys(missing_items)),
        }

    def _load_stock_descriptors(self, stock_codes: List[str], period_end: str) -> Dict[str, Dict[str, Optional[float]]]:
        result = {
            code: self._stock_cache[(code, period_end)]
            for code in stock_codes
            if (code, period_end) in self._stock_cache
        }
        missing_codes = [code for code in stock_codes if code not in result]
        if not missing_codes:
            return result

        start_date = (datetime.strptime(period_end, "%Y%m%d") - timedelta(days=420)).strftime("%Y%m%d")
        price_frame = self._safe_frame(
            lambda: self.data_service.pro.daily(
                ts_code=",".join(missing_codes),
                start_date=start_date,
                end_date=period_end,
                fields="ts_code,trade_date,close",
            )
        )
        factor_frame = self._safe_frame(
            lambda: self.data_service.pro.adj_factor(
                ts_code=",".join(missing_codes),
                start_date=start_date,
                end_date=period_end,
                fields="ts_code,trade_date,adj_factor",
            )
        )
        market_returns = self._market_returns(period_end, start_date)

        for code in missing_codes:
            stock_prices = price_frame[price_frame["ts_code"] == code].copy() if "ts_code" in price_frame else pd.DataFrame()
            stock_factors = factor_frame[factor_frame["ts_code"] == code].copy() if "ts_code" in factor_frame else pd.DataFrame()
            descriptor = self._price_descriptors(stock_prices, stock_factors, market_returns)
            descriptor.update(self._valuation_descriptors(code, start_date, period_end))
            descriptor.update(self._financial_descriptors(code, start_date, period_end))
            self._stock_cache[(code, period_end)] = descriptor
            result[code] = descriptor
        return result

    def _market_returns(self, period_end: str, start_date: str) -> pd.Series:
        cached = self._market_return_cache.get(period_end)
        if cached is not None:
            return cached
        frame = self._safe_frame(
            lambda: self.data_service.pro.index_daily(
                ts_code=self.market_benchmark,
                start_date=start_date,
                end_date=period_end,
                fields="ts_code,trade_date,close",
            )
        )
        if frame.empty or "trade_date" not in frame or "close" not in frame:
            result = pd.Series(dtype=float)
        else:
            ordered = frame.sort_values("trade_date")
            result = ordered.set_index("trade_date")["close"].astype(float).pct_change().dropna()
        self._market_return_cache[period_end] = result
        return result

    def _price_descriptors(
        self,
        prices: pd.DataFrame,
        factors: pd.DataFrame,
        market_returns: pd.Series,
    ) -> Dict[str, Optional[float]]:
        empty = {"beta": None, "momentum_12_1": None, "residual_volatility": None}
        if prices.empty or factors.empty:
            return empty
        merged = prices.merge(factors, on=["ts_code", "trade_date"], how="inner").sort_values("trade_date")
        if len(merged) < 60:
            return empty
        adjusted = merged["close"].astype(float) * merged["adj_factor"].astype(float)
        stock_returns = pd.Series(adjusted.pct_change().values, index=merged["trade_date"]).dropna()

        momentum = None
        if len(adjusted) >= 126:
            end_index = len(adjusted) - 22
            start_index = max(0, end_index - 252)
            if end_index > start_index and adjusted.iloc[start_index] > 0:
                momentum = float(adjusted.iloc[end_index] / adjusted.iloc[start_index] - 1)

        beta = None
        residual_volatility = None
        aligned = pd.concat([stock_returns.rename("stock"), market_returns.rename("market")], axis=1).dropna().tail(252)
        if len(aligned) >= 60 and float(aligned["market"].var()) > 0:
            beta = float(aligned["stock"].cov(aligned["market"]) / aligned["market"].var())
            alpha = float((aligned["stock"] - beta * aligned["market"]).mean())
            residuals = aligned["stock"] - alpha - beta * aligned["market"]
            residual_volatility = float(residuals.std(ddof=1) * math.sqrt(252))
        return {
            "beta": beta,
            "momentum_12_1": momentum,
            "residual_volatility": residual_volatility,
        }

    def _valuation_descriptors(self, code: str, start_date: str, period_end: str) -> Dict[str, Optional[float]]:
        frame = self._safe_frame(
            lambda: self.data_service.pro.daily_basic(
                ts_code=code,
                start_date=start_date,
                end_date=period_end,
                fields="ts_code,trade_date,turnover_rate,pb,total_mv",
            )
        )
        if frame.empty:
            return {"market_cap_cny_100m": None, "book_to_price": None, "turnover_rate": None}
        frame = frame.sort_values("trade_date")
        latest = frame.iloc[-1]
        total_mv = self._number(latest.get("total_mv"))
        pb = self._number(latest.get("pb"))
        turnover = [self._number(value) for value in frame.tail(63).get("turnover_rate", pd.Series(dtype=float)).tolist()]
        turnover = [value for value in turnover if value is not None]
        return {
            "market_cap_cny_100m": total_mv / 10000 if total_mv is not None and total_mv > 0 else None,
            "book_to_price": 1 / pb if pb is not None and pb > 0 else None,
            "turnover_rate": sum(turnover) / len(turnover) / 100 if turnover else None,
        }

    def _financial_descriptors(self, code: str, start_date: str, period_end: str) -> Dict[str, Optional[float]]:
        frame = self._safe_frame(
            lambda: self.data_service.pro.fina_indicator(
                ts_code=code,
                start_date=start_date,
                end_date=period_end,
                fields="ts_code,ann_date,end_date,debt_to_assets,q_sales_yoy,q_profit_yoy",
            )
        )
        if frame.empty:
            return {"debt_to_assets": None, "growth": None}
        if "ann_date" in frame:
            frame = frame[frame["ann_date"].astype(str) <= period_end]
        if frame.empty:
            return {"debt_to_assets": None, "growth": None}
        frame = frame.sort_values([column for column in ("ann_date", "end_date") if column in frame.columns])
        latest = frame.iloc[-1]
        debt = self._number(latest.get("debt_to_assets"))
        growth_values = [self._number(latest.get("q_sales_yoy")), self._number(latest.get("q_profit_yoy"))]
        growth_values = [value for value in growth_values if value is not None]
        return {
            "debt_to_assets": debt / 100 if debt is not None else None,
            "growth": sum(growth_values) / len(growth_values) / 100 if growth_values else None,
        }

    @staticmethod
    def _safe_frame(call) -> pd.DataFrame:
        try:
            frame = call()
            return frame if frame is not None else pd.DataFrame()
        except Exception:
            return pd.DataFrame()

    @staticmethod
    def _quarter_end(quarter: str) -> str:
        ends = {"Q1": "0331", "Q2": "0630", "Q3": "0930", "Q4": "1231"}
        return f"{quarter[:4]}{ends[quarter[4:]]}"

    @staticmethod
    def _supported_stock_code(code: str) -> bool:
        return code.endswith((".SH", ".SZ", ".BJ")) and code[:6].isdigit()

    @classmethod
    def _number(cls, value: Any) -> Optional[float]:
        try:
            parsed = float(value)
            return parsed if math.isfinite(parsed) else None
        except (TypeError, ValueError):
            return None

    @classmethod
    def _fund_nav_weight(cls, holding: Dict[str, Any]) -> Optional[float]:
        return fund_nav_weight(holding)
