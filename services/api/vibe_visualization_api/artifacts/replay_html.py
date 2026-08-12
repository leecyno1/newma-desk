from html import escape

from vibe_visualization_api.artifacts.archify import inject_newma_theme_adapter
from vibe_visualization_api.artifacts.models import ReplayArtifactCreate


REPLAY_THEME_STYLES = r"""
  <style data-newma-replay-theme-adapter>
    html[data-newma-theme] body {
      color: var(--vibe-text);
      background: var(--vibe-bg);
    }
    html[data-newma-theme] .meta,
    html[data-newma-theme] dt { color: var(--vibe-text-muted); }
    html[data-newma-theme] .notice {
      color: var(--vibe-warning);
      background: color-mix(in srgb, var(--vibe-warning) 10%, var(--vibe-surface));
      border-color: color-mix(in srgb, var(--vibe-warning) 48%, var(--vibe-border));
    }
    html[data-newma-theme] dl div {
      background: var(--vibe-surface);
      border-color: var(--vibe-border);
    }
    html[data-newma-theme] th,
    html[data-newma-theme] td { border-color: var(--vibe-border); }
    html[data-newma-theme] th { color: var(--vibe-text-muted); }
    html[data-newma-theme] .notes { color: var(--vibe-text-soft); }
  </style>
"""


def inject_newma_replay_theme_adapter(html: str) -> str:
    """Apply the shared artifact theme runtime plus replay-specific semantics."""
    if "data-newma-replay-theme-adapter" in html:
        return html
    themed = inject_newma_theme_adapter(html)
    marker = "</head>"
    index = themed.lower().find(marker)
    if index < 0:
        raise ValueError("replay artifact HTML does not contain a head element")
    return f"{themed[:index]}{REPLAY_THEME_STYLES}{themed[index:]}"


def render_replay_html(spec: ReplayArtifactCreate) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{escape(order.side.upper())}</td>"
        f"<td>{order.index}</td>"
        f"<td>{order.timestamp}</td>"
        f"<td>{order.price:.4f}</td>"
        "</tr>"
        for order in spec.orders
    ) or '<tr><td colspan="4">暂无模拟决策</td></tr>'
    metrics = "".join(
        f"<div><dt>{escape(str(key))}</dt><dd>{escape(str(value))}</dd></div>"
        for key, value in spec.metrics.items()
    )
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#f4efe3">
<title>{escape(spec.title)}</title><style>
:root{{color-scheme:light;font-family:"Manrope","Avenir Next","PingFang SC",sans-serif}}
body{{max-width:960px;margin:0 auto;padding:32px;color:var(--vibe-text,#173128);background:var(--vibe-bg,#f4efe3)}}h1{{font-size:24px;margin:0 0 6px}}
.meta{{color:var(--vibe-text-muted,#66766e);font-size:13px}}.notice{{padding:10px 12px;border:1px solid color-mix(in srgb,var(--vibe-warning,#a16207) 48%,var(--vibe-border,#d8cdbb));border-radius:8px;background:color-mix(in srgb,var(--vibe-warning,#a16207) 10%,var(--vibe-surface,#fbf7ef));color:var(--vibe-warning,#a16207);font-size:13px}}dl{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:8px;margin:24px 0}}
dl div{{padding:12px;border:1px solid var(--vibe-border,#d8cdbb);border-radius:8px;background:var(--vibe-surface,#fbf7ef)}}dt{{color:var(--vibe-text-muted,#66766e);font-size:12px}}dd{{margin:4px 0 0;font-weight:700}}
table{{width:100%;border-collapse:collapse;font-size:13px}}th,td{{padding:9px;border-bottom:1px solid var(--vibe-border,#d8cdbb);text-align:left}}th{{color:var(--vibe-text-muted,#66766e)}}
.notes{{margin-top:24px;white-space:pre-wrap;color:var(--vibe-text-soft,#3f5c51)}}
</style></head><body><h1>{escape(spec.title)}</h1>
<p class="meta">{escape(spec.security.market)} · {escape(spec.security.name)} ({escape(spec.security.symbol)}) · {escape(spec.timeframe)} · 回放 {spec.cursor}/{spec.total_bars}</p>
<p class="notice">仅用于模拟训练与复盘，不连接真实交易执行。</p>
<dl>{metrics}</dl><h2>模拟决策</h2><table><thead><tr><th>方向</th><th>位置</th><th>时间戳</th><th>价格</th></tr></thead><tbody>{rows}</tbody></table>
<div class="notes">{escape(spec.notes)}</div></body></html>"""
