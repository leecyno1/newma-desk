"""
基金指标工厂

统一计算收益、风险和相对基准指标，后续评分和筛选都应使用这里沉淀的指标快照。
"""
import math
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Tuple


class MetricFactory:
    """统一指标计算服务。"""

    def __init__(self, trading_days: int = 252, risk_free_rate: float = 0.02):
        self.trading_days = trading_days
        self.risk_free_rate = risk_free_rate

    def calculate_return_metrics(self, nav_series: List[Dict[str, Any]]) -> Dict[str, float]:
        """计算收益类指标。"""
        points = self._normalize_nav_series(nav_series)
        if len(points) < 2:
            return {}

        first_nav = points[0][1]
        last_nav = points[-1][1]
        if first_nav <= 0:
            return {}

        total_return = last_nav / first_nav - 1
        periods = max(len(points) - 1, 1)
        annualized_return = (1 + total_return) ** (self.trading_days / periods) - 1
        daily_returns = self._daily_returns(points)
        positive_ratio = sum(1 for value in daily_returns if value > 0) / len(daily_returns) if daily_returns else 0
        running_peak = points[0][1]
        record_breaking_days = 1
        for _, nav in points[1:]:
            if nav > running_peak:
                running_peak = nav
                record_breaking_days += 1

        return {
            "total_return": total_return,
            "annualized_return": annualized_return,
            "positive_return_ratio": positive_ratio,
            "record_breaking_days_ratio": record_breaking_days / len(points),
            "start_nav": first_nav,
            "end_nav": last_nav,
            "observations": float(len(points)),
        }

    def calculate_risk_metrics(self, nav_series: List[Dict[str, Any]]) -> Dict[str, float]:
        """计算风险类指标。"""
        points = self._normalize_nav_series(nav_series)
        if len(points) < 2:
            return {}

        daily_returns = self._daily_returns(points)
        if not daily_returns:
            return {}

        average_return = sum(daily_returns) / len(daily_returns)
        volatility = self._stddev(daily_returns)
        annualized_volatility = volatility * math.sqrt(self.trading_days)
        annualized_excess_return = average_return * self.trading_days - self.risk_free_rate
        sharpe_ratio = annualized_excess_return / annualized_volatility if annualized_volatility else 0
        downside_returns = [min(value, 0) for value in daily_returns]
        downside_deviation = self._stddev(downside_returns) * math.sqrt(self.trading_days)
        sortino_ratio = annualized_excess_return / downside_deviation if downside_deviation else 0
        max_drawdown = self._max_drawdown(points)
        calmar_ratio = self.calculate_return_metrics(nav_series).get("annualized_return", 0) / abs(max_drawdown) if max_drawdown else 0

        return {
            "annualized_volatility": annualized_volatility,
            "downside_risk": downside_deviation,
            "sharpe_ratio": sharpe_ratio,
            "sortino_ratio": sortino_ratio,
            "max_drawdown": max_drawdown,
            "calmar_ratio": calmar_ratio,
            "daily_return_mean": average_return,
            "daily_return_std": volatility,
        }

    def calculate_relative_metrics(
        self,
        nav_series: List[Dict[str, Any]],
        benchmark_series: List[Dict[str, Any]],
    ) -> Dict[str, float]:
        """计算相对基准指标。"""
        fund_points = self._normalize_nav_series(nav_series)
        benchmark_points = self._normalize_nav_series(benchmark_series)
        if len(fund_points) < 2 or len(benchmark_points) < 2:
            return {}

        fund_by_date = {item_date: value for item_date, value in fund_points}
        benchmark_by_date = {item_date: value for item_date, value in benchmark_points}
        shared_dates = sorted(set(fund_by_date) & set(benchmark_by_date))
        if len(shared_dates) < 2:
            return {}

        aligned_fund = [(item_date, fund_by_date[item_date]) for item_date in shared_dates]
        aligned_benchmark = [(item_date, benchmark_by_date[item_date]) for item_date in shared_dates]
        fund_total = aligned_fund[-1][1] / aligned_fund[0][1] - 1
        benchmark_total = aligned_benchmark[-1][1] / aligned_benchmark[0][1] - 1
        fund_returns = self._daily_returns(aligned_fund)
        benchmark_returns = self._daily_returns(aligned_benchmark)
        active_returns = [fund - benchmark for fund, benchmark in zip(fund_returns, benchmark_returns)]
        tracking_error = self._stddev(active_returns) * math.sqrt(self.trading_days)
        annualized_active = (sum(active_returns) / len(active_returns)) * self.trading_days if active_returns else 0
        information_ratio = annualized_active / tracking_error if tracking_error else 0

        return {
            "benchmark_return": benchmark_total,
            "excess_return": fund_total - benchmark_total,
            "tracking_error": tracking_error,
            "information_ratio": information_ratio,
            "active_return_mean": sum(active_returns) / len(active_returns) if active_returns else 0,
        }

    def build_metric_records(
        self,
        target_type: str,
        target_id: str,
        as_of_date: date,
        nav_series: List[Dict[str, Any]],
        benchmark_series: Optional[List[Dict[str, Any]]] = None,
        benchmark_code: Optional[str] = None,
        window: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """将计算结果转换为可持久化的指标记录。"""
        metrics: Dict[str, float] = {}
        metrics.update(self.calculate_return_metrics(nav_series))
        metrics.update(self.calculate_risk_metrics(nav_series))
        if benchmark_series:
            metrics.update(self.calculate_relative_metrics(nav_series, benchmark_series))

        records = []
        for metric_name, metric_value in metrics.items():
            records.append({
                "target_type": target_type,
                "target_id": target_id,
                "as_of_date": as_of_date,
                "metric_name": metric_name,
                "metric_value": Decimal(str(metric_value)),
                "metric_unit": "count" if metric_name == "observations" else "ratio",
                "window": window,
                "benchmark_code": benchmark_code if metric_name in {
                    "benchmark_return", "excess_return", "tracking_error", "information_ratio", "active_return_mean"
                } else None,
            })
        return records

    def calculate_and_save_fund_metrics(
        self,
        fund_code: str,
        as_of_date: Optional[date] = None,
        window: Optional[str] = None,
        source_snapshot_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """读取基金净值，计算指标并保存到 MetricSnapshot。"""
        from repositories import get_metric_snapshot_repo, get_nav_repo

        nav_repo = get_nav_repo()
        metric_repo = get_metric_snapshot_repo()
        nav_series = nav_repo.get_nav_series(fund_code)
        if not nav_series:
            return {"fund_code": fund_code, "saved": 0, "metrics": []}

        normalized = self._normalize_nav_series(nav_series)
        effective_as_of = as_of_date or normalized[-1][0]
        records = self.build_metric_records(
            target_type="fund",
            target_id=fund_code,
            as_of_date=effective_as_of,
            nav_series=nav_series,
            window=window,
        )
        saved = []
        for record in records:
            saved.append(metric_repo.upsert_metric(
                source_snapshot_id=source_snapshot_id,
                details={"calculation_engine": "MetricFactory"},
                **record,
            ))
        return {"fund_code": fund_code, "saved": len(saved), "metrics": saved}

    def _normalize_nav_series(self, nav_series: Iterable[Dict[str, Any]]) -> List[Tuple[date, float]]:
        points: List[Tuple[date, float]] = []
        for item in nav_series:
            nav_value = item.get("accum_nav") or item.get("adj_nav") or item.get("nav") or item.get("unit_nav")
            item_date = item.get("date") or item.get("trade_date")
            if nav_value is None or item_date is None:
                continue
            try:
                value = float(nav_value)
            except (TypeError, ValueError):
                continue
            if value <= 0 or math.isnan(value) or math.isinf(value):
                continue
            if isinstance(item_date, datetime):
                parsed_date = item_date.date()
            elif isinstance(item_date, date):
                parsed_date = item_date
            else:
                parsed_date = datetime.fromisoformat(str(item_date)).date()
            points.append((parsed_date, value))
        points.sort(key=lambda item: item[0])
        return points

    @staticmethod
    def _daily_returns(points: List[Tuple[date, float]]) -> List[float]:
        returns = []
        for index in range(1, len(points)):
            previous = points[index - 1][1]
            current = points[index][1]
            if previous > 0:
                returns.append(current / previous - 1)
        return returns

    @staticmethod
    def _stddev(values: List[float]) -> float:
        if len(values) < 2:
            return 0
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
        return math.sqrt(variance)

    @staticmethod
    def _max_drawdown(points: List[Tuple[date, float]]) -> float:
        peak = points[0][1]
        max_drawdown = 0.0
        for _, nav in points:
            if nav > peak:
                peak = nav
            drawdown = nav / peak - 1
            if drawdown < max_drawdown:
                max_drawdown = drawdown
        return max_drawdown
