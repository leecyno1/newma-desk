"""基金持仓权重的统一口径校验。"""
from dataclasses import dataclass
import math
from typing import Any, Dict, Iterable, List, Optional, Tuple


MAX_FUND_NAV_WEIGHT = 1.0
MAX_FUND_NAV_WEIGHT_SUM = 1.001
MIN_STYLE_COVERAGE = 0.20

VALID_WEIGHT = "valid"
PARTIAL_FUND_NAV_WEIGHT = "partial_fund_nav_weight"
MISSING_FUND_NAV_WEIGHT = "missing_fund_nav_weight"
INVALID_WEIGHT_SCALE = "invalid_weight_scale"


def _number(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    except (TypeError, ValueError):
        return None


def fund_nav_weight(holding: Dict[str, Any]) -> Optional[float]:
    """只读取明确标记为基金净值口径且未失效的权重。"""
    if str(holding.get("weight_validation_status") or "").lower() == INVALID_WEIGHT_SCALE:
        return None
    basis = str(holding.get("weight_basis") or "").strip().lower()
    explicit = holding.get("fund_nav_weight")
    if explicit is not None and basis in {"", "fund_nav"}:
        return _number(explicit)
    if basis == "fund_nav":
        return _number(holding.get("weight"))
    return None


@dataclass(frozen=True)
class HoldingWeightValidation:
    status: str
    total_weight: float
    valid_count: int
    missing_count: int
    invalid_count: int
    reason: Optional[str] = None

    @property
    def is_invalid(self) -> bool:
        return self.status == INVALID_WEIGHT_SCALE

    @property
    def is_complete(self) -> bool:
        return self.status == VALID_WEIGHT

    def as_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "total_weight": round(self.total_weight, 6),
            "valid_count": self.valid_count,
            "missing_count": self.missing_count,
            "invalid_count": self.invalid_count,
            "reason": self.reason,
        }


def validate_fund_nav_weights(holdings: Iterable[Dict[str, Any]]) -> HoldingWeightValidation:
    items = list(holdings)
    weights: List[float] = []
    missing_count = 0
    invalid_count = 0

    for holding in items:
        if str(holding.get("weight_validation_status") or "").lower() == INVALID_WEIGHT_SCALE:
            invalid_count += 1
            continue
        basis = str(holding.get("weight_basis") or "").strip().lower()
        raw = holding.get("fund_nav_weight")
        if raw is None and basis == "fund_nav":
            raw = holding.get("weight")
        if raw is None or basis not in {"", "fund_nav"}:
            missing_count += 1
            continue
        weight = _number(raw)
        if weight is None or weight < 0 or weight > MAX_FUND_NAV_WEIGHT:
            invalid_count += 1
            continue
        weights.append(weight)

    total_weight = sum(weights)
    if invalid_count:
        return HoldingWeightValidation(
            status=INVALID_WEIGHT_SCALE,
            total_weight=total_weight,
            valid_count=len(weights),
            missing_count=missing_count,
            invalid_count=invalid_count,
            reason="individual_weight_out_of_range",
        )
    if total_weight > MAX_FUND_NAV_WEIGHT_SUM:
        return HoldingWeightValidation(
            status=INVALID_WEIGHT_SCALE,
            total_weight=total_weight,
            valid_count=len(weights),
            missing_count=missing_count,
            invalid_count=len(weights),
            reason="portfolio_weight_sum_exceeds_one",
        )
    if not weights:
        return HoldingWeightValidation(
            status=MISSING_FUND_NAV_WEIGHT,
            total_weight=0.0,
            valid_count=0,
            missing_count=missing_count or len(items),
            invalid_count=0,
            reason="fund_nav_weight_unavailable",
        )
    if missing_count:
        return HoldingWeightValidation(
            status=PARTIAL_FUND_NAV_WEIGHT,
            total_weight=total_weight,
            valid_count=len(weights),
            missing_count=missing_count,
            invalid_count=0,
            reason="fund_nav_weight_incomplete",
        )
    return HoldingWeightValidation(
        status=VALID_WEIGHT,
        total_weight=total_weight,
        valid_count=len(weights),
        missing_count=0,
        invalid_count=0,
    )


def normalize_holding_weights(
    holdings: Iterable[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], HoldingWeightValidation]:
    """校验并清除异常基金净值权重，保留股票组合占比。"""
    normalized = [dict(item) for item in holdings]
    validation = validate_fund_nav_weights(normalized)

    if validation.is_invalid:
        for item in normalized:
            item["weight"] = None
            item["fund_nav_weight"] = None
            item["weight_basis"] = (
                "equity_portfolio"
                if _number(item.get("equity_portfolio_weight")) is not None
                else "unknown"
            )
            item["weight_validation_status"] = INVALID_WEIGHT_SCALE
        return normalized, validation

    for item in normalized:
        weight = fund_nav_weight(item)
        if weight is not None:
            item["weight"] = weight
            item["fund_nav_weight"] = weight
            item["weight_basis"] = "fund_nav"
        elif _number(item.get("equity_portfolio_weight")) is not None:
            item["weight"] = None
            item["fund_nav_weight"] = None
            item["weight_basis"] = "equity_portfolio"
        item["weight_validation_status"] = validation.status
    return normalized, validation
