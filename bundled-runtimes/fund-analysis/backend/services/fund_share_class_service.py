"""同一基金实体的份额类别与可核验费率事实。"""

import math
import re
from typing import Any, Dict, List, Optional


class FundShareClassService:
    BOUNDARY = (
        "同一基金不同份额通常共享投资组合，但费率、成立时间和销售对象可能不同；"
        "这里只展示本地已核验事实，不推荐具体份额。"
    )

    def __init__(self, classification_repo: Optional[Any] = None, fund_repo: Optional[Any] = None):
        if classification_repo is None or fund_repo is None:
            from repositories import get_fund_classification_repo, get_fund_repo

            classification_repo = classification_repo or get_fund_classification_repo()
            fund_repo = fund_repo or get_fund_repo()
        self.classification_repo = classification_repo
        self.fund_repo = fund_repo

    def get(self, wind_code: str) -> Dict[str, Any]:
        code = str(wind_code or "").strip().upper()
        if not self.fund_repo.get_fund(code):
            raise ValueError(f"Fund not found: {code}")

        rows = self.classification_repo.list_entity_share_classes(code)
        if not rows:
            return {
                "wind_code": code,
                "status": "unavailable",
                "entity": None,
                "share_count": 0,
                "shares": [],
                "fee_evidence": self._fee_evidence([]),
                "boundary": self.BOUNDARY,
                "missing_items": ["该基金尚未归一到基金实体与份额映射"],
            }

        shares = [self._share_payload(row, current_code=code) for row in rows]
        entity = {
            "entity_id": str(rows[0].get("entity_id") or ""),
            "canonical_code": str(rows[0].get("canonical_code") or ""),
            "canonical_name": str(rows[0].get("canonical_name") or ""),
        }
        return {
            "wind_code": code,
            "status": "available" if len(shares) > 1 else "single_share",
            "entity": entity,
            "share_count": len(shares),
            "shares": shares,
            "fee_evidence": self._fee_evidence(shares),
            "boundary": self.BOUNDARY,
            "missing_items": [],
        }

    @classmethod
    def _share_payload(cls, row: Dict[str, Any], current_code: str) -> Dict[str, Any]:
        raw_data = row.get("raw_data") if isinstance(row.get("raw_data"), dict) else {}
        info = raw_data.get("info") if isinstance(raw_data.get("info"), dict) else {}
        universe = raw_data.get("universe") if isinstance(raw_data.get("universe"), dict) else {}
        profile = raw_data.get("product_profile") if isinstance(raw_data.get("product_profile"), dict) else {}
        profile_fees = profile.get("fees") if isinstance(profile.get("fees"), dict) else {}

        management_fee = cls._profile_rate(profile_fees.get("management_fee_rate"))
        if management_fee is None:
            management_fee = cls._source_rate(
            info.get("management_fee"),
            info.get("m_fee"),
            universe.get("management_fee"),
            universe.get("m_fee"),
        )
        custodian_fee = cls._profile_rate(profile_fees.get("custodian_fee_rate"))
        if custodian_fee is None:
            custodian_fee = cls._source_rate(
            info.get("custodian_fee"),
            info.get("c_fee"),
            universe.get("custodian_fee"),
            universe.get("c_fee"),
        )
        sales_service_fee = cls._profile_rate(profile_fees.get("sales_service_fee_rate"))
        known_core_fee = None
        if management_fee is not None or custodian_fee is not None:
            known_core_fee = (management_fee or 0) + (custodian_fee or 0)

        missing = []
        if management_fee is None:
            missing.append("管理费率")
        if custodian_fee is None:
            missing.append("托管费率")
        if sales_service_fee is None:
            missing.append("销售服务费率")

        code = str(row.get("wind_code") or "").upper()
        return {
            "wind_code": code,
            "name": row.get("name"),
            "share_class": row.get("share_class"),
            "fee_class": row.get("fee_class"),
            "currency": row.get("currency") or "CNY",
            "is_primary": bool(row.get("is_primary")),
            "is_current": code == current_code,
            "nav": cls._number(row.get("nav")),
            "nav_date": row.get("nav_date"),
            "total_asset": cls._number(row.get("total_asset")),
            "establishment_date": row.get("establishment_date"),
            "management_fee_rate": management_fee,
            "custodian_fee_rate": custodian_fee,
            "sales_service_fee_rate": sales_service_fee,
            "known_core_fee_rate": known_core_fee,
            "fee_profile_status": profile.get("status") or "unavailable",
            "fee_source_url": (profile.get("source_urls") or {}).get("fees")
            if isinstance(profile.get("source_urls"), dict) else None,
            "fee_synced_at": profile.get("synced_at"),
            "missing_fee_items": missing,
            "source": row.get("share_source") or "fund_share_classes",
            "source_updated_at": row.get("source_updated_at") or row.get("updated_at"),
        }

    @staticmethod
    def _fee_evidence(shares: List[Dict[str, Any]]) -> Dict[str, Any]:
        core_ready = sum(1 for share in shares if share.get("known_core_fee_rate") is not None)
        sales_fee_ready = sum(1 for share in shares if share.get("sales_service_fee_rate") is not None)
        return {
            "core_fee_ready_count": core_ready,
            "sales_service_fee_ready_count": sales_fee_ready,
            "share_count": len(shares),
            "status": "complete" if shares and core_ready == len(shares) and sales_fee_ready == len(shares)
            else "partial" if core_ready else "insufficient",
            "note": "管理费和托管费可直接横向核对；销售服务费未取得时保持为空，不根据 A/C/Y 名称猜测。",
        }

    @classmethod
    def _profile_rate(cls, value: Any) -> Optional[float]:
        """公开费率页通常带百分号；无百分号时沿用项目既有费率口径。"""
        parsed = cls._parse_number(value)
        if parsed is None:
            return None
        text = str(value or "")
        return parsed / 100 if "%" in text or abs(parsed) >= 0.05 else parsed

    @classmethod
    def _source_rate(cls, *values: Any) -> Optional[float]:
        """Tushare fund_basic 费率字段以百分数记录，例如 0.9 表示 0.9%。"""
        for value in values:
            number = cls._parse_number(value)
            if number is not None:
                return number / 100
        return None

    @staticmethod
    def _parse_number(value: Any) -> Optional[float]:
        if value is None or value == "":
            return None
        text = str(value).strip().replace(",", "")
        matched = re.search(r"-?\d+(?:\.\d+)?", text)
        if not matched:
            return None
        number = float(matched.group(0))
        return number if math.isfinite(number) else None

    @staticmethod
    def _number(value: Any) -> Optional[float]:
        try:
            number = float(value)
            return number if math.isfinite(number) else None
        except (TypeError, ValueError):
            return None
