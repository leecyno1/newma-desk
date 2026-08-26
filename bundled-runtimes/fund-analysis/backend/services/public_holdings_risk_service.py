"""公开持仓统计风险模型。

使用真实持仓权重、复权股价和市场指数收益，估计已披露 A 股组合的市场风险与
特异风险。它是 Barra 描述子的补充证据，不是商业 Barra 多因子模型。
"""
import math
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd

from lib.holding_weight_validation import fund_nav_weight, validate_fund_nav_weights


MIN_OBSERVATIONS = 60


class PublicHoldingsRiskService:
    def __init__(self, data_service: Any, market_benchmark: str = "000985.CSI"):
        self.data_service = data_service
        self.market_benchmark = market_benchmark

    def analyze(self, holdings: List[Dict[str, Any]], quarter: str) -> Dict[str, Any]:
        validation = validate_fund_nav_weights(holdings)
        eligible = []
        for holding in holdings:
            code = str(holding.get("stock_code") or "").strip().upper()
            weight = fund_nav_weight(holding)
            if code.endswith((".SH", ".SZ", ".BJ")) and weight is not None and weight > 0:
                eligible.append({"stock_code": code, "weight": float(weight)})

        disclosed_weight = sum(item["weight"] for item in eligible)
        if not eligible or disclosed_weight <= 0:
            return self._unavailable(quarter, ["缺少具有基金净值权重的 A 股持仓。"])

        period_end = self._quarter_end(quarter)
        period_start = (
            datetime.strptime(period_end, "%Y%m%d") - timedelta(days=400)
        ).strftime("%Y%m%d")
        codes = [item["stock_code"] for item in eligible]
        price_frame = self._safe_frame(lambda: self.data_service.pro.daily(
            ts_code=",".join(codes),
            start_date=period_start,
            end_date=period_end,
            fields="ts_code,trade_date,close",
        ))
        adjustment_frame = self._safe_frame(lambda: self.data_service.pro.adj_factor(
            ts_code=",".join(codes),
            start_date=period_start,
            end_date=period_end,
            fields="ts_code,trade_date,adj_factor",
        ))
        market_frame = self._safe_frame(lambda: self.data_service.pro.index_daily(
            ts_code=self.market_benchmark,
            start_date=period_start,
            end_date=period_end,
            fields="ts_code,trade_date,close",
        ))
        stock_returns = self._stock_returns(price_frame, adjustment_frame)
        market_returns = self._market_returns(market_frame)
        if stock_returns.empty or market_returns.empty:
            return self._unavailable(quarter, ["持仓复权行情或市场指数行情不足。"])

        available_codes = [code for code in codes if code in stock_returns.columns]
        if not available_codes:
            return self._unavailable(quarter, ["持仓股票没有足够的复权收益序列。"])

        aligned = stock_returns[available_codes].join(market_returns.rename("market"), how="inner").dropna()
        if len(aligned) < MIN_OBSERVATIONS:
            return self._unavailable(
                quarter,
                [f"持仓与市场共同交易日仅 {len(aligned)} 个，低于 {MIN_OBSERVATIONS} 个最低门槛。"],
            )

        weights = {
            item["stock_code"]: item["weight"]
            for item in eligible
            if item["stock_code"] in available_codes
        }
        return_covered_weight = sum(weights.values())
        normalized_weights = {
            code: weight / return_covered_weight
            for code, weight in weights.items()
        }
        market = aligned["market"].astype(float)
        market_daily_variance = float(market.var(ddof=1))
        market_variance = market_daily_variance * 252
        stock_models = []
        weighted_stock_beta = 0.0
        diagonal_specific_variance = 0.0
        for code, weight in normalized_weights.items():
            stock = aligned[code].astype(float)
            beta = float(stock.cov(market) / market_daily_variance) if market_daily_variance > 0 else 0.0
            alpha = float((stock - beta * market).mean())
            residual = stock - alpha - beta * market
            residual_variance = float(residual.var(ddof=1) * 252)
            weighted_stock_beta += weight * beta
            diagonal_specific_variance += weight * weight * max(0.0, residual_variance)
            stock_models.append({
                "stock_code": code,
                "weight_within_disclosed_sleeve": round(weight, 6),
                "beta": round(beta, 6),
                "specific_volatility": round(math.sqrt(max(0.0, residual_variance)), 6),
            })

        sleeve_returns = sum(
            aligned[code].astype(float) * weight
            for code, weight in normalized_weights.items()
        )
        portfolio_beta = (
            float(sleeve_returns.cov(market) / market_daily_variance)
            if market_daily_variance > 0
            else weighted_stock_beta
        )
        portfolio_alpha = float((sleeve_returns - portfolio_beta * market).mean())
        portfolio_residual = sleeve_returns - portfolio_alpha - portfolio_beta * market
        specific_variance = max(0.0, float(portfolio_residual.var(ddof=1) * 252))
        systematic_variance = max(0.0, portfolio_beta * portfolio_beta * market_variance)
        modeled_variance = systematic_variance + specific_variance
        observed_variance = float(sleeve_returns.var(ddof=1) * 252)
        market_share = systematic_variance / modeled_variance if modeled_variance > 0 else None
        specific_share = specific_variance / modeled_variance if modeled_variance > 0 else None
        regression_r_squared = (
            max(0.0, min(1.0, 1 - specific_variance / observed_variance))
            if observed_variance > 0
            else None
        )
        missing_items = [
            "这是公开持仓单市场因子统计模型，不是商业 Barra 多因子风险模型。",
            "市场与特异风险来自已披露组合对宽基市场的时间序列回归，不能替代商业 Barra 的多因子协方差模型。",
        ]
        if disclosed_weight < 0.8:
            missing_items.append(
                f"可计算持仓仅覆盖基金净值的 {disclosed_weight:.1%}，风险结果只代表已披露 A 股部分。"
            )
        if return_covered_weight < disclosed_weight:
            missing_items.append(
                f"行情覆盖基金净值的 {return_covered_weight:.1%}，低于可计算持仓权重 {disclosed_weight:.1%}。"
            )

        return {
            "status": "partial_evidence",
            "method": "public_holdings_market_residual_risk_model",
            "is_formal_barra": False,
            "source": "tushare.daily+adj_factor+index_daily",
            "quarter": quarter,
            "period": {"start": period_start, "end": period_end},
            "market_benchmark": self.market_benchmark,
            "observations": len(aligned),
            "holdings_count": len(normalized_weights),
            "fund_nav_coverage": round(return_covered_weight, 6),
            "portfolio_beta": round(portfolio_beta, 6),
            "observed_volatility": round(math.sqrt(max(0.0, observed_variance)), 6),
            "modeled_volatility": round(math.sqrt(max(0.0, modeled_variance)), 6),
            "market_factor_volatility": round(math.sqrt(systematic_variance), 6),
            "specific_volatility": round(math.sqrt(max(0.0, specific_variance)), 6),
            "stock_specific_diagonal_volatility": round(math.sqrt(max(0.0, diagonal_specific_variance)), 6),
            "modeled_r_squared": round(regression_r_squared, 6) if regression_r_squared is not None else None,
            "systematic_share_of_modeled_risk": round(market_share, 6) if market_share is not None else None,
            "risk_contributions": [
                {
                    "factor": "MARKET",
                    "label": "市场系统性风险",
                    "variance": round(systematic_variance, 8),
                    "risk_share": round(market_share, 6) if market_share is not None else None,
                },
                {
                    "factor": "SPECIFIC",
                    "label": "股票特异风险",
                    "variance": round(specific_variance, 8),
                    "risk_share": round(specific_share, 6) if specific_share is not None else None,
                },
            ],
            "stock_models": sorted(
                stock_models,
                key=lambda item: item["weight_within_disclosed_sleeve"],
                reverse=True,
            ),
            "weight_validation": validation.as_dict(),
            "missing_items": missing_items,
        }

    @staticmethod
    def _stock_returns(prices: pd.DataFrame, adjustments: pd.DataFrame) -> pd.DataFrame:
        required_price = {"ts_code", "trade_date", "close"}
        required_adjustment = {"ts_code", "trade_date", "adj_factor"}
        if prices.empty or adjustments.empty:
            return pd.DataFrame()
        if not required_price.issubset(prices.columns) or not required_adjustment.issubset(adjustments.columns):
            return pd.DataFrame()
        merged = prices.merge(adjustments, on=["ts_code", "trade_date"], how="inner")
        merged["adjusted_close"] = merged["close"].astype(float) * merged["adj_factor"].astype(float)
        pivot = merged.pivot_table(index="trade_date", columns="ts_code", values="adjusted_close", aggfunc="last")
        return pivot.sort_index().pct_change(fill_method=None).dropna(how="all")

    @staticmethod
    def _market_returns(frame: pd.DataFrame) -> pd.Series:
        if frame.empty or not {"trade_date", "close"}.issubset(frame.columns):
            return pd.Series(dtype=float)
        ordered = frame.sort_values("trade_date")
        return ordered.set_index("trade_date")["close"].astype(float).pct_change().dropna()

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
    def _unavailable(quarter: str, missing_items: List[str]) -> Dict[str, Any]:
        return {
            "status": "insufficient_evidence",
            "method": "public_holdings_market_residual_risk_model",
            "is_formal_barra": False,
            "quarter": quarter,
            "risk_contributions": [],
            "missing_items": missing_items,
        }
