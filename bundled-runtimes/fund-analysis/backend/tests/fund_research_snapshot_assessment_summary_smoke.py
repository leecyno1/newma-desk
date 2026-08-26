import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.fund_research_snapshot_service import FundResearchSnapshotService


def main():
    evaluation = {
        "status": "ok",
        "classification": {"peer_group": "指数-科创50"},
        "peer_context": {"peer_group": "指数-科创50"},
        "explanatory_evidence": {
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
        "evaluation": {
            "overall_score": 92.57,
            "overall_grade": "S",
            "positive_factors": ["跟踪质量领先"],
            "negative_factors": [],
            "peer_percentiles": {
                "professional_score": {"rank": 2, "peer_count": 19, "percentile": 94.44}
            },
        },
    }
    style_profile = {
        "quantitative_labels": ["偏大盘"],
        "manager_memo_style_labels": ["景气驱动"],
        "holding_style": {"status": "peer_percentile_ready", "quarter": "2026Q1", "sample_size": 8},
    }
    research = [{"title": "经理交流", "report_date": "2026-08-01", "evidence_scope": "manager_level"}]
    attribution = {
        "status": "partial_evidence",
        "quarter": "2026Q2",
        "evidence_origin": {"mode": "saved_history"},
        "barra": {"descriptor_model_ready": True, "formal_model_ready": False},
        "brinson": {
            "status": "partial_evidence",
            "returns": {"active": 0.0123},
            "coverage": {"portfolio_holdings": 0.55},
            "effects": [{"label": "行业配置效应", "value": 0.02}],
        },
    }
    summary = FundResearchSnapshotService._assessment_summary(
        evaluation, style_profile, research, attribution, include_attribution=True,
        manager_stability={
            "status": "recent_change",
            "label": "团队近期有变动",
            "current_manager_count": 2,
            "current_manager_names": ["甲经理", "乙经理"],
            "team_mode": "co_managed",
            "current_team_start": "2025-09-12",
            "current_team_days": 337,
            "latest_change_date": "2025-09-12",
            "changes_last_year": 1,
            "changes_last_three_years": 2,
            "note": "现任 2 人（甲经理、乙经理），当前团队共同起点 2025-09-12；近三年有 2 个经理加入或离任节点。",
        },
        manager_tenure_performance={
            "status": "available",
            "coverage_status": "full_tenure",
            "requested_start_date": "2025-09-12",
            "actual_start_date": "2025-09-12",
            "actual_end_date": "2026-08-12",
            "coverage_ratio": 1.0,
            "total_return": 0.153,
            "annualized_return": 0.171,
            "max_drawdown": -0.082,
            "sharpe_ratio": 1.02,
            "included_in_score": True,
            "peer_ranking": {
                "metrics": {
                    "total_return": {"rank": 3, "peer_count": 18},
                },
            },
        },
        scale_trend={
            "status": "shrinking",
            "label": "规模明显缩水",
            "latest_report_date": "2026-06-30",
            "latest_asset_yi": 4.0,
            "one_year_change": -0.6,
            "peak_asset_yi": 10.0,
            "peak_date": "2025-06-30",
            "latest_from_peak": -0.6,
            "observations": 5,
            "note": "最新报告期净资产 4.00 亿元，较一年前 -60.0%，较可见历史峰值 -60.0%。规模下降较明显。",
        },
        drawdown_recovery={
            "status": "current_drawdown",
            "label": "当前仍在明显回撤中",
            "history_start": "2020-01-02",
            "history_end": "2026-08-12",
            "nav_basis": "accum_nav",
            "observations": 1600,
            "current_drawdown": -0.082,
            "current_underwater_days": 95,
            "worst_drawdown": -0.245,
            "worst_recovery_days": 186,
            "longest_underwater_days": 320,
            "material_episode_count": 4,
            "recovered_material_episode_count": 3,
            "note": "当前较最近高点回撤 8.2%，已持续 95 天。可见区间最大回撤 24.5%，谷底后 186 天修复。",
        },
        holding_style_drift={
            "status": "available",
            "level": "high",
            "label": "公开持仓风格变化较明显",
            "previous_quarter": "2026Q1",
            "latest_quarter": "2026Q2",
            "max_percentile_change": 0.51,
            "factor_changes": [],
            "included_in_score": False,
            "note": "2026Q1至2026Q2，公开持仓风格变化较明显。",
        },
    )
    assert summary["verdict"] == "近 1 年专业评分 92.6 分，同类综合第 2 / 19 名。", summary
    assert summary["style_evidence"]["labels"] == ["偏大盘"], summary
    assert summary["research_evidence"]["status"] == "manager_level", summary
    assert "不能外推" in summary["research_evidence"]["note"], summary
    assert summary["attribution_evidence"]["headline"] == "相对基准 +1.23%", summary
    assert "行业配置效应" in summary["attribution_evidence"]["detail"], summary
    assert summary["attribution_evidence"]["formal_barra_ready"] is False, summary
    stability = summary["holding_stability_evidence"]
    assert stability["label"] == "前十大持仓延续性较高", summary
    assert stability["included_in_score"] is False, summary
    assert "前十大权重重合度 90.8%" in stability["note"], summary
    assert "不是完整组合换手率" in stability["note"], summary
    manager_stability = summary["manager_stability_evidence"]
    assert manager_stability["status"] == "recent_change", summary
    assert manager_stability["included_in_score"] is False, summary
    assert manager_stability["changes_last_three_years"] == 2, summary
    tenure_performance = summary["manager_tenure_performance_evidence"]
    assert tenure_performance["coverage_status"] == "full_tenure", summary
    assert "任期收益 15.30%" in tenure_performance["note"], summary
    assert "同区间同类任期收益第 3 / 18 名" in tenure_performance["note"], summary
    scale_trend = summary["scale_trend_evidence"]
    assert scale_trend["status"] == "shrinking", summary
    assert scale_trend["included_in_score"] is False, summary
    drawdown_recovery = summary["drawdown_recovery_evidence"]
    assert drawdown_recovery["status"] == "current_drawdown", summary
    assert drawdown_recovery["current_underwater_days"] == 95, summary
    assert drawdown_recovery["included_in_score"] is False, summary
    style_drift = summary["style_drift_evidence"]
    assert style_drift["level"] == "high", summary
    assert style_drift["included_in_score"] is False, summary
    assert summary["risks"][0].startswith("公开持仓风格变化较明显"), summary

    thin_peer_evaluation = {
        **evaluation,
        "status": "partial",
        "peer_context": {
            "peer_group": "指数-沪深300医药卫生",
            "metric_window": "1y",
            "sample_status": "insufficient_peer_sample",
            "valid_metric_peer_count": 2,
            "minimum_peer_count": 5,
        },
        "evaluation": {**evaluation["evaluation"], "overall_score": None, "overall_grade": "insufficient_evidence"},
    }
    thin_peer_summary = FundResearchSnapshotService._assessment_summary(
        thin_peer_evaluation, style_profile, research, {"status": "not_requested"}, include_attribution=False
    )
    assert "同类有效样本只有 2 只" in thin_peer_summary["verdict"], thin_peer_summary
    assert "暂不输出综合分和同类排名" in thin_peer_summary["verdict"], thin_peer_summary

    highlight_evaluation = {
        "status": "ok",
        "target": {"as_of_date": "2026-08-12"},
        "peer_context": {"metric_window": "1y"},
        "evaluation": {
            "peer_percentiles": {
                "annualized_return": {
                    "value": 0.12, "percentile": 85, "rank": 2, "peer_count": 10,
                    "sample_status": "sufficient", "unit": "percent"
                },
                "max_drawdown": {
                    "value": -0.18, "percentile": 10, "sample_status": "sufficient", "unit": "percent"
                },
                "expense_ratio": {
                    "value": 0.014, "percentile": 5, "sample_status": "sufficient", "unit": "percent"
                },
                "aum": {
                    "value": 130.3194, "percentile": 100, "sample_status": "sufficient", "unit": "cny_100m"
                },
                "sharpe_ratio": {
                    "value": 1.1, "percentile": 90, "sample_status": "insufficient_peer_sample", "unit": "number"
                },
            },
        },
    }
    holding_experience = {
        "source": "local.postgres.fund_nav",
        "sample_end": "2026-08-12",
        "periods": [{
            "months": 12,
            "status": "sufficient",
            "sample_count": 502,
            "positive_probability": 0.828685,
            "worst_return": -0.045175,
            "return_threshold_probabilities": [
                {"threshold": 0, "probability": 0.828685},
                {"threshold": 0.03, "probability": 0.596},
            ],
        }],
    }
    highlights = FundResearchSnapshotService._detail_highlights(
        highlight_evaluation,
        holding_experience,
    )
    by_id = {item["id"]: item for item in highlights}
    assert by_id["peer_annualized_return"]["tone"] == "strength", highlights
    assert "同类第 2 / 10 名" in by_id["peer_annualized_return"]["detail"], highlights
    assert by_id["peer_max_drawdown"]["tone"] == "risk", highlights
    assert by_id["peer_aum"]["tone"] == "strength", highlights
    assert by_id["peer_expense_ratio"]["tone"] == "risk", highlights
    assert "不代表完整持有成本" in by_id["peer_expense_ratio"]["detail"], highlights
    assert "历史回放，不是未来预测" in by_id["holding_experience_12m"]["detail"], highlights
    assert "peer_sharpe_ratio" not in by_id, highlights
    assert len(highlights) <= 6, highlights

    brief = FundResearchSnapshotService._plain_language_brief(
        {"wind_code": "588000.SH", "name": "科创50ETF", "nav_date": "2026-08-12"},
        summary,
        highlights,
        holding_experience,
    )
    brief_items = {item["key"]: item for item in brief["items"]}
    assert brief["title"] == "一分钟看懂这只基金", brief
    assert brief_items["strength"]["evidence_id"] == "peer_annualized_return", brief
    assert "收益超过 3% 的概率 60%" in brief_items["holding"]["text"], brief
    assert "经理层纪要" in brief_items["style_research"]["text"], brief
    assert "延续 9 只重仓" in brief_items["holding_stability"]["text"], brief
    assert "当前团队共同起点" in brief_items["manager_stability"]["text"], brief
    assert "任期收益 15.30%" in brief_items["manager_tenure_performance"]["text"], brief
    assert "较一年前 -60.0%" in brief_items["scale_trend"]["text"], brief
    assert "当前较最近高点回撤 8.2%" in brief_items["drawdown_recovery"]["text"], brief
    assert "不构成投资建议" in brief["copy_text"], brief
    assert brief["evidence_count"] >= 3, brief

    not_run = FundResearchSnapshotService._assessment_summary(
        evaluation, style_profile, research, {"status": "not_requested"}, include_attribution=False
    )
    assert not_run["attribution_evidence"]["status"] == "not_run", not_run
    print("OK unified fund assessment summary keeps evaluation, memo scope and attribution boundaries")


if __name__ == "__main__":
    main()
