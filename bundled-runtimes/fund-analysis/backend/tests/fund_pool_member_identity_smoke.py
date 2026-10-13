import atexit
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import get_engine
from repositories.fund_pool_repo import FundPoolRepo
from smoke_cleanup import cleanup_fund_codes

WIND_CODE = "POOL.TEST.001"
POOL_NAME = "标识混用-smoke"


def _setup_fixtures() -> str:
    from sqlalchemy import text

    with get_engine().begin() as conn:
        conn.execute(text(
            "INSERT INTO funds (wind_code, name) VALUES (:code, :name) "
            "ON CONFLICT (wind_code) DO NOTHING"
        ), {"code": WIND_CODE, "name": "标识混用测试基金"})
        row = conn.execute(
            text("SELECT id::text FROM funds WHERE wind_code = :code"),
            {"code": WIND_CODE},
        ).fetchone()
        return str(row[0])


def _cleanup_pool(pool_id: str) -> None:
    from sqlalchemy import text

    with get_engine().begin() as conn:
        conn.execute(
            text("DELETE FROM fund_pools WHERE id = CAST(:pool_id AS UUID)"),
            {"pool_id": pool_id},
        )


def main() -> int:
    fund_uuid = _setup_fixtures()
    repo = FundPoolRepo()
    pool = repo.create_pool(name=POOL_NAME, description="标识混用冒烟", created_by="smoke-test")
    atexit.register(_cleanup_pool, pool["id"])
    atexit.register(cleanup_fund_codes, [WIND_CODE])

    # 1. UUID 入库归一为 wind_code，前端两条路径（自选传代码、研究清单传 UUID）落库后同格式
    member_by_uuid = repo.add_fund_to_pool(
        pool_id=pool["id"], fund_id=fund_uuid, status="candidate", created_by="smoke-test",
    )
    if member_by_uuid.get("fund_id") != WIND_CODE:
        raise AssertionError(f"UUID member must be stored as canonical wind_code: {member_by_uuid}")

    # 2. 同基金换用 wind_code 重复加入：返回同一成员行，不产生第二行
    member_by_code = repo.add_fund_to_pool(
        pool_id=pool["id"], fund_id=WIND_CODE, status="candidate", reason="重复加入", created_by="smoke-test",
    )
    if member_by_code.get("id") != member_by_uuid.get("id"):
        raise AssertionError(f"same fund via different identifier formats must dedupe to one member: {member_by_code}")

    members = repo.list_members(pool["id"])
    same_fund_members = [m for m in members if m.get("fund_wind_code") == WIND_CODE]
    if len(same_fund_members) != 1:
        raise AssertionError(f"exactly one member row per fund expected, got {len(same_fund_members)}")

    # 3. 本地基金库不认识的标识原样保留（既有测试基金路径兼容）
    unknown = repo.add_fund_to_pool(
        pool_id=pool["id"], fund_id="FUND-UNKNOWN-999", status="watch", created_by="smoke-test",
    )
    if unknown.get("fund_id") != "FUND-UNKNOWN-999":
        raise AssertionError(f"unknown fund identifier must be stored verbatim: {unknown}")

    print("OK fund pool member identifier normalization")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
