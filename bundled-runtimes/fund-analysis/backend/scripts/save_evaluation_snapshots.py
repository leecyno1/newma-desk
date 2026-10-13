#!/usr/bin/env python3
"""按窗口轮换保存基金评价快照，未变化时只记录调度尝试，输出 JSON 批次摘要。"""
import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

try:
    from dotenv import load_dotenv
    load_dotenv(BACKEND_DIR.parent / ".env.local")
    load_dotenv(BACKEND_DIR.parent / ".env")
    load_dotenv(BACKEND_DIR / ".env")
except Exception:
    pass

from services.fund_evaluation_history_service import FundEvaluationHistoryService  # noqa: E402
from services.fund_evaluation_service import FundEvaluationService  # noqa: E402
from database import get_engine  # noqa: E402


def pick_candidates(limit: int, fresh_quota: Optional[int] = None, window: str = "1y") -> List[str]:
    """组合持仓优先，各候选池按窗口尝试时间轮换，并预留新基金配额。"""
    from sqlalchemy import text

    if limit <= 0:
        return []
    if fresh_quota is None:
        fresh_quota = max(10, limit // 5)
    fresh_quota = min(limit, max(0, fresh_quota))

    engine = get_engine()
    holdings_query = text("""
        SELECT f.wind_code
        FROM funds f
        WHERE EXISTS (
            SELECT 1 FROM portfolio_holdings h
            JOIN portfolios p ON p.id = h.portfolio_id
            WHERE h.wind_code = f.wind_code AND p.status IN ('draft', 'active')
        )
        ORDER BY (f.raw_data -> 'evaluation_snapshot_attempts' ->> :window)::timestamptz ASC NULLS FIRST,
                 f.wind_code
        LIMIT :limit
    """)
    continuity_query = text("""
        SELECT latest.wind_code
        FROM (
            SELECT wind_code, MAX(created_at) AS last_created_at
            FROM fund_evaluation_snapshots
            WHERE evaluation_window = :window
            GROUP BY wind_code
        ) latest
        JOIN funds f ON f.wind_code = latest.wind_code
        WHERE NOT (f.wind_code = ANY(CAST(:holdings AS text[])))
        ORDER BY GREATEST(latest.last_created_at,
                         (f.raw_data -> 'evaluation_snapshot_attempts' ->> :window)::timestamptz) ASC,
                 latest.wind_code
        LIMIT :limit
    """)
    fresh_query = text("""
        SELECT metrics.target_id
        FROM (
            SELECT target_id, MAX(as_of_date) AS last_as_of_date
            FROM metric_snapshots
            WHERE target_type = 'fund'
            GROUP BY target_id
        ) metrics
        JOIN funds f ON f.wind_code = metrics.target_id
        WHERE NOT (f.wind_code = ANY(CAST(:holdings AS text[])))
          AND NOT EXISTS (
              SELECT 1 FROM fund_evaluation_snapshots s
              WHERE s.wind_code = f.wind_code AND s.evaluation_window = :window
          )
        ORDER BY (f.raw_data -> 'evaluation_snapshot_attempts' ->> :window)::timestamptz ASC NULLS FIRST,
                 metrics.last_as_of_date DESC, metrics.target_id
        LIMIT :limit
    """)
    with engine.connect() as conn:
        holdings = [row[0] for row in conn.execute(holdings_query, {"limit": limit, "window": window})]
        remaining = limit - len(holdings)
        if not remaining:
            return holdings
        params = {"limit": remaining, "window": window, "holdings": holdings}
        continuity = [row[0] for row in conn.execute(continuity_query, params)]
        fresh = [row[0] for row in conn.execute(fresh_query, params)] if fresh_quota else []
    fresh_limit = min(fresh_quota, remaining)
    continuity_limit = remaining - fresh_limit
    return (
        holdings + continuity[:continuity_limit] + fresh[:fresh_limit]
        + continuity[continuity_limit:] + fresh[fresh_limit:]
    )[:limit]


def record_attempt(wind_code: str, window: str) -> None:
    from sqlalchemy import text

    with get_engine().begin() as conn:
        conn.execute(text("""
            UPDATE funds
            SET raw_data = jsonb_set(
                COALESCE(raw_data, '{}'::jsonb), '{evaluation_snapshot_attempts}',
                COALESCE(raw_data -> 'evaluation_snapshot_attempts', '{}'::jsonb)
                || jsonb_build_object(CAST(:window AS text), CURRENT_TIMESTAMP)
            )
            WHERE wind_code = :wind_code
        """), {"wind_code": wind_code, "window": window})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=50, help="本次最多保存的基金数量")
    parser.add_argument("--codes", nargs="*", default=[], help="显式指定基金代码（覆盖自动选基）")
    parser.add_argument("--window", default="1y", help="评价窗口（默认 1y）")
    args = parser.parse_args()

    codes = [str(code).strip().upper() for code in args.codes if str(code).strip()]
    if not codes:
        codes = pick_candidates(args.limit, window=args.window)

    history_service = FundEvaluationHistoryService(
        evaluation_service=FundEvaluationService(),
    )

    saved: List[str] = []
    unchanged: List[str] = []
    failed: Dict[str, str] = {}
    for code in codes:
        try:
            result = history_service.save_current(code, window=args.window)
            if result.get("status") == "saved":
                saved.append(code)
            else:
                unchanged.append(code)
        except Exception as exc:  # 单只失败不阻断整批
            failed[code] = str(exc)[:200]
        try:
            record_attempt(code, args.window)
        except Exception as exc:
            failed[code] = f"记录调度尝试失败: {str(exc)[:150]}; {failed.get(code, '')}"[:200]

    print(
        json.dumps(
            {
                "candidate_count": len(codes),
                "saved_count": len(saved),
                "unchanged_count": len(unchanged),
                "failed_count": len(failed),
                "saved": saved[:50],
                "failed_sample": dict(list(failed.items())[:5]),
                "window": args.window,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
