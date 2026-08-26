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


def test_contact_table_has_compact_action_matrix_class():
    source = INDEX_HTML.read_text(encoding="utf-8")

    assert "contact-actions-matrix" in source
    assert "contact-action-row" in source


def test_render_contact_scorecard_has_dual_column_shell():
    source = INDEX_HTML.read_text(encoding="utf-8")
    script = "\n\n".join(
            [
                "function escapeHtml(v){ return String(v ?? ''); }",
                "function escapeJsAttr(v){ return String(v ?? ''); }",
                "function fmtTime(v){ return String(v || ''); }",
            "function formatContactHitRate(v){ const n = Number(v); if (!Number.isFinite(n)) return '—'; const r = n > 1 ? n / 100 : n; return `${(r * 100).toFixed(1)}%`; }",
            "function formatContactTimestamp(v){ return String(v || ''); }",
            "function formatSignedPercent(v){ const n = Number(v); if (!Number.isFinite(n)) return '—'; return `${n > 0 ? '+' : ''}${(n * 100).toFixed(1)}%`; }",
            "function contactDirectionLabel(v){ return String(v || '—'); }",
            "function contactEventKindLabel(v){ return String(v || '其他'); }",
            "function contactThesisStatusLabel(v){ return String(v || '待验证'); }",
            _extract_function(source, "renderContactSparkline"),
            _extract_function(source, "renderContactMarketCurve"),
            _extract_function(source, "renderContactEventTimeline"),
            _extract_function(source, "renderContactSubScores"),
            _extract_function(source, "contactScoreMatrixRow"),
            _extract_function(source, "renderContactScoreMatrix"),
            _extract_function(source, "renderContactClusterTopics"),
            _extract_function(source, "renderContactActionRecommendation"),
            _extract_function(source, "renderContactHorizonBreakdown"),
            _extract_function(source, "renderContactScorecard"),
            """
const html = renderContactScorecard({
  contact: { id: 'wxid_demo', alias: '张三', rating: 72, focus: true, watch: { enabled: true } },
  score: { final_rating: 72, manual_rating: 68, auto_rating: 75, accuracy_score: 74, service_value_score: 78, sample_size: 12, hit_rate_overall: 0.66, accuracy_by_horizon: { '1m': 0.55, '3m': 0.68, '1y': 0.72 }, score_breakdown: {}, value_breakdown: {}, frequency_penalty: 3 },
  analytics: {
    recommended_action: { action: '继续重点跟踪', reason: '近期改善明显' },
    sub_scores: { recommendation_accuracy: { score: 80, recent_90d_score: 70, recent_90d_samples: 3 } },
    horizon_event_groups: {},
    score_explanation: {
      headline: '综合分 72.0，样本稳定',
      drivers: [{ label: '准确度', value: 74, tone: 'good', detail: '命中率较高' }],
      strengths: ['主线集中'],
      risks: ['待验证较多'],
      next_steps: ['继续重点跟踪']
    }
  },
  market_curves: [
    { asset_name: '紫金矿业', asset_code: '601899', latest_market_date: '2026-07-13', latest_close: 12, data_age_days: 0, is_pending: true, items: [{ date: '2026-01-01', close: 10 }, { date: '2026-07-13', close: 12 }], anchor_points: [{ date: '2026-01-01', direction: 'bullish', label: '看好 ×2', count: 2, samples: ['继续看好'] }] },
    { asset_name: '宁德时代', asset_code: '300750', latest_market_date: '2026-07-13', latest_close: 96, data_age_days: 0, is_pending: false, items: [{ date: '2026-01-01', close: 100 }, { date: '2026-07-13', close: 96 }], anchor_points: [{ date: '2026-02-01', direction: 'bearish', label: '看空', count: 1, samples: ['短期看空'] }] }
  ],
  predictions: [{ source_time: '2026-02-01T09:00:00', asset_name: '紫金矿业', direction: 'bullish', normalized_text: '继续看好紫金矿业', evaluations: [{ horizon_code: '1m', direction_hit: true, excess_return: 0.08, event_score: 82 }] }],
  timeline: []
});
console.log(html);
""".strip(),
        ]
    )
    proc = subprocess.run(
        ["node", "-e", script],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    html = proc.stdout

    assert "contact-scorecard-shell" in html
    assert "contact-scorecard-primary" in html
    assert "contact-scorecard-secondary" in html
    assert "推荐标的价格曲线" in html
    assert "contact-score-trend-chart multi" in html
    assert "contact-score-overview" in html
    assert "综合分" in html
    assert "看好 ×2" in html
    assert "看空" in html
    assert "contact-score-matrix" in html
    assert "评分矩阵" in html
    assert "评分解释" in html
    assert "综合分 72.0" in html
    assert "行情截至 2026-07-13" in html
    assert "最新价 12.00" in html
    assert "待验证" in html
    assert "contact-score-terminal" in html
    assert "观点摘要" in html


def test_contact_scorecard_uses_fold_sections_for_secondary_blocks():
    source = INDEX_HTML.read_text(encoding="utf-8")

    assert "contact-score-fold" in source
    assert "<details class=\"contact-score-fold\"" in source
