"""同季度、同类基金的公开持仓跨市场比较。"""

import math
from statistics import median
from typing import Any, Dict, Iterable, List, Optional

from services.cross_market_holding_profile_service import CrossMarketHoldingProfileService


MINIMUM_PEER_COUNT = 5
MINIMUM_DISCLOSED_WEIGHT_FOR_MARKET_POSITION = 0.30
MARKET_EXPOSURE_METRICS = {"cn_a_weight", "hk_weight", "hk_share_of_disclosed"}
LABEL_METRICS = {
    "hk_share_of_disclosed",
    "market_allocation_hhi",
    "security_hhi",
    "industry_hhi",
    "top_three_share_of_disclosed",
}


def _number(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    except (TypeError, ValueError):
        return None


class CrossMarketPeerComparisonService:
    """把公开持仓画像转为有样本门槛的同类解释证据。"""

    METRICS: Dict[str, Dict[str, Any]] = {
        "cn_a_weight": {
            "label": "A股公开持仓占基金净值",
            "unit": "percent",
            "absolute_range": 0.10,
        },
        "hk_weight": {
            "label": "港股公开持仓占基金净值",
            "unit": "percent",
            "absolute_range": 0.10,
        },
        "hk_share_of_disclosed": {
            "label": "已披露持仓中的港股占比",
            "unit": "percent",
            "absolute_range": 0.15,
        },
        "market_allocation_hhi": {
            "label": "已披露市场配置集中度",
            "unit": "hhi",
            "absolute_range": 0.08,
        },
        "security_hhi": {
            "label": "已披露个股集中度",
            "unit": "hhi",
            "absolute_range": 0.05,
        },
        "industry_hhi": {
            "label": "已披露行业集中度",
            "unit": "hhi",
            "absolute_range": 0.05,
        },
        "top_three_share_of_disclosed": {
            "label": "已披露持仓前三大集中度",
            "unit": "percent",
            "absolute_range": 0.10,
        },
    }

    def __init__(
        self,
        holding_repo: Optional[Any] = None,
        classification_repo: Optional[Any] = None,
        profile_service: Optional[CrossMarketHoldingProfileService] = None,
    ):
        if holding_repo is None or classification_repo is None:
            from repositories import get_fund_classification_repo, get_holding_repo

            holding_repo = holding_repo or get_holding_repo()
            classification_repo = classification_repo or get_fund_classification_repo()
        self.holding_repo = holding_repo
        self.classification_repo = classification_repo
        self.profile_service = profile_service or CrossMarketHoldingProfileService()

    def build(
        self,
        wind_code: str,
        classification: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        code = str(wind_code or "").strip().upper()
        classification = classification or self.classification_repo.get_classification_context(code)
        peer_group_id = str(classification.get("peer_group_id") or "")
        peer_group_name = classification.get("peer_group") or classification.get("peer_group_name")
        minimum_peer_count = max(
            MINIMUM_PEER_COUNT,
            int(classification.get("minimum_peer_count") or MINIMUM_PEER_COUNT),
        )
        if classification.get("status") not in {"classified", "resolved"} or not peer_group_id:
            return self._unavailable(
                code,
                "classification_unavailable",
                peer_group_name,
                minimum_peer_count,
                ["缺少标准同类组，不能比较跨市场持仓。"],
            )

        quarter = self.holding_repo.get_latest_weighted_quarter(code)
        if not quarter:
            return self._unavailable(
                code,
                "holding_unavailable",
                peer_group_name,
                minimum_peer_count,
                ["缺少以基金净值为分母的公开持仓，不能比较跨市场暴露。"],
            )

        peer_funds = self.classification_repo.list_peer_funds(
            peer_group_id,
            target_wind_code=code,
        )
        peer_codes = list(dict.fromkeys([
            code,
            *[
                str(item.get("wind_code") or "").strip().upper()
                for item in peer_funds
                if str(item.get("wind_code") or "").strip()
            ],
        ]))
        holdings_map = self.holding_repo.get_holdings_map(peer_codes, quarter)
        profiles: Dict[str, Dict[str, Any]] = {}
        metric_rows: Dict[str, Dict[str, float]] = {}
        for peer_code in peer_codes:
            holdings = holdings_map.get(peer_code) or []
            if not holdings:
                continue
            profile = self.profile_service.analyze(holdings, quarter)
            if profile.get("status") not in {"available", "partial_evidence"}:
                continue
            metrics = self._profile_metrics(profile)
            if not metrics:
                continue
            profiles[peer_code] = profile
            metric_rows[peer_code] = metrics

        target_profile = profiles.get(code)
        target_metrics = metric_rows.get(code) or {}
        if not target_profile or not target_metrics:
            return self._unavailable(
                code,
                "holding_evidence_invalid",
                peer_group_name,
                minimum_peer_count,
                ["本基金最新公开持仓未通过权重口径校验，不能形成同类比较。"],
                quarter=quarter,
                peer_group_id=peer_group_id,
            )

        comparisons = []
        labels = []
        for metric_key, definition in self.METRICS.items():
            target_value = _number(target_metrics.get(metric_key))
            requires_disclosure_gate = metric_key in MARKET_EXPOSURE_METRICS
            target_disclosed_weight = _number(target_profile.get("total_disclosed_weight")) or 0.0
            target_eligible = (
                not requires_disclosure_gate
                or target_disclosed_weight >= MINIMUM_DISCLOSED_WEIGHT_FOR_MARKET_POSITION
            )
            values = [
                value
                for peer_code, metrics in metric_rows.items()
                if (
                    not requires_disclosure_gate
                    or (_number(profiles[peer_code].get("total_disclosed_weight")) or 0.0)
                    >= MINIMUM_DISCLOSED_WEIGHT_FOR_MARKET_POSITION
                )
                if (value := _number(metrics.get(metric_key))) is not None
            ]
            if target_value is None:
                continue
            sample_status = (
                "target_disclosure_insufficient"
                if not target_eligible
                else "sufficient"
                if len(values) >= minimum_peer_count
                else "insufficient_peer_sample"
            )
            dispersion = self._dispersion(values, float(definition["absolute_range"]))
            percentile = self._percentile(target_value, values) if sample_status == "sufficient" else None
            position_label = self._position_label(
                metric_key,
                definition["label"],
                percentile,
                dispersion.get("status") == "material",
            ) if percentile is not None else (
                "本基金公开持仓覆盖不足，不判断同类高低"
                if sample_status == "target_disclosure_insufficient"
                else "同类样本不足"
            )
            item = {
                "metric": metric_key,
                "label": definition["label"],
                "value": round(target_value, 6),
                "unit": definition["unit"],
                "percentile": round(percentile, 2) if percentile is not None else None,
                "position_label": position_label,
                "sample_size": len(values),
                "minimum_peer_count": minimum_peer_count,
                "sample_status": sample_status,
                "dispersion": dispersion,
                "disclosure_gate": {
                    "required": requires_disclosure_gate,
                    "target_disclosed_weight": round(target_disclosed_weight, 6),
                    "minimum_disclosed_weight": MINIMUM_DISCLOSED_WEIGHT_FOR_MARKET_POSITION,
                },
            }
            comparisons.append(item)
            if (
                sample_status == "sufficient"
                and dispersion.get("status") == "material"
                and percentile is not None
                and metric_key in LABEL_METRICS
                and (percentile <= 33.333333 or percentile >= 66.666667)
            ):
                labels.append(position_label)

        sufficient_metrics = [
            item for item in comparisons if item.get("sample_status") == "sufficient"
        ]
        missing_items = list(target_profile.get("missing_items") or [])
        if len(metric_rows) < minimum_peer_count:
            missing_items.append(
                f"{quarter} 同类公开持仓仅 {len(metric_rows)} 只，最低需要 {minimum_peer_count} 只；"
                "只展示本基金持仓证据，不生成同类高低标签。"
            )

        return {
            "status": "peer_comparison_ready" if sufficient_metrics else "insufficient_peer_sample",
            "method": "cross_market_holding_peer_comparison_v1",
            "included_in_score": False,
            "wind_code": code,
            "quarter": quarter,
            "peer_group_id": peer_group_id,
            "peer_group_name": peer_group_name,
            "classified_peer_count": len(peer_funds),
            "profile_peer_count": len(metric_rows),
            "minimum_peer_count": minimum_peer_count,
            "target": {
                "total_disclosed_weight": target_profile.get("total_disclosed_weight"),
                "metrics": target_metrics,
                "markets": [
                    {
                        "market_code": item.get("market_code"),
                        "market_label": item.get("market_label"),
                        "disclosed_weight": item.get("disclosed_weight"),
                        "share_of_disclosed": item.get("share_of_disclosed"),
                        "security_hhi": item.get("security_hhi"),
                        "industry_hhi": item.get("industry_hhi"),
                    }
                    for item in target_profile.get("markets") or []
                ],
            },
            "comparisons": comparisons,
            "labels": list(dict.fromkeys(labels)),
            "source": "local_postgres.holdings+standardized_peer_group_membership",
            "missing_items": list(dict.fromkeys(str(item) for item in missing_items if item)),
            "boundary": "同类比较只使用同一季度、同一标准同类组的公开持仓；属于解释证据，不参与基金评分。",
        }

    @classmethod
    def _profile_metrics(cls, profile: Dict[str, Any]) -> Dict[str, float]:
        total_weight = _number(profile.get("total_disclosed_weight"))
        if total_weight is None or total_weight <= 0:
            return {}
        markets = profile.get("markets") or []
        market_map = {
            str(item.get("market_code") or ""): item
            for item in markets
            if item.get("market_code")
        }
        market_shares = [
            value
            for item in markets
            if (value := _number(item.get("share_of_disclosed"))) is not None
        ]
        security_hhi = 0.0
        industry_hhi = 0.0
        classified_industry_weight = 0.0
        holding_weights = []
        for market in markets:
            market_share = _number(market.get("share_of_disclosed")) or 0.0
            market_security_hhi = _number(market.get("security_hhi"))
            if market_security_hhi is not None:
                security_hhi += market_share * market_share * market_security_hhi
            for industry in market.get("industry_exposures") or []:
                weight = _number(industry.get("fund_nav_weight"))
                if weight is not None and str(industry.get("industry") or "") != "行业待补":
                    industry_hhi += (weight / total_weight) ** 2
                    classified_industry_weight += weight
            for holding in market.get("top_holdings") or []:
                weight = _number(holding.get("fund_nav_weight"))
                if weight is not None:
                    holding_weights.append(weight)

        cn_a = market_map.get("CN_A") or {}
        hong_kong = market_map.get("HK") or {}
        metrics = {
            "cn_a_weight": _number(cn_a.get("disclosed_weight")) or 0.0,
            "hk_weight": _number(hong_kong.get("disclosed_weight")) or 0.0,
            "hk_share_of_disclosed": _number(hong_kong.get("share_of_disclosed")) or 0.0,
            "market_allocation_hhi": sum(value * value for value in market_shares),
            "security_hhi": security_hhi,
            "top_three_share_of_disclosed": sum(sorted(holding_weights, reverse=True)[:3]) / total_weight,
        }
        if classified_industry_weight / total_weight >= 0.8:
            metrics["industry_hhi"] = industry_hhi
        return metrics

    @staticmethod
    def _percentile(value: float, values: Iterable[float]) -> float:
        ordered = sorted(float(item) for item in values)
        if len(ordered) <= 1:
            return 50.0
        less = sum(1 for item in ordered if item < value)
        equal = sum(1 for item in ordered if math.isclose(item, value, rel_tol=1e-9, abs_tol=1e-12))
        average_zero_based_rank = less + max(0, equal - 1) / 2
        return average_zero_based_rank / (len(ordered) - 1) * 100

    @staticmethod
    def _dispersion(values: List[float], absolute_range: float) -> Dict[str, Any]:
        if not values:
            return {"status": "unavailable", "range": None, "material_threshold": absolute_range}
        span = max(values) - min(values)
        center = abs(float(median(values)))
        threshold = max(absolute_range, center * 0.20)
        return {
            "status": "material" if span >= threshold else "not_material",
            "range": round(span, 6),
            "material_threshold": round(threshold, 6),
        }

    @staticmethod
    def _position_label(metric: str, label: str, percentile: float, material: bool) -> str:
        if not material:
            return f"{label}同类差异不明显"
        if metric == "hk_share_of_disclosed":
            if percentile <= 33.333333:
                return "已披露持仓中港股暴露同类偏低"
            if percentile >= 66.666667:
                return "已披露持仓中港股暴露同类偏高"
            return "已披露持仓中港股暴露同类中等"
        if percentile <= 33.333333:
            return f"{label}同类偏低"
        if percentile >= 66.666667:
            return f"{label}同类偏高"
        return f"{label}同类中等"

    @staticmethod
    def _unavailable(
        wind_code: str,
        status: str,
        peer_group_name: Any,
        minimum_peer_count: int,
        missing_items: List[str],
        quarter: Optional[str] = None,
        peer_group_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {
            "status": status,
            "method": "cross_market_holding_peer_comparison_v1",
            "included_in_score": False,
            "wind_code": wind_code,
            "quarter": quarter,
            "peer_group_id": peer_group_id,
            "peer_group_name": peer_group_name,
            "profile_peer_count": 0,
            "minimum_peer_count": minimum_peer_count,
            "target": {},
            "comparisons": [],
            "labels": [],
            "source": "local_postgres.holdings+standardized_peer_group_membership",
            "missing_items": missing_items,
            "boundary": "同类比较只使用同一季度、同一标准同类组的公开持仓；属于解释证据，不参与基金评分。",
        }
