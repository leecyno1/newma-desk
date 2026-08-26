import json
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
INDEX_HTML = PROJECT_ROOT / "static" / "index.html"


def _extract_function(source: str, name: str) -> str:
    marker = f"function {name}("
    start = source.find(marker)
    if start < 0:
        raise AssertionError(f"missing function {name}")
    brace_start = source.find("{", start)
    if brace_start < 0:
        raise AssertionError(f"missing body for function {name}")
    depth = 0
    for idx in range(brace_start, len(source)):
        ch = source[idx]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return source[start : idx + 1]
    raise AssertionError(f"unterminated function {name}")


def test_contact_warning_board_has_count_mounts():
    source = INDEX_HTML.read_text(encoding="utf-8")

    assert 'id="contactWarningHighDropCount"' in source
    assert 'id="contactWarningRisingCount"' in source
    assert 'id="contactWarningWeakCount"' in source
    assert 'id="contactWarningWatchingCount"' in source


def test_render_contact_summary_preview_exposes_dense_rows_and_action_hint():
    source = INDEX_HTML.read_text(encoding="utf-8")
    js = "\n\n".join(
        [
            "function escapeHtml(value){ return String(value ?? '').replace(/[&<>\\\"']/g, (m)=>({ '&':'&amp;','<':'&lt;','>':'&gt;','\\\"':'&quot;',\"'\":'&#39;' }[m])); }",
            "function fmtTime(value){ return value ? String(value).slice(0, 16).replace('T', ' ') : ''; }",
            "function formatContactHitRate(value){ const num = Number(value); if (!Number.isFinite(num)) return '—'; const ratio = num > 1 ? (num / 100) : num; return `${(ratio * 100).toFixed(1)}%`; }",
            _extract_function(source, "renderContactSummaryPreview"),
            f"""
const html = renderContactSummaryPreview({json.dumps({
    "top_asset_name": "中际旭创",
    "latest_view_at": "2026-04-17T09:30:00",
    "total_predictions": 11,
    "pending_predictions": 2,
    "accuracy_score": 76,
    "service_value_score": 83,
    "hit_rate_1m": 0.61,
    "hit_rate_3m": 0.74,
    "recommended_action": {"action": "继续重点跟踪"},
    "watch_reason": "近3个月显著改善",
}, ensure_ascii=False)});
console.log(html);
""".strip(),
        ]
    )
    proc = subprocess.run(
        ["node", "-e", js],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    html = proc.stdout

    assert "contact-summary-topline" in html
    assert "contact-summary-bottomline" in html
    assert "继续重点跟踪" in html
    assert "近3个月显著改善" in html
