import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from routes.reports import _compact_research_reports, _evaluation_analysis_fallback
from services.ai_report import ClaudeReportGenerator


def main():
    compact = _compact_research_reports([{
        "id": "memo-1",
        "title": "经理纪要",
        "report_date": "2026-04-09",
        "manager_name": "测试经理",
        "evidence_scope": "manager_level",
        "summary": "很长的摘要 " * 300,
        "key_points": ["关键观点 " * 100, "第二观点", "第三观点", "第四观点"],
        "classifications": list(map(str, range(20))),
        "style_labels": list(map(str, range(20))),
    }])
    assert len(compact) == 1
    assert len(compact[0]["summary"]) <= 501
    assert len(compact[0]["key_points"]) == 3
    assert max(map(len, compact[0]["key_points"])) <= 300
    assert len(compact[0]["classifications"]) == 8
    assert compact[0]["evidence_scope"] == "manager_level"

    stability = {
        "status": "available",
        "label": "前十大持仓延续性较高",
        "latest_quarter": "2026Q2",
        "previous_quarter": "2026Q1",
        "top10_overlap_ratio": 0.908,
        "industry_overlap_ratio": 0.9311,
        "retained_holding_count": 9,
        "included_in_score": False,
    }
    style_drift = {
        "status": "available",
        "level": "medium",
        "label": "公开持仓风格出现一定变化",
        "previous_quarter": "2026Q1",
        "latest_quarter": "2026Q2",
        "max_percentile_change": 0.365413,
        "included_in_score": False,
        "note": "2026Q1至2026Q2，规模风格由中盘变为偏大盘。仅比较公开披露持仓的同类风格分位。",
    }
    generator = ClaudeReportGenerator(api_key="test-key")
    captured = {}
    generator._call_llm = lambda prompt, *_args, **_kwargs: captured.setdefault("prompt", prompt) or "ok"
    generator.generate_fund_evaluation_analysis(
        fund_data={"wind_code": "001583.OF"},
        evaluation_data={
            "status": "ok",
            "manager_tenure_performance": {
                "status": "partial",
                "coverage_status": "partial_since_data_start",
                "requested_start_date": "2020-01-01",
                "actual_start_date": "2023-07-21",
                "coverage_ratio": 0.41,
                "total_return": 0.09,
            },
            "period_performance": {
                "periods": [{"label": "2025 年", "return": 0.1, "coverage_status": "complete", "rank": 2, "peer_count": 10}],
            },
            "multi_period_evidence": {
                "status": "long_term_ready",
                "return_6m": 0.08,
                "return_1y": 0.16,
                "annualized_return_1y": 0.16,
                "annualized_return_3y": 0.13,
                "max_drawdown_1y": -0.12,
                "max_drawdown_3y": -0.20,
                "sharpe_ratio_3y": 0.9,
                "annualized_return_gap": 0.03,
                "consistency_status": "stable",
                "consistency_label": "短长期表现较一致",
            },
            "holding_style_drift": style_drift,
        },
        factor_evidence={"holding_style_drift_evidence": style_drift},
        attribution_evidence={},
        managers=[],
        research_reports=compact,
        assessment_summary={
            "holding_stability_evidence": stability,
            "style_drift_evidence": style_drift,
        },
    )
    prompt = captured["prompt"]
    assert "公开持仓稳定性仅比较相邻两期披露的前十大持仓" in prompt
    assert '"top10_overlap_ratio": 0.908' in prompt
    assert '"period_performance"' in prompt
    assert "coverage_status=partial" in prompt
    assert "partial_since_data_start 只能称为本地可见期" in prompt
    assert '"coverage_ratio": 0.41' in prompt
    assert "只有 status=long_term_ready 时才能描述完整近 3 年收益风险证据" in prompt
    assert '"consistency_status": "stable"' in prompt
    assert "holding_style_drift_evidence 只比较同一专业同类组内相邻公开持仓期" in prompt
    assert '"max_percentile_change": 0.365413' in prompt
    assert "manager_tenure_performance.status=not_applicable" in prompt

    fallback = _evaluation_analysis_fallback(
        fund_data={"wind_code": "001583.OF", "name": "测试基金"},
        evaluation={
            "status": "ok",
            "explanatory_evidence": {"holding_stability": stability},
            "manager_tenure_performance": {
                "status": "partial",
                "coverage_status": "partial_since_data_start",
                "requested_start_date": "2020-01-01",
                "actual_start_date": "2023-07-21",
                "coverage_ratio": 0.41,
                "total_return": 0.09,
            },
            "period_performance": {
                "periods": [
                    {"label": "2025 年", "return": 0.1, "coverage_status": "complete", "rank": 2, "peer_count": 10, "peer_median_return": 0.08},
                    {"label": "2024 年", "return": 0.03, "coverage_status": "partial"},
                ],
            },
            "multi_period_evidence": {
                "status": "long_term_ready",
                "return_6m": 0.08,
                "return_1y": 0.16,
                "annualized_return_1y": 0.16,
                "annualized_return_3y": 0.13,
                "max_drawdown_1y": -0.12,
                "max_drawdown_3y": -0.20,
                "sharpe_ratio_3y": 0.9,
                "annualized_return_gap": 0.03,
                "consistency_label": "短长期表现较一致",
            },
            "holding_style_drift": style_drift,
        },
        factor_evidence={"holding_style_drift_evidence": style_drift},
        attribution_evidence={},
        managers=[],
        research_reports=[],
        question="",
    )
    assert "前十大权重重合度 90.8%" in fallback
    assert "不等于完整组合换手率，也不参与基金评分" in fallback
    assert "2025 年：10.00%；同类中位数 8.00%；同类排名 2/10" in fallback
    assert "2024 年：3.00%；区间不完整，不参与年度同类排名" in fallback
    assert "本地净值从 2023-07-21 才开始，仅覆盖 41%" in fallback
    assert "不冒充完整任期，不生成同类排名，也不计入经理任期评分" in fallback
    assert "长期证据：近 3 年收益、最大回撤和 Sharpe 数据完整" in fallback
    assert "短长期一致性：短长期表现较一致，相差 3.0 个百分点" in fallback
    assert "公开持仓风格变化：2026Q1至2026Q2" in fallback
    assert "不是完整组合、RBSA 或 Barra，也不参与基金评分" in fallback

    passive_fallback = _evaluation_analysis_fallback(
        fund_data={"wind_code": "513300.SH", "name": "测试纳指 ETF"},
        evaluation={
            "status": "ok",
            "classification": {"evaluation_profile_key": "qdii_index"},
            "manager_tenure_performance": {"status": "not_applicable"},
        },
        factor_evidence={},
        attribution_evidence={},
        managers=[],
        research_reports=[],
        question="",
    )
    assert "该类别评价不使用经理任期指标，不构成评价缺口" in passive_fallback
    assert "当前基金经理资料待补" not in passive_fallback
    print("OK AI evaluation sends compact scoped memo evidence to the model")


if __name__ == "__main__":
    main()
