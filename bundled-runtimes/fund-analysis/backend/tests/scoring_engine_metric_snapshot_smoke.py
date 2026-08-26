import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.scoring_engine import FundScoringEngine


class FakeMetricRepo:
    def get_latest_panel(self, target_type, target_id):
        return [
            {"metric_name": "annualized_return", "metric_value": "0.18", "source_snapshot_id": "s1", "as_of_date": "2026-05-16"},
            {"metric_name": "max_drawdown", "metric_value": "-0.12", "source_snapshot_id": "s1", "as_of_date": "2026-05-16"},
            {"metric_name": "annualized_volatility", "metric_value": "0.16", "source_snapshot_id": "s1", "as_of_date": "2026-05-16"},
            {"metric_name": "sharpe_ratio", "metric_value": "1.20", "source_snapshot_id": "s1", "as_of_date": "2026-05-16"},
            {"metric_name": "sortino_ratio", "metric_value": "1.50", "source_snapshot_id": "s1", "as_of_date": "2026-05-16"},
            {"metric_name": "calmar_ratio", "metric_value": "1.00", "source_snapshot_id": "s1", "as_of_date": "2026-05-16"},
            {"metric_name": "information_ratio", "metric_value": "0.60", "source_snapshot_id": "s1", "as_of_date": "2026-05-16"},
        ]


class PartialMetricRepo:
    def get_latest_panel(self, target_type, target_id):
        return [{"metric_name": "annualized_return", "metric_value": "0.05", "as_of_date": "2026-05-16"}]


def main() -> int:
    engine = FundScoringEngine()
    score = engine.score_fund_from_metric_snapshots("UNIT.TEST", metric_repo=FakeMetricRepo())
    if score["target_id"] != "UNIT.TEST" or score["calculation_method"] != "metric_snapshot":
        print(f"Unexpected score metadata: {score}")
        return 1
    if not score["positive_factors"]:
        print(f"Expected positive factors: {score}")
        return 1
    if score["data_quality"]["status"] != "complete":
        print(f"Expected complete data quality: {score}")
        return 1
    partial = engine.score_fund_from_metric_snapshots("PARTIAL.TEST", metric_repo=PartialMetricRepo())
    if partial["data_quality"]["status"] != "partial" or not partial["missing_data"]:
        print(f"Expected partial data quality with missing data: {partial}")
        return 1
    print("OK scoring engine from metric snapshots")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
