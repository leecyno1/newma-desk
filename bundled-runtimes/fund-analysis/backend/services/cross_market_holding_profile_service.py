"""公开持仓的跨市场画像；与 A 股 Barra 描述子严格分离。"""

from typing import Any, Dict, List, Optional

from lib.holding_weight_validation import INVALID_WEIGHT_SCALE, fund_nav_weight, validate_fund_nav_weights


class CrossMarketHoldingProfileService:
    def __init__(self, industry_snapshot_repo: Optional[Any] = None):
        self.industry_snapshot_repo = industry_snapshot_repo

    def analyze(self, holdings: List[Dict[str, Any]], quarter: str) -> Dict[str, Any]:
        validation = validate_fund_nav_weights(holdings)
        if validation.status == INVALID_WEIGHT_SCALE:
            return {
                "status": "insufficient_evidence",
                "quarter": quarter,
                "source": "invalid_weight_scale_gate",
                "markets": [],
                "total_disclosed_weight": 0.0,
                "weight_validation": validation.as_dict(),
                "missing_items": ["持仓基金净值权重口径异常，已阻止跨市场持仓画像。"],
                "boundary": "跨市场画像只使用以基金净值为分母的公开持仓。",
            }

        rows = []
        for holding in holdings:
            weight = fund_nav_weight(holding)
            code = str(holding.get("stock_code") or "").strip().upper()
            if not code or weight is None or weight <= 0:
                continue
            rows.append({
                **holding,
                "stock_code": code,
                "weight": float(weight),
                "market_code": self._market_code(code),
            })

        total_weight = sum(item["weight"] for item in rows)
        if not rows or total_weight <= 0:
            return {
                "status": "insufficient_evidence",
                "quarter": quarter,
                "source": "fund_portfolio_disclosure_gate",
                "markets": [],
                "total_disclosed_weight": 0.0,
                "weight_validation": validation.as_dict(),
                "missing_items": ["缺少以基金净值为分母的公开持仓，不能计算跨市场画像。"],
                "boundary": "跨市场画像只使用以基金净值为分母的公开持仓。",
            }

        industry_evidence = self._enrich_hong_kong_industries(rows)
        markets = []
        for market_code in ("CN_A", "HK", "OTHER"):
            market_rows = [item for item in rows if item["market_code"] == market_code]
            if not market_rows:
                continue
            markets.append(self._market_profile(market_code, market_rows, total_weight, industry_evidence))

        missing_items = []
        if total_weight < 0.8:
            missing_items.append(
                f"公开持仓合计覆盖基金净值的 {total_weight:.1%}，市场和集中度结论只代表已披露部分。"
            )
        if any(item["market_code"] == "OTHER" for item in rows):
            missing_items.append("存在当前未识别的证券市场代码，已单独归入其他市场。")
        if industry_evidence.get("status") == "partial_evidence":
            missing_items.append(
                f"港股行业官方分类匹配 {industry_evidence.get('matched_holding_count', 0)}/"
                f"{industry_evidence.get('hong_kong_holding_count', 0)} 只。"
            )

        labels = self._labels(markets)
        has_hong_kong = any(item["market_code"] == "HK" for item in markets)
        return {
            "status": "available" if total_weight >= 0.8 and not missing_items else "partial_evidence",
            "method": "cross_market_disclosed_holding_profile",
            "quarter": quarter,
            "source": "local_postgres.holdings+hang_seng_indexes.official" if has_hong_kong else "local_postgres.holdings+tushare.stock_basic",
            "weight_basis": "fund_nav",
            "total_disclosed_weight": round(total_weight, 6),
            "markets": markets,
            "labels": labels,
            "industry_evidence": industry_evidence,
            "weight_validation": validation.as_dict(),
            "missing_items": missing_items,
            "boundary": "这是公开持仓的市场、行业与集中度画像，不是 Barra 因子模型，也不代表完整组合。",
        }

    def _enrich_hong_kong_industries(self, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        hong_kong_rows = [item for item in rows if item["market_code"] == "HK"]
        if not hong_kong_rows:
            return {"status": "not_applicable", "hong_kong_holding_count": 0, "matched_holding_count": 0}
        try:
            repo = self.industry_snapshot_repo
            if repo is None:
                from repositories import get_market_index_constituent_repo

                repo = get_market_index_constituent_repo()
            snapshot = repo.get_latest("HSCI-INDUSTRY")
        except Exception:
            snapshot = None
        if not snapshot:
            return {
                "status": "unavailable",
                "hong_kong_holding_count": len(hong_kong_rows),
                "matched_holding_count": 0,
            }
        industry_map = {
            str(item.get("constituent_code") or "").upper(): str(item.get("industry") or "")
            for item in snapshot.get("constituents") or []
            if item.get("constituent_code") and item.get("industry")
        }
        matched = 0
        for item in hong_kong_rows:
            industry = industry_map.get(item["stock_code"])
            if industry:
                item["industry"] = industry
                matched += 1
        return {
            "status": "available" if matched == len(hong_kong_rows) else "partial_evidence",
            "hong_kong_holding_count": len(hong_kong_rows),
            "matched_holding_count": matched,
            "as_of_date": snapshot.get("as_of_date"),
            "source": snapshot.get("source"),
        }

    @classmethod
    def _market_profile(
        cls,
        market_code: str,
        rows: List[Dict[str, Any]],
        total_weight: float,
        industry_evidence: Dict[str, Any],
    ) -> Dict[str, Any]:
        ordered = sorted(rows, key=lambda item: item["weight"], reverse=True)
        market_weight = sum(item["weight"] for item in ordered)
        normalized_weights = [item["weight"] / market_weight for item in ordered]
        industries: Dict[str, float] = {}
        for item in ordered:
            industry = str(item.get("industry") or "行业待补")
            industries[industry] = industries.get(industry, 0.0) + item["weight"]
        industry_rows = sorted(industries.items(), key=lambda item: item[1], reverse=True)
        classified_industry_weight = sum(
            item["weight"]
            for item in ordered
            if str(item.get("industry") or "").strip()
            and str(item.get("industry") or "").strip() != "行业待补"
        )
        market_labels = {"CN_A": "A股", "HK": "港股", "OTHER": "其他市场"}
        industry_source = (
            industry_evidence.get("source")
            if market_code == "HK"
            else "tushare.stock_basic"
            if market_code == "CN_A"
            else None
        )
        return {
            "market_code": market_code,
            "market_label": market_labels[market_code],
            "holding_count": len(ordered),
            "disclosed_weight": round(market_weight, 6),
            "share_of_disclosed": round(market_weight / total_weight, 6),
            "top_one_weight": round(ordered[0]["weight"], 6),
            "top_three_weight": round(sum(item["weight"] for item in ordered[:3]), 6),
            "top_three_share_within_market": round(sum(normalized_weights[:3]), 6),
            "security_hhi": round(sum(weight * weight for weight in normalized_weights), 6),
            "industry_hhi": round(sum((weight / market_weight) ** 2 for _, weight in industry_rows), 6),
            "industry_classification_coverage": round(classified_industry_weight / market_weight, 6),
            "industry_source": industry_source,
            "industry_as_of_date": industry_evidence.get("as_of_date") if market_code == "HK" else None,
            "industry_exposures": [
                {
                    "industry": industry,
                    "fund_nav_weight": round(weight, 6),
                    "share_within_market": round(weight / market_weight, 6),
                }
                for industry, weight in industry_rows
            ],
            "top_holdings": [
                {
                    "stock_code": item["stock_code"],
                    "stock_name": item.get("stock_name"),
                    "industry": item.get("industry") or "行业待补",
                    "fund_nav_weight": round(item["weight"], 6),
                }
                for item in ordered[:5]
            ],
        }

    @staticmethod
    def _labels(markets: List[Dict[str, Any]]) -> List[str]:
        labels = []
        hong_kong = next((item for item in markets if item["market_code"] == "HK"), None)
        if hong_kong and hong_kong["share_of_disclosed"] >= 0.5:
            labels.append("已披露持仓以港股为主")
        elif hong_kong and hong_kong["share_of_disclosed"] >= 0.2:
            labels.append("已披露持仓含明显港股暴露")
        for market in markets:
            if market["security_hhi"] >= 0.35:
                labels.append(f"{market['market_label']}个股集中度较高")
            if market["industry_hhi"] >= 0.45:
                labels.append(f"{market['market_label']}行业集中度较高")
        return list(dict.fromkeys(labels))

    @staticmethod
    def _market_code(code: str) -> str:
        if code.endswith(".HK"):
            return "HK"
        if code.endswith((".SH", ".SZ", ".BJ")):
            return "CN_A"
        return "OTHER"
