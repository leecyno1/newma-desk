from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.manager_tenure_peer_ranking_service import ManagerTenurePeerRankingService


class ClassificationRepo:
    def get_classification_context(self, code):
        return {
            "status": "resolved",
            "entity_id": "target-entity",
            "peer_group_id": "peer-active",
            "peer_group_name": "主动权益-测试组",
            "peer_group_membership_count": 7,
            "minimum_peer_count": 5,
        }

    def list_peer_period_nav_summaries(self, peer_group_id, start_date, end_date):
        return [
            {"entity_id": "target-entity", "wind_code": "TARGET.OF", "first_date": "2025-01-01", "last_date": "2025-12-31", "observations": 250, "first_nav": 1, "last_nav": 1.30, "record_breaking_days_ratio": 0.75, "max_drawdown": -0.12, "sharpe_ratio": 0.9},
            {"entity_id": "peer-1", "wind_code": "PEER1.OF", "first_date": "2025-01-02", "last_date": "2025-12-31", "observations": 249, "first_nav": 1, "last_nav": 1.50, "record_breaking_days_ratio": 0.90, "max_drawdown": -0.08, "sharpe_ratio": 1.2},
            {"entity_id": "peer-2", "wind_code": "PEER2.OF", "first_date": "2025-01-02", "last_date": "2025-12-31", "observations": 249, "first_nav": 1, "last_nav": 1.40, "record_breaking_days_ratio": 0.80, "max_drawdown": -0.10, "sharpe_ratio": 1.0},
            {"entity_id": "peer-3", "wind_code": "PEER3.OF", "first_date": "2025-01-02", "last_date": "2025-12-31", "observations": 249, "first_nav": 1, "last_nav": 1.20, "record_breaking_days_ratio": 0.70, "max_drawdown": -0.18, "sharpe_ratio": 0.5},
            {"entity_id": "peer-4", "wind_code": "PEER4.OF", "first_date": "2025-01-02", "last_date": "2025-12-31", "observations": 249, "first_nav": 1, "last_nav": 1.10, "record_breaking_days_ratio": 0.60, "max_drawdown": -0.22, "sharpe_ratio": 0.2},
            {"entity_id": "short-history", "wind_code": "SHORT.OF", "first_date": "2025-08-01", "last_date": "2025-12-31", "observations": 100, "first_nav": 1, "last_nav": 2},
        ]


def main():
    result = ManagerTenurePeerRankingService(ClassificationRepo()).rank({
        "fund_code": "TARGET.OF",
        "entity_id": "target-entity",
        "start_date": "2025-01-01",
        "metric_as_of_date": "2025-12-31",
        "metric_observations": 250,
        "tenure_return": 0.30,
        "annualized_return": 0.31,
        "record_breaking_days_ratio": 0.75,
        "max_drawdown": -0.15,
        "sharpe_ratio": 0.8,
    })
    metric = result["metrics"]["total_return"]
    assert result["status"] == "sufficient"
    assert result["valid_peer_count"] == 5
    assert metric["rank"] == 3
    assert metric["peer_count"] == 5
    assert metric["percentile"] == 50.0
    assert result["metrics"]["annualized_return"]["rank"] == 3
    assert result["metrics"]["record_breaking_days_ratio"]["rank"] == 3
    assert result["metrics"]["max_drawdown"]["rank"] == 3
    assert result["metrics"]["sharpe_ratio"]["rank"] == 3
    assert result["methodology_version"] == "manager_tenure_same_period_peer_rank_v3"

    partial = ManagerTenurePeerRankingService(ClassificationRepo()).rank({
        "fund_code": "TARGET.OF",
        "tenure_coverage_status": "partial_since_data_start",
        "tenure_coverage_ratio": 0.48,
        "metric_start_date": "2023-07-25",
        "metric_as_of_date": "2026-08-12",
        "tenure_return": 0.30,
    })
    assert partial["status"] == "partial_tenure_coverage"
    assert partial["metrics"] == {}
    print("manager tenure peer ranking service smoke passed")


if __name__ == "__main__":
    main()
