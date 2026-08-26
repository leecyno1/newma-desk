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


def _run_render(samples: list[str]) -> list[str]:
    source = INDEX_HTML.read_text(encoding="utf-8")
    js = "\n\n".join(
        [
            "const window = {};",
            """
window.marked = {
  setOptions() {},
  parse(input) {
    const lines = String(input || '').split('\\n');
    const out = [];
    let listOpen = false;
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) {
        if (listOpen) {
          out.push('</ul>');
          listOpen = false;
        }
        continue;
      }
      if (trimmed.startsWith('# ')) {
        if (listOpen) {
          out.push('</ul>');
          listOpen = false;
        }
        out.push(`<h1>${trimmed.slice(2)}</h1>`);
        continue;
      }
      if (trimmed.startsWith('## ')) {
        if (listOpen) {
          out.push('</ul>');
          listOpen = false;
        }
        out.push(`<h2>${trimmed.slice(3)}</h2>`);
        continue;
      }
      if (trimmed.startsWith('- ')) {
        if (!listOpen) {
          out.push('<ul>');
          listOpen = true;
        }
        out.push(`<li>${trimmed.slice(2)}</li>`);
        continue;
      }
      if (listOpen) {
        out.push('</ul>');
        listOpen = false;
      }
      out.push(`<p>${trimmed}</p>`);
    }
    if (listOpen) out.push('</ul>');
    return out.join('');
  }
};
            """.strip(),
            _extract_function(source, "escapeHtml"),
            _extract_function(source, "cleanSummaryRawText"),
            _extract_function(source, "decodeSummaryEscapes"),
            _extract_function(source, "unwrapSummaryMarkdown"),
            _extract_function(source, "renderMarkdown"),
            f"""
const samples = {json.dumps(samples, ensure_ascii=False)};
const outputs = samples.map((item) => renderMarkdown(item));
console.log(JSON.stringify(outputs));
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
    return json.loads(proc.stdout)


def test_render_markdown_unwraps_json_and_renders_html():
    [html] = _run_render(['{"markdown":"# 标题\\\\n- 一\\\\n- 二"}'])
    assert "<h1>标题</h1>" in html
    assert "<li>一</li>" in html
    assert '{"markdown"' not in html


def test_render_markdown_keeps_html_payload_raw():
    raw = "<div><h2>测试</h2><p>内容</p></div>"
    [html] = _run_render([raw])
    assert html == raw


def test_render_markdown_unwraps_nested_json_before_render():
    [html] = _run_render(['{"content":"{\\"markdown\\":\\"## 小节\\\\n内容\\"}"}'])
    assert "<h2>小节</h2>" in html
    assert "<p>内容</p>" in html
    assert '\\"markdown\\"' not in html


def test_render_markdown_rewrites_citation_badges():
    [html] = _run_render(["# 标题\n- 说明 (#58292)"])
    assert 'data-msg-id="58292"' in html
    assert 'citation-badge' in html
