"""基金经理单产品生涯曲线。

只读取本地真实任职、净值、基准与纪要证据，不拼接经理综合净值。
"""

from __future__ import annotations

from bisect import bisect_left
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from services.metric_factory import MetricFactory
from services.fund_product_identity import fund_product_identity
from services.manager_tenure_coverage import build_manager_tenure_coverage


class FundManagerCareerService:
    """输出可交互的经理单产品任职曲线。"""

    PERIOD_OPTIONS = [
        {"key": "tenure", "label": "任职以来"},
        {"key": "ytd", "label": "今年以来"},
        {"key": "3m", "label": "近3月"},
        {"key": "6m", "label": "近6月"},
        {"key": "1y", "label": "近1年"},
        {"key": "3y", "label": "近3年"},
        {"key": "5y", "label": "近5年"},
    ]

    def __init__(
        self,
        manager_repo: Optional[Any] = None,
        nav_repo: Optional[Any] = None,
        classification_repo: Optional[Any] = None,
        report_repo: Optional[Any] = None,
        peer_ranking_service: Optional[Any] = None,
        metric_factory: Optional[MetricFactory] = None,
        today: Optional[date] = None,
    ):
        self._manager_repo = manager_repo
        self._nav_repo = nav_repo
        self._classification_repo = classification_repo
        self._report_repo = report_repo
        self._peer_ranking_service = peer_ranking_service
        self.metric_factory = metric_factory or MetricFactory()
        self.today = today or date.today()

    def build(
        self,
        manager_id: str,
        fund_code: Optional[str] = None,
        tenure_start_date: Optional[str] = None,
        period: str = "tenure",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        requested_id = str(manager_id or "").strip()
        manager = self.manager_repo.get_manager(requested_id)
        if not manager:
            raise ValueError(f"Manager not found: {requested_id}")
        resolved_id = str(manager.get("wind_code") or requested_id)
        rows = self.manager_repo.list_fund_tenures(resolved_id)
        products = self._canonical_products(rows)
        if not products:
            return self._safe({
                "status": "empty",
                "reason": "manager_tenures_unavailable",
                "manager_id": resolved_id,
                "manager_name": manager.get("name"),
                "products": [],
                "curve": [],
                "events": [],
                "source": "local.postgres.manager_fund_tenures+fund_nav+research_reports",
                "simulation_used": False,
            })

        selected = self._select_product(products, fund_code, tenure_start_date)
        tenure_start = self._parse_date(selected.get("start_date"))
        tenure_end = self._parse_date(selected.get("end_date")) or self.today
        if tenure_start is None:
            raise ValueError("Selected product has no verified tenure start")
        requested_start, requested_end, period_label = self._resolve_range(
            period=period,
            tenure_start=tenure_start,
            tenure_end=min(tenure_end, self.today),
            custom_start=start_date,
            custom_end=end_date,
        )

        actual_code, nav_rows = self._load_nav(selected, requested_start, requested_end, fund_code)
        context = self.classification_repo.get_classification_context(actual_code) or {}
        mapping = context.get("benchmark_mapping") if isinstance(context.get("benchmark_mapping"), dict) else {}
        benchmark_code = str(mapping.get("benchmark_code") or "").strip() or None
        benchmark_name = str(mapping.get("benchmark_name") or "").strip() or None
        benchmark_type = str(mapping.get("benchmark_type") or "").strip() or None
        benchmark_evidence = mapping.get("evidence_refs") if isinstance(mapping.get("evidence_refs"), dict) else {}
        contract_components = benchmark_evidence.get("benchmarkComponents") or []
        declared_benchmark = str(benchmark_evidence.get("declaredBenchmark") or "").strip() or None
        if benchmark_type == "declared_allocation_bucket" and contract_components and declared_benchmark:
            performance_benchmark_code = "CONTRACT-COMPOSITE"
            performance_benchmark_name = declared_benchmark
            performance_benchmark_type = "contract_composite_benchmark"
        else:
            performance_benchmark_code = benchmark_code
            performance_benchmark_name = benchmark_name
            performance_benchmark_type = benchmark_type
        normalized_rows = self._normalize_rows(nav_rows)
        available_years = self._available_years(tenure_start, min(tenure_end, self.today))

        common_rows = [item for item in normalized_rows if item.get("benchmark_nav") is not None]
        if len(common_rows) >= 2:
            first_common = common_rows[0]["date"]
            last_common = common_rows[-1]["date"]
            metric_rows = [item for item in normalized_rows if first_common <= item["date"] <= last_common]
            benchmark_status = "available"
        else:
            metric_rows = normalized_rows
            benchmark_status = "mapping_missing" if not benchmark_code else "data_unavailable"

        if len(metric_rows) < 2:
            return self._safe({
                "status": "empty",
                "reason": "insufficient_local_nav",
                "manager_id": resolved_id,
                "manager_name": manager.get("name"),
                "products": products,
                "selected_product": {**selected, "actual_curve_code": actual_code},
                "period": period,
                "period_label": period_label,
                "requested_start_date": requested_start,
                "requested_end_date": requested_end,
                "available_years": available_years,
                "period_options": self.PERIOD_OPTIONS,
                "benchmark": {
                    "code": performance_benchmark_code,
                    "name": performance_benchmark_name,
                    "type": performance_benchmark_type,
                    "classification_code": benchmark_code,
                    "components": contract_components,
                    "status": benchmark_status,
                    "observations": len(common_rows),
                },
                "metrics": {},
                "curve": [],
                "events": [],
                "source": "local.postgres.manager_fund_tenures+fund_nav+research_reports",
                "simulation_used": False,
            })

        fund_series = [{"date": item["date"], "nav": item["nav"]} for item in metric_rows]
        benchmark_series = [
            {"date": item["date"], "nav": item["benchmark_nav"]}
            for item in metric_rows
            if item.get("benchmark_nav") is not None
        ]
        metrics: Dict[str, Any] = {}
        metrics.update(self.metric_factory.calculate_return_metrics(fund_series))
        metrics.update(self.metric_factory.calculate_risk_metrics(fund_series))
        if len(benchmark_series) >= 2:
            metrics.update(self.metric_factory.calculate_relative_metrics(fund_series, benchmark_series))

        fund_base = metric_rows[0]["nav"]
        benchmark_base = next(
            (item["benchmark_nav"] for item in metric_rows if item.get("benchmark_nav") is not None),
            None,
        )
        curve = [{
            "date": item["date"],
            "fund_return": item["nav"] / fund_base - 1,
            "benchmark_return": (
                item["benchmark_nav"] / benchmark_base - 1
                if benchmark_base and item.get("benchmark_nav") is not None else None
            ),
        } for item in metric_rows]
        actual_start = metric_rows[0]["date"]
        actual_end = metric_rows[-1]["date"]
        tenure_coverage = (
            build_manager_tenure_coverage(
                tenure_start,
                actual_start,
                actual_end,
                len(metric_rows),
            )
            if period == "tenure"
            else None
        )
        ranking_input = {
            "fund_code": actual_code,
            "entity_id": selected.get("entity_id"),
            "category": selected.get("category"),
            "tenure_return": metrics.get("total_return"),
            "annualized_return": metrics.get("annualized_return"),
            "record_breaking_days_ratio": metrics.get("record_breaking_days_ratio"),
            "max_drawdown": metrics.get("max_drawdown"),
            "sharpe_ratio": metrics.get("sharpe_ratio"),
            "metric_observations": metrics.get("observations"),
            "metric_start_date": actual_start,
            "metric_as_of_date": actual_end,
        }
        if tenure_coverage:
            ranking_input.update({
                "tenure_coverage_status": tenure_coverage.get("tenure_coverage_status"),
                "tenure_coverage_ratio": tenure_coverage.get("tenure_coverage_ratio"),
            })
        peer_ranking = self.peer_ranking_service.rank(ranking_input)
        events = self._events(resolved_id, actual_start, actual_end, curve)

        return self._safe({
            "status": "available",
            "manager_id": resolved_id,
            "manager_name": manager.get("name"),
            "products": products,
            "selected_product": {**selected, "actual_curve_code": actual_code},
            "period": period,
            "period_label": period_label,
            "requested_start_date": requested_start,
            "requested_end_date": requested_end,
            "actual_start_date": actual_start,
            "actual_end_date": actual_end,
            "tenure_coverage": tenure_coverage,
            "available_years": available_years,
            "period_options": self.PERIOD_OPTIONS,
            "benchmark": {
                "code": performance_benchmark_code,
                "name": performance_benchmark_name,
                "type": performance_benchmark_type,
                "classification_code": benchmark_code,
                "components": contract_components,
                "status": benchmark_status,
                "observations": len(benchmark_series),
                "coverage": len(benchmark_series) / len(metric_rows),
                "source": "local.postgres.fund_nav.benchmark_nav" if benchmark_status == "available" else None,
            },
            "metrics": metrics,
            "peer_ranking": peer_ranking,
            "curve": curve,
            "events": events,
            "evidence": {
                "nav_observations": len(metric_rows),
                "memo_event_count": len(events),
                "manager_tenure_start": tenure_start,
                "manager_tenure_end": selected.get("end_date"),
            },
            "source": "local.postgres.manager_fund_tenures+fund_nav+research_reports",
            "simulation_used": False,
        })

    def _load_nav(
        self,
        selected: Dict[str, Any],
        start_date: date,
        end_date: date,
        requested_code: Optional[str],
    ) -> Tuple[str, List[Dict[str, Any]]]:
        candidates = list(dict.fromkeys([
            str(requested_code or "").strip().upper(),
            str(selected.get("fund_code") or "").strip().upper(),
            *[str(code or "").strip().upper() for code in selected.get("share_codes") or []],
        ]))
        candidates = [code for code in candidates if code]
        fallback: Tuple[str, List[Dict[str, Any]]] = (candidates[0], [])
        for code in candidates:
            rows = self.nav_repo.get_nav_series(code, start_date.isoformat(), end_date.isoformat())
            if rows and not fallback[1]:
                fallback = (code, rows)
            if len(self._normalize_rows(rows)) >= 2:
                return code, rows
        return fallback

    @staticmethod
    def _canonical_products(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            code = str(row.get("fund_code") or "").strip().upper()
            if not code:
                continue
            entity = fund_product_identity(row)
            current = bool(row.get("is_current"))
            end_date = str(row.get("end_date") or "")[:10]
            grouped.setdefault(f"{entity}:{current}:{end_date}", []).append(row)

        products = []
        for group in grouped.values():
            representative = sorted(group, key=lambda item: (
                not bool(item.get("is_primary")),
                (item.get("performance_snapshot") or {}).get("status") != "available"
                if isinstance(item.get("performance_snapshot"), dict) else True,
                str(item.get("fund_code") or ""),
            ))[0]
            starts = [FundManagerCareerService._parse_date(item.get("start_date")) for item in group]
            starts = [item for item in starts if item]
            performance = representative.get("performance_snapshot")
            fund_code = str(representative.get("fund_code") or "").strip().upper()
            start_date = min(starts).isoformat() if starts else str(representative.get("start_date") or "")[:10]
            products.append({
                "fund_code": fund_code,
                "fund_name": representative.get("fund_name") or representative.get("fund_code"),
                "category": representative.get("peer_group_name") or representative.get("strategy_name") or representative.get("type"),
                "start_date": start_date,
                "end_date": representative.get("end_date"),
                "is_current": bool(representative.get("is_current")),
                "entity_id": representative.get("entity_id"),
                "tenure_key": f"{fund_code}::{start_date}",
                "share_codes": [str(item.get("fund_code") or "").strip().upper() for item in group],
                "share_count": len(group),
                "metric_status": (
                    performance.get("status") if isinstance(performance, dict) else "unavailable"
                ),
                "nav_observations": (
                    performance.get("observations") if isinstance(performance, dict) else None
                ),
            })
        return sorted(products, key=lambda item: (
            bool(item.get("is_current")),
            item.get("metric_status") == "available",
            str(item.get("start_date") or ""),
            str(item.get("fund_code") or ""),
        ), reverse=True)

    @staticmethod
    def _select_product(
        products: List[Dict[str, Any]],
        fund_code: Optional[str],
        tenure_start_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        requested = str(fund_code or "").strip().upper()
        if not requested:
            return products[0]
        candidates = [
            item for item in products
            if requested == item.get("fund_code") or requested in (item.get("share_codes") or [])
        ]
        requested_start = FundManagerCareerService._parse_date(tenure_start_date)
        selected = next((
            item for item in candidates
            if requested_start is None or FundManagerCareerService._parse_date(item.get("start_date")) == requested_start
        ), None)
        if not selected:
            raise ValueError(f"Fund tenure does not belong to manager: {requested}")
        return selected

    def _resolve_range(
        self,
        period: str,
        tenure_start: date,
        tenure_end: date,
        custom_start: Optional[str],
        custom_end: Optional[str],
    ) -> Tuple[date, date, str]:
        key = str(period or "tenure").strip().lower()
        end = tenure_end
        if key == "tenure":
            start, label = tenure_start, "任职以来"
        elif key == "ytd":
            start, label = date(end.year, 1, 1), "今年以来"
        elif key in {"3m", "6m", "1y", "3y", "5y"}:
            days = {"3m": 92, "6m": 183, "1y": 365, "3y": 1096, "5y": 1827}[key]
            start = end - timedelta(days=days)
            label = dict((item["key"], item["label"]) for item in self.PERIOD_OPTIONS)[key]
        elif key.startswith("year:"):
            try:
                year = int(key.split(":", 1)[1])
            except ValueError as error:
                raise ValueError("Invalid natural year") from error
            start, end, label = date(year, 1, 1), date(year, 12, 31), str(year)
        elif key == "custom":
            start = self._parse_date(custom_start)
            custom_end_date = self._parse_date(custom_end)
            if start is None or custom_end_date is None:
                raise ValueError("Custom range requires start_date and end_date")
            end, label = custom_end_date, "自定义"
        else:
            raise ValueError(f"Unsupported period: {key}")
        start = max(start, tenure_start)
        end = min(end, tenure_end, self.today)
        if start > end:
            raise ValueError("Selected range is outside manager tenure")
        return start, end, label

    @staticmethod
    def _normalize_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized: Dict[date, Dict[str, Any]] = {}
        for row in rows:
            item_date = FundManagerCareerService._parse_date(row.get("date") or row.get("trade_date"))
            value = FundManagerCareerService._positive_number(
                row.get("accum_nav") or row.get("adj_nav") or row.get("nav") or row.get("unit_nav")
            )
            if item_date is None or value is None:
                continue
            normalized[item_date] = {
                "date": item_date,
                "nav": value,
                "benchmark_nav": FundManagerCareerService._positive_number(row.get("benchmark_nav")),
            }
        return [normalized[key] for key in sorted(normalized)]

    def _events(
        self,
        manager_id: str,
        start_date: date,
        end_date: date,
        curve: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        rows = self.report_repo.list_reports_for_manager_exact(manager_id, limit=200)
        curve_dates = [self._parse_date(item.get("date")) for item in curve]
        curve_dates = [item for item in curve_dates if item]
        events = []
        for row in rows:
            report_date = self._parse_date(row.get("report_date"))
            if report_date is None or not start_date <= report_date <= end_date:
                continue
            title = str(row.get("title") or "无标题纪要")
            event_type = "定期报告" if any(word in title for word in ("季报", "年报")) else "调研纪要"
            events.append({
                "id": str(row.get("id") or ""),
                "date": report_date,
                "chart_date": self._nearest_date(report_date, curve_dates),
                "type": event_type,
                "title": title,
                "summary": str(row.get("summary") or "")[:240],
                "source": row.get("source"),
                "tags": row.get("tags") or [],
                "local_relative_path": row.get("local_relative_path"),
            })
        return sorted(events, key=lambda item: item["date"], reverse=True)

    @staticmethod
    def _nearest_date(target: date, dates: List[date]) -> Optional[date]:
        if not dates:
            return None
        index = bisect_left(dates, target)
        if index >= len(dates):
            return dates[-1]
        if index == 0:
            return dates[0]
        before, after = dates[index - 1], dates[index]
        return before if target - before <= after - target else after

    @staticmethod
    def _available_years(start: date, end: date) -> List[int]:
        return list(range(end.year, start.year - 1, -1))

    @staticmethod
    def _parse_date(value: Any) -> Optional[date]:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        text = str(value or "").strip()[:10]
        try:
            return date.fromisoformat(text) if text else None
        except ValueError:
            return None

    @staticmethod
    def _positive_number(value: Any) -> Optional[float]:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    @classmethod
    def _safe(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {key: cls._safe(item) for key, item in value.items()}
        if isinstance(value, list):
            return [cls._safe(item) for item in value]
        if isinstance(value, (date, datetime, UUID, Decimal)):
            return str(value)
        return value

    @property
    def manager_repo(self):
        if self._manager_repo is None:
            from repositories import get_manager_repo
            self._manager_repo = get_manager_repo()
        return self._manager_repo

    @property
    def nav_repo(self):
        if self._nav_repo is None:
            from repositories import get_nav_repo
            self._nav_repo = get_nav_repo()
        return self._nav_repo

    @property
    def classification_repo(self):
        if self._classification_repo is None:
            from repositories import get_fund_classification_repo
            self._classification_repo = get_fund_classification_repo()
        return self._classification_repo

    @property
    def report_repo(self):
        if self._report_repo is None:
            from repositories.local_research_folder_repo import PostgresLocalResearchFolderRepo
            self._report_repo = PostgresLocalResearchFolderRepo()
        return self._report_repo

    @property
    def peer_ranking_service(self):
        if self._peer_ranking_service is None:
            from services.manager_tenure_peer_ranking_service import ManagerTenurePeerRankingService

            self._peer_ranking_service = ManagerTenurePeerRankingService(
                classification_repo=self.classification_repo,
            )
        return self._peer_ranking_service
