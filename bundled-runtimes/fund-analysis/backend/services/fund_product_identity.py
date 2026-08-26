"""基金产品与份额身份工具。

只处理同一产品的 A/C/Y 等份额后缀，不根据名称猜测基金分类。
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict


_SHARE_SUFFIX = re.compile(
    r"(?:[-_ /]?)([A-Z])(?:类|份额)?"
    r"(?:[-_ /]?(?:CNY|RMB|USD|HKD)(?:[-_ /]?(?:现汇|现钞))?)?$",
    re.IGNORECASE,
)


def normalize_fund_product_name(value: Any) -> str:
    """移除明确的份额后缀，保留 ETF/LOF/QDII 产品名。"""
    name = re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(value or ""))).strip()
    if not name:
        return ""
    if name.upper().endswith(("ETF", "LOF", "QDII")):
        return name
    return _SHARE_SUFFIX.sub("", name).rstrip("-_ /") or name


def fund_product_identity(row: Dict[str, Any]) -> str:
    """优先使用标准基金实体，缺失时才使用份额名称归一结果。"""
    entity_id = str(row.get("entity_id") or "").strip()
    if entity_id:
        return f"entity:{entity_id}"
    name = normalize_fund_product_name(
        row.get("canonical_name") or row.get("fund_name") or row.get("name")
    )
    if name:
        return f"name:{name.lower()}"
    return f"code:{str(row.get('fund_code') or row.get('wind_code') or '').strip().upper()}"
