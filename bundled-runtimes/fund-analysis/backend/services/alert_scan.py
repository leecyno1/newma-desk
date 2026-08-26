"""
预警扫描服务
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from repositories import get_alert_repo, get_fund_pool_repo, get_metric_snapshot_repo


class AlertScanService:
    def __init__(
        self,
        pool_repo=None,
        metric_repo=None,
        alert_repo=None,
        peer_service=None,
        sales_rule_repo=None,
        today: Optional[date] = None,
        max_members_per_status: Optional[int] = None,
        include_peer_metrics: bool = True,
    ):
        self.pool_repo = pool_repo or get_fund_pool_repo()
        self.metric_repo = metric_repo or get_metric_snapshot_repo()
        self.alert_repo = alert_repo or get_alert_repo()
        self.sales_rule_repo = sales_rule_repo
        self._sales_rule_engine = None
        if peer_service is None:
            from services.peer_comparison_service import PeerComparisonService

            peer_service = PeerComparisonService()
        self.peer_service = peer_service
        self.today = today or date.today()
        self.max_members_per_status = max_members_per_status
        self.include_peer_metrics = include_peer_metrics

    def scan(self) -> Dict[str, Any]:
        created_events: List[Dict[str, Any]] = []
        pools = self.pool_repo.list_pools()

        for pool in pools:
            for status in ["watch", "core", "candidate"]:
                members = self.pool_repo.list_members(pool["id"], status=status)
                if self.max_members_per_status is not None:
                    members = members[:max(0, self.max_members_per_status)]
                for member in members:
                    sales_rule_issues = self._sales_rule_evidence_issues(member)
                    if sales_rule_issues:
                        wind_code = self._member_wind_code(member)
                        created_events.append(self.alert_repo.create_event(
                            rule_id=None,
                            fund_id=member["fund_id"],
                            pool_member_id=member["id"],
                            event_type="sales_rule_evidence",
                            severity="high" if status in {"candidate", "core"} else "medium",
                            title="销售规则/R1-R5 证据过期或待补",
                            message=f"销售规则买前证据未满足 30 天复核窗口：{'；'.join(sales_rule_issues[:5])}",
                            status="new",
                            details={
                                "pool_id": pool["id"],
                                "member_status": status,
                                "wind_code": wind_code,
                                "fund_code": wind_code,
                                "purchase_plan": "sip",
                                "planned_amount": 1000,
                                "evidence_window_days": 30,
                                "missing_items": sales_rule_issues,
                            },
                        ))

                    metric_map = self._metric_map(self.metric_repo.get_latest_panel("fund", member["fund_id"]))
                    drawdown = metric_map.get("max_drawdown")
                    if drawdown is not None and drawdown <= Decimal("-0.15"):
                        created_events.append(self.alert_repo.create_event(
                            rule_id=None,
                            fund_id=member["fund_id"],
                            pool_member_id=member["id"],
                            event_type="drawdown",
                            severity="high" if drawdown <= Decimal("-0.2") else "medium",
                            title="回撤超过阈值",
                            message=f"当前最大回撤 {drawdown}，已超过监控阈值",
                            status="new",
                            details={"current_drawdown": float(drawdown), "pool_id": pool["id"]},
                        ))
                    review_date = self._parse_date(member.get("next_review_date"))
                    if review_date is not None and review_date < self.today:
                        overdue_days = (self.today - review_date).days
                        created_events.append(self.alert_repo.create_event(
                            rule_id=None,
                            fund_id=member["fund_id"],
                            pool_member_id=member["id"],
                            event_type="review_due",
                            severity="high" if overdue_days >= 30 and status == "core" else "medium",
                            title="基金池成员复核到期",
                            message=f"下次复核日 {review_date.isoformat()} 已过期 {overdue_days} 天",
                            status="new",
                            details={"pool_id": pool["id"], "member_status": status, "overdue_days": overdue_days},
                        ))
                    weak_peer_metrics = self._weak_peer_metrics(member["fund_id"]) if self.include_peer_metrics else []
                    if weak_peer_metrics:
                        created_events.append(self.alert_repo.create_event(
                            rule_id=None,
                            fund_id=member["fund_id"],
                            pool_member_id=member["id"],
                            event_type="peer_percentile",
                            severity="high" if any(item["percentile"] <= 20 for item in weak_peer_metrics) else "medium",
                            title="同类分位进入尾部区间",
                            message="；".join([f"{item['label']} 分位 {item['percentile']}" for item in weak_peer_metrics]),
                            status="new",
                            details={"pool_id": pool["id"], "member_status": status, "weak_peer_metrics": weak_peer_metrics},
                        ))

        return {
            "status": "completed",
            "created": len(created_events),
            "events": created_events,
        }

    def _weak_peer_metrics(self, fund_id: str) -> List[Dict[str, Any]]:
        try:
            percentiles = self.peer_service.build_peer_percentiles(fund_id, window="1y").get("metrics", {})
        except Exception:
            return []
        watched = {
            "professional_score": "专业评分",
            "annualized_return": "1Y 年化收益",
        }
        weak_metrics = []
        for metric_name, label in watched.items():
            metric = percentiles.get(metric_name) or {}
            percentile = metric.get("percentile")
            if percentile is None:
                continue
            try:
                percentile_value = float(percentile)
            except Exception:
                continue
            if percentile_value <= 25:
                weak_metrics.append({
                    "metric_name": metric_name,
                    "label": label,
                    "percentile": round(percentile_value, 2),
                })
        return weak_metrics

    def _sales_rule_evidence_issues(self, member: Dict[str, Any]) -> List[str]:
        rule = self._latest_sales_rule(member)
        if not rule:
            return ["销售规则整条待补", "R1-R5 风险等级缺少 30 天来源背书"]

        source_date = self._parse_date(rule.get("source_updated_at"))
        issues: List[str] = []
        if source_date is None:
            issues.append("销售规则来源日期待补")
        else:
            age_days = (self.today - source_date).days
            if age_days < 0:
                issues.append("销售规则来源日期晚于当前扫描日，需重新核验")
            elif age_days > 30:
                issues.append(f"销售规则来源已过期 {age_days} 天，超过 30 天买前复核窗口")

        risk_level = str(rule.get("risk_level") or "").strip().upper()
        if risk_level not in {"R1", "R2", "R3", "R4", "R5"}:
            issues.append("R1-R5 风险等级待补")
        elif source_date is None or (self.today - source_date).days < 0 or (self.today - source_date).days > 30:
            issues.append(f"{risk_level} 风险等级缺少 30 天内来源背书")

        purchase_status = str(rule.get("purchase_status") or "").strip().lower()
        if not purchase_status or purchase_status == "unknown":
            issues.append("申购状态待补")
        if rule.get("purchase_fee_rate") is None:
            issues.append("申购费率待补")
        if not rule.get("redemption_fee_rules"):
            issues.append("赎回费规则待补")

        return issues

    def _latest_sales_rule(self, member: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if self.sales_rule_repo is not None:
            return self.sales_rule_repo.get_latest_rule(member)
        wind_code = self._member_wind_code(member)
        if not wind_code:
            return None
        try:
            from sqlalchemy import create_engine, text
            try:
                from backend.database import get_database_url
            except ModuleNotFoundError:
                from database import get_database_url

            if self._sales_rule_engine is None:
                self._sales_rule_engine = create_engine(get_database_url(), pool_pre_ping=True)
            sql = text("""
                SELECT
                    wind_code,
                    platform,
                    purchase_status,
                    purchase_fee_rate,
                    redemption_fee_rules,
                    risk_level,
                    source_updated_at,
                    updated_at
                FROM fund_sales_rules
                WHERE UPPER(wind_code) = UPPER(:wind_code)
                ORDER BY source_updated_at DESC NULLS LAST, updated_at DESC NULLS LAST
                LIMIT 1
            """)
            with self._sales_rule_engine.connect() as conn:
                row = conn.execute(sql, {"wind_code": wind_code}).fetchone()
            if not row:
                return None
            data = dict(row._mapping)
            for key, value in list(data.items()):
                if isinstance(value, (datetime, date)):
                    data[key] = value.isoformat()
            return data
        except Exception:
            return None

    @staticmethod
    def _member_wind_code(member: Dict[str, Any]) -> str:
        return str(
            member.get("fund_wind_code")
            or member.get("wind_code")
            or member.get("fund_code")
            or member.get("fund_id")
            or ""
        ).strip().upper()

    @staticmethod
    def _metric_map(panel: List[Dict[str, Any]]) -> Dict[str, Decimal]:
        result: Dict[str, Decimal] = {}
        for item in panel:
            name = item.get("metric_name")
            value = item.get("metric_value")
            if name is None or value is None:
                continue
            try:
                result[name] = Decimal(str(value))
            except Exception:
                continue
        return result

    @staticmethod
    def _parse_date(value: Any) -> Optional[date]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        try:
            return datetime.fromisoformat(str(value)[:10]).date()
        except Exception:
            return None
