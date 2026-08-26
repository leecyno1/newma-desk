"""相邻公开持仓期的风格变化证据。"""
import json
import math
from typing import Any, Dict, List, Optional


class HoldingStyleDriftService:
    """比较同一专业同类组内的持仓风格分位，不冒充完整组合或 RBSA。"""

    METHODOLOGY = "adjacent_disclosed_holding_style_percentile_change_v1"
    READY_STATUSES = {"peer_percentile_ready", "peer_percentile_neutral"}
    FACTOR_LABELS = {
        "SIZE": "规模风格",
        "BTOP": "价值风格",
        "BETA": "Beta",
        "MOMENTUM": "动量",
        "RESVOL": "波动风格",
        "LIQUIDITY": "换手特征",
        "LEVERAGE": "杠杆特征",
        "GROWTH": "成长风格",
    }

    def __init__(self, snapshot_repo: Optional[Any] = None):
        if snapshot_repo is None:
            from repositories import get_holding_style_snapshot_repo
            snapshot_repo = get_holding_style_snapshot_repo()
        self.snapshot_repo = snapshot_repo

    def get(self, wind_code: str) -> Dict[str, Any]:
        rows = self.snapshot_repo.list_history(wind_code, limit=6)
        return self.analyze(str(wind_code or "").strip().upper(), rows)

    @classmethod
    def analyze(cls, wind_code: str, snapshots: List[Dict[str, Any]]) -> Dict[str, Any]:
        ready = [
            dict(item)
            for item in snapshots
            if str(item.get("status") or "") in cls.READY_STATUSES
        ]
        ready.sort(key=lambda item: str(item.get("quarter") or ""), reverse=True)
        if len(ready) < 2:
            return cls._insufficient(
                wind_code,
                ready,
                "至少需要两个已完成同类分位计算的公开持仓期，才能判断风格变化。",
            )

        latest, previous = ready[0], ready[1]
        latest_group = str(latest.get("peer_group_id") or "")
        previous_group = str(previous.get("peer_group_id") or "")
        if not latest_group or latest_group != previous_group:
            return cls._insufficient(
                wind_code,
                [latest, previous],
                "相邻持仓期的专业同类组不同，风格分位不可直接比较。",
                status="incomparable",
            )

        latest_factors = cls._factor_map(latest)
        previous_factors = cls._factor_map(previous)
        common_factors = sorted(set(latest_factors) & set(previous_factors))
        if not common_factors:
            return cls._insufficient(
                wind_code,
                [latest, previous],
                "相邻持仓期没有共同且有效的同类风格分位，暂不能判断风格变化。",
            )

        changes = []
        for factor in common_factors:
            latest_item = latest_factors[factor]
            previous_item = previous_factors[factor]
            latest_percentile = cls._number(latest_item.get("percentile"))
            previous_percentile = cls._number(previous_item.get("percentile"))
            if latest_percentile is None or previous_percentile is None:
                continue
            delta = latest_percentile - previous_percentile
            previous_label = str(previous_item.get("percentile_label") or "").replace("同类", "")
            latest_label = str(latest_item.get("percentile_label") or "").replace("同类", "")
            changes.append({
                "factor": factor,
                "label": cls.FACTOR_LABELS.get(factor, factor),
                "previous_percentile": round(previous_percentile, 6),
                "latest_percentile": round(latest_percentile, 6),
                "percentile_change": round(delta, 6),
                "absolute_change": round(abs(delta), 6),
                "previous_label": previous_label,
                "latest_label": latest_label,
                "bucket_changed": bool(previous_label and latest_label and previous_label != latest_label),
            })

        if not changes:
            return cls._insufficient(
                wind_code,
                [latest, previous],
                "相邻持仓期的同类风格分位缺少有效数值。",
            )

        changes.sort(key=lambda item: item["absolute_change"], reverse=True)
        changed_factor_count = sum(1 for item in changes if item["bucket_changed"])
        max_change = max(item["absolute_change"] for item in changes)
        top_changes = changes[:3]
        average_top_change = sum(item["absolute_change"] for item in top_changes) / len(top_changes)
        previous_labels = set(cls._string_list(previous.get("style_labels")))
        latest_labels = set(cls._string_list(latest.get("style_labels")))
        added_labels = sorted(latest_labels - previous_labels)
        removed_labels = sorted(previous_labels - latest_labels)

        if changed_factor_count >= 3 or max_change >= 0.40:
            level = "high"
            label = "公开持仓风格变化较明显"
        elif changed_factor_count or max_change >= 0.20 or added_labels or removed_labels:
            level = "medium"
            label = "公开持仓风格出现一定变化"
        else:
            level = "low"
            label = "公开持仓风格基本稳定"

        transitions = []
        for item in changes:
            if item["bucket_changed"]:
                transitions.append(
                    f"{item['label']}由{item['previous_label']}变为{item['latest_label']}"
                )
            elif item["absolute_change"] >= 0.20:
                transitions.append(
                    f"{item['label']}同类分位变化 {item['absolute_change'] * 100:.0f} 个百分点"
                )
            if len(transitions) >= 2:
                break
        transition_text = "，主要变化为" + "、".join(transitions) if transitions else ""
        note = (
            f"{previous.get('quarter') or '上一期'}至{latest.get('quarter') or '最新一期'}，{label}{transition_text}。"
            "仅比较公开披露持仓的同类风格分位，不代表完整组合，也不是收益基础风格分析。"
        )

        return {
            "status": "available",
            "wind_code": wind_code,
            "methodology": cls.METHODOLOGY,
            "level": level,
            "label": label,
            "previous_quarter": previous.get("quarter"),
            "latest_quarter": latest.get("quarter"),
            "peer_group_id": latest_group,
            "peer_group_name": latest.get("peer_group_name"),
            "factor_count": len(changes),
            "changed_factor_count": changed_factor_count,
            "max_percentile_change": round(max_change, 6),
            "average_top_percentile_change": round(average_top_change, 6),
            "factor_changes": changes,
            "added_labels": added_labels,
            "removed_labels": removed_labels,
            "previous_labels": sorted(previous_labels),
            "latest_labels": sorted(latest_labels),
            "previous_disclosed_weight": cls._number(previous.get("holdings_disclosed_weight")),
            "latest_disclosed_weight": cls._number(latest.get("holdings_disclosed_weight")),
            "included_in_score": False,
            "source": "local.postgres.holding_style_snapshots",
            "note": note,
            "boundary": "相邻公开持仓期风格变化只作解释，不直接改变基金评分。",
            "missing_items": [],
        }

    @classmethod
    def _factor_map(cls, snapshot: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        return {
            str(item.get("factor") or "").upper(): item
            for item in cls._dict_list(snapshot.get("peer_percentiles"))
            if item.get("factor")
            and item.get("signal_status") != "not_material"
            and cls._number(item.get("percentile")) is not None
        }

    @classmethod
    def _insufficient(
        cls,
        wind_code: str,
        snapshots: List[Dict[str, Any]],
        reason: str,
        status: str = "insufficient_evidence",
    ) -> Dict[str, Any]:
        return {
            "status": status,
            "wind_code": wind_code,
            "methodology": cls.METHODOLOGY,
            "level": "unavailable",
            "label": "公开持仓风格变化待补",
            "previous_quarter": snapshots[1].get("quarter") if len(snapshots) > 1 else None,
            "latest_quarter": snapshots[0].get("quarter") if snapshots else None,
            "factor_changes": [],
            "added_labels": [],
            "removed_labels": [],
            "included_in_score": False,
            "source": "local.postgres.holding_style_snapshots",
            "note": reason,
            "boundary": "相邻公开持仓期风格变化只作解释，不直接改变基金评分。",
            "missing_items": [reason],
        }

    @staticmethod
    def _dict_list(value: Any) -> List[Dict[str, Any]]:
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                return []
        return [dict(item) for item in value] if isinstance(value, list) else []

    @staticmethod
    def _string_list(value: Any) -> List[str]:
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                value = [value]
        return [str(item) for item in value if str(item or "").strip()] if isinstance(value, list) else []

    @staticmethod
    def _number(value: Any) -> Optional[float]:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if math.isfinite(parsed) else None
