"""基金前十大公开重仓股相似度。"""

from itertools import combinations
from math import sqrt
from typing import Any, Dict, List, Optional, Tuple


class FundHoldingSimilarityService:
    SOURCE = "local.postgres.holdings"
    METHODOLOGY = "same_quarter_top10_normalized_overlap_v1"
    SCOPE = "仅比较同一报告期前十大公开重仓股，并将各自前十大权重归一化；不是完整组合相关性，也不代表未来收益联动。"

    def __init__(self, holding_repo: Optional[Any] = None):
        if holding_repo is None:
            from repositories import get_holding_repo

            holding_repo = get_holding_repo()
        self.holding_repo = holding_repo

    def build(self, wind_codes: List[str]) -> Dict[str, Any]:
        codes = []
        for value in wind_codes:
            code = str(value or "").strip().upper()
            if code and code not in codes:
                codes.append(code)
        if len(codes) < 2:
            raise ValueError("至少需要两只基金计算重仓相似度")
        if len(codes) > 6:
            raise ValueError("单次最多比较 6 只基金")

        histories = {
            code: self._prepare_history(self.holding_repo.get_holdings_history(code))
            for code in codes
        }
        pairs = [self._compare_pair(left, right, histories[left], histories[right]) for left, right in combinations(codes, 2)]
        available = [item for item in pairs if item["status"] == "available"]
        available.sort(key=lambda item: item["overlap_ratio"], reverse=True)
        unavailable = [item for item in pairs if item["status"] != "available"]
        ordered_pairs = available + unavailable

        return {
            "status": "available" if len(available) == len(pairs) else "partial" if available else "insufficient",
            "wind_codes": codes,
            "methodology": self.METHODOLOGY,
            "scope": self.SCOPE,
            "source": self.SOURCE,
            "simulation_used": False,
            "pair_count": len(pairs),
            "available_pair_count": len(available),
            "highest_overlap_pair": available[0] if available else None,
            "pairs": ordered_pairs,
            "missing_codes": [code for code in codes if not histories[code]],
        }

    def _compare_pair(
        self,
        fund_a: str,
        fund_b: str,
        history_a: Dict[str, Dict[str, Any]],
        history_b: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        common_quarters = sorted(set(history_a) & set(history_b), reverse=True)
        if not common_quarters:
            return self._unavailable_pair(fund_a, fund_b, "没有同一报告期的可信前十大持仓")

        quarter = common_quarters[0]
        snapshot_a = history_a[quarter]
        snapshot_b = history_b[quarter]
        holdings_a = snapshot_a["holdings"]
        holdings_b = snapshot_b["holdings"]
        map_a = {item["stock_code"]: item for item in holdings_a}
        map_b = {item["stock_code"]: item for item in holdings_b}
        common_codes = set(map_a) & set(map_b)
        union_codes = set(map_a) | set(map_b)

        common_holdings = []
        for stock_code in common_codes:
            item_a = map_a[stock_code]
            item_b = map_b[stock_code]
            contribution = min(item_a["normalized_weight"], item_b["normalized_weight"])
            common_holdings.append({
                "stock_code": stock_code,
                "stock_name": item_a.get("stock_name") or item_b.get("stock_name") or stock_code,
                "weight_a": item_a["raw_weight"],
                "weight_b": item_b["raw_weight"],
                "normalized_weight_a": item_a["normalized_weight"],
                "normalized_weight_b": item_b["normalized_weight"],
                "overlap_contribution": contribution,
            })
        common_holdings.sort(key=lambda item: item["overlap_contribution"], reverse=True)

        overlap_ratio = round(sum(item["overlap_contribution"] for item in common_holdings), 8)
        jaccard_score = round(len(common_codes) / len(union_codes), 8) if union_codes else 0.0
        cosine_similarity = self._cosine_similarity(map_a, map_b, union_codes)
        similarity_level = self._similarity_level(overlap_ratio, jaccard_score)

        return {
            "status": "available",
            "fund_a": fund_a,
            "fund_b": fund_b,
            "quarter": quarter,
            "report_date_a": snapshot_a.get("report_date"),
            "report_date_b": snapshot_b.get("report_date"),
            "weight_basis_a": snapshot_a.get("weight_basis"),
            "weight_basis_b": snapshot_b.get("weight_basis"),
            "holding_count_a": len(holdings_a),
            "holding_count_b": len(holdings_b),
            "common_holding_count": len(common_codes),
            "union_holding_count": len(union_codes),
            "overlap_ratio": overlap_ratio,
            "jaccard_score": jaccard_score,
            "cosine_similarity": cosine_similarity,
            "similarity_level": similarity_level,
            "common_holdings": common_holdings,
            "scope": self.SCOPE,
            "missing_items": [],
        }

    @classmethod
    def _prepare_history(cls, rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            quarter = str(row.get("quarter") or "").strip()
            if quarter:
                grouped.setdefault(quarter, []).append(row)

        prepared = {}
        for quarter, quarter_rows in grouped.items():
            snapshot = cls._prepare_snapshot(quarter_rows)
            if snapshot is not None:
                prepared[quarter] = snapshot
        return prepared

    @classmethod
    def _prepare_snapshot(cls, rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        allowed_basis = {str(row.get("weight_basis") or "") for row in rows} & {"fund_nav", "equity_portfolio"}
        if len(allowed_basis) != 1:
            return None
        weight_basis = next(iter(allowed_basis))
        weight_field = "weight" if weight_basis == "fund_nav" else "equity_portfolio_weight"

        holdings = []
        for row in rows:
            stock_code = str(row.get("stock_code") or "").strip().upper()
            weight = cls._positive_number(row.get(weight_field))
            if stock_code and weight is not None:
                holdings.append({
                    "stock_code": stock_code,
                    "stock_name": str(row.get("stock_name") or "").strip(),
                    "raw_weight": weight,
                })
        holdings.sort(key=lambda item: item["raw_weight"], reverse=True)
        holdings = holdings[:10]
        if len(holdings) < 5:
            return None

        total_weight = sum(item["raw_weight"] for item in holdings)
        if total_weight <= 0:
            return None
        for item in holdings:
            item["normalized_weight"] = round(item["raw_weight"] / total_weight, 8)

        first = rows[0] if rows else {}
        return {
            "weight_basis": weight_basis,
            "report_date": first.get("report_date"),
            "announcement_date": first.get("announcement_date"),
            "holdings": holdings,
        }

    @staticmethod
    def _cosine_similarity(
        map_a: Dict[str, Dict[str, Any]],
        map_b: Dict[str, Dict[str, Any]],
        union_codes: set[str],
    ) -> float:
        dot = sum(map_a.get(code, {}).get("normalized_weight", 0.0) * map_b.get(code, {}).get("normalized_weight", 0.0) for code in union_codes)
        norm_a = sqrt(sum(map_a.get(code, {}).get("normalized_weight", 0.0) ** 2 for code in union_codes))
        norm_b = sqrt(sum(map_b.get(code, {}).get("normalized_weight", 0.0) ** 2 for code in union_codes))
        return round(dot / (norm_a * norm_b), 8) if norm_a > 0 and norm_b > 0 else 0.0

    @staticmethod
    def _similarity_level(overlap_ratio: float, jaccard_score: float) -> str:
        if overlap_ratio >= 0.55 or jaccard_score >= 0.5:
            return "high"
        if overlap_ratio >= 0.25 or jaccard_score >= 0.25:
            return "medium"
        return "low"

    @classmethod
    def _unavailable_pair(cls, fund_a: str, fund_b: str, reason: str) -> Dict[str, Any]:
        return {
            "status": "insufficient",
            "fund_a": fund_a,
            "fund_b": fund_b,
            "quarter": None,
            "overlap_ratio": None,
            "jaccard_score": None,
            "cosine_similarity": None,
            "similarity_level": "unknown",
            "common_holdings": [],
            "scope": cls.SCOPE,
            "missing_items": [reason],
        }

    @staticmethod
    def _positive_number(value: Any) -> Optional[float]:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None
