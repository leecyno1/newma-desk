"""对比最近两期公开持仓，解释重仓股名单和权重变化。"""

from decimal import Decimal
from typing import Any, Dict, List, Optional


class FundHoldingChangeService:
    def __init__(self, repo: Optional[Any] = None, data_service: Optional[Any] = None):
        if repo is None:
            from repositories import get_holding_repo

            repo = get_holding_repo()
        self.repo = repo
        self.data_service = data_service

    def analyze(self, wind_code: str, refresh_missing: bool = True) -> Dict[str, Any]:
        history = self.repo.get_holdings_history(wind_code)
        grouped = self._group_by_quarter(history)

        if len(grouped) < 2 and refresh_missing:
            data_service = self.data_service
            if data_service is None:
                from service_registry import get_data_service

                data_service = get_data_service()
            for quarter in self._recent_completed_quarters(4):
                if quarter in grouped:
                    continue
                rows = data_service.get_fund_holdings(wind_code, quarter)
                if rows:
                    self.repo.upsert_holdings(wind_code, quarter, rows)
                    grouped[quarter] = rows
                if len(grouped) >= 2:
                    break

        quarters = sorted(grouped, reverse=True)
        if len(quarters) < 2:
            return {
                "wind_code": wind_code,
                "status": "insufficient_evidence",
                "latest_quarter": quarters[0] if quarters else None,
                "previous_quarter": None,
                "weight_basis": None,
                "changes": [],
                "summary": {},
                "missing_items": ["至少需要两个季度的公开持仓才能比较变化"],
            }

        latest_quarter, previous_quarter = quarters[:2]
        latest = grouped[latest_quarter][:10]
        previous = grouped[previous_quarter][:10]
        weight_basis = self._common_weight_basis(latest, previous)
        if not weight_basis:
            return {
                "wind_code": wind_code,
                "status": "insufficient_evidence",
                "latest_quarter": latest_quarter,
                "previous_quarter": previous_quarter,
                "weight_basis": None,
                "changes": [],
                "summary": {},
                "missing_items": ["最近两期持仓没有一致的可比权重口径"],
            }

        latest_map = {str(item.get("stock_code") or ""): item for item in latest if item.get("stock_code")}
        previous_map = {str(item.get("stock_code") or ""): item for item in previous if item.get("stock_code")}
        changes = []
        for stock_code in set(latest_map) | set(previous_map):
            latest_row = latest_map.get(stock_code)
            previous_row = previous_map.get(stock_code)
            latest_weight = self._number((latest_row or {}).get(weight_basis))
            previous_weight = self._number((previous_row or {}).get(weight_basis))
            delta = None if latest_weight is None or previous_weight is None else round(latest_weight - previous_weight, 8)
            if latest_row is None:
                change_type = "exited_top10"
            elif previous_row is None:
                change_type = "entered_top10"
            elif delta is not None and delta >= 0.001:
                change_type = "increased"
            elif delta is not None and delta <= -0.001:
                change_type = "decreased"
            else:
                change_type = "stable"
            row = latest_row or previous_row or {}
            changes.append({
                "stock_code": stock_code,
                "stock_name": row.get("stock_name") or stock_code,
                "industry": row.get("industry") or "",
                "latest_weight": latest_weight,
                "previous_weight": previous_weight,
                "weight_change": delta,
                "change_type": change_type,
            })

        changes.sort(
            key=lambda item: abs(item["weight_change"])
            if item["weight_change"] is not None
            else (item["latest_weight"] or item["previous_weight"] or 0),
            reverse=True,
        )
        comparable = [item for item in changes if item["weight_change"] is not None]
        increases = [item for item in comparable if item["weight_change"] > 0]
        decreases = [item for item in comparable if item["weight_change"] < 0]
        concentration_trend = self._concentration_trend(grouped, quarters[:4], weight_basis)
        industry_changes = self._industry_changes(latest, previous, weight_basis)
        stability = self._stability(latest, previous, weight_basis)
        latest_concentration = concentration_trend[0] if concentration_trend else {}
        previous_concentration = concentration_trend[1] if len(concentration_trend) > 1 else {}
        return {
            "wind_code": wind_code,
            "status": "available",
            "latest_quarter": latest_quarter,
            "previous_quarter": previous_quarter,
            "latest_report_date": self._report_date(latest),
            "previous_report_date": self._report_date(previous),
            "weight_basis": weight_basis,
            "changes": changes,
            "concentration_trend": concentration_trend,
            "industry_changes": industry_changes,
            "stability": stability,
            "summary": {
                "entered_top10_count": sum(item["change_type"] == "entered_top10" for item in changes),
                "exited_top10_count": sum(item["change_type"] == "exited_top10" for item in changes),
                "largest_increase": max(increases, key=lambda item: item["weight_change"], default=None),
                "largest_decrease": min(decreases, key=lambda item: item["weight_change"], default=None),
                "latest_top3_weight": latest_concentration.get("top3_weight"),
                "latest_top10_weight": latest_concentration.get("top10_weight"),
                "top3_weight_change": self._difference(latest_concentration.get("top3_weight"), previous_concentration.get("top3_weight")),
                "top10_weight_change": self._difference(latest_concentration.get("top10_weight"), previous_concentration.get("top10_weight")),
            },
            "source": "local.postgres.holdings",
            "scope": "持仓、集中度和行业变化均基于公开披露的前十大重仓股；权重变化不等同于基金经理主动买卖。",
            "missing_items": [],
        }

    @classmethod
    def _stability(
        cls,
        latest: List[Dict[str, Any]],
        previous: List[Dict[str, Any]],
        weight_basis: str,
    ) -> Dict[str, Any]:
        latest_weights = cls._normalized_weights(latest, weight_basis, "stock_code")
        previous_weights = cls._normalized_weights(previous, weight_basis, "stock_code")
        latest_industries = cls._normalized_weights(latest, weight_basis, "industry")
        previous_industries = cls._normalized_weights(previous, weight_basis, "industry")
        latest_codes = set(latest_weights)
        previous_codes = set(previous_weights)
        common_codes = latest_codes & previous_codes
        union_codes = latest_codes | previous_codes
        overlap_ratio = cls._overlap_ratio(latest_weights, previous_weights)
        industry_overlap_ratio = cls._overlap_ratio(latest_industries, previous_industries)
        jaccard_score = len(common_codes) / len(union_codes) if union_codes else 0.0
        level = cls._stability_level(overlap_ratio, jaccard_score)
        labels = {
            "high": "前十大持仓延续性较高",
            "medium": "前十大持仓有一定调整",
            "low": "前十大持仓变化较大",
        }
        return {
            "status": "available",
            "methodology": "consecutive_quarter_top10_normalized_overlap_v1",
            "level": level,
            "label": labels[level],
            "top10_overlap_ratio": round(overlap_ratio, 8),
            "industry_overlap_ratio": round(industry_overlap_ratio, 8),
            "jaccard_score": round(jaccard_score, 8),
            "retained_holding_count": len(common_codes),
            "union_holding_count": len(union_codes),
            "included_in_score": False,
            "boundary": "仅比较相邻两期公开前十大重仓股并归一化权重；不等同于完整组合换手率，也不修改基金综合评分。",
        }

    @classmethod
    def _normalized_weights(
        cls,
        rows: List[Dict[str, Any]],
        weight_basis: str,
        group_field: str,
    ) -> Dict[str, float]:
        buckets: Dict[str, float] = {}
        for row in rows:
            key = str(row.get(group_field) or "未知").strip()
            weight = cls._number(row.get(weight_basis))
            if not key or weight is None or weight <= 0:
                continue
            buckets[key] = buckets.get(key, 0.0) + weight
        total = sum(buckets.values())
        if total <= 0:
            return {}
        return {key: value / total for key, value in buckets.items()}

    @staticmethod
    def _overlap_ratio(left: Dict[str, float], right: Dict[str, float]) -> float:
        return sum(min(left.get(key, 0.0), right.get(key, 0.0)) for key in set(left) | set(right))

    @staticmethod
    def _stability_level(overlap_ratio: float, jaccard_score: float) -> str:
        if overlap_ratio >= 0.55 or jaccard_score >= 0.5:
            return "high"
        if overlap_ratio >= 0.25 or jaccard_score >= 0.25:
            return "medium"
        return "low"

    @staticmethod
    def _group_by_quarter(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            quarter = str(row.get("quarter") or "")
            if quarter:
                grouped.setdefault(quarter, []).append(row)
        return grouped

    @classmethod
    def _common_weight_basis(cls, latest: List[Dict[str, Any]], previous: List[Dict[str, Any]]) -> Optional[str]:
        rows = latest + previous
        if rows and all(cls._number(item.get("equity_portfolio_weight")) is not None for item in rows):
            return "equity_portfolio_weight"
        if rows and all(cls._number(item.get("weight")) is not None for item in rows):
            return "weight"
        return None

    @classmethod
    def _concentration_trend(
        cls,
        grouped: Dict[str, List[Dict[str, Any]]],
        quarters: List[str],
        weight_basis: str,
    ) -> List[Dict[str, Any]]:
        trend = []
        for quarter in quarters:
            rows = grouped.get(quarter, [])[:10]
            weights = [cls._number(item.get(weight_basis)) for item in rows]
            if not rows or any(value is None for value in weights):
                continue
            numeric_weights = [value for value in weights if value is not None]
            industry_buckets: Dict[str, float] = {}
            for row, weight in zip(rows, numeric_weights):
                industry = str(row.get("industry") or "未知")
                industry_buckets[industry] = industry_buckets.get(industry, 0.0) + weight
            top_industry, top_industry_weight = max(industry_buckets.items(), key=lambda item: item[1], default=("", 0.0))
            trend.append({
                "quarter": quarter,
                "report_date": cls._report_date(rows),
                "top3_weight": round(sum(numeric_weights[:3]), 8),
                "top10_weight": round(sum(numeric_weights), 8),
                "top_industry": top_industry,
                "top_industry_weight": round(top_industry_weight, 8),
            })
        return trend

    @classmethod
    def _industry_changes(
        cls,
        latest: List[Dict[str, Any]],
        previous: List[Dict[str, Any]],
        weight_basis: str,
    ) -> List[Dict[str, Any]]:
        def aggregate(rows: List[Dict[str, Any]]) -> Dict[str, float]:
            buckets: Dict[str, float] = {}
            for row in rows:
                weight = cls._number(row.get(weight_basis))
                if weight is None:
                    continue
                industry = str(row.get("industry") or "未知")
                buckets[industry] = buckets.get(industry, 0.0) + weight
            return buckets

        latest_buckets = aggregate(latest)
        previous_buckets = aggregate(previous)
        changes = [{
            "industry": industry,
            "latest_weight": round(latest_buckets.get(industry, 0.0), 8),
            "previous_weight": round(previous_buckets.get(industry, 0.0), 8),
            "weight_change": round(latest_buckets.get(industry, 0.0) - previous_buckets.get(industry, 0.0), 8),
        } for industry in set(latest_buckets) | set(previous_buckets)]
        changes.sort(key=lambda item: abs(item["weight_change"]), reverse=True)
        return changes

    @staticmethod
    def _difference(latest: Any, previous: Any) -> Optional[float]:
        if latest is None or previous is None:
            return None
        return round(float(latest) - float(previous), 8)

    @staticmethod
    def _number(value: Any) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return float(value)
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _report_date(rows: List[Dict[str, Any]]) -> Optional[str]:
        values = [str(item.get("report_date") or "") for item in rows if item.get("report_date")]
        return max(values) if values else None

    @staticmethod
    def _recent_completed_quarters(limit: int) -> List[str]:
        from datetime import datetime

        now = datetime.now()
        year = now.year
        quarter = (now.month - 1) // 3 + 1
        result = []
        for _ in range(limit):
            quarter -= 1
            if quarter == 0:
                year -= 1
                quarter = 4
            result.append(f"{year}Q{quarter}")
        return result
