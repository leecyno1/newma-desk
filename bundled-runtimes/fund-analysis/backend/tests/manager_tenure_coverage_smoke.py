from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.manager_tenure_coverage import (
    build_manager_tenure_coverage,
    metric_details_coverage_status,
)
from services.professional_scoring_service import ProfessionalScoringService


def main():
    full = build_manager_tenure_coverage(
        "2026-01-01", "2026-01-05", "2026-08-12", 150
    )
    assert full["tenure_coverage_status"] == "full_tenure"
    assert full["peer_ranking_eligible"] is True

    partial = build_manager_tenure_coverage(
        "2019-12-09", "2023-07-25", "2026-08-12", 744
    )
    assert partial["tenure_coverage_status"] == "partial_since_data_start"
    assert 0.4 < partial["tenure_coverage_ratio"] < 0.6
    assert partial["peer_ranking_eligible"] is False
    assert metric_details_coverage_status({
        "manager_tenure_start": "2019-12-09",
        "window_start_date": "2023-07-25",
    }) == "partial_since_data_start"

    panel = [
        {
            "metric_window": "manager_tenure",
            "metric_name": "annualized_return",
            "metric_value": 0.12,
            "details": partial,
        },
        {
            "metric_window": "1y",
            "metric_name": "annualized_return",
            "metric_value": 0.08,
            "details": {},
        },
    ]
    scoring = ProfessionalScoringService.__new__(ProfessionalScoringService)
    metrics = scoring._metrics_by_window(panel)
    assert "manager_tenure" not in metrics
    assert metrics["1y"]["annualized_return"] == 0.08
    print("manager tenure coverage gates partial history from ranking and scoring")


if __name__ == "__main__":
    main()
