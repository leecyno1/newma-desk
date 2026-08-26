import os
import sys

# Ensure project root is on sys.path (repo uses namespace package `app/` without __init__.py)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.services.llm_client import DEFAULT_MODULE_PROMPTS


def test_market_prompt_requires_quant_json():
    u = DEFAULT_MODULE_PROMPTS["market"]["user"]
    assert '"quant"' in u
    assert '"markdown"' in u
    assert "宏观政策" in u
    assert "行业/赛道" in u
    assert "公司基本面" in u
    assert "投资策略" in u
    assert "市场情绪" in u
    assert "风险/负面" in u
    assert "公司/事件" not in u


def test_newswatch_prompt_requires_quant_json_and_sections():
    u = DEFAULT_MODULE_PROMPTS["newswatch"]["user"]
    assert '"quant"' in u
    # Ensure the fixed 7-section structure is encoded in defaults
    assert "## 海外/地缘" in u
    assert "## 科技/民生" in u
