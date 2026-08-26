#!/usr/bin/env python3
"""清除历史异常基金净值权重，保留股票组合占比。"""
import argparse
import json
import sys
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

from database import get_engine
from lib.holding_weight_validation import MAX_FUND_NAV_WEIGHT_SUM


INVALID_GROUPS_SQL = text("""
    SELECT
        wind_code,
        quarter,
        COUNT(*) AS row_count,
        COUNT(*) FILTER (WHERE weight < 0 OR weight > 1) AS invalid_row_count,
        MAX(weight) AS max_weight,
        SUM(weight) AS total_weight
    FROM holdings
    WHERE weight IS NOT NULL
      AND COALESCE(weight_basis, 'fund_nav') = 'fund_nav'
    GROUP BY wind_code, quarter
    HAVING BOOL_OR(weight < 0 OR weight > 1)
       OR SUM(weight) > :max_total
    ORDER BY SUM(weight) DESC
""")


def _serialize(rows: List[Any]) -> List[Dict[str, Any]]:
    return [
        {
            "wind_code": str(row.wind_code),
            "quarter": str(row.quarter),
            "row_count": int(row.row_count),
            "invalid_row_count": int(row.invalid_row_count),
            "max_weight": float(row.max_weight),
            "total_weight": float(row.total_weight),
        }
        for row in rows
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="修复异常基金持仓权重")
    parser.add_argument("--apply", action="store_true", help="实际写入；默认仅预览")
    args = parser.parse_args()

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE holdings ADD COLUMN IF NOT EXISTS weight_validation_status VARCHAR(30)"
        ))
        before_rows = conn.execute(
            INVALID_GROUPS_SQL,
            {"max_total": MAX_FUND_NAV_WEIGHT_SUM},
        ).fetchall()
        before = _serialize(before_rows)

        updated_rows = 0
        if args.apply and before:
            targets = [f"{item['wind_code']}|{item['quarter']}" for item in before]
            result = conn.execute(
                text("""
                    UPDATE holdings
                    SET
                        weight = NULL,
                        weight_basis = CASE
                            WHEN equity_portfolio_weight IS NOT NULL THEN 'equity_portfolio'
                            ELSE 'unknown'
                        END,
                        weight_validation_status = 'invalid_weight_scale'
                    WHERE (wind_code || '|' || quarter) = ANY(:targets)
                """),
                {"targets": targets},
            )
            updated_rows = int(result.rowcount or 0)

        after_rows = conn.execute(
            INVALID_GROUPS_SQL,
            {"max_total": MAX_FUND_NAV_WEIGHT_SUM},
        ).fetchall()

    print(json.dumps({
        "mode": "apply" if args.apply else "preview",
        "before": {
            "fund_quarters": len(before),
            "rows": sum(item["row_count"] for item in before),
            "items": before,
        },
        "updated_rows": updated_rows,
        "after": {
            "fund_quarters": len(after_rows),
            "rows": sum(int(row.row_count) for row in after_rows),
            "items": _serialize(after_rows),
        },
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
