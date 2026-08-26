#!/usr/bin/env python3
"""按日积累基金评价历史快照。

对最近有滚动指标面板的基金逐只调用 FundEvaluationHistoryService.save_current：
- 评价没有变化时不重复写入（服务内部去重），因此可以每日安全重跑；
- 输出 JSON 摘要供 scheduled_update runbook 记录。

选基口径：metric_snapshots 中 fund 维度最近更新的 target_id（评价输入已就绪的基金）。
"""
import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

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


def pick_candidates(limit: int) -> List[str]:
    """选基优先级：组合持仓 > 已有快照基金（保证时序连续）> 最近有指标的新基金。

 组合持仓优先：保证组合页评价摘要尽快可用（否则用户在推荐页看到评分、
 组合页却长期显示暂无快照）。"""
    from sqlalchemy import text

    engine = get_engine()
    holdings_query = text(
        """
        SELECT DISTINCT h.wind_code
        FROM portfolio_holdings h
        JOIN portfolios p ON p.id = h.portfolio_id
        WHERE p.status IN ('draft', 'active')
        """
    )
    continuity_query = text(
        """
        SELECT wind_code
        FROM fund_evaluation_snapshots
        GROUP BY wind_code
        ORDER BY MAX(created_at) DESC
        LIMIT :limit
        """
    )
    with engine.connect() as conn:
        holdings = [
            str(row[0]).strip().upper()
            for row in conn.execute(holdings_query).fetchall()
            if row[0]
        ]
        continuity = [
            str(row[0]).strip().upper()
            for row in conn.execute(continuity_query, {"limit": limit}).fetchall()
            if row[0]
        ]
        remaining = limit - len(continuity)
        fresh: List[str] = []
        if remaining > 0:
            fresh_query = text(
                """
                SELECT target_id
                FROM metric_snapshots
                WHERE target_type = 'fund'
                  AND target_id NOT IN (SELECT wind_code FROM fund_evaluation_snapshots)
                GROUP BY target_id
                ORDER BY MAX(as_of_date) DESC, target_id
                LIMIT :limit
                """
            )
            fresh = [
                str(row[0]).strip().upper()
                for row in conn.execute(fresh_query, {"limit": remaining}).fetchall()
                if row[0]
            ]
    # 去重自防：三级列表间不应重叠，但保守合并（组合持仓最优先）
    seen: set = set()
    ordered: List[str] = []
    for code in holdings + continuity + fresh:
        if code and code not in seen:
            seen.add(code)
            ordered.append(code)
    return ordered[:limit]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=50, help="本次最多保存的基金数量")
    parser.add_argument("--codes", nargs="*", default=[], help="显式指定基金代码（覆盖自动选基）")
    parser.add_argument("--window", default="1y", help="评价窗口（默认 1y）")
    args = parser.parse_args()

    codes = [str(code).strip().upper() for code in args.codes if str(code).strip()]
    if not codes:
        codes = pick_candidates(args.limit)

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
    return 0 if len(failed) < len(codes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
