import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.fund_research_snapshot_service import FundResearchSnapshotService


def main():
    class FakeRow:
        _mapping = {
            "id": "memo-1",
            "manager_id": "MGR-1",
            "manager_name": "测试经理",
            "title": "经理交流纪要",
            "report_date": "2026-04-09",
            "source": "本地调研纪要文件夹",
            "summary": "经理层观点",
            "key_points": [],
            "classifications": [],
            "style_labels": [],
            "tags": [],
            "review_proposals": [],
            "updated_at": "2026-04-09",
        }

    class FakeResult:
        def fetchall(self):
            return [FakeRow()]

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, _sql, params):
            assert params["wind_code"] == "FUND.OF"
            assert params["manager_ids"] == ["MGR-1"]
            assert "research_report_managers" in str(_sql)
            return FakeResult()

    class FakeEngine:
        def connect(self):
            return FakeConnection()

    service = FundResearchSnapshotService()
    import database

    original_get_engine = database.get_engine
    database.get_engine = lambda: FakeEngine()
    try:
        reports = service._postgres_manager_research_reports("FUND.OF", ["MGR-1"], 5)
    finally:
        database.get_engine = original_get_engine

    assert len(reports) == 1
    assert reports[0]["evidence_scope"] == "manager_level"
    assert reports[0]["manager_name"] == "测试经理"
    tenure_only = service._research_evidence_scope("FUND.OF", [{
        "kind": "fund",
        "value": "FUND.OF",
        "review_status": "confirmed",
        "extraction_source": "tushare.fund_manager",
    }])
    assert tenure_only == "manager_level"
    explicit_fund = service._research_evidence_scope("FUND.OF", [{
        "kind": "fund",
        "value": "FUND.OF",
        "review_status": "confirmed",
        "extraction_source": "deterministic_rules",
    }])
    assert explicit_fund == "fund_specific"
    targeted_fund_label = service._research_evidence_scope("FUND.OF", [{
        "kind": "style_label",
        "scope": "fund",
        "value": "周期",
        "target_fund_ids": ["FUND.OF"],
        "review_status": "confirmed",
        "extraction_source": "deterministic_profile_rule",
    }])
    assert targeted_fund_label == "fund_specific"
    other_fund_label = service._research_evidence_scope("FUND.OF", [{
        "kind": "style_label",
        "scope": "fund",
        "value": "周期",
        "target_fund_ids": ["OTHER.OF"],
        "review_status": "confirmed",
        "extraction_source": "deterministic_profile_rule",
    }])
    assert other_fund_label == "manager_level"
    manager_label = service._research_evidence_scope("FUND.OF", [{
        "kind": "style_label",
        "scope": "manager",
        "value": "价值",
        "target_fund_ids": [],
        "review_status": "confirmed",
        "extraction_source": "explicit_field",
    }])
    assert manager_label == "manager_level"
    assert service._research_evidence_scope("FUND.OF", []) == "manager_level"

    scoped_style = service._style_profile({}, [
        {
            "evidence_scope": "fund_specific",
            "classifications": ["周期资源"],
            "style_labels": ["周期"],
        },
        {
            "evidence_scope": "manager_level",
            "classifications": ["均衡配置"],
            "style_labels": ["价值"],
        },
    ])
    assert scoped_style["memo_classifications"] == ["周期资源"]
    assert scoped_style["memo_style_labels"] == ["周期"]
    assert scoped_style["manager_memo_classifications"] == ["均衡配置"]
    assert scoped_style["manager_memo_style_labels"] == ["价值"]
    assert service._research_scope_counts([
        {"evidence_scope": "fund_specific"},
        {"evidence_scope": "manager_level"},
    ]) == (1, 1)
    mixed_labels = service._scoped_research_labels(
        "FUND.OF",
        [
            {
                "kind": "style_label",
                "scope": "fund",
                "value": "周期",
                "target_fund_ids": ["FUND.OF"],
                "review_status": "confirmed",
            },
            {
                "kind": "style_label",
                "scope": "manager",
                "value": "价值",
                "target_fund_ids": [],
                "review_status": "confirmed",
            },
        ],
        ["行业主题"],
        ["周期", "价值"],
        "fund_specific",
    )
    assert mixed_labels == {
        "fund_classifications": ["行业主题"],
        "fund_style_labels": ["周期"],
        "manager_classifications": [],
        "manager_style_labels": ["价值"],
    }
    print("OK fund evaluation supplements exact reviewed manager memos without calling them fund-specific")


if __name__ == "__main__":
    main()
