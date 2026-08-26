from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
INDEX_HTML = PROJECT_ROOT / "static" / "index.html"


def test_contact_summary_cell_uses_compact_class():
    source = INDEX_HTML.read_text(encoding="utf-8")

    assert "contact-summary-cell-compact" in source
    assert 'class="contact-summary-cell contact-summary-cell-compact"' in source


def test_contact_scorecard_tables_use_terminal_table_class():
    source = INDEX_HTML.read_text(encoding="utf-8")

    assert "contact-score-table-terminal" in source
    assert 'class="contact-score-table contact-score-table-terminal"' in source


def test_send_panel_has_explicit_split_scroll_constraints():
    source = INDEX_HTML.read_text(encoding="utf-8")

    assert ".send-right .send-table-container" in source
    assert ".send-left { width:" in source
    assert "overflow: hidden;" in source
