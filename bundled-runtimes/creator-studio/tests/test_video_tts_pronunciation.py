import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from video_tts_pronunciation import normalize_tts_text


def test_normalizes_section_number_as_ordinal() -> None:
    assert normalize_tts_text("01 成交还热") == "第一 成交还热"


def test_reads_year_digit_by_digit() -> None:
    assert normalize_tts_text("先把时间拨回 1985 年。") == "先把时间拨回 一九八五年。"
    assert normalize_tts_text("2026 年") == "二零二六年"


def test_normalizes_date_percentage_and_quantities() -> None:
    text = "7 月 13 日跌 9%，从 2023 年的 8 万片到 2028 年的 50 万片。"
    assert normalize_tts_text(text) == "七月十三日跌 百分之九，从 二零二三年的 八万片到 二零二八年的 五十万片。"


def test_normalizes_model_numbers_without_treating_them_as_years() -> None:
    assert normalize_tts_text("H100 成本占 66%") == "H 一百 成本占 百分之六十六"
