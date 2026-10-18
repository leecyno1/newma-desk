"""Run from the active Deepsee runtime directory, with its DATABASE_URL/.env."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.chatlog_backfill import backfill


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True, help="Inclusive local date, e.g. 2026-04-15")
    parser.add_argument("--account-id", required=True, help="Verified WeChat account ID, also used by WS")
    args = parser.parse_args()
    result = backfill(start=datetime.fromisoformat(args.start).astimezone(),
                      end=datetime.now().astimezone(), account_id=args.account_id,
                      progress=lambda line: print(line, flush=True))
    print(json.dumps(result, ensure_ascii=False), flush=True)
