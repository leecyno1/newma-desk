from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
INDEX_HTML = PROJECT_ROOT / "static" / "index.html"


def test_contact_scorecard_frontend_wires_annual_asset_leaders():
    source = INDEX_HTML.read_text(encoding="utf-8")

    assert "analytics?.annual_asset_leaders" in source
    assert "年度标的领先榜" in source
    assert "average" not in source.lower() or "avg_excess_return" in source
