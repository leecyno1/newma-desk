#!/usr/bin/env python3
"""同步当前恒指快照，或导入指定的恒生官方历史事实表。"""

import argparse
import json
import sys
from pathlib import Path

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

from database import init_database
from repositories import get_market_index_constituent_repo
from services.hang_seng_index_service import HangSengIndexService


def parse_args():
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--historical-factsheet-url")
    source.add_argument("--historical-factsheet-file", type=Path)
    parser.add_argument(
        "--source-url",
        help="本地历史 PDF 对应的恒生官网来源地址，用于证据追溯。",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    init_database()
    service = HangSengIndexService()
    historical = bool(args.historical_factsheet_url or args.historical_factsheet_file)
    if args.historical_factsheet_file:
        if not args.source_url:
            raise SystemExit("导入本地历史事实表时必须提供 --source-url")
        snapshot = service.get_hsi_factsheet_snapshot(
            factsheet_url=args.source_url,
            pdf_content=args.historical_factsheet_file.read_bytes(),
        )
    elif args.historical_factsheet_url:
        snapshot = service.get_hsi_factsheet_snapshot(args.historical_factsheet_url)
    else:
        snapshot = service.get_hsi_snapshot(refresh=True)

    if snapshot.get("status") != "available":
        print(json.dumps(snapshot, ensure_ascii=False, indent=2))
        return 1

    repo = get_market_index_constituent_repo()
    written = repo.replace_snapshot(snapshot)
    industry_written = 0
    if not historical:
        industry_snapshot = {
            "index_code": "HSCI-INDUSTRY",
            "as_of_date": snapshot.get("as_of_date"),
            "constituents": snapshot.get("industry_constituents") or [],
            "source": snapshot.get("source"),
            "source_urls": [HangSengIndexService.INDUSTRY_URL],
        }
        industry_written = repo.replace_snapshot(industry_snapshot)
    print(json.dumps({
        "status": snapshot.get("status"),
        "mode": "historical_factsheet" if historical else "current_snapshot",
        "index_code": snapshot.get("index_code"),
        "as_of_date": snapshot.get("as_of_date"),
        "constituent_count": snapshot.get("constituent_count"),
        "weighted_constituent_count": snapshot.get("weighted_constituent_count"),
        "published_weight": snapshot.get("published_weight"),
        "written": written,
        "industry_classification_count": len(snapshot.get("industry_constituents") or []),
        "industry_classification_written": industry_written,
        "source": snapshot.get("source"),
        "missing_items": snapshot.get("missing_items") or [],
    }, ensure_ascii=False, indent=2))
    return 0 if written and (historical or industry_written) else 1


if __name__ == "__main__":
    raise SystemExit(main())
