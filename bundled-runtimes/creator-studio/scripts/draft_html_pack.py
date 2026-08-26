#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import os
import re
from pathlib import Path
from urllib import request as urllib_request


ROOT = Path(__file__).resolve().parents[1]
CHARTJS_URL = "https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"


def read_text(path: Path) -> str:
    return path.expanduser().resolve().read_text(encoding="utf-8", errors="replace")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def load_chart_js(chartjs_file: str | None = None, *, required: bool = False) -> str:
    candidates = []
    if chartjs_file:
        candidates.append(Path(chartjs_file).expanduser())
    candidates.extend(
        [
            ROOT / "vendor/chart.umd.min.js",
            ROOT / "assets/vendor/chart.umd.min.js",
            Path(os.environ.get("HTML_ANYTHING_ROOT", str(ROOT / "vendor/reserved/render/html-anything"))).expanduser()
            / "next/node_modules/chart.js/dist/chart.umd.min.js",
            Path(os.environ.get("HTML_ANYTHING_ROOT", str(ROOT / "vendor/reserved/render/html-anything"))).expanduser()
            / "node_modules/chart.js/dist/chart.umd.min.js",
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate.read_text(encoding="utf-8", errors="replace")
    if not required:
        return ""
    with urllib_request.urlopen(CHARTJS_URL, timeout=20) as response:
        return response.read().decode("utf-8", errors="replace")


def strip_external_css_imports(css: str) -> str:
    return re.sub(r"@import\s+url\([^)]+\);\s*", "", css, flags=re.I)


def ensure_head_injection(html_text: str, injection: str) -> str:
    if "</head>" in html_text:
        return html_text.replace("</head>", injection + "\n</head>", 1)
    return injection + "\n" + html_text


def has_chart_usage(html_text: str) -> bool:
    return bool(re.search(r"<canvas\b|new\s+Chart\s*\(|Chart\.register|chart\.umd", html_text, flags=re.I))


def inline_chartjs(html_text: str, chartjs_file: str | None = None) -> str:
    chart_required = has_chart_usage(html_text)
    chart_script_pattern = r"<script\b[^>]*src=[\"'][^\"']*chart[^\"']*\.js[^\"']*[\"'][^>]*>\s*</script>"
    external_chart = re.search(chart_script_pattern, html_text, flags=re.I)
    if not chart_required and not external_chart:
        return html_text
    html_text = re.sub(
        chart_script_pattern + r"\s*",
        "",
        html_text,
        flags=re.I,
    )
    if "Chart.js v4.4.4" in html_text and "function(t,e)" in html_text:
        return html_text
    chart_js = load_chart_js(chartjs_file, required=True)
    script = f"<script>/* Chart.js v4.4.4 - Inlined by Newma Draft */\n{chart_js}\n</script>"
    return ensure_head_injection(html_text, script)


def normalize_chart_runtime(html_text: str) -> str:
    html_text = re.sub(r"(responsive\s*:\s*)true\b", r"\1false", html_text, flags=re.I)
    html_text = re.sub(r"(type\s*:\s*['\"])log(['\"])", r"\1logarithmic\2", html_text, flags=re.I)
    return html_text


def ensure_canvas_dimensions(html_text: str, *, width: int = 700, height: int = 350) -> str:
    def repl(match: re.Match[str]) -> str:
        tag = match.group(0)
        if not re.search(r"\bwidth\s*=", tag, flags=re.I):
            tag = tag[:-1] + f' width="{width}">'
        if not re.search(r"\bheight\s*=", tag, flags=re.I):
            tag = tag[:-1] + f' height="{height}">'
        return tag

    return re.sub(r"<canvas\b[^>]*>", repl, html_text, flags=re.I)


def add_draft_meta(html_text: str) -> str:
    if "name=\"dasheng-draft-html\"" in html_text:
        return html_text
    return ensure_head_injection(html_text, '<meta name="dasheng-draft-html" content="v1">')


def add_editing_contract(html_text: str) -> str:
    css = """
<style id="dasheng-draft-html-contract">
.dasheng-edit-bar{position:fixed;z-index:99999;top:12px;right:12px;display:flex;gap:8px;padding:8px 10px;border:1px solid #d7dce5;border-radius:999px;background:#111827;color:#fff;box-shadow:0 8px 24px rgba(15,23,42,.18);font-size:13px}
.dasheng-edit-bar button{border:0;border-radius:999px;padding:6px 10px;background:#fff;color:#111827;cursor:pointer}
.dasheng-edit-bar button:hover{background:#e5efff}
[contenteditable="true"]{outline:2px dashed transparent;outline-offset:6px}
.dasheng-editing [contenteditable="true"]{outline-color:#1a6fb5;background:rgba(26,111,181,.035)}
.dasheng-disclaimer{margin:40px auto 0;padding:16px 18px;border-top:1px solid #d7dce5;color:#667085;font-size:13px;line-height:1.8}
.dasheng-chart-fallback{padding:12px 14px;border:1px solid #e3e7ee;border-radius:12px;background:#f8fafc;color:#475467;font-size:13px}
</style>
"""
    js = """
<script id="dasheng-draft-html-runtime">
document.addEventListener('DOMContentLoaded',function(){
  var root=document.querySelector('[data-dasheng-edit-root]')||document.querySelector('[contenteditable="true"]')||document.body;
  if(root && !root.getAttribute('contenteditable')){root.setAttribute('contenteditable','true');}
  var bar=document.querySelector('.dasheng-edit-bar')||document.querySelector('.edit-bar');
  if(!bar){
    bar=document.createElement('div');
    bar.className='dasheng-edit-bar';
    bar.innerHTML='<button type="button" data-action="toggle">编辑/预览</button><button type="button" data-action="select">全选</button><button type="button" data-action="save">保存HTML</button>';
    document.body.appendChild(bar);
  }
  bar.addEventListener('click',function(e){
    var t=e.target;
    if(!t || !t.getAttribute){return;}
    var action=t.getAttribute('data-action');
    if(action==='toggle'){
      document.body.classList.toggle('dasheng-editing');
      if(root){root.setAttribute('contenteditable',document.body.classList.contains('dasheng-editing')?'true':'false');}
    }
    if(action==='select'){
      var range=document.createRange();
      range.selectNodeContents(root||document.body);
      var sel=window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
    }
    if(action==='save'){
      var blob=new Blob(['<!DOCTYPE html>\\n'+document.documentElement.outerHTML],{type:'text/html;charset=utf-8'});
      var a=document.createElement('a');
      a.href=URL.createObjectURL(blob);
      a.download=(document.title||'dasheng-draft')+'.html';
      a.click();
      setTimeout(function(){URL.revokeObjectURL(a.href);},1200);
    }
  });
  if(typeof Chart==='undefined'){
    var canvases=document.querySelectorAll('canvas');
    for(var i=0;i<canvases.length;i++){
      var note=document.createElement('div');
      note.className='dasheng-chart-fallback';
      note.textContent='图表库未加载，发布前请截图或重新生成图表。';
      canvases[i].insertAdjacentElement('afterend',note);
    }
  }
});
</script>
"""
    if "dasheng-draft-html-contract" not in html_text:
        html_text = ensure_head_injection(html_text, css)
    if "dasheng-draft-html-runtime" not in html_text:
        html_text = html_text.replace("</body>", js + "\n</body>", 1) if "</body>" in html_text else html_text + js
    return html_text


def ensure_contenteditable_root(html_text: str) -> str:
    if "contenteditable=\"true\"" in html_text or "contenteditable='true'" in html_text:
        return html_text
    for pattern in [
        r"(<main\b[^>]*)(>)",
        r"(<article\b[^>]*)(>)",
        r"(<section\b[^>]*class=[\"'][^\"']*container[^\"']*[\"'][^>]*)(>)",
        r"(<div\b[^>]*class=[\"'][^\"']*container[^\"']*[\"'][^>]*)(>)",
    ]:
        if re.search(pattern, html_text, flags=re.I):
            return re.sub(pattern, r'\1 data-dasheng-edit-root="true" contenteditable="true"\2', html_text, count=1, flags=re.I)
    return re.sub(r"(<body\b[^>]*)(>)", r'\1 data-dasheng-edit-root="true" contenteditable="true"\2', html_text, count=1, flags=re.I)


def ensure_disclaimer(html_text: str) -> str:
    if "免责声明" in html_text:
        return html_text
    block = (
        '<section class="dasheng-disclaimer">'
        '<strong>免责声明：</strong>本文仅为信息整理与研究讨论，不构成投资、交易或购房建议。'
        '文中数据、图表与判断请以官方披露、交易所公告和权威机构最新信息为准。'
        '</section>'
    )
    if "</body>" in html_text:
        return html_text.replace("</body>", block + "\n</body>", 1)
    return html_text + block


def normalize_sample_html(source: Path, output: Path, chartjs_file: str | None = None) -> Path:
    text = read_text(source)
    text = re.sub(r"@import\s+url\([^)]+\);\s*", "", text, flags=re.I)
    text = normalize_chart_runtime(text)
    text = ensure_canvas_dimensions(text)
    text = inline_chartjs(text, chartjs_file)
    text = add_draft_meta(text)
    text = ensure_contenteditable_root(text)
    text = ensure_disclaimer(text)
    text = add_editing_contract(text)
    write_text(output, text)
    return output


def markdown_to_html(md: str) -> str:
    lines = md.splitlines()
    out: list[str] = []
    table_buffer: list[str] = []

    def flush_table() -> None:
        nonlocal table_buffer
        if len(table_buffer) < 2:
            for row in table_buffer:
                out.append(f"<p>{html.escape(row)}</p>")
            table_buffer = []
            return
        headers = [item.strip() for item in table_buffer[0].strip("|").split("|")]
        body_rows = table_buffer[2:]
        out.append("<table><thead><tr>" + "".join(f"<th>{html.escape(h)}</th>" for h in headers) + "</tr></thead><tbody>")
        for row in body_rows:
            cells = [item.strip() for item in row.strip("|").split("|")]
            out.append("<tr>" + "".join(f"<td><span>{html.escape(c)}</span></td>" for c in cells) + "</tr>")
        out.append("</tbody></table>")
        table_buffer = []

    for raw in lines:
        line = raw.rstrip()
        if "|" in line and line.strip().startswith("|"):
            table_buffer.append(line)
            continue
        if table_buffer:
            flush_table()
        if not line:
            continue
        if line.startswith("# "):
            out.append(f"<h1>{html.escape(line[2:].strip())}</h1>")
        elif line.startswith("## "):
            out.append(f"<h2>{html.escape(line[3:].strip())}</h2>")
        elif line.startswith("### "):
            out.append(f"<h3>{html.escape(line[4:].strip())}</h3>")
        elif line.startswith("- "):
            out.append(f"<p class=\"bullet\">• {html.escape(line[2:].strip())}</p>")
        else:
            out.append(f"<p>{html.escape(line)}</p>")
    if table_buffer:
        flush_table()
    return "\n".join(out)


def image_specs_to_blocks(image_specs: list[dict] | None) -> list[str]:
    blocks: list[str] = []
    for index, spec in enumerate(image_specs or [], start=1):
        src = str(spec.get("data_uri") or spec.get("src") or "").strip()
        if not src:
            continue
        title = html.escape(str(spec.get("title") or f"配图 {index}"))
        caption = html.escape(str(spec.get("caption") or spec.get("source") or ""))
        alt = html.escape(str(spec.get("alt") or title))
        source_url = str(spec.get("source_url") or "").strip()
        source_html = f' <a href="{html.escape(source_url)}">来源</a>' if source_url else ""
        blocks.append(
            '<figure class="article-image">'
            f'<img src="{html.escape(src)}" alt="{alt}">'
            f'<figcaption><strong>{title}</strong>'
            + (f'｜{caption}' if caption else "")
            + source_html
            + '</figcaption></figure>'
        )
    return blocks


def image_specs_to_html(image_specs: list[dict] | None) -> str:
    return "\n".join(image_specs_to_blocks(image_specs))


def chart_specs_to_blocks(chart_specs: list[dict] | None) -> tuple[list[str], str]:
    chart_specs = chart_specs or []
    if not chart_specs:
        return [], ""
    sections: list[str] = []
    configs: list[dict] = []
    for index, raw in enumerate(chart_specs, start=1):
        chart_id = re.sub(r"[^0-9A-Za-z_-]+", "-", str(raw.get("id") or f"chart-{index}")).strip("-")
        if not chart_id:
            chart_id = f"chart-{index}"
        title = str(raw.get("title") or f"图表 {index}")
        caption = str(raw.get("caption") or raw.get("source") or "")
        source_url = str(raw.get("source_url") or "").strip()
        width = int(raw.get("width") or 700)
        height = int(raw.get("height") or 350)
        datasets = raw.get("datasets") or []
        if not isinstance(datasets, list) or not datasets:
            continue
        options = raw.get("options") or {}
        if not isinstance(options, dict):
            options = {}
        config = {
            "type": raw.get("type") or "bar",
            "data": {
                "labels": raw.get("labels") or [],
                "datasets": datasets,
            },
            "options": options,
        }
        config["options"].setdefault("plugins", {})
        config["options"]["plugins"].setdefault("title", {"display": True, "text": title})
        config["options"]["responsive"] = False
        config["options"].setdefault("maintainAspectRatio", False)
        configs.append({"id": chart_id, "config": config})
        source_html = f' <a href="{html.escape(source_url)}">来源</a>' if source_url else ""
        sections.append(
            '<section class="chart-card">'
            f'<h2>{html.escape(title)}</h2>'
            f'<canvas id="{html.escape(chart_id)}" width="{width}" height="{height}"></canvas>'
            f'<p class="chart-caption">{html.escape(caption)}{source_html}</p>'
            '</section>'
        )
    config_json = json.dumps(configs, ensure_ascii=False)
    script = f"""
<script id="dasheng-draft-chart-runtime">
document.addEventListener('DOMContentLoaded',function(){{
  if(typeof Chart==='undefined'){{return;}}
  function deepMerge(a,b){{for(var k in b){{if(a[k]&&typeof a[k]==='object'&&typeof b[k]==='object'&&!Array.isArray(a[k])&&!Array.isArray(b[k])){{deepMerge(a[k],b[k]);}}else{{a[k]=b[k];}}}}return a;}}
  var base={{options:{{responsive:false,maintainAspectRatio:false,plugins:{{legend:{{labels:{{font:{{size:11}}}}}}}}}}}};
  var charts={config_json};
  for(var i=0;i<charts.length;i++){{
    var item=charts[i];
    var node=document.getElementById(item.id);
    if(!node){{continue;}}
    var cfg=deepMerge(JSON.parse(JSON.stringify(base)),item.config);
    new Chart(node,cfg);
  }}
}});
</script>
"""
    return sections, script


def chart_specs_to_html(chart_specs: list[dict] | None) -> str:
    sections, script = chart_specs_to_blocks(chart_specs)
    return "\n".join(sections) + script


def place_asset_blocks(body_html: str, asset_blocks: list[str]) -> str:
    if not asset_blocks:
        return body_html
    remaining = list(asset_blocks)

    def after_h2(match: re.Match[str]) -> str:
        if not remaining:
            return match.group(0)
        return match.group(0) + "\n" + remaining.pop(0)

    text = re.sub(r"<h2\b[^>]*>.*?</h2>", after_h2, body_html, count=len(remaining), flags=re.I | re.S)
    if not remaining:
        return text
    tail = "\n".join(remaining)
    ref_match = re.search(r"<h2\b[^>]*>引用与待补源</h2>", text)
    if ref_match:
        return text[: ref_match.start()] + tail + "\n" + text[ref_match.start() :]
    return text + "\n" + tail


def build_html_from_markdown(
    *,
    markdown_text: str,
    title: str,
    chart_needs: list[str] | None = None,
    visual_needs: list[str] | None = None,
    chart_specs: list[dict] | None = None,
    image_specs: list[dict] | None = None,
    chartjs_file: str | None = None,
) -> str:
    chart_needs = chart_needs or []
    visual_needs = visual_needs or []
    body_html = markdown_to_html(markdown_text)
    image_blocks = image_specs_to_blocks(image_specs)
    chart_blocks, chart_runtime = chart_specs_to_blocks(chart_specs)
    body_html = place_asset_blocks(body_html, image_blocks + chart_blocks)
    css = """
<style>
:root{--bg:#fafafa;--paper:#fff;--text:#1a1a2e;--muted:#667085;--red:#c41230;--blue:#1a6fb5;--border:#d7dce5}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:"Noto Serif SC","Noto Sans SC","PingFang SC",serif;line-height:1.85;font-size:16px}
.page{max-width:860px;margin:0 auto;padding:56px 28px 84px;background:var(--paper)}h1{font-size:34px;line-height:1.25;margin:24px 0 28px;color:var(--text)}h2{margin:36px 0 14px;padding-left:14px;border-left:5px solid var(--red);font-size:24px}h3{margin:26px 0 10px;color:var(--blue);font-size:19px}p{margin:1em 0}table{width:100%;border-collapse:collapse;margin:20px 0;font-size:14px}th,td{border:1px solid var(--border);padding:9px 10px;text-align:left}th{background:#f0f4f8}.bullet{padding-left:1em;color:#344054}.article-image,.chart-card{margin:30px 0;padding:16px;border:1px solid var(--border);background:#fbfaf7}.article-image img{display:block;width:100%;max-width:760px;max-height:520px;object-fit:cover;margin:auto}.article-image figcaption,.chart-caption{margin-top:8px;color:var(--muted);font-size:13px}.chart-card canvas{display:block;margin:10px auto 0;max-width:100%}
</style>
"""
    text = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{html.escape(title)}</title>
<meta name="dasheng-draft-html" content="v1">
{css}
</head>
<body>
<main class="page" data-dasheng-edit-root="true" contenteditable="true">
{body_html}
{chart_runtime}
</main>
</body>
</html>"""
    text = inline_chartjs(text, chartjs_file) if chart_specs else text
    return add_editing_contract(ensure_disclaimer(text))


def write_draft_html_from_markdown(
    markdown_file: Path,
    output: Path,
    *,
    title: str,
    chart_needs: list[str] | None = None,
    visual_needs: list[str] | None = None,
    chart_specs: list[dict] | None = None,
    image_specs: list[dict] | None = None,
    chartjs_file: str | None = None,
) -> Path:
    html_text = build_html_from_markdown(
        markdown_text=read_text(markdown_file),
        title=title,
        chart_needs=chart_needs,
        visual_needs=visual_needs,
        chart_specs=chart_specs,
        image_specs=image_specs,
        chartjs_file=chartjs_file,
    )
    write_text(output, html_text)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Build or normalize Newma draft HTML")
    parser.add_argument("--input-html")
    parser.add_argument("--draft-file")
    parser.add_argument("--output", required=True)
    parser.add_argument("--title")
    parser.add_argument("--chart-need", action="append", default=[])
    parser.add_argument("--visual-need", action="append", default=[])
    parser.add_argument("--chart-specs-file")
    parser.add_argument("--image-specs-file")
    parser.add_argument("--chartjs-file")
    args = parser.parse_args()
    output = Path(args.output).expanduser().resolve()
    if args.input_html:
        normalize_sample_html(Path(args.input_html), output, args.chartjs_file)
    elif args.draft_file:
        title = args.title or Path(args.draft_file).stem
        chart_specs = json.loads(read_text(Path(args.chart_specs_file))) if args.chart_specs_file else None
        image_specs = json.loads(read_text(Path(args.image_specs_file))) if args.image_specs_file else None
        write_draft_html_from_markdown(
            Path(args.draft_file),
            output,
            title=title,
            chart_needs=args.chart_need,
            visual_needs=args.visual_need,
            chart_specs=chart_specs,
            image_specs=image_specs,
            chartjs_file=args.chartjs_file,
        )
    else:
        parser.error("必须提供 --input-html 或 --draft-file")
    print(output)


if __name__ == "__main__":
    main()
