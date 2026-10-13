import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

from sync_fund_manager_tenure import select_snapshot_backlog_managers


def main() -> int:
    # 批量补快照：优先选"在管产品多、但任一在管任期缺 performance_snapshot"的经理，
    # 跳过已有可用快照的经理，避免重复消耗 Tushare 配额。
    managers = select_snapshot_backlog_managers(limit=20)
    if not managers:
        print("no snapshot-backlog managers found in this environment")
        return 0
    for manager_id, in_charge_count, avail_count in managers:
        assert "|" in manager_id, f"manager ids must be canonical composite ids: {manager_id}"
        assert in_charge_count >= 1, f"backlog managers must have in-charge products: {manager_id}"
        assert avail_count < in_charge_count, (
            f"backlog managers must have at least one missing in-charge snapshot: {manager_id}"
        )
    # 排序优先级：缺失条目多的经理排前面
    missing = [in_charge - avail for _, in_charge, avail in managers]
    assert missing == sorted(missing, reverse=True), f"managers must be ordered by missing snapshots: {missing}"
    print(f"OK snapshot backlog selector returned {len(managers)} managers, e.g. {managers[0][0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
