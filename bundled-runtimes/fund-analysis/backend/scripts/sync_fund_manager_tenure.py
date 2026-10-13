#!/usr/bin/env python3
"""为基金选择器同步真实基金经理关系和任期评价指标。"""

import argparse
import json
import os
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

from database import get_engine, load_shared_database_environment, prepare_database
from service_registry import get_strict_tushare_service
from services.fund_manager_tenure_sync_service import FundManagerTenureSyncService


def select_research_linked_codes(limit: int, missing_only: bool) -> List[str]:
    missing_sql = ""
    if missing_only:
        missing_sql = """
          AND (
            COALESCE(cardinality(fund.manager_ids), 0) = 0
            OR profile.manager_tenure_start IS NULL
            OR NOT EXISTS (
              SELECT 1 FROM metric_snapshots metric
              WHERE metric.target_type = 'fund'
                AND metric.target_id = linked.wind_code
                AND metric.metric_window = 'manager_tenure'
                AND metric.metric_name = 'tenure_days'
            )
          )
        """
    sql = text(f"""
        WITH linked AS (
          SELECT DISTINCT proposal->>'value' AS wind_code
          FROM research_reports report
          CROSS JOIN LATERAL jsonb_array_elements(COALESCE(report.review_proposals, '[]')) proposal
          WHERE proposal->>'kind' = 'fund'
            AND proposal->>'extraction_source' = 'tushare.fund_manager'
        )
        SELECT linked.wind_code
        FROM linked
        JOIN funds fund ON fund.wind_code = linked.wind_code
        JOIN fund_share_classes share
          ON share.wind_code = linked.wind_code AND share.status = 'active'
        JOIN fund_entities entity ON entity.id = share.entity_id
        JOIN strategy_families family ON family.id = entity.strategy_family_id
        LEFT JOIN fund_research_profiles profile ON profile.wind_code = linked.wind_code
        WHERE family.key NOT IN ('index_broad', 'index_fixed_income', 'cash_management')
          {missing_sql}
        ORDER BY linked.wind_code
        LIMIT :limit
    """)
    with get_engine().connect() as conn:
        return [row.wind_code for row in conn.execute(sql, {"limit": max(1, limit)}).fetchall()]


def select_fund_selection_coverage_codes(limit: int, missing_only: bool) -> List[str]:
    """优先补齐有真实评价指标的主动与固收基金经理关系。"""
    missing_sql = ""
    if missing_only:
        missing_sql = "AND COALESCE(cardinality(fund.manager_ids), 0) = 0"
    sql = text(f"""
        WITH representatives AS (
          SELECT DISTINCT ON (entity.id)
            share.wind_code,
            fund.total_asset,
            EXISTS (
              SELECT 1 FROM metric_snapshots metric
              WHERE metric.target_type = 'fund'
                AND metric.target_id = share.wind_code
                AND metric.metric_window = '1y'
                AND metric.metric_name = 'annualized_return'
            ) AS metric_ready
          FROM fund_entities entity
          JOIN strategy_families family ON family.id = entity.strategy_family_id
          JOIN fund_share_classes share
            ON share.entity_id = entity.id AND share.status = 'active'
          JOIN funds fund ON fund.wind_code = share.wind_code
          WHERE entity.lifecycle_stage = 'active'
            AND family.key NOT IN ('index_broad', 'index_fixed_income', 'cash_management')
            AND share.wind_code LIKE '%.OF'
            {missing_sql}
          ORDER BY entity.id, share.is_primary DESC, fund.total_asset DESC NULLS LAST, share.wind_code
        )
        SELECT wind_code
        FROM representatives
        ORDER BY metric_ready DESC, total_asset DESC NULLS LAST, wind_code
        LIMIT :limit
    """)
    with get_engine().connect() as conn:
        return [row.wind_code for row in conn.execute(sql, {"limit": max(1, limit)}).fetchall()]


def select_snapshot_backlog_managers(limit: int) -> List[tuple]:
    """选"在管产品多、但有在管任期缺 performance_snapshot"的经理，按缺失条目降序。

    只有 sync_manager 会写任期绩效快照（sync_fund 不写），因此批量补快照
    必须以经理为单位；优先补缺失最多的经理能让同一份 Tushare 配额产出最多可用证据。
    """
    sql = text("""
        WITH tenure AS (
          SELECT
            manager_id,
            COUNT(*) FILTER (WHERE end_date IS NULL) AS in_charge,
            COUNT(*) FILTER (
              WHERE end_date IS NULL
                AND performance_snapshot->>'status' = 'available'
            ) AS in_charge_available
          FROM manager_fund_tenures
          WHERE manager_id LIKE '%|%'
          GROUP BY manager_id
        )
        SELECT manager_id, in_charge, in_charge_available
        FROM tenure
        WHERE in_charge_available < in_charge
          AND in_charge >= 1
        ORDER BY (in_charge - in_charge_available) DESC, in_charge DESC, manager_id
        LIMIT :limit
    """)
    with get_engine().connect() as conn:
        return [
            (row.manager_id, row.in_charge, row.in_charge_available)
            for row in conn.execute(sql, {"limit": max(1, limit)}).fetchall()
        ]


def main() -> int:
    parser = argparse.ArgumentParser(description="同步真实基金经理关系和任期指标")
    parser.add_argument("--codes", default="", help="逗号分隔基金代码")
    parser.add_argument("--manager-id", default="", help="规范基金经理 ID；同步该经理完整产品任职史")
    parser.add_argument(
        "--snapshot-backlog",
        type=int,
        default=0,
        help="按缺失任期绩效快照的条目数选经理批量同步（每日调度小额配额入口，如 --snapshot-backlog 3）",
    )
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--include-existing", action="store_true")
    parser.add_argument(
        "--fund-selection-coverage",
        action="store_true",
        help="补齐基金选择器中主动与固收基金的经理关系",
    )
    parser.add_argument("--throttle", type=float, default=0.15)
    args = parser.parse_args()

    load_shared_database_environment()
    prepare_database(os.environ.get("FUND_DATABASE_INIT_MODE", "check"))
    if args.manager_id.strip():
        result = FundManagerTenureSyncService(get_strict_tushare_service()).sync_manager(args.manager_id.strip())
        print(json.dumps(result, ensure_ascii=False))
        return 1 if result.get("status") == "failed" else 0

    if args.snapshot_backlog > 0:
        backlog = select_snapshot_backlog_managers(args.snapshot_backlog)
        if not backlog:
            print(json.dumps({"requested": 0, "synced": 0, "failed": 0, "reason": "no_snapshot_backlog"}, ensure_ascii=False))
            return 0
        service = FundManagerTenureSyncService(get_strict_tushare_service())
        summary = {"requested": len(backlog), "synced": 0, "failed": 0, "managers": []}
        for index, (manager_id, in_charge, in_charge_available) in enumerate(backlog, start=1):
            result = service.sync_manager(manager_id)
            ok = result.get("status") == "synced"
            summary["synced" if ok else "failed"] += 1
            summary["managers"].append({
                "manager_id": manager_id,
                "status": result.get("status"),
                "current_tenures": result.get("current_tenure_count"),
                "nav_points_saved": result.get("nav_points_saved"),
            })
            print(
                f"[{index}/{len(backlog)}] {str(result.get('status')).upper()} {manager_id} "
                f"在管={result.get('current_tenure_count', 0)} 净值点={result.get('nav_points_saved', 0)}"
            )
            if args.throttle > 0:
                time.sleep(args.throttle)
        print(json.dumps(summary, ensure_ascii=False))
        return 1 if summary["failed"] else 0

    codes = [item.strip().upper() for item in args.codes.split(",") if item.strip()]
    if not codes:
        if args.fund_selection_coverage:
            codes = select_fund_selection_coverage_codes(args.limit, missing_only=not args.include_existing)
        else:
            codes = select_research_linked_codes(args.limit, missing_only=not args.include_existing)
    else:
        codes = codes[:max(1, args.limit)]
    if not codes:
        print("没有需要同步经理任期的基金。")
        return 0

    service = FundManagerTenureSyncService(get_strict_tushare_service())
    results = []
    for index, code in enumerate(codes, start=1):
        result = service.sync_fund(code)
        results.append(result)
        print(
            f"[{index}/{len(codes)}] {result['status'].upper()} {code} "
            f"经理={result.get('manager_count', 0)} 任期起点={result.get('manager_tenure_start') or '-'} "
            f"指标={result.get('tenure_metrics_saved', 0)}"
        )
        if args.throttle > 0:
            time.sleep(args.throttle)

    summary = {
        "requested": len(results),
        "synced": sum(item["status"] == "synced" for item in results),
        "skipped": sum(item["status"] == "skipped" for item in results),
        "failed": sum(item["status"] == "failed" for item in results),
        "tenure_metrics_saved": sum(item.get("tenure_metrics_saved", 0) for item in results),
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
