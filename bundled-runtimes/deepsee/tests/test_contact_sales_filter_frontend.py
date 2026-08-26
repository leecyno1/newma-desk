from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
INDEX_HTML = PROJECT_ROOT / "static" / "index.html"


def test_contact_management_has_exclude_sales_filter_and_row_flag():
    source = INDEX_HTML.read_text(encoding="utf-8")

    assert 'id="contactExcludeSalesFilter"' in source
    assert 'data-is-sales' in source
    assert 'contactExcludeSalesFilter' in source
    assert 'excludeSales' in source
