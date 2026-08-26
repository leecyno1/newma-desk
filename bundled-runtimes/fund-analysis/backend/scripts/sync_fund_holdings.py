#!/usr/bin/env python3
"""批量同步可用于持仓画像和 Brinson 归因的真实基金持仓。"""
import argparse
import json
import sys
import time
from datetime import datetime
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

from database import get_engine, init_database
from lib.fund_status import active_fund_sql
from repositories import get_holding_repo
from scripts.sync_holding_style_snapshots import sync_holding_style_snapshots
from service_registry import get_strict_tushare_service
from services.fund_holding_weight_service import FundHoldingWeightService


def quarter_before(quarter: str) -> str:
    year = int(quarter[:4])
    number = int(quarter[-1])
    return f"{year - 1}Q4" if number == 1 else f"{year}Q{number - 1}"


def default_quarters(now: datetime | None = None) -> List[str]:
    reference = now or datetime.now()
    current = f"{reference.year}Q{(reference.month - 1) // 3 + 1}"
    latest_completed = quarter_before(current)
    return [quarter_before(latest_completed), latest_completed]


def parse_codes(values: List[str]) -> List[str]:
    codes = []
    for value in values:
        for code in value.split(","):
            normalized = code.strip().upper()
            if normalized and normalized not in codes:
                codes.append(normalized)
    return codes


def existing_quarters(codes: List[str], quarters: List[str]) -> Dict[str, set[str]]:
    if not codes or not quarters:
        return {}
    with get_engine().connect() as conn:
        rows = conn.execute(
            text("""
                SELECT DISTINCT wind_code, quarter
                FROM holdings
                WHERE wind_code = ANY(:codes) AND quarter = ANY(:quarters)
            """),
            {"codes": codes, "quarters": quarters},
        ).fetchall()
    result: Dict[str, set[str]] = {}
    for row in rows:
        result.setdefault(str(row.wind_code), set()).add(str(row.quarter))
    return result


def select_candidates(limit: int, quarters: List[str], include_existing: bool) -> List[str]:
    sql = text(f"""
        WITH representatives AS (
            SELECT DISTINCT ON (entity.id)
                share.wind_code,
                share.is_primary,
                fund.total_asset,
                EXISTS (
                    SELECT 1
                    FROM metric_snapshots metric
                    WHERE metric.target_type = 'fund'
                      AND metric.target_id = share.wind_code
                      AND metric.metric_window = '1y'
                      AND metric.metric_name = 'annualized_return'
                ) AS has_one_year_metric,
                EXISTS (
                    SELECT 1
                    FROM benchmark_mappings benchmark
                    WHERE benchmark.entity_id = entity.id
                      AND benchmark.status = 'active'
                      AND benchmark.benchmark_code ~ '^[0-9A-Z]{{6,12}}\\.(SH|SZ|CSI)$'
                ) AS has_market_benchmark,
                EXISTS (
                    SELECT 1
                    FROM manager_fund_tenures tenure
                    JOIN research_report_managers report_manager
                      ON report_manager.manager_id = tenure.manager_id
                    WHERE tenure.fund_code = share.wind_code
                      AND tenure.is_current = TRUE
                ) AS has_research_memo
            FROM fund_entities entity
            JOIN fund_share_classes share
              ON share.entity_id = entity.id
             AND share.status = 'active'
            JOIN funds fund ON fund.wind_code = share.wind_code
            WHERE entity.lifecycle_stage = 'active'
              AND entity.strategy_family_id IS NOT NULL
              AND entity.asset_class IN ('equity', 'index', 'multi_asset')
              AND ({active_fund_sql('fund')})
            ORDER BY entity.id, share.is_primary DESC, fund.total_asset DESC NULLS LAST, share.wind_code
        )
        SELECT representative.wind_code
        FROM representatives representative
        WHERE :include_existing OR (
            SELECT COUNT(DISTINCT holding.quarter)
            FROM holdings holding
            WHERE holding.wind_code = representative.wind_code
              AND holding.quarter = ANY(:quarters)
        ) < :quarter_count
        ORDER BY
            representative.has_research_memo DESC,
            representative.has_one_year_metric DESC,
            representative.has_market_benchmark DESC,
            representative.is_primary DESC,
            representative.total_asset DESC NULLS LAST,
            representative.wind_code
        LIMIT :limit
    """)
    with get_engine().connect() as conn:
        rows = conn.execute(
            sql,
            {
                "include_existing": include_existing,
                "quarters": quarters,
                "quarter_count": len(quarters),
                "limit": max(1, limit),
            },
        ).fetchall()
    return [str(row.wind_code) for row in rows]


def main() -> int:
    parser = argparse.ArgumentParser(description="同步真实基金持仓、修复权重并刷新同类持仓风格")
    parser.add_argument("--codes", nargs="*", default=[], help="指定基金代码，可用空格或逗号分隔")
    parser.add_argument("--limit", type=int, default=10, help="未指定代码时的基金数量")
    parser.add_argument("--quarters", nargs="*", default=[], help="指定季度，默认为当前归因所需前期持仓和最新完整季度")
    parser.add_argument("--include-existing", action="store_true", help="重新同步已有持仓的季度")
    parser.add_argument("--throttle", type=float, default=0.3, help="每次 Tushare 请求组之间的间隔秒数")
    parser.add_argument("--skip-holding-style", action="store_true", help="只同步持仓，不刷新持仓风格与同类分位")
    args = parser.parse_args()

    quarters = [value.strip().upper() for value in args.quarters if value.strip()] or default_quarters()
    if any(len(value) != 6 or value[4] != "Q" or value[-1] not in "1234" for value in quarters):
        raise ValueError("季度必须使用 YYYYQ1-YYYYQ4")

    init_database()
    codes = parse_codes(args.codes)
    if not codes:
        codes = select_candidates(max(1, args.limit), quarters, args.include_existing)
    existing = existing_quarters(codes, quarters)

    data_service = get_strict_tushare_service()
    holding_repo = get_holding_repo()
    weight_service = FundHoldingWeightService()
    results: List[Dict[str, Any]] = []
    saved_rows = 0
    repaired_quarters = 0

    for code in codes:
        for quarter in quarters:
            if not args.include_existing and quarter in existing.get(code, set()):
                holdings = holding_repo.get_holdings(code, quarter)
                enrichment = weight_service.enrich(
                    code,
                    quarter,
                    holdings,
                    refresh_allocation=True,
                )
                if enrichment.get("changed") and holding_repo.upsert_holdings(code, quarter, enrichment["holdings"]):
                    repaired_quarters += 1
                    results.append({
                        "wind_code": code,
                        "quarter": quarter,
                        "status": "repaired_existing_weights",
                        "holding_count": len(enrichment["holdings"]),
                        "weight_source": enrichment.get("weight_source"),
                        "weight_validation": enrichment.get("weight_validation"),
                    })
                else:
                    results.append({
                        "wind_code": code,
                        "quarter": quarter,
                        "status": "skipped_existing",
                        "holding_count": len(holdings),
                        "weight_source": enrichment.get("weight_source"),
                        "weight_validation": enrichment.get("weight_validation"),
                        "missing_items": enrichment.get("missing_items") or [],
                    })
                continue
            holdings = data_service.get_fund_holdings(code, quarter)
            if not holdings:
                results.append({"wind_code": code, "quarter": quarter, "status": "unavailable", "holding_count": 0})
            else:
                enrichment = weight_service.enrich(
                    code,
                    quarter,
                    holdings,
                    refresh_allocation=True,
                )
                holdings = enrichment["holdings"]
            if holdings and holding_repo.upsert_holdings(code, quarter, holdings):
                nav_weight_count = sum(1 for item in holdings if item.get("weight_basis") == "fund_nav")
                results.append({
                    "wind_code": code,
                    "quarter": quarter,
                    "status": "saved",
                    "holding_count": len(holdings),
                    "fund_nav_weight_count": nav_weight_count,
                    "formal_weight_ready": nav_weight_count == len(holdings),
                    "weight_source": enrichment.get("weight_source"),
                    "weight_validation": enrichment.get("weight_validation"),
                    "missing_items": enrichment.get("missing_items") or [],
                })
                saved_rows += len(holdings)
            elif holdings:
                results.append({"wind_code": code, "quarter": quarter, "status": "store_failed", "holding_count": len(holdings)})
            if args.throttle > 0:
                time.sleep(args.throttle)

    if args.skip_holding_style:
        holding_style = {"status": "skipped", "reason": "disabled_by_option"}
    elif not codes:
        holding_style = {"status": "skipped", "reason": "no_funds_selected"}
    else:
        holding_style = sync_holding_style_snapshots(
            codes=codes,
            quarters=quarters,
            limit=max(1, len(codes) * len(quarters)),
            include_existing=True,
            data_service=data_service,
        )
    output = {
        "source": "tushare.fund_portfolio+fund_nav+holding_style_peer_percentile",
        "mock_mode": data_service.mock_mode,
        "fund_count": len(codes),
        "quarters": quarters,
        "saved_rows": saved_rows,
        "repaired_quarters": repaired_quarters,
        "holding_style": holding_style,
        "results": results,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
