#!/usr/bin/env python3
"""动态图表生成器：chart_data.json → 竖屏 HTML 动画图表（视频段用）。

用法：
    python scripts/build_animated_charts.py --chart-data <chart_data.json> [--chart-id T06-debt-milestones] [--out-dir <dir>]

输出：
    <chart_id>.html  —— 竖屏 1080×1920 动画图表（黄黑主调，与视频风格一致）
    动画类型：grow（柱生长）/ draw（线绘制）/ count_up（数字滚动）/ progressive（逐条出现）

渲染为视频段（配合现有 html-anything 视频桥）：
    Chrome Headless 逐帧截图或 --screenshot 模式直接出 PNG。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

HTML_TMPL = """<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<title>{title}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ width: {width}px; height: {height}px; background: #FFD93B; font-family: -apple-system, "PingFang SC", sans-serif; overflow: hidden; position: relative; }}
.paper-tex {{ position: absolute; inset: 0; opacity: 0.06; background-image: repeating-linear-gradient(0deg, transparent 0 38px, #222 38px 39px), repeating-linear-gradient(90deg, transparent 0 60px, #222 60px 62px); }}
.header {{ position: absolute; top: 160px; left: 0; right: 0; text-align: center; }}
.title {{ font-size: 72px; font-weight: 800; color: #1a1a1a; letter-spacing: 2px; }}
.subtitle {{ font-size: 34px; color: #555; margin-top: 22px; }}
.chart {{ position: absolute; top: 460px; left: 90px; right: 90px; bottom: 560px; display: flex; align-items: flex-end; justify-content: space-around; }}
{chart_css}
.anno {{ position: absolute; bottom: 300px; left: 90px; right: 90px; text-align: center; }}
.anno-pill {{ display: inline-block; font-size: 40px; font-weight: 700; color: #fff; background: #1a1a1a; padding: 18px 44px; border-radius: 60px; opacity: 0; animation: fadeUp 0.7s ease forwards; animation-delay: {anno_delay}s; }}
.anno-pill.red {{ background: #C0392B; }}
.source {{ position: absolute; bottom: 130px; left: 90px; right: 90px; text-align: center; font-size: 26px; color: #777; }}
@keyframes fadeUp {{ from {{ opacity: 0; transform: translateY(30px); }} to {{ opacity: 1; transform: none; }} }}
@keyframes growUp {{ from {{ height: 0; }} }}
</style></head><body>
<div class="paper-tex"></div>
<div class="header"><div class="title">{title}</div><div class="subtitle">{subtitle}</div></div>
<div class="chart">{chart_body}</div>
<div class="anno"><span class="anno-pill {anno_class}">{anno_text}</span></div>
<div class="source">数据来源：{source}</div>
</body></html>"""


def build_bar_html(chart: dict) -> tuple[str, str]:
    vals = chart["y_axis"]["values"]
    xs = [str(x) for x in chart["x_axis"]["values"]]
    labels = chart.get("data_labels") or [f"{v:g}" for v in vals]
    vmax = max(abs(v) for v in vals) or 1
    has_neg = any(v < 0 for v in vals)
    bars, ticks = [], []
    for i, (x, v, lab) in enumerate(zip(xs, vals, labels)):
        h = abs(v) / vmax * 100
        delay = 0.15 * i
        color = "#C0392B" if v < 0 else "#1a1a1a"
        anim = f"height: {h:.0f}%; animation: growUp 0.9s cubic-bezier(.2,.8,.2,1) {delay}s backwards;"
        if has_neg:
            bars.append(
                f'<div style="display:flex;flex-direction:column;align-items:center;justify-content:flex-end;width:130px;height:100%;">'
                f'<div style="color:{color};font-size:44px;font-weight:800;margin-bottom:12px;opacity:0;animation:fadeUp .5s {delay + 0.7}s forwards;">{lab}</div>'
                f'<div style="width:130px;{anim}background:{color};border-radius:10px 10px 0 0;"></div></div>'
                if v >= 0 else
                f'<div style="display:flex;flex-direction:column;align-items:center;justify-content:flex-start;width:130px;height:100%;">'
                f'<div style="width:130px;animation:growUp 0.9s cubic-bezier(.2,.8,.2,1) {delay}s backwards;height:{h:.0f}%;background:{color};border-radius:0 0 10px 10px;"></div>'
                f'<div style="color:{color};font-size:44px;font-weight:800;margin-top:12px;opacity:0;animation:fadeUp .5s {delay + 0.7}s forwards;">{lab}</div></div>'
            )
        else:
            bars.append(
                f'<div style="display:flex;flex-direction:column;align-items:center;justify-content:flex-end;width:130px;height:100%;">'
                f'<div style="color:{color};font-size:48px;font-weight:800;margin-bottom:14px;opacity:0;animation:fadeUp .5s {delay + 0.7}s forwards;">{lab}</div>'
                f'<div style="width:130px;{anim}background:{color};border-radius:12px 12px 0 0;"></div></div>'
            )
        ticks.append(f'<div style="font-size:38px;color:#333;margin-top:16px;">{x}</div>')
    body = "".join(bars)
    css = ".bar-col{display:flex;flex-direction:column;align-items:center;justify-content:flex-end;width:150px;height:100%;}"
    return body, css


def build_line_html(chart: dict) -> tuple[str, str]:
    vals = chart["y_axis"]["values"]
    xs = [str(x) for x in chart["x_axis"]["values"]]
    vmin, vmax = min(vals), max(vals)
    rng = (vmax - vmin) or 1
    W, H, PAD = 900, 720, 60
    pts = [(PAD + i * (W - 2 * PAD) / (len(vals) - 1), H - PAD - (v - vmin) / rng * (H - 2 * PAD)) for i, v in enumerate(vals)]
    path = "M " + " L ".join(f"{x:.0f} {y:.0f}" for x, y in pts)
    dots = "".join(
        f'<circle cx="{x:.0f}" cy="{y:.0f}" r="14" fill="#1a1a1a" opacity="0" style="animation:fadeUp .4s {0.3 + 0.28 * i}s forwards;"/>'
        for i, (x, y) in enumerate(pts)
    )
    labels = "".join(
        f'<text x="{x:.0f}" y="{H - 12}" text-anchor="middle" font-size="34" fill="#333">{xv}</text>'
        for (x, _), xv in zip(pts, xs)
    )
    vlabels = "".join(
        f'<text x="{x:.0f}" y="{y - 26:.0f}" text-anchor="middle" font-size="38" font-weight="700" fill="{"#C0392B" if i == len(vals)-1 else "#1a1a1a"}" opacity="0" style="animation:fadeUp .4s {0.5 + 0.28 * i}s forwards;">{v:g}</text>'
        for i, ((x, y), v) in enumerate(zip(pts, vals))
    )
    body = (
        f'<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
        f'<line x1="{PAD}" y1="{H - PAD}" x2="{W - PAD}" y2="{H - PAD}" stroke="#333" stroke-width="3"/>'
        f'<path d="{path}" stroke="#1a1a1a" stroke-width="9" fill="none" stroke-linecap="round" stroke-linejoin="round" '
        f'style="stroke-dasharray:2600;stroke-dashoffset:2600;animation:dash 2.2s ease-out forwards;"/>'
        f'{dots}{labels}{vlabels}</svg>'
        f'<style>@keyframes dash{{to{{stroke-dashoffset:0;}}}}</style>'
    )
    css = ".chart{align-items:center;}"
    return body, css


def main() -> int:
    parser = argparse.ArgumentParser(description="Build animated HTML charts from chart_data.json")
    parser.add_argument("--chart-data", required=True)
    parser.add_argument("--chart-id", help="只生成指定 chart_id（缺省全部）")
    parser.add_argument("--out-dir", help="输出目录（默认 chart_data.json 同目录 animated_charts/）")
    parser.add_argument("--aspect", choices=["portrait-9x16", "landscape-16x9", "square-1x1"],
                        help="画幅（缺省读 chart.orientation；模板 presets 见 configs/workflow/video_template_registry.json chart_aspect_presets）")
    args = parser.parse_args()

    doc = json.loads(Path(args.chart_data).read_text(encoding="utf-8"))
    out_dir = Path(args.out_dir).expanduser().resolve() if args.out_dir else Path(args.chart_data).parent / "animated_charts"
    out_dir.mkdir(parents=True, exist_ok=True)

    presets = {"portrait-9x16": (1080, 1920), "landscape-16x9": (1920, 1080), "square-1x1": (1080, 1080)}
    for chart in doc.get("charts", []):
        if args.chart_id and chart["chart_id"] != args.chart_id:
            continue
        # 画幅：命令行 > chart.orientation > 默认竖屏（历史行为）
        aspect = args.aspect
        if not aspect:
            aspect = "portrait-9x16" if chart.get("orientation", "portrait") == "portrait" else "landscape-16x9"
        width, height = presets[aspect]
        ctype = chart.get("chart_type", "bar")
        body, css = build_line_html(chart) if ctype == "line" else build_bar_html(chart)
        annos = chart.get("annotations") or []
        anno_text = annos[-1]["label"] if annos else chart.get("notes", "")
        anno_class = "red" if annos and annos[-1].get("emphasis") else ""
        anno_delay = 2.4 if ctype == "line" else 0.15 * len(chart["y_axis"]["values"]) + 1.0
        html = HTML_TMPL.format(
            width=width, height=height,
            title=chart["title"], subtitle=chart.get("subtitle", ""),
            chart_body=body, chart_css=css,
            anno_text=anno_text, anno_class=anno_class,
            anno_delay=f"{anno_delay:.1f}",
            source=chart.get("source", ""),
        )
        out = out_dir / f"{chart['chart_id']}.html"
        out.write_text(html, encoding="utf-8")
        print(f"[{chart['chart_id']}] → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
