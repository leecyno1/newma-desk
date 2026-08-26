import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.fund_research_snapshot_service import FundResearchSnapshotService


def main():
    evaluation = {
        "status": "partial",
        "target": {"wind_code": "000001.OF", "as_of_date": "2026-08-14"},
        "classification": {"evaluation_profile_key": "multi_asset_equity"},
        "peer_context": {"peer_group": "混合型-偏股配置", "peer_group_id": "peer-1"},
        "evaluation": {
            "overall_score": 88.2,
            "overall_grade": "A",
            "peer_percentiles": {"professional_score": {"percentile": 0.82}},
            "data_quality": {"status": "partial"},
        },
        "missing_items": ["缺少基金专属调研纪要"],
    }
    profile = {
        "peer_group": "混合型-偏股配置",
        "holding_style_evidence": [{
            "value": "大盘",
            "status": "quantitative",
            "source": "holding_style_peer_percentile",
            "basis": "2026Q1 · 同类样本 18 只",
            "quarter": "2026Q1",
            "peer_group_id": "peer-1",
            "peer_group_name": "混合型-偏股配置",
            "sample_size": 18,
            "minimum_peer_count": 5,
            "percentiles": [{"factor": "SIZE", "percentile": 0.88}],
        }],
        "memo_style_suggestions": [{"value": "价值", "status": "llm_suggested"}],
        "derived_style_evidence": [{"value": "成长", "status": "derived", "source": "standardized_benchmark"}],
    }
    candidate = {
        "id": "000001.OF",
        "wind_code": "000001.OF",
        "name": "名称中含红利成长但不得据此贴标签",
        "type": "混合型",
        "nav_date": "2026-08-14",
        "research_profile": profile,
        "style_profile": FundResearchSnapshotService.project_style_profile(profile),
        "fund_evaluation": evaluation,
        "rolling_metrics": {
            "6m": {"total_return": 0.08},
            "1y": {"total_return": 0.16, "annualized_return": 0.16, "max_drawdown": -0.12},
            "3y": {"annualized_return": 0.13, "max_drawdown": -0.20, "sharpe_ratio": 0.9, "as_of_date": "2026-08-14"},
        },
        "recommendation_evidence": {
            "data_as_of": "2026-08-14",
            "reasons": ["同类评价证据完整"],
            "risks": ["历史表现不代表未来"],
        },
    }

    snapshot = FundResearchSnapshotService.candidate_snapshot(candidate)
    assert snapshot["evaluation"] == evaluation, snapshot
    assert snapshot["style_profile"]["primary_label"] == "大盘", snapshot
    assert snapshot["style_profile"]["status"] == "quantitative", snapshot
    assert snapshot["evidence"]["missing_items"] == evaluation["missing_items"], snapshot
    assert snapshot["multi_period_evidence"]["status"] == "long_term_ready", snapshot
    assert snapshot["multi_period_evidence"]["consistency_status"] == "stable", snapshot
    assert snapshot["multi_period_evidence"]["used_in_score"] is True, snapshot
    assert "professional_scoring" not in snapshot, snapshot
    assert "research_snapshot" not in snapshot, snapshot

    confirmed = FundResearchSnapshotService.project_style_profile({
        **profile,
        "style_label": "均衡",
    })
    assert confirmed["primary_label"] == "均衡", confirmed
    assert confirmed["status"] == "confirmed", confirmed

    no_evidence = FundResearchSnapshotService.project_style_profile({})
    assert no_evidence["primary_label"] is None, no_evidence
    assert no_evidence["status"] == "unavailable", no_evidence

    divergent = FundResearchSnapshotService.project_multi_period_evidence({
        "1y": {"annualized_return": "0.31"},
        "3y": {"annualized_return": "0.15", "max_drawdown": "-0.17", "sharpe_ratio": "0.85"},
    }, "multi_asset_equity")
    assert divergent["status"] == "long_term_ready", divergent
    assert divergent["consistency_status"] == "divergent", divergent

    canonical_holding = FundResearchSnapshotService.project_style_profile({
        "holding_style_evidence": [{"value": "偏小盘", "status": "quantitative"}],
    })
    assert canonical_holding["primary_label"] == "小盘", canonical_holding

    bond_holding = FundResearchSnapshotService.project_style_profile({
        "bond_holding_style_profile": {"status": "available", "period_count": 4},
        "bond_holding_style_evidence": [{
            "value": "金融债",
            "status": "quantitative",
            "basis": "近 4 期金融债主导",
            "period_count": 4,
        }],
        "derived_style_evidence": [{"value": "固收+", "status": "derived"}],
    })
    assert bond_holding["primary_label"] == "金融债", bond_holding
    assert bond_holding["status"] == "quantitative", bond_holding
    assert bond_holding["quantitative_labels"] == ["金融债"], bond_holding
    assert bond_holding["bond_holding_style"]["period_count"] == 4, bond_holding

    fof_holding = FundResearchSnapshotService.project_style_profile({
        "fof_holding_style_profile": {
            "status": "available",
            "report_date": "2026-06-30",
            "disclosed_fund_count": 10,
            "disclosed_nav_ratio": 60.0,
            "top5_nav_ratio": 40.0,
        },
        "fof_holding_style_evidence": [{
            "value": "底层高集中",
            "status": "quantitative",
            "basis": "公开底层基金 10 只",
            "report_date": "2026-06-30",
            "disclosed_fund_count": 10,
            "disclosed_nav_ratio": 60.0,
            "top5_nav_ratio": 40.0,
        }],
    })
    assert fof_holding["primary_label"] == "底层高集中", fof_holding
    assert fof_holding["status"] == "quantitative", fof_holding
    assert fof_holding["quantitative_labels"] == ["底层高集中"], fof_holding
    assert fof_holding["fof_holding_style"]["disclosed_fund_count"] == 10, fof_holding

    analysis = FundResearchSnapshotService.project_analysis_evidence({
        "barra": {"status": "partial_evidence"},
        "brinson": {"status": "ok"},
        "nav_factor_lens": {"status": "available"},
        "nav_return_attribution": {"status": "available"},
        "benchmark": "000300.SH",
        "benchmark_source": "standardized_classification",
        "evidence_origin": {"mode": "saved"},
    }, snapshot["style_profile"])
    assert analysis["factor_evidence"]["holding_style_peer_evidence"]["status"] == "peer_percentile_ready", analysis
    assert analysis["factor_evidence"]["benchmark"] == "000300.SH", analysis
    assert analysis["attribution_evidence"]["status"] == "ok", analysis

    print("OK fund research snapshot is the single projection for evaluation, style, multi-period and AI evidence")


if __name__ == "__main__":
    main()
