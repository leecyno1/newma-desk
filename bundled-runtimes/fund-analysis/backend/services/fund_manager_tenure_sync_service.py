"""从真实 Tushare 任职记录补齐基金经理与任期评价数据。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Dict, Iterable, List, Optional

from services.manager_tenure_metric_service import ManagerTenureMetricService
from services.manager_tenure_coverage import build_manager_tenure_coverage
from services.metric_factory import MetricFactory
from services.fund_nav_evidence_service import FundNavDataEnrichmentService


class FundManagerTenureSyncService:
    """同步经理关系、现任团队起点和任期净值指标。"""

    def __init__(
        self,
        data_service: Any,
        fund_repo: Optional[Any] = None,
        manager_repo: Optional[Any] = None,
        profile_repo: Optional[Any] = None,
        classification_repo: Optional[Any] = None,
        tenure_metric_service: Optional[Any] = None,
        nav_repo: Optional[Any] = None,
    ):
        self.data_service = data_service
        self._fund_repo = fund_repo
        self._manager_repo = manager_repo
        self._profile_repo = profile_repo
        self._classification_repo = classification_repo
        self._nav_repo = nav_repo
        self.tenure_metric_service = tenure_metric_service or ManagerTenureMetricService()
        self.metric_factory = MetricFactory()
        self._benchmark_cache: Dict[tuple[str, str, str], List[Dict[str, Any]]] = {}

    def sync_fund(self, wind_code: str) -> Dict[str, Any]:
        code = str(wind_code or "").strip().upper()
        fund = self.fund_repo.get_fund(code)
        if not fund:
            return {"wind_code": code, "status": "skipped", "reason": "fund_not_found"}
        company = self._fund_company(fund)

        rows = self.data_service.get_fund_managers(code)
        active = [row for row in rows if row.get("is_current_manager") and row.get("manager_id")]
        active_ids = list(dict.fromkeys(str(row["manager_id"]) for row in active))
        begin_dates = sorted(
            str(row.get("begin_date"))[:10]
            for row in active
            if row.get("begin_date")
        )
        if not active_ids or not begin_dates:
            return {
                "wind_code": code,
                "status": "skipped",
                "reason": "current_manager_unavailable",
                "manager_rows": len(rows),
            }

        synced_at = datetime.now(UTC).isoformat()
        manager_write_failed = []
        manager_rows: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            manager_id = str(row.get("manager_id") or "").strip()
            if manager_id:
                manager_rows.setdefault(manager_id, []).append(row)
        for manager_id, history in manager_rows.items():
            row = next((item for item in history if item.get("is_current_manager")), None)
            row = row or max(history, key=lambda item: str(item.get("begin_date") or ""))
            is_current = bool(row.get("is_current_manager"))
            saved = self.manager_repo.upsert_manager(manager_id, {
                "name": row.get("name") or manager_id.split("|")[0],
                "company": company,
                "education": row.get("education") or "",
                "experience_years": self._years_since(row.get("begin_date")),
                "management_years": self._years_since(row.get("begin_date")),
                "current_funds": [code] if is_current else [],
                "historical_performance": {
                    "fund_code": code,
                    "fund_tenure_start": row.get("begin_date"),
                    "fund_tenure_end": row.get("end_date"),
                    "is_current_manager": is_current,
                },
                "raw_data": {
                    "source": "tushare.fund_manager",
                    "synced_at": synced_at,
                    "fund_code": code,
                    "manager_id": manager_id,
                    "fund_manager_row": row.get("raw_data") or row,
                },
            })
            if not saved:
                manager_write_failed.append(manager_id)

        if manager_write_failed:
            return {
                "wind_code": code,
                "status": "failed",
                "reason": "manager_update_failed",
                "manager_ids": manager_write_failed,
            }

        tenure_start = max(begin_dates)
        if not self.fund_repo.update_manager_assignments(code, active_ids, {
            "source": "tushare.fund_manager",
            "synced_at": synced_at,
            "manager_ids": active_ids,
            "manager_tenure_start": tenure_start,
        }):
            return {"wind_code": code, "status": "failed", "reason": "fund_update_failed"}

        context = self.classification_repo.get_classification_context(code) or {}
        benchmark = context.get("benchmark_mapping") or {}
        self.profile_repo.upsert_manager_tenure(
            wind_code=code,
            manager_tenure_start=tenure_start,
            primary_benchmark=str(benchmark.get("benchmark_code") or benchmark.get("benchmark_name") or ""),
            peer_group=str(context.get("peer_group_name") or context.get("peer_group_key") or ""),
            evidence={
                "manager_tenure": {
                    "source": "tushare.fund_manager",
                    "current_team_latest_begin_date": tenure_start,
                    "manager_ids": active_ids,
                    "synced_at": synced_at,
                }
            },
        )
        metrics = self.tenure_metric_service.calculate_and_save_for_fund(code)
        return {
            "wind_code": code,
            "status": "synced",
            "manager_ids": active_ids,
            "manager_count": len(active_ids),
            "manager_tenure_start": tenure_start,
            "tenure_metrics_saved": int(metrics.get("saved") or 0),
            "tenure_metric_reason": metrics.get("reason"),
        }

    def sync_manager(self, manager_id: str) -> Dict[str, Any]:
        """一次同步一个经理的完整产品任职史。"""
        requested_id = str(manager_id or "").strip()
        manager = self.manager_repo.get_manager(requested_id)
        resolved_id = str((manager or {}).get("wind_code") or requested_id)
        rows = self.data_service.get_manager_tenures(resolved_id)
        if not rows:
            return {"manager_id": resolved_id, "status": "skipped", "reason": "manager_tenures_unavailable"}

        authoritative_id = next(
            (
                str(row.get("manager_id") or "").strip()
                for row in rows
                if str(row.get("manager_id") or "").strip()
            ),
            resolved_id,
        )
        resolved_id = authoritative_id or resolved_id
        fund_by_code: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            fund_code = str(row.get("fund_code") or "").strip().upper()
            if fund_code and fund_code not in fund_by_code:
                fund = self.fund_repo.get_fund(fund_code)
                if fund:
                    fund_by_code[fund_code] = fund

        manager_bootstrapped = False
        if not manager:
            identity_parts = (resolved_id.split("|") + ["", ""])[0:3]
            earliest_start = min(
                (str(row.get("start_date"))[:10] for row in rows if row.get("start_date")),
                default="",
            )
            current_codes = list(dict.fromkeys(
                str(row.get("fund_code") or "").strip().upper()
                for row in rows
                if row.get("is_current") and str(row.get("fund_code") or "").strip()
            ))
            company = next(
                (self._fund_company(fund) for fund in fund_by_code.values() if self._fund_company(fund)),
                "",
            )
            saved = self.manager_repo.upsert_manager(resolved_id, {
                "name": identity_parts[0] or resolved_id,
                "company": company,
                "education": identity_parts[2],
                "experience_years": None,
                "management_years": self._years_since(earliest_start) if earliest_start else None,
                "current_funds": current_codes,
                "historical_performance": {
                    "tenure_count": len(rows),
                    "current_tenure_count": sum(bool(row.get("is_current")) for row in rows),
                    "source": "tushare.fund_manager",
                },
                "raw_data": {
                    "source": "tushare.fund_manager",
                    "manager_id": resolved_id,
                    "gender": identity_parts[1],
                    "education": identity_parts[2],
                    "bootstrapped_from_manager_tenures": True,
                },
            })
            if not saved:
                return {"manager_id": resolved_id, "status": "failed", "reason": "manager_bootstrap_failed"}
            manager_bootstrapped = True

        local_rows = []
        missing_funds = []
        nav_points_saved = 0
        benchmark_points_saved = 0
        for row in rows:
            fund_code = str(row.get("fund_code") or "").strip().upper()
            fund = fund_by_code.get(fund_code)
            if not fund:
                missing_funds.append(row.get("fund_code"))
                continue
            performance = self._tenure_performance(row)
            nav_points_saved += int(performance.get("nav_points_saved") or 0)
            benchmark_points_saved += int(performance.get("benchmark_observations") or 0)
            local_rows.append({
                **row,
                "fund_name": fund.get("name") or row.get("fund_name"),
                "performance_snapshot": performance,
            })

        if not self.manager_repo.replace_fund_tenures(resolved_id, local_rows):
            return {"manager_id": resolved_id, "status": "failed", "reason": "tenure_replace_failed"}

        active_rows = [row for row in local_rows if row.get("is_current")]
        for row in active_rows:
            fund_code = str(row["fund_code"])
            fund = self.fund_repo.get_fund(fund_code) or {}
            active_ids = list(dict.fromkeys([*(fund.get("manager_ids") or []), resolved_id]))
            self.fund_repo.update_manager_assignments(fund_code, active_ids, {
                "source": "tushare.fund_manager",
                "manager_ids": active_ids,
                "manager_tenure_start": row.get("start_date"),
                "synced_at": datetime.now(UTC).isoformat(),
            })

        return {
            "manager_id": resolved_id,
            "status": "synced",
            "manager_bootstrapped": manager_bootstrapped,
            "tenure_count": len(local_rows),
            "current_tenure_count": len(active_rows),
            "historical_tenure_count": len(local_rows) - len(active_rows),
            "current_fund_codes": list(dict.fromkeys(str(row["fund_code"]) for row in active_rows)),
            "missing_local_fund_codes": [str(code) for code in missing_funds if code],
            "nav_points_saved": nav_points_saved,
            "benchmark_points_saved": benchmark_points_saved,
        }

    def sync_fund_history(self, wind_code: str) -> Dict[str, Any]:
        """现场补齐一只基金的全部经理任职记录，不触发全量产品净值同步。"""
        code = str(wind_code or "").strip().upper()
        fund = self.fund_repo.get_fund(code)
        if not fund:
            return {"wind_code": code, "status": "failed", "reason": "fund_not_found"}

        rows = self.data_service.get_fund_managers(code)
        if not rows:
            return {"wind_code": code, "status": "skipped", "reason": "manager_rows_unavailable"}

        company = self._fund_company(fund)
        synced_at = datetime.now(UTC).isoformat()
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            manager_id = str(row.get("manager_id") or "").strip()
            begin_date = str(row.get("begin_date") or "")[:10]
            if manager_id and begin_date:
                grouped.setdefault(manager_id, []).append(row)

        saved = 0
        active_ids = []
        active_begin_dates = []
        for manager_id, history in grouped.items():
            representative = next((row for row in history if row.get("is_current_manager")), None)
            representative = representative or max(history, key=lambda row: str(row.get("begin_date") or ""))
            is_current = any(bool(row.get("is_current_manager")) for row in history)
            if not self.manager_repo.upsert_manager(manager_id, {
                "name": representative.get("name") or manager_id.split("|")[0],
                "company": company,
                "education": representative.get("education") or "",
                "experience_years": self._years_since(min(str(row.get("begin_date")) for row in history)),
                "management_years": self._years_since(min(str(row.get("begin_date")) for row in history)),
                "current_funds": [code] if is_current else [],
                "historical_performance": {
                    "fund_code": code,
                    "tenure_count": len(history),
                    "source": "tushare.fund_manager",
                },
                "raw_data": {
                    "source": "tushare.fund_manager",
                    "synced_at": synced_at,
                    "fund_code": code,
                    "manager_id": manager_id,
                },
            }):
                return {"wind_code": code, "status": "failed", "reason": "manager_update_failed"}

            tenure_rows = [{
                "fund_code": code,
                "fund_name": row.get("fund_name") or fund.get("name") or code,
                "start_date": row.get("begin_date"),
                "end_date": row.get("end_date"),
                "is_current": bool(row.get("is_current_manager")),
                "source": "tushare.fund_manager",
                "raw_data": row.get("raw_data") or row,
            } for row in history]
            saved += int(self.manager_repo.upsert_fund_tenures(manager_id, tenure_rows) or 0)

            if is_current:
                active_ids.append(manager_id)
                active_begin_dates.extend(
                    str(row.get("begin_date"))[:10]
                    for row in history
                    if row.get("is_current_manager") and row.get("begin_date")
                )

        if not saved:
            return {"wind_code": code, "status": "failed", "reason": "tenure_write_failed"}

        active_ids = list(dict.fromkeys(active_ids))
        tenure_start = max(active_begin_dates) if active_begin_dates else None
        if active_ids and not self.fund_repo.update_manager_assignments(code, active_ids, {
            "source": "tushare.fund_manager",
            "synced_at": synced_at,
            "manager_ids": active_ids,
            "manager_tenure_start": tenure_start,
        }):
            return {"wind_code": code, "status": "failed", "reason": "fund_update_failed"}

        return {
            "wind_code": code,
            "status": "synced",
            "manager_count": len(grouped),
            "current_manager_count": len(active_ids),
            "tenure_records_saved": saved,
            "manager_ids": list(grouped),
            "manager_tenure_start": tenure_start,
            "source": "tushare.fund_manager",
        }

    def _tenure_performance(self, tenure: Dict[str, Any]) -> Dict[str, Any]:
        fund_code = str(tenure.get("fund_code") or "")
        start_date = str(tenure.get("start_date") or "")[:10]
        end_date = str(tenure.get("end_date") or datetime.now(UTC).date().isoformat())[:10]
        if not fund_code or not start_date:
            return {"status": "unavailable", "reason": "invalid_tenure_period"}
        try:
            nav_series = self.data_service.get_fund_nav(fund_code, start_date, end_date)
        except Exception as exc:
            return {"status": "unavailable", "reason": str(exc)[:180]}
        fund = self.fund_repo.get_fund(fund_code) or {}
        enrichment = FundNavDataEnrichmentService(
            self.data_service,
            classification_adapter=self.classification_repo,
        ).enrich(
            wind_code=fund_code,
            fund_type=fund.get("type"),
            nav_series=nav_series,
            start_date=start_date,
            end_date=end_date,
        )
        nav_series = enrichment.get("nav_series") or nav_series
        points = self.metric_factory._normalize_nav_series(nav_series)
        if len(points) < 2:
            return {"status": "unavailable", "reason": "insufficient_nav", "observations": len(points)}
        benchmark_code = str(enrichment.get("benchmark_code") or "").strip().upper()
        benchmark_series = [
            {
                "date": item.get("date") or item.get("trade_date"),
                "nav": item.get("benchmark_nav"),
            }
            for item in nav_series
            if item.get("benchmark_nav") is not None
        ]
        benchmark_points = self.metric_factory._normalize_nav_series(benchmark_series)
        benchmark_by_date = {day.isoformat(): value for day, value in benchmark_points}
        matched_benchmark_points = sum(
            str(item.get("date") or "")[:10] in benchmark_by_date
            for item in nav_series
        )
        persisted_nav = [
            {
                **item,
                "benchmark_nav": benchmark_by_date.get(str(item.get("date") or "")[:10]),
            }
            for item in nav_series
        ]
        nav_saved = self.nav_repo.upsert_nav_series(fund_code, persisted_nav, replace_range=True)
        normalized = [{"date": day, "nav": nav} for day, nav in points]
        coverage = build_manager_tenure_coverage(
            start_date,
            points[0][0],
            points[-1][0],
            len(points),
        )
        return_metrics = self.metric_factory.calculate_return_metrics(normalized)
        risk_metrics = self.metric_factory.calculate_risk_metrics(normalized)
        relative_metrics = self.metric_factory.calculate_relative_metrics(
            normalized,
            [{"date": day, "nav": nav} for day, nav in benchmark_points],
        ) if benchmark_points else {}
        return {
            "status": "available",
            "start_date": points[0][0].isoformat(),
            "end_date": points[-1][0].isoformat(),
            "observations": len(points),
            "total_return": return_metrics.get("total_return"),
            "annualized_return": return_metrics.get("annualized_return"),
            "record_breaking_days_ratio": return_metrics.get("record_breaking_days_ratio"),
            "max_drawdown": risk_metrics.get("max_drawdown"),
            "annualized_volatility": risk_metrics.get("annualized_volatility"),
            "downside_risk": risk_metrics.get("downside_risk"),
            "sharpe_ratio": risk_metrics.get("sharpe_ratio"),
            "sortino_ratio": risk_metrics.get("sortino_ratio"),
            "benchmark_code": benchmark_code or None,
            "benchmark_observations": matched_benchmark_points,
            "benchmark_return": relative_metrics.get("benchmark_return"),
            "excess_return": relative_metrics.get("excess_return"),
            "nav_points_saved": len(persisted_nav) if nav_saved else 0,
            "source": "tushare.fund_nav",
            **coverage,
        }

    def _benchmark_code(self, fund_code: str) -> str:
        context = self.classification_repo.get_classification_context(fund_code) or {}
        mapping = context.get("benchmark_mapping") or {}
        return str(mapping.get("benchmark_code") or "").strip().upper()

    def _benchmark_series(self, benchmark_code: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        if not benchmark_code or not hasattr(self.data_service, "get_benchmark_nav"):
            return []
        cache_key = (benchmark_code, start_date, end_date)
        if cache_key not in self._benchmark_cache:
            try:
                self._benchmark_cache[cache_key] = self.data_service.get_benchmark_nav(
                    benchmark_code,
                    start_date,
                    end_date,
                ) or []
            except Exception:
                self._benchmark_cache[cache_key] = []
        return self._benchmark_cache[cache_key]

    def sync_funds(self, wind_codes: Iterable[str]) -> Dict[str, Any]:
        results = [self.sync_fund(code) for code in wind_codes]
        return {
            "requested": len(results),
            "synced": sum(item["status"] == "synced" for item in results),
            "skipped": sum(item["status"] == "skipped" for item in results),
            "failed": sum(item["status"] == "failed" for item in results),
            "tenure_metrics_saved": sum(item.get("tenure_metrics_saved", 0) for item in results),
            "results": results,
        }

    @staticmethod
    def _years_since(value: Any) -> float:
        try:
            start = datetime.fromisoformat(str(value)[:10]).date()
        except (TypeError, ValueError):
            return 0.0
        return round(max(0, (datetime.now(UTC).date() - start).days) / 365.25, 2)

    @staticmethod
    def _fund_company(fund: Dict[str, Any]) -> str:
        raw_data = fund.get("raw_data") if isinstance(fund.get("raw_data"), dict) else {}
        for value in (
            fund.get("company"),
            raw_data.get("company"),
            (raw_data.get("universe") or {}).get("company") if isinstance(raw_data.get("universe"), dict) else None,
            (raw_data.get("info") or {}).get("company") if isinstance(raw_data.get("info"), dict) else None,
        ):
            company = str(value or "").strip()
            if company:
                return company
        return ""

    @property
    def fund_repo(self):
        if self._fund_repo is None:
            from repositories import get_fund_repo
            self._fund_repo = get_fund_repo()
        return self._fund_repo

    @property
    def manager_repo(self):
        if self._manager_repo is None:
            from repositories import get_manager_repo
            self._manager_repo = get_manager_repo()
        return self._manager_repo

    @property
    def profile_repo(self):
        if self._profile_repo is None:
            from repositories import get_research_profile_repo
            self._profile_repo = get_research_profile_repo()
        return self._profile_repo

    @property
    def classification_repo(self):
        if self._classification_repo is None:
            from repositories import get_fund_classification_repo
            self._classification_repo = get_fund_classification_repo()
        return self._classification_repo

    @property
    def nav_repo(self):
        if self._nav_repo is None:
            from repositories import get_nav_repo
            self._nav_repo = get_nav_repo()
        return self._nav_repo
