"""把公开持仓描述子转换为同季度、同类基金分位证据。"""
import json
import math
from statistics import median
from typing import Any, Dict, Iterable, List, Optional


FACTOR_LABELS = {
    "SIZE": ("同类偏小盘", "同类中盘", "同类偏大盘"),
    "BTOP": ("同类偏高估值", "同类估值中性", "同类偏价值"),
    "BETA": ("同类低 Beta", "同类 Beta 中性", "同类高 Beta"),
    "MOMENTUM": ("同类动量偏弱", "同类动量中性", "同类动量偏强"),
    "RESVOL": ("同类低波", "同类波动中等", "同类高波"),
    "LIQUIDITY": ("同类换手偏低", "同类换手中等", "同类换手偏高"),
    "LEVERAGE": ("同类杠杆偏低", "同类杠杆中等", "同类杠杆偏高"),
    "GROWTH": ("同类成长偏弱", "同类成长中等", "同类成长偏强"),
}

# 横截面差异过小时，纯排名会把跟踪同一指数的基金夸张成相反风格。
# 同时满足样本门槛与以下“绝对差异/相对差异”门槛，才允许贴风格标签。
MIN_MATERIAL_RELATIVE_RANGE = 0.10
MIN_MATERIAL_ABSOLUTE_RANGE = {
    "SIZE": 50.0,
    "BTOP": 0.05,
    "BETA": 0.15,
    "MOMENTUM": 0.10,
    "RESVOL": 0.05,
    "LIQUIDITY": 0.01,
    "LEVERAGE": 0.05,
    "GROWTH": 0.10,
}

PEER_MISSING_ITEM_PREFIXES = (
    "缺少标准同类组，不能计算持仓风格同类分位。",
    "同季度同类描述子样本未达到",
    "同类样本数量已达门槛，但描述子横截面差异不显著",
)


def _json_list(value: Any) -> List[Dict[str, Any]]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    return [dict(item) for item in value] if isinstance(value, list) else []


def _number(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    except (TypeError, ValueError):
        return None


class HoldingStylePeerService:
    """同类分位只在达到标准同类组最低样本数后输出。"""

    @staticmethod
    def _descriptor_map(snapshot: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        return {
            str(item.get("factor") or "").upper(): item
            for item in _json_list(snapshot.get("descriptors"))
            if item.get("factor") and _number(item.get("exposure")) is not None
        }

    @staticmethod
    def _percentile(value: float, values: Iterable[float]) -> float:
        ordered = sorted(float(item) for item in values)
        if len(ordered) <= 1:
            return 0.5
        less = sum(1 for item in ordered if item < value)
        equal = sum(1 for item in ordered if math.isclose(item, value, rel_tol=1e-9, abs_tol=1e-12))
        average_zero_based_rank = less + max(0, equal - 1) / 2
        return average_zero_based_rank / (len(ordered) - 1)

    @staticmethod
    def _factor_label(factor: str, percentile: float) -> str:
        low, middle, high = FACTOR_LABELS.get(factor, ("同类低位", "同类中位", "同类高位"))
        if percentile <= 1 / 3:
            return low
        if percentile >= 2 / 3:
            return high
        return middle

    @staticmethod
    def _dispersion(factor: str, values: List[float]) -> Dict[str, Any]:
        minimum = min(values)
        maximum = max(values)
        span = maximum - minimum
        center = abs(float(median(values)))
        absolute_threshold = float(MIN_MATERIAL_ABSOLUTE_RANGE.get(factor, 0.05))
        material_threshold = max(absolute_threshold, center * MIN_MATERIAL_RELATIVE_RANGE)
        return {
            "status": "material" if span >= material_threshold else "not_material",
            "range": round(span, 6),
            "relative_range": round(span / center, 6) if center > 1e-12 else None,
            "material_threshold": round(material_threshold, 6),
            "absolute_threshold": absolute_threshold,
            "relative_threshold": MIN_MATERIAL_RELATIVE_RANGE,
        }

    def enrich(
        self,
        snapshot: Dict[str, Any],
        peer_snapshots: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        result = dict(snapshot)
        descriptors = self._descriptor_map(result)
        minimum_peer_count = max(5, int(result.get("minimum_peer_count") or 5))
        peer_percentiles: List[Dict[str, Any]] = []

        for factor, descriptor in descriptors.items():
            target_value = float(descriptor["exposure"])
            peer_values = []
            for peer in peer_snapshots:
                peer_descriptor = self._descriptor_map(peer).get(factor)
                peer_value = _number(peer_descriptor.get("exposure")) if peer_descriptor else None
                if peer_value is not None:
                    peer_values.append(peer_value)
            if len(peer_values) < minimum_peer_count:
                continue
            percentile = self._percentile(target_value, peer_values)
            dispersion = self._dispersion(factor, peer_values)
            material = dispersion["status"] == "material"
            peer_percentiles.append({
                "factor": factor,
                "label": descriptor.get("label") or factor,
                "exposure": target_value,
                "unit": descriptor.get("unit"),
                "percentile": round(percentile, 6),
                "percentile_label": self._factor_label(factor, percentile) if material else "同类差异不显著",
                "signal_status": dispersion["status"],
                "dispersion": dispersion,
                "sample_size": len(peer_values),
                "minimum_peer_count": minimum_peer_count,
                "peer_group_id": result.get("peer_group_id"),
                "peer_group_key": result.get("peer_group_key"),
                "peer_group_name": result.get("peer_group_name"),
                "quarter": result.get("quarter"),
                "source": "holding_style_peer_percentile_v1",
            })

        percentile_map = {
            item["factor"]: item
            for item in peer_percentiles
            if item.get("signal_status") == "material"
        }
        style_labels = []
        if percentile_map.get("SIZE"):
            style_labels.append(percentile_map["SIZE"]["percentile_label"].replace("同类", ""))

        btop = percentile_map.get("BTOP")
        growth = percentile_map.get("GROWTH")
        if btop and btop["percentile"] >= 2 / 3:
            style_labels.append("偏价值")
        elif btop and growth and btop["percentile"] <= 1 / 3 and growth["percentile"] >= 2 / 3:
            style_labels.append("偏成长")
        elif btop and growth:
            style_labels.append("价值成长均衡")

        resvol = percentile_map.get("RESVOL")
        if resvol and resvol["percentile"] <= 1 / 3:
            style_labels.append("低波")
        elif resvol and resvol["percentile"] >= 2 / 3:
            style_labels.append("高波")

        missing_items = [
            item
            for item in (result.get("missing_items") or [])
            if not str(item).startswith(PEER_MISSING_ITEM_PREFIXES)
        ]
        if not result.get("peer_group_id"):
            missing_items.append("缺少标准同类组，不能计算持仓风格同类分位。")
        elif not peer_percentiles:
            missing_items.append(
                f"同季度同类描述子样本未达到 {minimum_peer_count} 只，只展示原始持仓描述子，不贴风格标签。"
            )
        elif not style_labels:
            missing_items.append(
                "同类样本数量已达门槛，但描述子横截面差异不显著，只展示分位证据，不贴风格标签。"
            )

        result.update({
            "peer_percentiles": peer_percentiles,
            "style_labels": list(dict.fromkeys(style_labels)),
            "peer_sample_size": max((item["sample_size"] for item in peer_percentiles), default=len(peer_snapshots)),
            "minimum_peer_count": minimum_peer_count,
            "status": (
                "peer_percentile_ready"
                if peer_percentiles and style_labels
                else "peer_percentile_neutral"
                if peer_percentiles
                else result.get("status") or "descriptor_ready"
            ),
            "missing_items": list(dict.fromkeys(missing_items)),
        })
        return result
