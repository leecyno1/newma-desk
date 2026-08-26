#!/usr/bin/env python3
"""批量同步真实基金经理目录和完整产品任职关系。"""

import argparse
import json
import math
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

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
from repositories import get_manager_repo
from service_registry import get_strict_tushare_service


def clean_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    result = str(value).strip()
    return "" if result.lower() in {"nan", "nat", "none", "null"} else result


def date_text(value: Any) -> str:
    result = clean_text(value)
    if len(result) == 8 and result.isdigit():
        return f"{result[:4]}-{result[4:6]}-{result[6:]}"
    return result[:10] if len(result) >= 10 else ""


def load_local_funds() -> Dict[str, Dict[str, str]]:
    with get_engine().connect() as conn:
        rows = conn.execute(text("""
            SELECT
                wind_code,
                name,
                COALESCE(
                    NULLIF(raw_data#>>'{universe,company}', ''),
                    NULLIF(raw_data#>>'{info,company}', ''),
                    NULLIF(raw_data->>'company', '')
                ) AS company
            FROM funds
        """)).fetchall()
    return {
        str(row._mapping["wind_code"]).upper(): {
            "name": clean_text(row._mapping.get("name")),
            "company": clean_text(row._mapping.get("company")),
        }
        for row in rows
    }


def build_manager_records(
    source_rows: Iterable[Dict[str, Any]],
    local_funds: Dict[str, Dict[str, str]],
) -> List[Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}
    for source in source_rows:
        name = clean_text(source.get("name"))
        if not name:
            continue
        gender = clean_text(source.get("gender"))
        education = clean_text(source.get("edu") or source.get("education"))
        manager_id = f"{name}|{gender}|{education}"
        record = grouped.setdefault(manager_id, {
            "manager_id": manager_id,
            "name": name,
            "company": clean_text(source.get("company")),
            "education": education,
            "tenures": [],
        })

        existing_keys = {
            (item["fund_code"], item["start_date"], item.get("end_date") or "")
            for item in record["tenures"]
        }
        for fund in source.get("funds") or []:
            fund_code = clean_text(fund.get("wind_code")).upper()
            start_date = date_text(fund.get("start_date"))
            end_date = date_text(fund.get("end_date"))
            if fund_code not in local_funds or not start_date:
                continue
            key = (fund_code, start_date, end_date)
            if key in existing_keys:
                continue
            record["tenures"].append({
                "fund_code": fund_code,
                # fund_manager 接口在缺少 fund_name 字段时会回退为基金代码；
                # 本地基金档案已有正式名称，应优先使用，避免经理页展示一串代码。
                "fund_name": (
                    clean_text(local_funds[fund_code].get("name"))
                    or clean_text(fund.get("fund_name"))
                    or fund_code
                ),
                "start_date": start_date,
                "end_date": end_date or None,
                "is_current": not end_date,
                "raw_data": {"source": "tushare.fund_manager"},
            })
            existing_keys.add(key)

    synced_at = datetime.now(UTC).isoformat()
    result = []
    today = date.today()
    for record in grouped.values():
        tenures = sorted(
            record["tenures"],
            key=lambda item: (item["start_date"], item["fund_code"]),
        )
        if not tenures:
            continue
        current_funds = list(dict.fromkeys(
            item["fund_code"] for item in tenures if item["is_current"]
        ))
        company = clean_text(record.get("company"))
        if not company:
            company = next(
                (
                    local_funds[code]["company"]
                    for code in current_funds
                    if clean_text(local_funds[code].get("company"))
                ),
                next(
                    (
                        local_funds[item["fund_code"]]["company"]
                        for item in tenures
                        if clean_text(local_funds[item["fund_code"]].get("company"))
                    ),
                    "",
                ),
            )
        earliest_start = date.fromisoformat(tenures[0]["start_date"])
        management_years = round((today - earliest_start).days / 365.25, 2)
        result.append({
            **record,
            "company": company,
            "work_years": int(management_years),
            "management_years": management_years,
            "current_funds": current_funds,
            "tenures": tenures,
            "historical_performance": {
                "tenure_count": len(tenures),
                "current_tenure_count": len(current_funds),
                "source": "tushare.fund_manager",
            },
            "raw_data": {
                "source": "tushare.fund_manager",
                "synced_at": synced_at,
                "universe_sync": True,
            },
        })
    return sorted(result, key=lambda item: (item["name"], item["manager_id"]))


def main() -> int:
    parser = argparse.ArgumentParser(description="同步基金经理全量目录与任职关系")
    parser.add_argument("--limit", type=int, default=0, help="仅同步前 N 位经理；0 表示全部")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    init_database()
    data_service = get_strict_tushare_service()
    payload = data_service.get_manager_list(page=1, page_size=100000)
    source_rows = payload.get("managers") or []
    if not source_rows:
        raise RuntimeError("Tushare 未返回基金经理目录")

    records = build_manager_records(source_rows, load_local_funds())
    if args.limit > 0:
        records = records[:args.limit]
    tenure_count = sum(len(record.get("tenures") or []) for record in records)
    if args.dry_run:
        print(json.dumps({
            "status": "dry_run",
            "source_manager_count": len(source_rows),
            "local_manager_count": len(records),
            "tenure_count": tenure_count,
        }, ensure_ascii=False))
        return 0

    saved = get_manager_repo().upsert_manager_universe(records)
    print(json.dumps({
        "status": "synced",
        "source_manager_count": len(source_rows),
        "local_manager_count": len(records),
        **saved,
        "source": "tushare.fund_manager",
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
