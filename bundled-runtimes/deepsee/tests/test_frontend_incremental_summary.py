from pathlib import Path


def test_message_overlay_uses_incremental_derive_without_force():
    html = Path("static/index.html").read_text(encoding="utf-8")
    start = html.index("async function deriveAndOverlayForLoadedRows")
    block = html[start: html.index("// 等待完成", start)]
    assert "message_ids: ids, force: false" in block
    assert "message_ids: ids, force: true" not in block


def test_wechat_auto_derive_threshold_matches_backend():
    html = Path("static/index.html").read_text(encoding="utf-8")
    assert "const AI_MIN_CHARS = 20" in html
    assert "const AI_MIN_CHARS = 50" not in html
