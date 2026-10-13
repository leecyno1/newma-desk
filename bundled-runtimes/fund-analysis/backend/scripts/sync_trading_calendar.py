"""显式更新公开交易日历快照；默认预览，不改数据库或评分。"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.fund_trading_calendar import SNAPSHOT_PATH, fetch_calendar_snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-year", type=int, default=2020)
    parser.add_argument("--end-year", type=int, default=date.today().year)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    from dotenv import load_dotenv
    root = Path(__file__).resolve().parents[2]
    for path in (root / ".env.local", root / ".env", root / "backend" / ".env"):
        load_dotenv(path, override=False)
    from services.tushare_service import TushareDataService
    snapshot = fetch_calendar_snapshot(TushareDataService(mock_mode=False, strict_no_mock=True).pro,
                                       args.start_year, args.end_year)
    if args.apply:
        SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = SNAPSHOT_PATH.with_suffix(".tmp")
        temporary.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(SNAPSHOT_PATH)
    print(json.dumps(snapshot, ensure_ascii=False))


if __name__ == "__main__":
    main()
