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


def _run_cleanup(samples: list[str]) -> list[str]:
    source = INDEX_HTML.read_text(encoding="utf-8")
    js = "\n\n".join(
        [
            _extract_function(source, "cleanSummaryTableCellText"),
            f"""
const samples = {json.dumps(samples, ensure_ascii=False)};
const outputs = samples.map((item) => cleanSummaryTableCellText(item));
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


def test_table_cleanup_strips_ai_prefix():
    outputs = _run_cleanup(["ai: 时间：2026-04-03 09:19。本次会议围绕房地产展开讨论。"])
    assert outputs == ["时间：2026-04-03 09:19。本次会议围绕房地产展开讨论。"]


def test_table_cleanup_strips_fallback_prefix_and_blank_lines():
    outputs = _run_cleanup(["\n fallback: 这是兜底摘要 \n"])
    assert outputs == ["这是兜底摘要"]

