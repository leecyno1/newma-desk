"""
高级基金研究服务

提供确定性的净值行为因子镜头和主动收益解释。
这些结果是补充证据，不是 Barra 或 Brinson。
"""
import math
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple


class InvestmentAnalysisService:
    """基金因子与主动归因。"""

    TRADING_DAYS = 252
    FACTOR_META = {
        "equity_beta": {"label": "权益 Beta", "vol": 0.16, "direction": "risk"},
        "momentum": {"label": "收益动量", "vol": 0.20, "direction": "return"},
        "downside_risk": {"label": "下行风险", "vol": 0.18, "direction": "risk"},
        "consistency": {"label": "持续胜率", "vol": 0.10, "direction": "quality"},
        "capacity": {"label": "规模容量", "vol": 0.08, "direction": "quality"},
        "liquidity": {"label": "流动性", "vol": 0.07, "direction": "quality"},
    }
    TYPE_BETA = {
        "money": 0.02,
        "bond": 0.15,
        "index": 1.0,
        "stock": 0.95,
        "hybrid": 0.65,
        "qdii": 0.80,
    }

    def __init__(self, market_data_adapter: Optional[Any] = None):
        self._market_data_adapter = market_data_adapter

    def factor_lens(
        self,
        wind_code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        fund = self._get_fund(wind_code)
        returns = self._returns(fund["wind_code"], start_date, end_date)
        metrics = self._metrics(returns)
        missing_items = []
        if metrics.get("observations", 0) < 60:
            missing_items.append("净值收益序列少于 60 个观测，因子镜头不输出正式评分")
        exposures = self._style_exposures(fund, metrics)
        risk_contributions = self._risk_contributions(exposures)
        concentration = max((item["risk_contribution"] for item in risk_contributions), default=0)
        score = None if missing_items else max(0, min(100, 82 - concentration * 35 - abs(exposures["downside_risk"]) * 12 + exposures["consistency"] * 8))

        return {
            "fund": self._fund_summary(fund),
            "date_range": self._date_range(returns),
            "style_exposures": [
                {
                    "factor": factor,
                    "label": self.FACTOR_META[factor]["label"],
                    "exposure": round(value, 6),
                    "direction": self.FACTOR_META[factor]["direction"],
                }
                for factor, value in exposures.items()
            ],
            "risk_contributions": risk_contributions,
            "factor_score": round(score, 2) if score is not None else None,
            "status": "insufficient_evidence" if missing_items else "ok",
            "source": "nav_metric_evidence",
            "missing_items": missing_items,
            "diagnostics": self._factor_diagnostics(fund, metrics, exposures, concentration),
            "metrics": metrics,
        }

    def advanced_attribution(
        self,
        wind_code: str,
        benchmark: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        fund = self._get_fund(wind_code)
        fund_returns = self._returns(fund["wind_code"], start_date, end_date)
        effective_start = start_date or (min(fund_returns) if fund_returns else None)
        effective_end = end_date or (max(fund_returns) if fund_returns else None)
        benchmark_returns, benchmark_label, benchmark_source = self._benchmark_returns(
            fund,
            benchmark,
            effective_start,
            effective_end,
        )
        shared_dates = sorted(set(fund_returns) & set(benchmark_returns))
        if len(shared_dates) < 2:
            return self._insufficient_attribution(
                fund,
                benchmark,
                benchmark_label,
                benchmark_source,
                fund_returns,
                benchmark_returns,
                ["基金与基准重叠收益序列不足，无法输出主动归因"],
            )

        fund_values = [fund_returns[item_date] for item_date in shared_dates]
        benchmark_values = [benchmark_returns[item_date] for item_date in shared_dates]
        fund_return = self._cumulative_return(fund_values)
        benchmark_return = self._cumulative_return(benchmark_values)
        active_return = fund_return - benchmark_return
        beta = self._beta(fund_values, benchmark_values)
        beta_effect = (beta - 1) * benchmark_return
        alpha_effect = active_return - beta_effect
        selection_effect = alpha_effect * 0.72
        residual = active_return - beta_effect - selection_effect
        downside_capture = self._capture_ratio(fund_values, benchmark_values, up_market=False)
        upside_capture = self._capture_ratio(fund_values, benchmark_values, up_market=True)
        information_ratio = self._information_ratio(fund_values, benchmark_values)

        return {
            "fund": self._fund_summary(fund),
            "benchmark": {
                "code": benchmark or benchmark_label,
                "label": benchmark_label,
                "source": benchmark_source,
            },
            "date_range": {
                "start": shared_dates[0],
                "end": shared_dates[-1],
                "observations": len(shared_dates),
            },
            "returns": {
                "fund": round(fund_return, 6),
                "benchmark": round(benchmark_return, 6),
                "active": round(active_return, 6),
            },
            "effects": [
                {"name": "beta_timing", "label": "Beta / 择时效应", "value": round(beta_effect, 6)},
                {"name": "selection_alpha", "label": "选基 / Alpha 效应", "value": round(selection_effect, 6)},
                {"name": "residual", "label": "残差与未解释项", "value": round(residual, 6)},
            ],
            "diagnostics": {
                "beta": round(beta, 6),
                "upside_capture": upside_capture,
                "downside_capture": downside_capture,
                "information_ratio": information_ratio,
                "explained_active_return": round(beta_effect + selection_effect + residual, 6),
            },
            "recommendations": self._attribution_recommendations(active_return, beta, upside_capture, downside_capture, information_ratio),
            "status": "ok",
            "source": benchmark_source,
            "missing_items": [],
        }

    def _get_fund(self, identifier: str) -> Dict[str, Any]:
        from repositories import get_fund_repo

        fund = get_fund_repo().get_fund_by_identifier(identifier)
        if not fund:
            raise ValueError(f"Fund not found: {identifier}")
        return fund

    def _returns(
        self,
        wind_code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, float]:
        from repositories import get_nav_repo

        points = []
        for item in get_nav_repo().get_nav_series(wind_code, start_date=start_date, end_date=end_date):
            item_date = str(item.get("date") or "")[:10]
            if not item_date:
                continue
            daily_return = item.get("daily_return")
            nav = item.get("nav") or item.get("unit_nav") or item.get("accum_nav")
            try:
                points.append((item_date, float(Decimal(str(nav))) if nav is not None else None, float(Decimal(str(daily_return))) if daily_return is not None else None))
            except Exception:
                continue

        returns = {}
        for index, (item_date, nav, daily_return) in enumerate(points):
            if daily_return is not None:
                returns[item_date] = daily_return
            elif index > 0 and nav is not None and points[index - 1][1]:
                previous_nav = points[index - 1][1]
                if previous_nav and previous_nav > 0:
                    returns[item_date] = nav / previous_nav - 1
        return returns

    def _benchmark_returns(
        self,
        fund: Dict[str, Any],
        benchmark: Optional[str],
        start_date: Optional[str],
        end_date: Optional[str],
    ) -> Tuple[Dict[str, float], str, str]:
        if benchmark:
            direct = self._returns(benchmark, start_date, end_date)
            if len(direct) >= 2:
                return direct, benchmark, "nav_series"
            market_series = self._market_benchmark_returns(benchmark, start_date, end_date)
            if len(market_series) >= 2:
                return market_series, benchmark, "market_data_adapter"
            return {}, benchmark, "benchmark_series_unavailable"

        fund_type = fund.get("type")
        peer_returns = []
        for peer in self._benchmark_peer_funds(fund):
            peer_code = peer.get("wind_code")
            if not peer_code or peer_code == fund.get("wind_code"):
                continue
            values = self._returns(peer_code, start_date, end_date)
            if len(values) >= 2:
                peer_returns.append(values)

        if peer_returns:
            shared_dates = sorted(set.intersection(*(set(item) for item in peer_returns)))
            if len(shared_dates) >= 2:
                return {
                    item_date: sum(peer[item_date] for peer in peer_returns) / len(peer_returns)
                    for item_date in shared_dates
                }, f"{fund_type or 'fund'}_peer_average", "peer_average"

        return {}, f"{fund_type or 'fund'}_peer_average", "insufficient_benchmark_evidence"

    def _market_benchmark_returns(
        self,
        benchmark: str,
        start_date: Optional[str],
        end_date: Optional[str],
    ) -> Dict[str, float]:
        if not start_date or not end_date:
            return {}
        rows = self._get_market_data_adapter().get_benchmark_nav(benchmark, start_date, end_date)
        points = []
        for row in rows or []:
            item_date = str(row.get("date") or "")[:10]
            nav = row.get("nav")
            try:
                if item_date and nav is not None:
                    points.append((item_date, float(Decimal(str(nav)))))
            except Exception:
                continue
        points.sort(key=lambda item: item[0])
        return {
            points[index][0]: points[index][1] / points[index - 1][1] - 1
            for index in range(1, len(points))
            if points[index - 1][1] > 0
        }

    def _get_market_data_adapter(self):
        if self._market_data_adapter is None:
            from service_registry import get_data_service

            self._market_data_adapter = get_data_service()
        return self._market_data_adapter

    def _benchmark_peer_funds(self, fund: Dict[str, Any]) -> List[Dict[str, Any]]:
        fund_type = str(fund.get("type") or "").strip()
        if not fund_type:
            return []
        peers = self._query_funds_by_types([fund_type])
        if len(peers) >= 2:
            return peers
        return self._query_funds_by_types(self._broad_type_values(fund_type))

    def _query_funds_by_types(self, fund_types: List[str]) -> List[Dict[str, Any]]:
        normalized_types = [str(item).strip() for item in fund_types if str(item or "").strip()]
        if not normalized_types:
            return []
        from repositories import get_fund_repo
        from sqlalchemy import text

        sql = """
            SELECT *
            FROM funds
            WHERE type = ANY(:fund_types)
            ORDER BY wind_code ASC
            LIMIT 200
        """
        with get_fund_repo().engine.connect() as conn:
            rows = conn.execute(text(sql), {"fund_types": normalized_types}).fetchall()
        return [dict(row._mapping) for row in rows]

    def _broad_type_values(self, fund_type: str) -> List[str]:
        text = fund_type.lower()
        if any(token in text for token in ["stock", "equity", "股票"]):
            return ["stock", "hybrid", "股票型", "普通股票型", "混合型", "偏股混合型", "灵活配置型"]
        if any(token in text for token in ["hybrid", "混合", "偏股"]):
            return ["hybrid", "stock", "混合型", "偏股混合型", "灵活配置型", "股票型"]
        if any(token in text for token in ["bond", "债"]):
            return ["bond", "债券型", "中长期纯债型", "混合债券型", "短期纯债型"]
        if any(token in text for token in ["index", "指数"]):
            return ["index", "指数型", "被动指数型", "增强指数型"]
        if any(token in text for token in ["money", "货币"]):
            return ["money", "货币型"]
        if any(token in text for token in ["qdii", "全球", "海外"]):
            return ["qdii", "QDII", "国际(QDII)"]
        return [fund_type]

    def _insufficient_attribution(
        self,
        fund: Dict[str, Any],
        benchmark: Optional[str],
        benchmark_label: str,
        benchmark_source: str,
        fund_returns: Dict[str, float],
        benchmark_returns: Dict[str, float],
        missing_items: List[str],
    ) -> Dict[str, Any]:
        shared_dates = sorted(set(fund_returns) & set(benchmark_returns))
        return {
            "fund": self._fund_summary(fund),
            "benchmark": {
                "code": benchmark or benchmark_label,
                "label": benchmark_label,
                "source": benchmark_source,
            },
            "date_range": {
                "start": shared_dates[0] if shared_dates else None,
                "end": shared_dates[-1] if shared_dates else None,
                "observations": len(shared_dates),
            },
            "returns": {
                "fund": None,
                "benchmark": None,
                "active": None,
            },
            "effects": [],
            "diagnostics": {
                "beta": None,
                "upside_capture": None,
                "downside_capture": None,
                "information_ratio": None,
                "explained_active_return": None,
            },
            "recommendations": ["补齐可验证基准或同类收益序列后再运行主动归因。"],
            "status": "insufficient_evidence",
            "source": "evidence_gate",
            "missing_items": missing_items,
        }

    def _style_exposures(self, fund: Dict[str, Any], metrics: Dict[str, Any]) -> Dict[str, float]:
        fund_type = str(fund.get("type") or "").lower()
        total_asset = float(fund.get("total_asset") or 0)
        volatility = abs(float(metrics.get("annualized_volatility") or 0))
        annualized_return = float(metrics.get("annualized_return") or 0)
        max_drawdown = abs(float(metrics.get("max_drawdown") or 0))
        positive_ratio = float(metrics.get("positive_return_ratio") or 0.5)

        beta_base = self.TYPE_BETA.get(fund_type, 0.55)
        beta = max(0, min(1.6, beta_base + max(0, volatility - 0.12) * 1.5))
        capacity = max(-1, min(1, math.log10(max(total_asset, 1)) / 3))
        liquidity = max(-1, min(1, capacity - max_drawdown))

        return {
            "equity_beta": beta,
            "momentum": max(-1, min(1, annualized_return * 2.5)),
            "downside_risk": max(0, min(1.5, max_drawdown * 3)),
            "consistency": max(-1, min(1, positive_ratio * 2 - 1)),
            "capacity": capacity,
            "liquidity": liquidity,
        }

    def _risk_contributions(self, exposures: Dict[str, float]) -> List[Dict[str, Any]]:
        raw = []
        for factor, exposure in exposures.items():
            factor_vol = self.FACTOR_META[factor]["vol"]
            raw_risk = abs(exposure) * factor_vol
            raw.append({
                "factor": factor,
                "label": self.FACTOR_META[factor]["label"],
                "exposure": round(exposure, 6),
                "raw_risk": raw_risk,
            })
        total = sum(item["raw_risk"] for item in raw) or 1
        result = [
            {
                **item,
                "risk_contribution": round(item["raw_risk"] / total, 6),
            }
            for item in raw
        ]
        result.sort(key=lambda item: item["risk_contribution"], reverse=True)
        return result

    def _factor_diagnostics(
        self,
        fund: Dict[str, Any],
        metrics: Dict[str, Any],
        exposures: Dict[str, float],
        concentration: float,
    ) -> List[str]:
        diagnostics = []
        if exposures["downside_risk"] >= 0.6:
            diagnostics.append("最大回撤贡献较高，研究结论中应单独解释回撤来源和恢复路径。")
        if concentration >= 0.35:
            diagnostics.append("单一因子风险贡献偏集中，需要复核风格标签与持仓暴露是否一致。")
        if exposures["momentum"] > 0.4 and exposures["consistency"] > 0:
            diagnostics.append("收益动量与胜率同时为正，短期趋势质量较好。")
        if (fund.get("total_asset") or 0) < 2:
            diagnostics.append("基金规模偏小，需关注流动性、清盘与申赎冲击。")
        if not diagnostics:
            diagnostics.append("因子结构相对均衡，建议继续结合持仓与经理任期复核。")
        if metrics.get("observations", 0) < 120:
            diagnostics.append("净值样本不足半年，因子结论置信度需下调。")
        return diagnostics

    def _attribution_recommendations(
        self,
        active_return: float,
        beta: float,
        upside_capture: Optional[float],
        downside_capture: Optional[float],
        information_ratio: Optional[float],
    ) -> List[str]:
        recommendations = []
        if active_return > 0:
            recommendations.append("当前区间超额收益为正，可继续追踪 Alpha 来源是否稳定。")
        else:
            recommendations.append("当前区间超额收益为负，建议复核风格暴露与持仓贡献。")
        if beta > 1.15:
            recommendations.append("Beta 偏高，后续被其他模块使用时需额外关注权益市场同步回撤。")
        if downside_capture is not None and downside_capture < 1:
            recommendations.append("下行捕获率低于 1，显示一定防守能力。")
        if upside_capture is not None and upside_capture < 0.8:
            recommendations.append("上行捕获不足，若定位为进攻型基金需进一步解释。")
        if information_ratio is not None and information_ratio > 0.5:
            recommendations.append("信息比率较好，超额收益相对波动具备可跟踪价值。")
        return recommendations

    def _metrics(self, returns: Dict[str, float]) -> Dict[str, Any]:
        values = list(returns.values())
        if not values:
            return {
                "observations": 0,
                "total_return": 0,
                "annualized_return": 0,
                "annualized_volatility": 0,
                "max_drawdown": 0,
                "positive_return_ratio": None,
            }
        total = self._cumulative_return(values)
        annualized = self._annualized_return(values)
        volatility = self._std(values) * math.sqrt(self.TRADING_DAYS)
        nav = 1.0
        path = []
        for value in values:
            nav *= 1 + value
            path.append(nav)
        return {
            "observations": len(values),
            "total_return": round(total, 6),
            "annualized_return": round(annualized, 6),
            "annualized_volatility": round(volatility, 6),
            "max_drawdown": round(self._max_drawdown(path), 6),
            "positive_return_ratio": round(len([value for value in values if value > 0]) / len(values), 6),
        }

    def _date_range(self, returns: Dict[str, float]) -> Dict[str, Any]:
        dates = sorted(returns)
        return {
            "start": dates[0] if dates else None,
            "end": dates[-1] if dates else None,
            "observations": len(dates),
        }

    def _fund_summary(self, fund: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": str(fund.get("id")) if fund.get("id") else fund.get("wind_code"),
            "wind_code": fund.get("wind_code"),
            "name": fund.get("name"),
            "type": fund.get("type"),
            "total_asset": fund.get("total_asset"),
        }

    def _annualized_return(self, values: List[float]) -> float:
        if not values:
            return 0.0
        total = self._cumulative_return(values)
        return (1 + total) ** (self.TRADING_DAYS / len(values)) - 1

    def _cumulative_return(self, values: List[float]) -> float:
        nav = 1.0
        for value in values:
            nav *= 1 + value
        return nav - 1

    def _std(self, values: List[float]) -> float:
        if len(values) < 2:
            return 0.0
        avg = sum(values) / len(values)
        return math.sqrt(sum((value - avg) ** 2 for value in values) / (len(values) - 1))

    def _cov(self, left: List[float], right: List[float]) -> float:
        if len(left) < 2 or len(left) != len(right):
            return 0.0
        left_avg = sum(left) / len(left)
        right_avg = sum(right) / len(right)
        return sum((left[index] - left_avg) * (right[index] - right_avg) for index in range(len(left))) / (len(left) - 1)

    def _corr(self, left: List[float], right: List[float]) -> float:
        left_std = self._std(left)
        right_std = self._std(right)
        if not left_std or not right_std:
            return 0.0
        return self._cov(left, right) / (left_std * right_std)

    def _beta(self, fund_values: List[float], benchmark_values: List[float]) -> float:
        variance = self._cov(benchmark_values, benchmark_values)
        if not variance:
            return 1.0
        return self._cov(fund_values, benchmark_values) / variance

    def _information_ratio(self, fund_values: List[float], benchmark_values: List[float]) -> Optional[float]:
        active_values = [fund_values[index] - benchmark_values[index] for index in range(len(fund_values))]
        tracking_error = self._std(active_values) * math.sqrt(self.TRADING_DAYS)
        active_return = self._annualized_return(active_values)
        return round(active_return / tracking_error, 6) if tracking_error else None

    def _capture_ratio(self, fund_values: List[float], benchmark_values: List[float], up_market: bool) -> Optional[float]:
        selected = [
            (fund_values[index], benchmark_values[index])
            for index in range(len(fund_values))
            if (benchmark_values[index] > 0 if up_market else benchmark_values[index] < 0)
        ]
        if not selected:
            return None
        fund_sum = sum(item[0] for item in selected)
        bench_sum = sum(item[1] for item in selected)
        if bench_sum == 0:
            return None
        return round(fund_sum / bench_sum, 6)

    def _max_drawdown(self, nav_path: List[float]) -> float:
        peak = nav_path[0] if nav_path else 1
        max_drawdown = 0.0
        for nav in nav_path:
            peak = max(peak, nav)
            if peak:
                max_drawdown = min(max_drawdown, nav / peak - 1)
        return max_drawdown
