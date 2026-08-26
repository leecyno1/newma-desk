import json
import os
import re
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


def _run_unwrap_samples(samples: list[object]) -> list[str]:
    source = INDEX_HTML.read_text(encoding="utf-8")
    js = "\n\n".join(
        [
            _extract_function(source, "cleanSummaryRawText"),
            _extract_function(source, "decodeSummaryEscapes"),
            _extract_function(source, "unwrapSummaryMarkdown"),
            f"""
const samples = {json.dumps(samples, ensure_ascii=False)};
const outputs = samples.map((item) => unwrapSummaryMarkdown(item));
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


def test_frontend_unwraps_plain_json_markdown():
    outputs = _run_unwrap_samples(
        ['{"markdown":"# 标题\\\\n- 一\\\\n- 二"}']
    )
    assert outputs == ["# 标题\n- 一\n- 二"]


def test_frontend_unwraps_quoted_markdown_string():
    outputs = _run_unwrap_samples(
        ['"# 标题\\\\n- 一\\\\n- 二"']
    )
    assert outputs == ["# 标题\n- 一\n- 二"]


def test_frontend_unwraps_nested_json_content():
    outputs = _run_unwrap_samples(
        ['{"content":"{\\"markdown\\":\\"## 小节\\\\n内容\\"}"}']
    )
    assert outputs == ["## 小节\n内容"]


def test_frontend_keeps_html_payload_intact():
    outputs = _run_unwrap_samples(
        ['```json\\n{"html":"<table><tr><td>A</td></tr></table>"}\\n```']
    )
    assert outputs == ["<table><tr><td>A</td></tr></table>"]
