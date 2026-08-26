import os
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.fund_evaluation_history_service import FundEvaluationHistoryService


class FakeEvaluationService:
    def __init__(self):
        self.calls = 0

    def load_context(self, wind_code):
        return {"found": True, "fund": {"wind_code": wind_code}}

    def evaluate_from_context(self, context, window="1y"):
        self.calls += 1
        score = 70.0 if self.calls == 1 else 72.5
        rank = 8 if self.calls == 1 else 6
        return {
            "status": "ok",
            "methodology_version": "fund_evaluation_v2",
            "target": {"wind_code": context["fund"]["wind_code"], "as_of_date": "2026-08-12"},
            "classification": {"peer_group_id": "peer-active", "peer_group": "主动权益"},
            "peer_context": {"metric_window": window, "peer_group_id": "peer-active", "peer_group": "主动权益"},
            "evaluation": {
                "overall_score": score,
                "overall_grade": "B",
                "calculation_method": "category_evaluation_methodology_v2:active_equity",
                "dimension_scores": {"return": {"score": score, "weight": 0.5}},
                "peer_percentiles": {
                    "professional_score": {"rank": rank, "peer_count": 20, "percentile": 70 if self.calls == 1 else 75}
                },
                "data_quality": {"status": "complete", "score": 95},
                "source_snapshot_ids": ["snapshot-1"],
            },
            "explanatory_evidence": {
                "cross_market_holding": {
                    "status": "peer_comparison_ready",
                    "quarter": "2026Q2",
                    "peer_group_name": "主动权益",
                    "profile_peer_count": 8,
                    "minimum_peer_count": 5,
                    "labels": ["港股公开持仓占基金净值同类偏高"],
                    "included_in_score": False,
                },
                "holding_stability": {
                    "status": "available",
                    "label": "前十大持仓延续性较高",
                    "latest_quarter": "2026Q2",
                    "previous_quarter": "2026Q1",
                    "top10_overlap_ratio": 0.908,
                    "industry_overlap_ratio": 0.9311,
                    "retained_holding_count": 9,
                    "included_in_score": False,
                }
            },
            "missing_items": [],
        }


class FakeSnapshotRepo:
    def __init__(self):
        self.rows = []

    def create(self, snapshot):
        created_at = datetime(2026, 8, 14, 10, 0) + timedelta(minutes=len(self.rows))
        row = {**snapshot, "id": f"history-{len(self.rows) + 1}", "created_at": created_at}
        self.rows.insert(0, row)
        return row

    def list_history(self, wind_code, evaluation_window=None, limit=30):
        rows = [row for row in self.rows if row["wind_code"] == wind_code]
        if evaluation_window:
            rows = [row for row in rows if row["evaluation_window"] == evaluation_window]
        return rows[:limit]

    def list_recent(self, evaluation_window=None, status=None, limit=30):
        rows = list(self.rows)
        if evaluation_window:
            rows = [row for row in rows if row["evaluation_window"] == evaluation_window]
        if status:
            rows = [row for row in rows if row["status"] == status]
        return [
            {**row, "fund_name": "测试基金", "fund_type": "指数型"}
            for row in rows[:limit]
        ]

    def get(self, snapshot_id, wind_code):
        return next(
            (row for row in self.rows if row["id"] == snapshot_id and row["wind_code"] == wind_code),
            None,
        )


def main():
    service = FundEvaluationHistoryService(
        evaluation_service=FakeEvaluationService(),
        snapshot_repo=FakeSnapshotRepo(),
    )

    first = service.save_current("000001.OF", window="1y")
    assert first["snapshot"]["overall_score"] == 70.0, first
    assert first["evaluation"]["evaluation"]["overall_score"] == 70.0, first
    assert first["history"]["items"][0]["change"] is None, first

    second = service.save_current("000001.OF", window="1y")
    latest = second["history"]["items"][0]
    assert latest["change"]["score_delta"] == 2.5, second
    assert latest["change"]["rank_change"] == 2.0, second
    assert latest["change"]["comparable"] is True, second
    assert "综合评分上升" in latest["change"]["summary"], second
    assert latest["source_snapshot_ids"] == ["snapshot-1"], second
    assert latest["cross_market_holding"]["quarter"] == "2026Q2", second
    assert latest["cross_market_holding"]["included_in_score"] is False, second
    assert latest["holding_stability"]["top10_overlap_ratio"] == 0.908, second
    assert latest["holding_stability"]["retained_holding_count"] == 9, second
    assert latest["holding_stability"]["included_in_score"] is False, second
    assert second["history"]["statistics"]["by_window"]["1y"]["average_score"] == 71.25, second
    assert "peer_metrics" not in latest, second
    assert "investment_decision" not in second, second

    saved = service.get_snapshot("000001.OF", second["snapshot"]["id"])
    assert saved["evaluation"]["evaluation"]["overall_score"] == 72.5, saved
    assert saved["evaluation"]["explanatory_evidence"]["cross_market_holding"]["profile_peer_count"] == 8, saved

    recent = service.list_recent(evaluation_window="1y", status="ok", limit=10)
    assert recent["total"] == 2, recent
    assert recent["items"][0]["fund_name"] == "测试基金", recent

    unchanged = service.save_current("000001.OF", window="1y")
    assert unchanged["status"] == "unchanged", unchanged
    assert len(service.snapshot_repo.rows) == 2, unchanged
    assert len(unchanged["history"]["items"]) == 2, unchanged

    database_typed_snapshot = {
        **service._snapshot_fields(unchanged["evaluation"], "1y"),
        "as_of_date": date(2026, 8, 12),
        "overall_score": Decimal("72.50"),
        "peer_percentile": Decimal("75.0000"),
    }
    assert service._same_snapshot(
        service._snapshot_fields(unchanged["evaluation"], "1y"),
        database_typed_snapshot,
    ) is True

    partial_coverage = service._evidence_coverage({
        "return": {"score": 80, "weight": 0.5, "included_in_score": True},
        "risk": {"score": 70, "weight": 0.4, "included_in_score": True},
        "manager_tenure": {"score": None, "weight": 0.1, "included_in_score": False},
    })
    assert partial_coverage["coverage_percent"] == 90.0, partial_coverage
    assert partial_coverage["missing_dimensions"] == ["manager_tenure"], partial_coverage

    methodology_change = service._change(
        {
            "wind_code": "000001.OF",
            "evaluation_window": "1y",
            "methodology_version": "fund_evaluation_v3",
            "calculation_method": "category_evaluation_methodology_v3:index_fund:1y",
            "peer_group_id": "peer-index-hs300",
            "overall_score": 45.29,
            "peer_rank": 50,
            "peer_count": 60,
            "peer_percentile": 16.95,
            "dimension_scores": {},
            "evidence_coverage": {"coverage_percent": 100},
            "data_quality": {"score": 100},
            "missing_items": [],
            "status": "ok",
        },
        {
            "wind_code": "000001.OF",
            "evaluation_window": "1y",
            "methodology_version": "fund_evaluation_v2",
            "calculation_method": "category_evaluation_methodology_v2:index_fund",
            "peer_group_id": "peer-index-hs300",
            "overall_score": 45.29,
            "peer_rank": 11,
            "peer_count": 15,
            "peer_percentile": 28.57,
            "dimension_scores": {},
            "evidence_coverage": {"coverage_percent": 100},
            "data_quality": {"score": 100},
            "missing_items": [],
            "status": "ok",
        },
    )
    assert methodology_change["comparable"] is False, methodology_change
    assert methodology_change["rank_change"] is None, methodology_change
    assert methodology_change["raw_rank_change"] == -39.0, methodology_change
    assert "不宜直接比较" in methodology_change["summary"], methodology_change

    print("OK evaluation history deduplicates unchanged snapshots and explains only comparable changes")


if __name__ == "__main__":
    main()
