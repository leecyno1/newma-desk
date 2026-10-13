import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import get_engine, init_database
from services.peer_comparison_service import PeerComparisonService


def pick_metric_rich_funds(count: int = 2) -> list:
    # 冒烟依赖真实指标数据：动态选取 1y 指标快照最多的基金，避免硬编码基金随数据集变化失效。
    from sqlalchemy import text

    with get_engine().connect() as conn:
        rows = conn.execute(text(
            "SELECT target_id FROM metric_snapshots WHERE metric_window = '1y'"
            " GROUP BY target_id ORDER BY COUNT(*) DESC LIMIT :count"
        ), {"count": count}).fetchall()
    if len(rows) < count:
        raise AssertionError(f"metric_snapshots lacks {count} funds with 1y metrics")
    return [str(row[0]) for row in rows]


def main() -> int:
    init_database()

    codes = pick_metric_rich_funds()
    matrix = PeerComparisonService().build_comparison_matrix(codes, window="1y")
    rows = {row.get("metric_name"): row for row in matrix.get("matrix_rows", [])}

    if len(matrix.get("funds", [])) != 2:
        raise AssertionError(f"Expected two funds: {matrix}")
    for metric_name in ["annualized_return", "max_drawdown", "sharpe_ratio", "professional_score"]:
        if metric_name not in rows:
            raise AssertionError(f"Missing comparison row {metric_name}: {matrix}")
        if not rows[metric_name].get("best_code"):
            raise AssertionError(f"Missing best code for {metric_name}: {rows[metric_name]}")
    if not matrix.get("recommendations"):
        raise AssertionError(f"Expected comparison recommendations: {matrix}")

    print("OK comparison matrix includes peer percentiles and best-fund rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
