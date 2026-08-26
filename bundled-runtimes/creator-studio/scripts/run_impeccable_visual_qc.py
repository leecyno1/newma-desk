#!/usr/bin/env python3
"""impeccable 视觉 QC 适配器（B 级晋级：HTML 分镜/动态图表/标题系统浏览器审计）。

用法：
    python scripts/run_impeccable_visual_qc.py --target <html文件或URL> [--viewport 1080x1920] [--output-dir <dir>]

行为：
1. 调用 vendor/reserved/design/impeccable 的 CLI detect（--json），支持本地 HTML 文件或 URL。
2. 审计报告写入 <output-dir>/impeccable_qc_report.json（默认与目标同级的 qc/ 目录；
   严禁写入 skills/、vendor/ 或仓库配置目录——输出路径受保护）。
3. 摘要打印 failure/advisory 计数；exit code：有 failure 则 1，全过则 0（供 QC 门禁串联）。

定位：视觉 QC 顾问——补足 design-taste-frontend 与 review-animations，不替代二者；
只报告可测量的技术项（对比度/响应式/性能/语义），不做主观设计裁决。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
IMPECCABLE_CLI = PROJECT_ROOT / "vendor" / "reserved" / "design" / "impeccable" / "cli" / "bin" / "cli.js"
FORBIDDEN_OUTPUT_PARTS = {"skills", "vendor", "node_modules", ".git", "configs"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run impeccable visual QC audit on an HTML deliverable or URL.")
    parser.add_argument("--target", required=True, help="HTML file path or http(s) URL to audit.")
    parser.add_argument("--viewport", default="1080x1920", help="Browser viewport for URL scans (default 1080x1920).")
    parser.add_argument("--scope", default=None, help="Optional rule scope filter (type, layout).")
    parser.add_argument("--output-dir", default=None, help="Report output dir (default: <target parent>/qc).")
    return parser.parse_args()


def resolve_output_dir(target: str, output_dir: str | None) -> Path:
    if output_dir:
        out = Path(output_dir).expanduser().resolve()
    elif target.startswith(("http://", "https://")):
        out = PROJECT_ROOT / "tmp" / "impeccable_qc"
    else:
        out = Path(target).expanduser().resolve().parent / "qc"
    parts = set(out.parts)
    if parts & FORBIDDEN_OUTPUT_PARTS:
        raise SystemExit(f"forbidden output dir (protected path): {out}")
    out.mkdir(parents=True, exist_ok=True)
    return out


def main() -> int:
    args = parse_args()
    if not IMPECCABLE_CLI.exists():
        raise SystemExit(f"impeccable CLI missing: {IMPECCABLE_CLI}")

    cmd = ["node", str(IMPECCABLE_CLI), "detect", "--json", "--viewport", args.viewport]
    if args.scope:
        cmd += ["--scope", args.scope]
    cmd.append(args.target)

    proc = subprocess.run(cmd, text=True, capture_output=True, check=False, timeout=180)
    raw = proc.stdout.strip()
    try:
        findings = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        findings = {"parse_error": True, "stdout": raw[-2000:], "stderr": proc.stderr[-1000:]}

    out_dir = resolve_output_dir(args.target, args.output_dir)
    report_path = out_dir / "impeccable_qc_report.json"
    report = {
        "schema_version": "newma.impeccable_qc_report.v1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "target": args.target,
        "viewport": args.viewport,
        "cli_exit_code": proc.returncode,
        "findings": findings,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # findings 为数组（每项含 severity: error|warning|advisory），或对象（含 failures/advisory）
    if isinstance(findings, list):
        fail_count = sum(1 for x in findings if isinstance(x, dict) and x.get("severity") == "error")
        warn_count = sum(1 for x in findings if isinstance(x, dict) and x.get("severity") == "warning")
        adv_count = sum(1 for x in findings if isinstance(x, dict) and x.get("severity") == "advisory")
    elif isinstance(findings, dict):
        failures = findings.get("failures")
        advisory = findings.get("advisory")
        fail_count = len(failures) if isinstance(failures, list) else int(findings.get("failureCount", 0) or 0)
        warn_count = int(findings.get("warningCount", 0) or 0)
        adv_count = len(advisory) if isinstance(advisory, list) else int(findings.get("advisoryCount", 0) or 0)
    else:
        fail_count = warn_count = adv_count = 0
    print(json.dumps({
        "report": str(report_path),
        "target": args.target,
        "errors": fail_count,
        "warnings": warn_count,
        "advisory": adv_count,
        "cli_exit_code": proc.returncode,
    }, ensure_ascii=False, indent=2))
    return 1 if fail_count else 0


if __name__ == "__main__":
    sys.exit(main())
