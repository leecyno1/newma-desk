#!/usr/bin/env python3
"""离线计算持仓风格描述子，并在同季度标准同类组内计算分位。"""
import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

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
from repositories import (
    get_fund_classification_repo,
    get_holding_repo,
    get_holding_style_snapshot_repo,
)
from service_registry import get_strict_tushare_service
from services.holding_style_factor_service import HoldingStyleFactorService
from services.holding_style_peer_service import HoldingStylePeerService


def _codes(values: List[str]) -> List[str]:
    result = []
    for value in values:
        for code in value.split(","):
            normalized = code.strip().upper()
            if normalized and normalized not in result:
                result.append(normalized)
    return result


def _candidates(codes: List[str], quarters: List[str], limit: int, include_existing: bool) -> List[Tuple[str, str]]:
    clauses = [
        "COALESCE(h.weight_basis, 'fund_nav') = 'fund_nav'",
        "COALESCE(h.weight_validation_status, 'valid') <> 'invalid_weight_scale'",
    ]
    params: Dict[str, Any] = {"limit": max(1, limit)}
    if codes:
        clauses.append("h.wind_code = ANY(:codes)")
        params["codes"] = codes
    if quarters:
        clauses.append("h.quarter = ANY(:quarters)")
        params["quarters"] = quarters
    if not include_existing:
        clauses.append("snapshot.wind_code IS NULL")

    sql = text(f"""
        SELECT h.wind_code, h.quarter
        FROM holdings h
        LEFT JOIN holding_style_snapshots snapshot
          ON snapshot.wind_code = h.wind_code AND snapshot.quarter = h.quarter
        WHERE {' AND '.join(clauses)}
        GROUP BY h.wind_code, h.quarter, snapshot.wind_code
        HAVING SUM(h.weight) > 0
           AND SUM(h.weight) <= 1.001
           AND BOOL_AND(h.weight BETWEEN 0 AND 1)
        ORDER BY h.quarter DESC, h.wind_code
        LIMIT :limit
    """)
    with get_engine().connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [(str(row.wind_code), str(row.quarter)) for row in rows]


def sync_holding_style_snapshots(
    codes: List[str],
    quarters: List[str],
    limit: int = 20,
    include_existing: bool = False,
    data_service: Any = None,
) -> Dict[str, Any]:
    init_database()
    candidates = _candidates(
        _codes(codes),
        [item.strip().upper() for item in quarters if item.strip()],
        limit,
        include_existing,
    )
    data_service = data_service or get_strict_tushare_service()
    analyzer = HoldingStyleFactorService(data_service)
    classification_repo = get_fund_classification_repo()
    holding_repo = get_holding_repo()
    snapshot_repo = get_holding_style_snapshot_repo()
    peer_service = HoldingStylePeerService()
    touched_groups = set()
    results = []

    for wind_code, quarter in candidates:
        holdings = holding_repo.get_holdings(wind_code, quarter)
        analysis = analyzer.analyze(holdings, quarter)
        context = classification_repo.get_classification_context(wind_code) or {}
        snapshot = {
            "wind_code": wind_code,
            "quarter": quarter,
            "peer_group_id": context.get("peer_group_id"),
            "peer_group_key": context.get("peer_group_key"),
            "peer_group_name": context.get("peer_group_name"),
            "descriptors": analysis.get("descriptors") or [],
            "peer_percentiles": [],
            "style_labels": [],
            "peer_sample_size": 0,
            "minimum_peer_count": int(context.get("minimum_peer_count") or 5),
            "holdings_disclosed_weight": analysis.get("holdings_disclosed_weight"),
            "source": analysis.get("source") or "holding_style_descriptor_v1",
            "status": "descriptor_ready" if analysis.get("descriptors") else "insufficient_evidence",
            "missing_items": analysis.get("missing_items") or [],
        }
        snapshot_repo.upsert(snapshot)
        if snapshot.get("peer_group_id"):
            touched_groups.add((snapshot["peer_group_id"], quarter))
        results.append({
            "wind_code": wind_code,
            "quarter": quarter,
            "status": snapshot["status"],
            "descriptor_count": len(snapshot["descriptors"]),
            "peer_group_name": snapshot.get("peer_group_name"),
        })

    percentile_updates = 0
    for peer_group_id, quarter in sorted(touched_groups):
        peers = snapshot_repo.list_peer(peer_group_id, quarter)
        for peer in peers:
            snapshot_repo.upsert(peer_service.enrich(peer, peers))
            percentile_updates += 1

    return {
        "source": "holding_style_descriptor_v1+holding_style_peer_percentile_v1",
        "candidate_count": len(candidates),
        "percentile_updates": percentile_updates,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="同步公开持仓风格描述子与同类分位")
    parser.add_argument("--codes", nargs="*", default=[])
    parser.add_argument("--quarters", nargs="*", default=[])
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--include-existing", action="store_true")
    args = parser.parse_args()

    output = sync_holding_style_snapshots(
        codes=args.codes,
        quarters=args.quarters,
        limit=args.limit,
        include_existing=args.include_existing,
    )
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
