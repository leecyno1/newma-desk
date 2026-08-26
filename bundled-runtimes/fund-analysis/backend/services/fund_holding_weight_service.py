"""用同报告期基金净资产把公开重仓股市值转换为基金净值权重。"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from lib.holding_weight_validation import normalize_holding_weights, validate_fund_nav_weights


class FundHoldingWeightService:
    """优先保留 Tushare 已给出的净值权重，缺失时使用东财定期报告净资产补齐。"""

    NET_ASSET_YI_TO_CNY = 100_000_000
    STOCK_RATIO_TOLERANCE = 0.02

    def __init__(self, asset_allocation_service: Optional[Any] = None):
        self._asset_allocation_service = asset_allocation_service

    def enrich(
        self,
        wind_code: str,
        quarter: str,
        holdings: List[Dict[str, Any]],
        refresh_allocation: bool = False,
    ) -> Dict[str, Any]:
        normalized, initial_validation = normalize_holding_weights(holdings)
        if initial_validation.is_complete:
            return self._result(normalized, initial_validation, "existing_fund_nav_weight", False)

        report_date = self._quarter_end(quarter)
        allocation_payload = self.asset_allocation_service.get(
            wind_code,
            limit=20,
            refresh=refresh_allocation,
        )
        allocation = next(
            (
                item for item in allocation_payload.get("history", [])
                if str(item.get("report_date") or "")[:10] == report_date
            ),
            None,
        )
        net_asset_yi = self._number((allocation or {}).get("net_asset_yi"))
        if net_asset_yi is None or net_asset_yi <= 0:
            return self._result(
                normalized,
                initial_validation,
                "fund_net_asset_unavailable",
                False,
                [f"{report_date} 定期报告缺少基金净资产，不能换算基金净值权重。"],
            )

        fund_net_asset_cny = net_asset_yi * self.NET_ASSET_YI_TO_CNY
        enriched = []
        for holding in normalized:
            item = dict(holding)
            market_value_cny = self._number(item.get("market_cap"))
            if market_value_cny is not None and market_value_cny >= 0:
                weight = market_value_cny / fund_net_asset_cny
                item.update({
                    "weight": weight,
                    "fund_nav_weight": weight,
                    "weight_basis": "fund_nav",
                    "fund_net_asset": fund_net_asset_cny,
                    "fund_net_asset_basis": "eastmoney.asset_allocation.net_asset_yi",
                    "fund_net_asset_date": report_date,
                    "weight_source": (allocation or {}).get("source") or "eastmoney.fundf10.asset_allocation",
                    "weight_source_url": (allocation or {}).get("source_url"),
                })
            enriched.append(item)

        implied_weight = sum(
            value for value in (self._number(item.get("fund_nav_weight")) for item in enriched)
            if value is not None
        )
        stock_ratio = self._number((allocation or {}).get("stock_ratio"))
        if stock_ratio is not None and implied_weight > stock_ratio + self.STOCK_RATIO_TOLERANCE:
            return self._result(
                normalized,
                initial_validation,
                "allocation_consistency_gate",
                False,
                [
                    f"重仓股推算权重 {implied_weight:.1%} 高于同报告期股票仓位 {stock_ratio:.1%}，"
                    "已拒绝使用该净资产分母。"
                ],
                allocation,
            )

        enriched, validation = normalize_holding_weights(enriched)
        if validation.is_invalid:
            return self._result(
                enriched,
                validation,
                "invalid_weight_scale",
                False,
                ["推算后的基金净值权重超出合法范围，未进入持仓风格和归因计算。"],
                allocation,
            )
        return self._result(
            enriched,
            validation,
            "eastmoney.asset_allocation.net_asset_yi",
            validation.valid_count > 0,
            [],
            allocation,
        )

    @property
    def asset_allocation_service(self):
        if self._asset_allocation_service is None:
            from services.fund_asset_allocation_service import FundAssetAllocationService

            self._asset_allocation_service = FundAssetAllocationService()
        return self._asset_allocation_service

    @staticmethod
    def _quarter_end(quarter: str) -> str:
        suffix = {"Q1": "03-31", "Q2": "06-30", "Q3": "09-30", "Q4": "12-31"}.get(quarter[4:])
        if not suffix or len(quarter) != 6 or not quarter[:4].isdigit():
            raise ValueError("季度必须使用 YYYYQ1-YYYYQ4")
        return f"{quarter[:4]}-{suffix}"

    @staticmethod
    def _number(value: Any) -> Optional[float]:
        try:
            parsed = float(value)
            return parsed if math.isfinite(parsed) else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _result(
        holdings: List[Dict[str, Any]],
        validation: Any,
        source: str,
        changed: bool,
        missing_items: Optional[List[str]] = None,
        allocation: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {
            "holdings": holdings,
            "weight_validation": validation.as_dict(),
            "weight_source": source,
            "changed": changed,
            "allocation": allocation,
            "missing_items": missing_items or [],
        }
