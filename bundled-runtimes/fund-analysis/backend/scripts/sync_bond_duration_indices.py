#!/usr/bin/env python3
"""同步债基久期模型所需的中债 4 组 20 条分期限指数。"""

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
from services.chinabond_index_service import ChinaBondIndexService


def main() -> int:
    parser = argparse.ArgumentParser(description="同步中债分期限财富指数和平均市值法久期")
    parser.add_argument("--lookback-years", type=int, default=4)
    args = parser.parse_args()

    init_database()
    result = ChinaBondIndexService().sync(lookback_years=args.lookback_years)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
