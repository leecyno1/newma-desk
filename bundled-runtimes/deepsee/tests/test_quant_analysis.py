import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def test_render_quant_section_includes_table_and_colored_cells_without_bars():
    from app.services.quant_analysis import normalize_quant, render_quant_section_markdown

    quant = {
        "topics": [
            {"topic": "贵金属", "bullish_ids": ["1", "2", "2"], "bearish_ids": ["3"], "neutral_ids": []}
        ]
    }
    q = normalize_quant(quant)
    md = render_quant_section_markdown(q, module="market")
    assert "## 量化分析" in md
    assert "| 议题 |" in md
    assert "quant-bars" not in md
    assert "quant-tone-bullish" in md
    assert "quant-tone-bearish" in md
    assert "quant-tone-neutral" in md
    assert "证据：" not in md
