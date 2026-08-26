import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from video_official_evidence import normalize_source_text, verify_excerpt


def test_normalize_source_text_joins_pdf_hyphenated_line_breaks():
    value = "AI-related product reve-\nnue achieved triple-digit growth"

    assert normalize_source_text(value) == "ai-related product revenue achieved triple-digit growth"


def test_normalize_source_text_standardizes_smart_quotes():
    value = "Cloud Intelligence Group’s \u201cAI\u201d revenue"

    assert normalize_source_text(value) == "cloud intelligence group's \"ai\" revenue"


def test_verify_excerpt_ignores_pdf_layout_whitespace_and_case():
    page = "Cloud Intelligence Group's external revenue growth\n accelerated to 40%."
    excerpt = "cloud intelligence group's external revenue growth accelerated to 40%."

    assert verify_excerpt(page, excerpt) is True


def test_verify_excerpt_handles_natural_hyphen_split_across_pdf_lines():
    page = "expenses increased by 33.4% year-\nover-year to RMB9.0 billion"
    excerpt = "expenses increased by 33.4% year-over-year to RMB9.0 billion"

    assert verify_excerpt(page, excerpt) is True


def test_verify_excerpt_rejects_claim_not_present_on_page():
    page = "Total revenue reached RMB99.1 billion."

    assert verify_excerpt(page, "Adjusted net profit doubled year-over-year.") is False
