import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from video_model_evidence import (
    build_cost_comparison,
    extract_artificial_analysis_scores,
    extract_deepseek_prices,
    extract_gpt4_8k_price,
)


def test_extract_gpt4_8k_price_converts_per_1k_to_per_1m():
    text = "使用定价为每 1K 提示令牌 0.03 美元，每 1K 补全令牌 0.06 美元。"

    assert extract_gpt4_8k_price(text) == {"input_usd_per_1m": 30.0, "output_usd_per_1m": 60.0}


def test_build_cost_comparison_calculates_percent_of_gpt4_baseline():
    baseline = {"input_usd_per_1m": 30.0, "output_usd_per_1m": 60.0}
    models = [
        {
            "model": "DeepSeek-V4-Flash",
            "price_per_1m_tokens_usd": {"input_cache_miss": 0.14, "output": 0.28},
        }
    ]

    rows = build_cost_comparison(baseline, models)

    assert rows[0]["input_vs_gpt4_pct"] == 0.4667
    assert rows[0]["output_vs_gpt4_pct"] == 0.4667


def test_extract_deepseek_prices_requires_flash_and_pro():
    payload = {
        "models": [
            {"model": "DeepSeek-V4-Flash", "price_per_1m_tokens_usd": {}},
            {"model": "DeepSeek-V4-Pro", "price_per_1m_tokens_usd": {}},
        ]
    }

    assert {item["model"] for item in extract_deepseek_prices(payload)} == {
        "DeepSeek-V4-Flash",
        "DeepSeek-V4-Pro",
    }


def test_extract_artificial_analysis_scores_reads_same_leaderboard_pair():
    text = "DeepSeek V4 Flash (high)\nHy3-preview\n37\n34\nReasoning models"

    assert extract_artificial_analysis_scores(text) == {"deepseek_v4_flash": 37, "hy3_preview": 34}
