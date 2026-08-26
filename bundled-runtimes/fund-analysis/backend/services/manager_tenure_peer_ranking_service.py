"""基金经理产品任期的同类同区间排名。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional


class ManagerTenurePeerRankingService:
    """只用显式同类组和同一日期区间的真实净值排名。"""

    MIN_OBSERVATIONS = 20
    MIN_PERIOD_COVERAGE = 0.90
    MIN_OBSERVATION_COVERAGE = 0.80
    METRICS = (
        ("total_return", "同类任期收益"),
        ("record_breaking_days_ratio", "同类创新高天数占比"),
        ("annualized_return", "同类任期年化收益"),
        ("max_drawdown", "同类任期回撤控制"),
        ("sharpe_ratio", "同类任期 Sharpe"),
    )

    def __init__(self, classification_repo: Optional[Any] = None):
        self._classification_repo = classification_repo

    def rank(self, tenure: Dict[str, Any]) -> Dict[str, Any]:
        target_code = str(tenure.get("fund_code") or "").strip().upper()
        coverage_status = str(
            tenure.get("tenure_coverage_status")
            or tenure.get("coverage_status")
            or ""
        ).strip()
        if coverage_status and coverage_status != "full_tenure":
            return {
                **self._unavailable("partial_tenure_coverage", target_code),
                "tenure_coverage_status": coverage_status,
                "tenure_coverage_ratio": self._number(tenure.get("tenure_coverage_ratio")),
                "period_start": self._date_text(
                    tenure.get("metric_start_date") or tenure.get("actual_start_date")
                ),
                "period_end": self._date_text(
                    tenure.get("metric_as_of_date") or tenure.get("actual_end_date")
                ),
            }
        target_values = {
            "total_return": self._first_number(tenure.get("tenure_return"), tenure.get("total_return")),
            "record_breaking_days_ratio": self._number(tenure.get("record_breaking_days_ratio")),
            "annualized_return": self._number(tenure.get("annualized_return")),
            "max_drawdown": self._number(tenure.get("max_drawdown")),
            "sharpe_ratio": self._number(tenure.get("sharpe_ratio")),
        }
        period_start = self._date(tenure.get("metric_start_date") or tenure.get("start_date"))
        period_end = self._date(tenure.get("metric_as_of_date") or tenure.get("end_date"))
        if target_values["total_return"] is None:
            return self._unavailable("target_metric_unavailable", target_code)
        if not period_start or not period_end or period_end <= period_start:
            return self._unavailable("invalid_period", target_code)

        context = self.classification_repo.get_classification_context(target_code) or {}
        peer_group_id = str(context.get("peer_group_id") or "").strip()
        peer_group_name = str(context.get("peer_group_name") or tenure.get("category") or "").strip()
        minimum_peer_count = max(2, int(context.get("minimum_peer_count") or 5))
        if context.get("status") != "resolved" or not peer_group_id:
            return {
                **self._unavailable("classification_unavailable", target_code),
                "peer_group_name": peer_group_name or None,
            }

        summaries = self.classification_repo.list_peer_period_nav_summaries(
            peer_group_id,
            period_start,
            period_end,
        )
        requested_days = max(1, (period_end - period_start).days)
        expected_observations = max(2, round(requested_days / 365.25 * 252) + 1)
        target_entity_id = str(tenure.get("entity_id") or context.get("entity_id") or "")
        valid_peers: List[Dict[str, Any]] = []
        nav_available_count = 0
        for summary in summaries:
            if target_entity_id and str(summary.get("entity_id") or "") == target_entity_id:
                continue
            nav_available_count += 1
            peer = self._peer_value(summary, requested_days, expected_observations)
            if peer:
                valid_peers.append(peer)

        if target_values["annualized_return"] is None:
            target_values["annualized_return"] = self._annualized_return(
                target_values["total_return"],
                int(tenure.get("metric_observations") or 0),
            )
        metrics = {
            metric_name: self._rank_metric(
                metric_name,
                label,
                target_values.get(metric_name),
                [
                    (peer["wind_code"], peer[metric_name])
                    for peer in valid_peers
                    if peer.get(metric_name) is not None
                ],
                minimum_peer_count,
            )
            for metric_name, label in self.METRICS
        }
        total_return_metric = metrics["total_return"]
        status = "sufficient" if total_return_metric["sample_status"] == "sufficient" else "insufficient_peer_sample"
        return {
            "status": status,
            "target_code": target_code,
            "peer_group_id": peer_group_id,
            "peer_group_name": peer_group_name or None,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "classified_peer_count": int(context.get("peer_group_membership_count") or 0),
            "nav_available_peer_count": nav_available_count,
            "valid_peer_count": total_return_metric["peer_count"],
            "metric_valid_peer_counts": {
                metric_name: metric["peer_count"]
                for metric_name, metric in metrics.items()
            },
            "minimum_peer_count": minimum_peer_count,
            "coverage_policy": {
                "minimum_period_coverage_ratio": self.MIN_PERIOD_COVERAGE,
                "minimum_observation_coverage_ratio": self.MIN_OBSERVATION_COVERAGE,
                "minimum_observations": self.MIN_OBSERVATIONS,
                "expected_observations": expected_observations,
            },
            "metrics": metrics,
            "source": "peer_group_members+fund_nav+manager_fund_tenures.performance_snapshot",
            "methodology_version": "manager_tenure_same_period_peer_rank_v3",
        }

    def _peer_value(
        self,
        summary: Dict[str, Any],
        requested_days: int,
        expected_observations: int,
    ) -> Optional[Dict[str, Any]]:
        first_date = self._date(summary.get("first_date"))
        last_date = self._date(summary.get("last_date"))
        first_nav = self._number(summary.get("first_nav"))
        last_nav = self._number(summary.get("last_nav"))
        observations = int(summary.get("observations") or 0)
        if not first_date or not last_date or first_nav is None or last_nav is None or first_nav <= 0:
            return None
        period_coverage = max(0.0, (last_date - first_date).days / requested_days)
        observation_coverage = observations / expected_observations
        if (
            observations < self.MIN_OBSERVATIONS
            or period_coverage < self.MIN_PERIOD_COVERAGE
            or observation_coverage < self.MIN_OBSERVATION_COVERAGE
        ):
            return None
        total_return = last_nav / first_nav - 1
        return {
            "wind_code": str(summary.get("wind_code") or ""),
            "total_return": total_return,
            "record_breaking_days_ratio": self._number(summary.get("record_breaking_days_ratio")),
            "annualized_return": self._annualized_return(total_return, observations),
            "max_drawdown": self._number(summary.get("max_drawdown")),
            "sharpe_ratio": self._number(summary.get("sharpe_ratio")),
        }

    @classmethod
    def _rank_metric(
        cls,
        metric_name: str,
        label: str,
        target_value: Optional[float],
        peer_values: List[tuple[str, float]],
        minimum_peer_count: int,
    ) -> Dict[str, Any]:
        peer_count = len(peer_values) + (1 if target_value is not None else 0)
        if target_value is None:
            return {
                "metric_name": metric_name,
                "label": label,
                "value": None,
                "rank": None,
                "peer_count": peer_count,
                "percentile": None,
                "sample_status": "target_metric_unavailable",
            }
        if peer_count < minimum_peer_count:
            return {
                "metric_name": metric_name,
                "label": label,
                "value": target_value,
                "rank": None,
                "peer_count": peer_count,
                "percentile": None,
                "sample_status": "insufficient_peer_sample",
            }
        rank = 1 + sum(value > target_value for _, value in peer_values)
        percentile = 100.0 if peer_count == 1 else (peer_count - rank) / (peer_count - 1) * 100
        return {
            "metric_name": metric_name,
            "label": label,
            "value": target_value,
            "rank": rank,
            "peer_count": peer_count,
            "percentile": round(percentile, 2),
            "sample_status": "sufficient",
        }

    @staticmethod
    def _unavailable(status: str, target_code: str) -> Dict[str, Any]:
        return {
            "status": status,
            "target_code": target_code,
            "metrics": {},
            "methodology_version": "manager_tenure_same_period_peer_rank_v3",
        }

    @staticmethod
    def _annualized_return(total_return: Optional[float], observations: int) -> Optional[float]:
        if total_return is None or total_return <= -1 or observations < 2:
            return None
        return (1 + total_return) ** (252 / (observations - 1)) - 1

    @staticmethod
    def _date(value: Any) -> Optional[date]:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(str(value or "")[:10])
        except ValueError:
            return None

    @staticmethod
    def _number(value: Any) -> Optional[float]:
        try:
            number = float(value)
            return number if number == number else None
        except (TypeError, ValueError):
            return None

    @classmethod
    def _first_number(cls, *values: Any) -> Optional[float]:
        for value in values:
            number = cls._number(value)
            if number is not None:
                return number
        return None

    @classmethod
    def _date_text(cls, value: Any) -> Optional[str]:
        parsed = cls._date(value)
        return parsed.isoformat() if parsed else None

    @property
    def classification_repo(self):
        if self._classification_repo is None:
            from repositories import get_fund_classification_repo

            self._classification_repo = get_fund_classification_repo()
        return self._classification_repo
