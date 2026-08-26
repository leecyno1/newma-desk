#!/usr/bin/env python3
"""将公开基金档案、资产配置和持有人结构同步到本地基金库。"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import List

from sqlalchemy import text

BASE_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BASE_DIR.parent
sys.path.insert(0, str(BASE_DIR))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT_DIR / ".env.local")
    load_dotenv(ROOT_DIR / ".env")
    load_dotenv(BASE_DIR / ".env")
except Exception:
    pass

from database import get_engine, init_database
from lib.fund_status import active_fund_sql
from services.fund_asset_allocation_service import FundAssetAllocationService
from services.fund_holder_structure_service import FundHolderStructureService
from services.fund_product_profile_service import FundProductProfileService


def parse_codes(value: str) -> List[str]:
    return list(dict.fromkeys(item.strip().upper() for item in value.split(",") if item.strip()))


def select_candidates(limit: int, include_existing: bool) -> List[str]:
    existing_filter = "" if include_existing else """
        AND (
          NOT (COALESCE(fund.raw_data, '{}'::jsonb) ? 'product_profile')
          OR NOT EXISTS (
            SELECT 1 FROM fund_asset_allocations allocation
            WHERE allocation.wind_code = fund.wind_code
          )
          OR NOT EXISTS (
            SELECT 1 FROM fund_holder_structures holder
            WHERE holder.wind_code = fund.wind_code
          )
        )
    """
    sql = text(f"""
        SELECT fund.wind_code
        FROM funds fund
        WHERE {active_fund_sql('fund')}
          {existing_filter}
        ORDER BY fund.total_asset DESC NULLS LAST, fund.wind_code
        LIMIT :limit
    """)
    with get_engine().connect() as conn:
        return [str(row.wind_code) for row in conn.execute(sql, {"limit": max(1, limit)}).fetchall()]


def main() -> int:
    parser = argparse.ArgumentParser(description="同步基金产品档案、完整费率、资产配置和持有人结构")
    parser.add_argument("--codes", default="", help="逗号分隔的基金代码")
    parser.add_argument("--limit", type=int, default=10, help="未指定代码时按规模同步的数量")
    parser.add_argument("--include-existing", action="store_true", help="重新同步已有产品档案")
    parser.add_argument("--throttle", type=float, default=0.2)
    args = parser.parse_args()

    init_database()
    codes = parse_codes(args.codes) or select_candidates(args.limit, args.include_existing)
    profile_service = FundProductProfileService()
    allocation_service = FundAssetAllocationService()
    holder_service = FundHolderStructureService()
    results = []
    for index, code in enumerate(codes, start=1):
        try:
            profile = profile_service.sync(code)
            allocation = allocation_service.sync(code)
            holder = holder_service.sync(code)
            result = {
                "wind_code": code,
                "status": profile.get("status"),
                "asset_allocation_status": allocation.get("status"),
                "asset_allocation_records": int(allocation.get("records") or 0),
                "holder_structure_status": holder.get("status"),
                "holder_structure_records": int(holder.get("records") or 0),
                "product_fields": sum(bool(value) for value in (profile.get("product") or {}).values()),
                "fee_rule_count": sum(
                    len((profile.get("fees") or {}).get(key) or [])
                    for key in ("subscription_fee_rules", "purchase_fee_rules", "redemption_fee_rules")
                ),
            }
        except Exception as exc:
            result = {"wind_code": code, "status": "failed", "error": str(exc)}
        results.append(result)
        print(
            f"[{index}/{len(codes)}] {code} "
            f"产品档案={result['status']} "
            f"资产配置={result.get('asset_allocation_status')} "
            f"持有人={result.get('holder_structure_status')}"
        )
        if args.throttle > 0:
            time.sleep(args.throttle)

    summary = {
        "source": FundProductProfileService.SOURCE,
        "requested": len(results),
        "available": sum(item["status"] == "available" for item in results),
        "asset_allocation_synced": sum(item.get("asset_allocation_status") == "synced" for item in results),
        "holder_structure_synced": sum(item.get("holder_structure_status") == "synced" for item in results),
        "failed": sum(item["status"] == "failed" for item in results),
        "results": results,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
