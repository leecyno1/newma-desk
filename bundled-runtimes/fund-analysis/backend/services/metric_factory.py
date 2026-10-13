"""
基金指标工厂

统一计算收益、风险和相对基准指标，后续评分和筛选都应使用这里沉淀的指标快照。
"""
import math
from datetime import date
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Tuple

from services.performance_nav_series import normalize_performance_rows, performance_evidence, daily_risk_rows, select_performance_window


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
        elapsed_days = (points[-1][0] - points[0][0]).days
        annualized_return = (1 + total_return) ** (365.25 / elapsed_days) - 1
        daily_returns = self._daily_returns([
            (row["date"], row["nav"]) for row in normalize_performance_rows(nav_series)
        ])
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

        evidence = performance_evidence(normalize_performance_rows(nav_series))
        max_drawdown = self._max_drawdown(points)
        calmar_ratio = self.calculate_return_metrics(nav_series).get("annualized_return", 0) / abs(max_drawdown) if max_drawdown else 0
        if not evidence["daily_risk_eligible"]:
            # 区间收益与可见点回撤仍可观察，但不能把月频/缺口样本当日频风险。
            observed_risk = {"max_drawdown": max_drawdown, "calmar_ratio": calmar_ratio}
            if evidence["missing_observations"] == 0 and evidence["longest_gap_days"] <= 35:
                observed_risk["monthly_win_rate"] = self._monthly_win_rate(points, self._daily_returns(points))
            return observed_risk
        risk_points = [(row["date"], row["nav"]) for row in daily_risk_rows(normalize_performance_rows(nav_series))]
        daily_returns = self._daily_returns(risk_points)
        if not daily_returns:
            return {}

        average_return = sum(daily_returns) / len(daily_returns)
        volatility = self._stddev(daily_returns)
        annualized_volatility = volatility * math.sqrt(self.trading_days)
        annualized_excess_return = average_return * self.trading_days - self.risk_free_rate
        sharpe_ratio = annualized_excess_return / annualized_volatility if annualized_volatility else 0
        downside_metrics = self.calculate_downside_metrics(daily_returns)
        var_95 = self._percentile(daily_returns, 0.05)
        tail_returns = [value for value in daily_returns if value <= var_95]
        cvar_95 = sum(tail_returns) / len(tail_returns) if tail_returns else 0

        return {
            "annualized_volatility": annualized_volatility,
            **downside_metrics,
            "sharpe_ratio": sharpe_ratio,
            "max_drawdown": max_drawdown,
            "calmar_ratio": calmar_ratio,
            "var_95": var_95,
            "cvar_95": cvar_95,
            "monthly_win_rate": self._monthly_win_rate(points, self._daily_returns(points)),
            "daily_return_mean": average_return,
            "daily_return_std": volatility,
        }

    def calculate_downside_metrics(self, daily_returns: List[float]) -> Dict[str, float]:
        """以年化无风险利率为目标，按全样本下行二阶矩计算风险。"""
        if not daily_returns:
            return {}
        # 目标收益线性折日，与分子的算术年化口径保持一致。
        daily_target = self.risk_free_rate / self.trading_days
        shortfalls = [min(value - daily_target, 0.0) for value in daily_returns]
        second_moment = sum(value**2 for value in shortfalls) / len(daily_returns)
        downside_deviation = math.sqrt(second_moment * self.trading_days)
        annualized_excess_return = sum(daily_returns) / len(daily_returns) * self.trading_days - self.risk_free_rate
        return {
            "downside_risk": downside_deviation,
            "sortino_ratio": annualized_excess_return / downside_deviation if downside_deviation else 0,
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
        relative = {"benchmark_return": benchmark_total, "excess_return": fund_total - benchmark_total}
        # 日期交集不能把基金或基准缺失的披露日删除后接成一个日收益。
        fund_risk = daily_risk_rows(normalize_performance_rows(nav_series))
        benchmark_risk = daily_risk_rows(normalize_performance_rows(benchmark_series))
        if (len(fund_risk) < 2 or len(benchmark_risk) < 2
                or [row["date"] for row in fund_risk] != [row["date"] for row in benchmark_risk]):
            return relative
        fund_returns = self._daily_returns([(row["date"], row["nav"]) for row in fund_risk])
        benchmark_returns = self._daily_returns([(row["date"], row["nav"]) for row in benchmark_risk])
        active_returns = [fund - benchmark for fund, benchmark in zip(fund_returns, benchmark_returns)]
        tracking_error = self._stddev(active_returns) * math.sqrt(self.trading_days)
        annualized_active = (sum(active_returns) / len(active_returns)) * self.trading_days if active_returns else 0
        information_ratio = annualized_active / tracking_error if tracking_error else 0

        return {
            **relative,
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
        calendar_days = {'1y': 365, '3y': 1095, '5y': 1825}.get(window)
        if calendar_days:
            nav_series, complete = select_performance_window(nav_series, calendar_days, as_of_date)
            if not complete:
                return []
        else:
            nav_series = normalize_performance_rows(nav_series, as_of_date=as_of_date)
        evidence = performance_evidence(nav_series)
        evidence.update({"risk_free_rate": self.risk_free_rate,
                         "window_policy": "calendar_days_with_baseline_v1" if calendar_days else "exact_supplied_interval",
                         "coverage_status": "full" if calendar_days else "observed_interval",
                         "window_start_date": next((row['date'] for row in nav_series if row['nav'] is not None), None),
                         "window_end_date": next((row['date'] for row in reversed(nav_series) if row['nav'] is not None), None),
                         "risk_annualization": f"daily_{self.trading_days}" if evidence["daily_risk_eligible"] else "unavailable"})
        # 不用不完整的新面板局部覆盖旧风险指标；历史面板保留原日期和版本。
        if not evidence["daily_risk_eligible"]:
            return []
        metrics: Dict[str, float] = {}
        metrics.update(self.calculate_return_metrics(nav_series))
        metrics.update(self.calculate_risk_metrics(nav_series))
        if benchmark_series:
            if calendar_days:
                benchmark_series, complete = select_performance_window(benchmark_series, calendar_days, as_of_date)
                if not complete:
                    return []
            else:
                benchmark_series = normalize_performance_rows(benchmark_series, as_of_date=as_of_date)
            if not benchmark_series or (nav_series[0]['date'], nav_series[-1]['date']) != (benchmark_series[0]['date'], benchmark_series[-1]['date']):
                return []
            relative_metrics = self.calculate_relative_metrics(nav_series, benchmark_series)
            if "tracking_error" not in relative_metrics:
                return []  # 基准缺证也不能局部刷新一套混合日期的指标面板。
            metrics.update(relative_metrics)

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
                "details": {"calculation_engine": "MetricFactory", **evidence},
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
        nav_series = nav_repo.get_nav_series(
            fund_code, end_date=as_of_date.isoformat() if as_of_date else None,
        )
        normalized = self._normalize_nav_series(nav_series, as_of_date=as_of_date)
        if len(normalized) < 2:
            return {"fund_code": fund_code, "saved": 0, "metrics": []}

        effective_as_of = as_of_date or normalized[-1][0]
        records = self.build_metric_records(
            target_type="fund",
            target_id=fund_code,
            as_of_date=effective_as_of,
            nav_series=nav_series,
            window=window,
        )
        if not records:
            return {"fund_code": fund_code, "saved": 0, "reason": "insufficient_daily_adjusted_nav", "metrics": []}
        saved = metric_repo.upsert_metrics([{**record, 'source_snapshot_id': source_snapshot_id} for record in records])
        return {"fund_code": fund_code, "saved": len(saved), "metrics": saved}

    def _normalize_nav_series(
        self,
        nav_series: Iterable[Dict[str, Any]],
        as_of_date: Optional[date] = None,
    ) -> List[Tuple[date, float]]:
        return [(row["date"], row["nav"]) for row in normalize_performance_rows(nav_series, as_of_date)
                if row["nav"] is not None]

    @staticmethod
    def _daily_returns(points: List[Tuple[date, float]]) -> List[float]:
        returns = []
        for index in range(1, len(points)):
            previous = points[index - 1][1]
            current = points[index][1]
            if previous is not None and current is not None and previous > 0:
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
    def _percentile(values: List[float], level: float) -> float:
        if not values:
            return 0
        ordered = sorted(values)
        position = level * (len(ordered) - 1)
        lower = int(math.floor(position))
        upper = int(math.ceil(position))
        fraction = position - lower
        return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction

    @staticmethod
    def _monthly_win_rate(points: List[Tuple[date, float]], daily_returns: List[float]) -> float:
        if not daily_returns:
            return 0
        monthly: Dict[Tuple[int, int], float] = {}
        for (point_date, _), value in zip(points[1:], daily_returns):
            key = (point_date.year, point_date.month)
            monthly[key] = (1 + monthly.get(key, 0.0)) * (1 + value) - 1
        positive = sum(1 for value in monthly.values() if value > 0)
        return positive / len(monthly) if monthly else 0

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
