import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import init_database
from services.peer_comparison_service import PeerComparisonService


def main() -> int:
    init_database()

    matrix = PeerComparisonService().build_comparison_matrix(["000002.OF", "000007.OF"], window="1y")
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
