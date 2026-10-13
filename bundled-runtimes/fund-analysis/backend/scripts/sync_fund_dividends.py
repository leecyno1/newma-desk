#!/usr/bin/env python3
"""批量同步基金分红事件（tushare fund_div）。

选基口径：有净值的研究宇宙（fund_nav 去重）。排序优先已确认分红史基金
（最久未同步在前，分红是连续事件，既有派息基金最可能新增），其次是从未
同步过的基金（发现首次分红）。replace 语义幂等，可安全重跑。
"""
import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

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

from database import get_engine, init_database  # noqa: E402
from repositories import get_fund_dividends_repo  # noqa: E402
from service_registry import get_strict_tushare_service  # noqa: E402


def select_candidates(limit: int) -> List[str]:
    sql = text("""
        WITH universe AS (SELECT DISTINCT wind_code FROM fund_nav)
        SELECT u.wind_code
        FROM universe u
        ORDER BY
            CASE WHEN EXISTS (
                SELECT 1 FROM fund_dividends d WHERE d.wind_code = u.wind_code
            ) THEN 0 ELSE 1 END,
            (SELECT MAX(d2.updated_at) FROM fund_dividends d2 WHERE d2.wind_code = u.wind_code) ASC NULLS FIRST,
            u.wind_code
        LIMIT :limit
    """)
    with get_engine().connect() as conn:
        rows = conn.execute(sql, {"limit": max(1, limit)}).fetchall()
    return [str(row[0]) for row in rows]


def parse_codes(values: List[str]) -> List[str]:
    codes = []
    for value in values:
        for code in value.split(","):
            normalized = code.strip().upper()
            if normalized and normalized not in codes:
                codes.append(normalized)
    return codes


def main() -> int:
    parser = argparse.ArgumentParser(description="同步基金分红事件（tushare fund_div）")
    parser.add_argument("--codes", nargs="*", default=[], help="指定基金代码，可用空格或逗号分隔")
    parser.add_argument("--limit", type=int, default=100, help="未指定代码时的基金数量")
    parser.add_argument("--throttle", type=float, default=0.3, help="每次 Tushare 请求之间的间隔秒数")
    args = parser.parse_args()

    init_database()
    codes = parse_codes(args.codes) or select_candidates(args.limit)

    data_service = get_strict_tushare_service()
    repo = get_fund_dividends_repo()

    saved_funds: List[str] = []
    empty_funds: List[str] = []
    failed: Dict[str, str] = {}
    total_events = 0

    for code in codes:
        try:
            rows = data_service.get_fund_dividends(code)
            repo.replace_fund_dividends(code, rows)
            if rows:
                saved_funds.append(code)
                total_events += len(rows)
            else:
                empty_funds.append(code)
        except Exception as exc:  # 单只失败不阻断整批
            failed[code] = str(exc)[:200]
        if args.throttle > 0:
            time.sleep(args.throttle)

    print(json.dumps({
        "requested": len(codes),
        "funds_with_dividends": len(saved_funds),
        "funds_without_dividends": len(empty_funds),
        "total_events": total_events,
        "failed_count": len(failed),
        "failed_sample": dict(list(failed.items())[:5]),
    }, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
