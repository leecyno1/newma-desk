import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.ai_report import ClaudeReportGenerator


def main():
    generator = ClaudeReportGenerator(api_key="test-key")
    captured = {}
    generator._call_llm = lambda prompt, *_args, **_kwargs: captured.setdefault("prompt", prompt) or "ok"
    generator.generate_fund_evaluation_analysis(
        fund_data={"wind_code": "588040.SH"},
        evaluation_data={"status": "ok"},
        factor_evidence={
            "holding_style_peer_evidence": {
                "status": "peer_percentile_neutral",
                "labels": [],
                "peer_percentiles": [{"factor": "SIZE", "percentile_label": "同类差异不显著"}],
            }
        },
        attribution_evidence={},
        managers=[],
        research_reports=[],
    )
    prompt = captured["prompt"]
    assert "holding_style_peer_evidence" in prompt
    assert "不是完整 Barra 风险模型" in prompt
    assert "只有 status=peer_percentile_ready 时才能作为量化风格标签" in prompt
    assert "同类差异不显著" in prompt
    print("OK AI evaluation keeps holding peer styles separate from formal Barra and refuses neutral labels")


if __name__ == "__main__":
    main()
