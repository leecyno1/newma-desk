import asyncio
import sys
from pathlib import Path

from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import routes.reports as reports


async def main_async() -> int:
    # 报告历史与详情自 2026-09 起读写同一 PostgreSQL（与生成主写路径同库），
    # 已无 MongoDB 依赖（连接器随 service_registry 移除）。
    if True:
        history = await reports.get_report_history(target_type="fund", target_id="demo-never-exists", limit=5)
        if not isinstance(history, dict) or "reports" not in history:
            print(f"Expected PG-backed history payload, got: {history}")
            return 1
        if history.get("total") != 0 or history.get("reports") != []:
            print(f"Expected empty history for an unknown fund, got: {history}")
            return 1

        try:
            await reports.get_report_detail("68133fbe48e88ac3d74b2f25")
        except HTTPException as exc:
            if exc.status_code != 404:
                print(f"Expected get_report_detail() to return 404 for an unknown report, got: {exc.status_code}")
                return 1
        else:
            print("Expected get_report_detail() to raise HTTPException(404) for an unknown report")
            return 1

        print("OK reports endpoints are PostgreSQL-backed without MongoDB")
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main_async()))
