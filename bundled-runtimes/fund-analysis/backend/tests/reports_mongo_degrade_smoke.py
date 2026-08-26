import asyncio
import sys
from pathlib import Path

from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import routes.reports as reports
import service_registry


async def main_async() -> int:
    original_get_db = service_registry.get_db
    service_registry.get_db = lambda: None
    try:
        history = await reports.get_report_history(target_type="fund", target_id="demo", limit=5)
        if history != {"total": 0, "reports": []}:
            print(f"Expected empty history when MongoDB is unavailable, got: {history}")
            return 1

        try:
            await reports.get_report_detail("68133fbe48e88ac3d74b2f25")
        except HTTPException as exc:
            if exc.status_code != 503:
                print(f"Expected get_report_detail() to return 503 when MongoDB is unavailable, got: {exc.status_code}")
                return 1
        else:
            print("Expected get_report_detail() to raise HTTPException(503) when MongoDB is unavailable")
            return 1

        print("OK reports mongo degrade")
        return 0
    finally:
        service_registry.get_db = original_get_db


if __name__ == "__main__":
    sys.exit(asyncio.run(main_async()))
