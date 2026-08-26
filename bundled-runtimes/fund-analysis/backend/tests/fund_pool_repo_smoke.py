import os
import sys
from datetime import date

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from repositories.fund_pool_repo import FundPoolRepo


def main() -> int:
    repo = FundPoolRepo()

    pool = repo.create_pool(
        name="候选池-smoke",
        description="测试候选池",
        created_by="smoke-test",
        is_default=True,
    )
    if not pool.get("id"):
        print(f"Expected pool id, got: {pool}")
        return 1

    member = repo.add_fund_to_pool(
        pool_id=pool["id"],
        fund_id="FUND-TEST-001",
        status="candidate",
        reason="全市场浏览器加入",
        latest_conclusion="初步观察",
        evidence={"source": "market"},
        risk_notes="需观察回撤",
        next_review_date=date(2026, 6, 30),
        created_by="smoke-test",
    )
    if member.get("status") != "candidate":
        print(f"Expected candidate member, got: {member}")
        return 1

    listed = repo.list_members(pool["id"], status="candidate")
    if len(listed) < 1:
        print(f"Expected members in candidate status, got: {listed}")
        return 1

    updated = repo.update_member_status(
        member_id=member["id"],
        status="watch",
        latest_conclusion="转入观察",
        updated_by="smoke-reviewer",
    )
    if updated.get("status") != "watch":
        print(f"Expected watch status, got: {updated}")
        return 1

    deduped = repo.add_fund_to_pool(
        pool_id=pool["id"],
        fund_id="FUND-TEST-001",
        status="candidate",
        reason="重复加入测试",
        created_by="smoke-test",
    )
    if deduped.get("id") != member.get("id"):
        print(f"Expected duplicate add to return existing member, got: {deduped}")
        return 1

    print("OK fund pool repository lifecycle")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
