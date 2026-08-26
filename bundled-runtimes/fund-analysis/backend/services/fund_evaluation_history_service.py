"""专业基金评价历史：保存、变化比较和统计。"""
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from services.fund_evaluation_service import FundEvaluationService


class FundEvaluationHistoryService:
    DIMENSION_LABELS = {
        "return": "收益能力",
        "risk": "风险控制",
        "risk_adjusted": "风险调整后收益",
        "consistency": "表现稳定性",
        "manager_tenure": "经理任期",
        "tracking_quality": "跟踪质量",
        "cost_efficiency": "成本效率",
        "scale_liquidity": "规模与流动性",
        "excess_return": "超额收益",
        "active_efficiency": "主动管理效率",
        "drawdown_control": "回撤控制",
        "income_competitiveness": "收益竞争力",
        "capital_preservation": "净值稳定性",
        "income_stability": "收益稳定性",
        "data_quality": "数据质量",
    }

    def __init__(
        self,
        evaluation_service: Optional[FundEvaluationService] = None,
        snapshot_repo: Optional[Any] = None,
    ):
        self.evaluation_service = evaluation_service or FundEvaluationService()
        if snapshot_repo is None:
            from repositories import get_fund_evaluation_snapshot_repo
            snapshot_repo = get_fund_evaluation_snapshot_repo()
        self.snapshot_repo = snapshot_repo

    def save_current(self, wind_code: str, window: str = "1y") -> Dict[str, Any]:
        context = self.evaluation_service.load_context(wind_code)
        if not context.get("found"):
            raise ValueError(f"基金不存在: {wind_code}")
        evaluation = self.evaluation_service.evaluate_from_context(context, window=window)
        snapshot_fields = self._snapshot_fields(evaluation, window)
        latest_rows = self.snapshot_repo.list_history(
            snapshot_fields["wind_code"],
            snapshot_fields["evaluation_window"],
            limit=1,
        )
        if latest_rows and self._same_snapshot(snapshot_fields, latest_rows[0]):
            saved = latest_rows[0]
            save_status = "unchanged"
        else:
            saved = self.snapshot_repo.create(snapshot_fields)
            save_status = "saved"
        history = self.list_history(wind_code, evaluation_window=window, limit=30)
        return {
            "status": save_status,
            "message": "评价没有变化，未重复保存。" if save_status == "unchanged" else "本次评价已保存。",
            "snapshot": self._public_item(saved),
            "evaluation": evaluation,
            "history": history,
            "boundary": "评分历史用于研究复核，不构成投资建议。",
        }

    def get_snapshot(self, wind_code: str, snapshot_id: str) -> Dict[str, Any]:
        row = self.snapshot_repo.get(snapshot_id, str(wind_code or "").strip().upper())
        if not row:
            raise ValueError(f"评价记录不存在: {snapshot_id}")
        return {
            "status": "ok",
            "item": self._public_item(row),
            "evaluation": row.get("snapshot") or {},
            "boundary": "评分历史用于研究复核，不构成投资建议。",
        }

    def list_history(
        self,
        wind_code: str,
        evaluation_window: Optional[str] = None,
        limit: int = 30,
    ) -> Dict[str, Any]:
        rows = self.snapshot_repo.list_history(wind_code, evaluation_window, limit)
        items = self._with_changes([self._public_item(row) for row in rows])
        return {
            "status": "ok" if items else "empty",
            "wind_code": str(wind_code or "").strip().upper(),
            "evaluation_window": evaluation_window,
            "items": items,
            "statistics": self._statistics(items),
            "boundary": "评分历史用于研究复核，不构成投资建议。",
        }

    def list_recent(
        self,
        evaluation_window: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 30,
    ) -> Dict[str, Any]:
        rows = self.snapshot_repo.list_recent(evaluation_window, status, limit)
        items = self._with_changes([self._public_item(row) for row in rows])
        return {
            "status": "ok" if items else "empty",
            "evaluation_window": evaluation_window,
            "evaluation_status": status,
            "items": items,
            "total": len(items),
            "boundary": "评价结果用于研究复核，不构成投资建议。",
        }

    @staticmethod
    def _snapshot_fields(evaluation: Dict[str, Any], window: str) -> Dict[str, Any]:
        result = evaluation.get("evaluation") or {}
        target = evaluation.get("target") or {}
        peer_context = evaluation.get("peer_context") or {}
        classification = evaluation.get("classification") or {}
        professional_peer = (result.get("peer_percentiles") or {}).get("professional_score") or {}
        return {
            "wind_code": str(target.get("wind_code") or "").strip().upper(),
            "evaluation_window": str(peer_context.get("metric_window") or window),
            "as_of_date": target.get("as_of_date"),
            "status": evaluation.get("status") or "unavailable",
            "methodology_version": evaluation.get("methodology_version") or "unknown",
            "calculation_method": result.get("calculation_method"),
            "peer_group_id": peer_context.get("peer_group_id") or classification.get("peer_group_id"),
            "peer_group_name": peer_context.get("peer_group") or classification.get("peer_group"),
            "overall_score": result.get("overall_score"),
            "overall_grade": result.get("overall_grade"),
            "peer_rank": professional_peer.get("rank"),
            "peer_count": professional_peer.get("peer_count"),
            "peer_percentile": professional_peer.get("percentile"),
            "dimension_scores": result.get("dimension_scores") or {},
            "peer_metrics": result.get("peer_percentiles") or {},
            "data_quality": result.get("data_quality") or {},
            "missing_items": evaluation.get("missing_items") or [],
            "source_snapshot_ids": result.get("source_snapshot_ids") or [],
            "snapshot": evaluation,
        }

    @staticmethod
    def _public_item(row: Dict[str, Any]) -> Dict[str, Any]:
        data_quality = row.get("data_quality") or {}
        dimension_scores = row.get("dimension_scores") or {}
        snapshot = row.get("snapshot") or {}
        cross_market = (
            (snapshot.get("explanatory_evidence") or {}).get("cross_market_holding")
            or {}
        )
        holding_stability = (
            (snapshot.get("explanatory_evidence") or {}).get("holding_stability")
            or {}
        )
        return {
            "id": row.get("id"),
            "wind_code": row.get("wind_code"),
            "fund_name": row.get("fund_name"),
            "fund_type": row.get("fund_type"),
            "evaluation_window": row.get("evaluation_window"),
            "as_of_date": row.get("as_of_date"),
            "status": row.get("status"),
            "methodology_version": row.get("methodology_version"),
            "calculation_method": row.get("calculation_method"),
            "peer_group_id": row.get("peer_group_id"),
            "peer_group_name": row.get("peer_group_name"),
            "overall_score": row.get("overall_score"),
            "overall_grade": row.get("overall_grade"),
            "peer_rank": row.get("peer_rank"),
            "peer_count": row.get("peer_count"),
            "peer_percentile": row.get("peer_percentile"),
            "dimension_scores": dimension_scores,
            "evidence_coverage": FundEvaluationHistoryService._evidence_coverage(dimension_scores),
            "data_quality": {
                "status": data_quality.get("status"),
                "score": data_quality.get("score"),
            },
            "missing_items": row.get("missing_items") or [],
            "source_snapshot_ids": row.get("source_snapshot_ids") or [],
            "cross_market_holding": {
                "status": cross_market.get("status"),
                "quarter": cross_market.get("quarter"),
                "peer_group_name": cross_market.get("peer_group_name"),
                "profile_peer_count": cross_market.get("profile_peer_count") or 0,
                "minimum_peer_count": cross_market.get("minimum_peer_count") or 5,
                "labels": cross_market.get("labels") or [],
                "included_in_score": False,
            },
            "holding_stability": {
                "status": holding_stability.get("status"),
                "label": holding_stability.get("label"),
                "latest_quarter": holding_stability.get("latest_quarter"),
                "previous_quarter": holding_stability.get("previous_quarter"),
                "top10_overlap_ratio": holding_stability.get("top10_overlap_ratio"),
                "industry_overlap_ratio": holding_stability.get("industry_overlap_ratio"),
                "retained_holding_count": holding_stability.get("retained_holding_count"),
                "included_in_score": False,
            },
            "created_at": row.get("created_at"),
        }

    @classmethod
    def _with_changes(cls, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped: Dict[tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
        for item in items:
            grouped[(
                str(item.get("wind_code") or ""),
                str(item.get("evaluation_window") or ""),
            )].append(item)

        for window_items in grouped.values():
            for index, item in enumerate(window_items):
                previous = window_items[index + 1] if index + 1 < len(window_items) else None
                item["change"] = cls._change(item, previous)
        return items

    @classmethod
    def _change(
        cls,
        current: Dict[str, Any],
        previous: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if previous is None:
            return None
        methodology_changed = current.get("methodology_version") != previous.get("methodology_version")
        calculation_method_changed = current.get("calculation_method") != previous.get("calculation_method")
        peer_group_changed = current.get("peer_group_id") != previous.get("peer_group_id")
        comparable = not (methodology_changed or calculation_method_changed or peer_group_changed)
        raw_score_delta = cls._delta(current.get("overall_score"), previous.get("overall_score"))
        raw_rank_change = cls._delta(previous.get("peer_rank"), current.get("peer_rank"))
        raw_percentile_delta = cls._delta(current.get("peer_percentile"), previous.get("peer_percentile"))
        dimension_deltas = cls._dimension_deltas(
            current.get("dimension_scores") or {},
            previous.get("dimension_scores") or {},
        ) if comparable else {}
        drivers = cls._dimension_drivers(dimension_deltas)
        comparison_status = (
            "methodology_changed" if methodology_changed or calculation_method_changed
            else "peer_group_changed" if peer_group_changed
            else "comparable"
        )
        current_missing = set(str(item) for item in current.get("missing_items") or [])
        previous_missing = set(str(item) for item in previous.get("missing_items") or [])
        current_coverage = (current.get("evidence_coverage") or {}).get("coverage_percent")
        previous_coverage = (previous.get("evidence_coverage") or {}).get("coverage_percent")
        current_quality = (current.get("data_quality") or {}).get("score")
        previous_quality = (previous.get("data_quality") or {}).get("score")
        peer_count_delta = cls._delta(current.get("peer_count"), previous.get("peer_count"))
        change = {
            "comparison_status": comparison_status,
            "comparable": comparable,
            "score_delta": raw_score_delta if comparable else None,
            "raw_score_delta": raw_score_delta,
            "rank_change": raw_rank_change if comparable else None,
            "raw_rank_change": raw_rank_change,
            "percentile_delta": raw_percentile_delta if comparable else None,
            "raw_percentile_delta": raw_percentile_delta,
            "peer_count_delta": peer_count_delta,
            "dimension_deltas": dimension_deltas,
            "drivers": drivers,
            "evidence_coverage_delta": cls._delta(current_coverage, previous_coverage),
            "data_quality_delta": cls._delta(current_quality, previous_quality),
            "missing_items_added": sorted(current_missing - previous_missing),
            "missing_items_resolved": sorted(previous_missing - current_missing),
            "status_changed": current.get("status") != previous.get("status"),
            "methodology_changed": methodology_changed,
            "calculation_method_changed": calculation_method_changed,
            "peer_group_changed": peer_group_changed,
        }
        change["summary"] = cls._change_summary(current, previous, change)
        return change

    @classmethod
    def _change_summary(
        cls,
        current: Dict[str, Any],
        previous: Dict[str, Any],
        change: Dict[str, Any],
    ) -> str:
        if change["comparison_status"] == "methodology_changed":
            return "评价方法已更新，本次分数和名次与上次不宜直接比较。"
        if change["comparison_status"] == "peer_group_changed":
            return "专业同类组已变化，本次分数和名次与上次不宜直接比较。"
        if change.get("status_changed"):
            return f"评价状态由 {previous.get('status') or '待补'} 变为 {current.get('status') or '待补'}。"

        score_delta = change.get("score_delta")
        drivers = change.get("drivers") or []
        driver_text = "、".join(
            cls.DIMENSION_LABELS.get(item["key"], item["key"])
            for item in drivers[:2]
        )
        if score_delta is not None and abs(score_delta) >= 0.05:
            direction = "上升" if score_delta > 0 else "下降"
            reason = f"，主要变化来自{driver_text}" if driver_text else ""
            return f"综合评分{direction} {abs(score_delta):.1f} 分{reason}。"

        rank_change = change.get("rank_change")
        if rank_change is not None and rank_change != 0:
            direction = "上升" if rank_change > 0 else "下降"
            peer_text = (
                f"，同类样本 {previous.get('peer_count')} → {current.get('peer_count')} 只"
                if previous.get("peer_count") is not None and current.get("peer_count") is not None
                else ""
            )
            return f"综合评分基本不变，同类名次{direction} {abs(rank_change):.0f} 位{peer_text}。"

        coverage_delta = change.get("evidence_coverage_delta")
        if coverage_delta is not None and coverage_delta != 0:
            direction = "提高" if coverage_delta > 0 else "下降"
            return f"综合评分基本不变，评价证据覆盖{direction} {abs(coverage_delta):.0f} 个百分点。"
        return "核心评分、同类位置和证据覆盖与上次基本一致。"

    @staticmethod
    def _dimension_drivers(deltas: Dict[str, float]) -> List[Dict[str, Any]]:
        return [
            {
                "key": key,
                "delta": delta,
                "direction": "improved" if delta > 0 else "weakened",
            }
            for key, delta in sorted(deltas.items(), key=lambda item: abs(item[1]), reverse=True)
            if abs(delta) >= 0.05
        ][:3]

    @staticmethod
    def _evidence_coverage(dimensions: Dict[str, Any]) -> Dict[str, Any]:
        configured_weight = 0.0
        covered_weight = 0.0
        missing_dimensions: List[str] = []
        scored_count = 0
        for key, raw_dimension in dimensions.items():
            dimension = raw_dimension if isinstance(raw_dimension, dict) else {}
            weight = float(dimension.get("weight") or 0)
            configured_weight += weight
            included = dimension.get("included_in_score")
            if included is None:
                included = dimension.get("score") is not None
            if included:
                covered_weight += weight
                scored_count += 1
            else:
                missing_dimensions.append(key)

        coverage_percent = None
        if configured_weight > 0:
            coverage_percent = round(min(1.0, covered_weight / configured_weight) * 100, 2)
        elif dimensions:
            coverage_percent = round(scored_count / len(dimensions) * 100, 2)
        return {
            "configured_weight": round(configured_weight, 6),
            "covered_weight": round(covered_weight, 6),
            "coverage_percent": coverage_percent,
            "missing_dimensions": missing_dimensions,
        }

    @staticmethod
    def _same_snapshot(current: Dict[str, Any], previous: Dict[str, Any]) -> bool:
        keys = (
            "wind_code", "evaluation_window", "as_of_date", "status",
            "methodology_version", "calculation_method", "peer_group_id",
            "overall_score", "overall_grade", "peer_rank", "peer_count",
            "peer_percentile", "dimension_scores", "data_quality",
            "missing_items", "source_snapshot_ids",
        )
        current_value = {key: current.get(key) for key in keys}
        previous_value = {key: previous.get(key) for key in keys}
        return FundEvaluationHistoryService._normalized_value(
            current_value
        ) == FundEvaluationHistoryService._normalized_value(previous_value)

    @staticmethod
    def _normalized_value(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: FundEvaluationHistoryService._normalized_value(item)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [FundEvaluationHistoryService._normalized_value(item) for item in value]
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, (Decimal, int, float)) and not isinstance(value, bool):
            return float(value)
        return value

    @classmethod
    def _dimension_deltas(cls, current: Dict[str, Any], previous: Dict[str, Any]) -> Dict[str, float]:
        result: Dict[str, float] = {}
        for key in current.keys() | previous.keys():
            current_score = (current.get(key) or {}).get("score") if isinstance(current.get(key), dict) else None
            previous_score = (previous.get(key) or {}).get("score") if isinstance(previous.get(key), dict) else None
            delta = cls._delta(current_score, previous_score)
            if delta is not None:
                result[key] = delta
        return result

    @staticmethod
    def _delta(current: Any, previous: Any) -> Optional[float]:
        if current is None or previous is None:
            return None
        return round(float(current) - float(previous), 2)

    @classmethod
    def _statistics(cls, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for item in items:
            grouped[str(item.get("evaluation_window") or "")].append(item)

        by_window = {}
        for window, window_items in grouped.items():
            scores = [float(item["overall_score"]) for item in window_items if item.get("overall_score") is not None]
            latest = window_items[0]
            oldest = window_items[-1]
            full_period_change = cls._change(latest, oldest) if latest is not oldest else None
            by_window[window] = {
                "snapshot_count": len(window_items),
                "scored_snapshot_count": len(scores),
                "latest_score": latest.get("overall_score"),
                "highest_score": max(scores) if scores else None,
                "lowest_score": min(scores) if scores else None,
                "average_score": round(sum(scores) / len(scores), 2) if scores else None,
                "score_change": full_period_change.get("score_delta") if full_period_change else None,
                "latest_peer_rank": latest.get("peer_rank"),
                "rank_change": full_period_change.get("rank_change") if full_period_change else None,
                "comparison_status": full_period_change.get("comparison_status") if full_period_change else "first_record",
                "change_summary": full_period_change.get("summary") if full_period_change else "首次评价记录。",
            }
        return {"total": len(items), "by_window": by_window}
