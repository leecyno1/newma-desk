"""首页同类组覆盖必须使用轻量数据库聚合。"""

from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.fund_recommendation_service import FundRecommendationService  # noqa: E402


class ClassificationRepo:
    def list_peer_group_coverage_inventory(self, limit):
        assert limit == 100
        return [
            {"id": "g1", "key": "equity", "name": "主动权益", "minimum_peer_count": 5,
             "classified_count": 20, "database_fund_count": 20},
            {"id": "g2", "key": "bond", "name": "纯债", "minimum_peer_count": 5,
             "classified_count": 4, "database_fund_count": 4},
        ]

    def list_peer_group_inventory(self, limit):
        assert limit == 100
        return [{"key": "equity", "evaluated_fund_count": 8}]


def main():
    result = FundRecommendationService(
        classification_repo=ClassificationRepo(),
    ).build_home_coverage_report(limit=100)
    assert result["summary"]["category_count"] == 2
    assert result["summary"]["ready_category_count"] == 1
    assert result["summary"]["recommendation_ready_count"] == 8
    assert result["summary"]["metric_ready_count"] == 8
    assert result["groups"][0]["status"] == "ready"
    assert result["groups"][1]["status"] == "partial"
    print("fund home coverage uses lightweight peer-group inventory")


if __name__ == "__main__":
    main()
