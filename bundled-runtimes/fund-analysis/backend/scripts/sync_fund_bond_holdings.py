#!/usr/bin/env python3
"""将公开重仓债券及其可解释券种结构同步到本地。"""

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
from services.fund_bond_holding_service import FundBondHoldingService


def parse_codes(value: str) -> List[str]:
    return list(dict.fromkeys(item.strip().upper() for item in value.split(",") if item.strip()))


def select_candidates(limit: int, include_existing: bool) -> List[str]:
    existing_filter = "" if include_existing else "AND NOT EXISTS (SELECT 1 FROM fund_bond_holdings holding WHERE holding.wind_code = fund.wind_code)"
    sql = text(f"""
        SELECT fund.wind_code
        FROM funds fund
        WHERE {active_fund_sql('fund')}
          AND (fund.type ILIKE '%债%' OR fund.name ILIKE '%债%')
          {existing_filter}
        ORDER BY fund.total_asset DESC NULLS LAST, fund.wind_code
        LIMIT :limit
    """)
    with get_engine().connect() as conn:
        return [str(row.wind_code) for row in conn.execute(sql, {"limit": max(1, limit)}).fetchall()]


def main() -> int:
    parser = argparse.ArgumentParser(description="同步公开重仓债券结构")
    parser.add_argument("--codes", default="", help="逗号分隔的基金代码")
    parser.add_argument("--limit", type=int, default=10, help="未指定代码时按规模同步的债券基金数量")
    parser.add_argument("--include-existing", action="store_true", help="重新同步已有债券持仓")
    parser.add_argument("--metadata-periods", type=int, default=1, help="补齐最近多少期的债券主数据，0 表示只更新券种，专业画像建议使用 4")
    parser.add_argument("--throttle", type=float, default=0.25)
    args = parser.parse_args()

    init_database()
    codes = parse_codes(args.codes) or select_candidates(args.limit, args.include_existing)
    service = FundBondHoldingService()
    results = []
    for index, code in enumerate(codes, start=1):
        result = service.sync(code, metadata_periods=max(0, min(args.metadata_periods, 6)))
        results.append(result)
        print(f"[{index}/{len(codes)}] {code} {result['status']} {result.get('records', 0)} 条")
        if args.throttle > 0:
            time.sleep(args.throttle)

    summary = {
        "source": FundBondHoldingService.SOURCE,
        "requested": len(results),
        "synced": sum(item["status"] == "synced" for item in results),
        "unavailable": sum(item["status"] != "synced" for item in results),
        "records": sum(int(item.get("records") or 0) for item in results),
        "results": results,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
