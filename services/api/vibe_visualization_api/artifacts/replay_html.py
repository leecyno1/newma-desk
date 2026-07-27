from html import escape

from vibe_visualization_api.artifacts.models import ReplayArtifactCreate


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
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(spec.title)}</title><style>
:root{{color-scheme:light dark;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
body{{max-width:960px;margin:0 auto;padding:32px;color:#0f172a;background:#fff}}h1{{font-size:24px;margin:0 0 6px}}
.meta{{color:#64748b;font-size:13px}}.notice{{padding:10px 12px;border:1px solid #f59e0b;border-radius:8px;background:#fffbeb;color:#92400e;font-size:13px}}dl{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:8px;margin:24px 0}}
dl div{{padding:12px;border:1px solid #e2e8f0;border-radius:8px}}dt{{color:#64748b;font-size:12px}}dd{{margin:4px 0 0;font-weight:700}}
table{{width:100%;border-collapse:collapse;font-size:13px}}th,td{{padding:9px;border-bottom:1px solid #e2e8f0;text-align:left}}
.notes{{margin-top:24px;white-space:pre-wrap;color:#334155}}@media(prefers-color-scheme:dark){{body{{color:#e2e8f0;background:#0f172a}}dl div,th,td{{border-color:#334155}}.meta,dt{{color:#94a3b8}}.notice{{background:#451a03;color:#fde68a;border-color:#b45309}}.notes{{color:#cbd5e1}}}}
</style></head><body><h1>{escape(spec.title)}</h1>
<p class="meta">{escape(spec.security.market)} · {escape(spec.security.name)} ({escape(spec.security.symbol)}) · {escape(spec.timeframe)} · 回放 {spec.cursor}/{spec.total_bars}</p>
<p class="notice">仅用于模拟训练与复盘，不连接真实交易执行。</p>
<dl>{metrics}</dl><h2>模拟决策</h2><table><thead><tr><th>方向</th><th>位置</th><th>时间戳</th><th>价格</th></tr></thead><tbody>{rows}</tbody></table>
<div class="notes">{escape(spec.notes)}</div></body></html>"""
