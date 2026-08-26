#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

from canonical_workflow import stage_contract_snapshot
from path_config import get_project_root


ROOT = get_project_root()
RUNS_ROOT = ROOT / "skills" / "dasheng-daily-shared" / "runtime-data" / "runs"
LIVE_SCRIPT = ROOT / "skills" / "dasheng-daily-shared" / "runtime" / "feishu-live.js"
PLAN_SCRIPT = ROOT / "skills" / "dasheng-daily-shared" / "runtime" / "feishu-plan.js"


def list_runs() -> list[Path]:
    if not RUNS_ROOT.exists():
        return []
    candidates = [item for item in RUNS_ROOT.iterdir() if item.is_dir()]
    return sorted(candidates, key=lambda item: item.stat().st_mtime, reverse=True)


def pick_run(run_id: str | None, latest: bool) -> str:
    if run_id:
        return run_id
    if latest:
        runs = list_runs()
        if not runs:
            raise SystemExit("未找到可用 run 目录")
        return runs[0].name
    raise SystemExit("请提供 run_id，或使用 --latest")


def extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if not text:
        raise ValueError("命令未返回内容")
    decoder = json.JSONDecoder()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        lines = text.splitlines()
        for index, line in enumerate(lines):
            if not line.strip().startswith("{"):
                continue
            candidate = "\n".join(lines[index:])
            try:
                parsed, _ = decoder.raw_decode(candidate)
                return parsed
            except json.JSONDecodeError:
                continue
        raise


def run_node(script: Path, run_id: str) -> dict[str, Any]:
    return run_node_with_args(script, run_id, [])


def run_node_with_args(script: Path, run_id: str, extra_args: list[str]) -> dict[str, Any]:
    proc = subprocess.run(
        ["node", str(script), run_id, *extra_args],
        capture_output=True,
        text=True,
        check=False,
    )
    payload = proc.stdout if proc.stdout.strip() else proc.stderr
    if proc.returncode != 0 and not payload.strip():
        raise SystemExit(f"命令失败，无输出：{script}")
    try:
        data = extract_json(payload)
    except Exception as exc:
        if script == LIVE_SCRIPT:
            bridge_dir = get_bridge_dir(run_id)
            execution_log_file = bridge_dir / "live-execution.json"
            if execution_log_file.exists():
                data = json.loads(execution_log_file.read_text(encoding="utf-8"))
                data["execution_log_file"] = str(execution_log_file)
                data["manifest_file"] = str(RUNS_ROOT / run_id / "run_manifest.json")
                data["finalized_actions_file"] = data.get("finalized_actions_file") or str(bridge_dir / "finalized-actions.json")
            else:
                raise SystemExit(f"无法解析命令输出：{script}\n{exc}\n---\n{payload[:2000]}") from exc
        else:
            raise SystemExit(f"无法解析命令输出：{script}\n{exc}\n---\n{payload[:2000]}") from exc
    data["_meta"] = {
        "returncode": proc.returncode,
        "stderr": proc.stderr.strip(),
        "stdout_prefix": proc.stdout[:500],
    }
    return data


def summarize_live(data: dict[str, Any]) -> dict[str, Any]:
    actions = data.get("actions", [])
    counter = Counter(action.get("status", "unknown") for action in actions)
    completed_urls = {
        action["key"]: action.get("result", {}).get("url")
        for action in actions
        if action.get("status") == "completed" and isinstance(action.get("result"), dict) and action.get("result", {}).get("url")
    }
    blocked = []
    for action in actions:
        if action.get("status") == "completed":
            continue
        error = action.get("error")
        error_summary = None
        if isinstance(error, dict):
            subjects = error.get("data", {}).get("error", {}).get("permission_violations", [])
            scopes = [item.get("subject") for item in subjects if item.get("subject")]
            error_summary = {
                "message": error.get("message"),
                "code": error.get("code"),
                "required_scopes": scopes,
                "log_id": error.get("data", {}).get("error", {}).get("log_id"),
            }
        blocked.append(
            {
                "key": action.get("key"),
                "status": action.get("status"),
                "note": action.get("note"),
                "error": error_summary,
            }
        )
    run_id = data.get("run_id")
    return {
        "run_id": data.get("run_id"),
        "status_counter": dict(counter),
        "completed_urls": completed_urls,
        "non_completed": blocked,
        "execution_log_file": data.get("execution_log_file"),
        "finalized_actions_file": data.get("finalized_actions_file"),
        "manifest_file": data.get("manifest_file"),
        "stage_contracts": stage_contract_snapshot(run_id) if run_id else None,
    }


def write_outputs(run_id: str, plan: dict[str, Any] | None, live: dict[str, Any] | None, summary: dict[str, Any] | None) -> Path:
    bridge_dir = RUNS_ROOT / run_id / "bridge"
    bridge_dir.mkdir(parents=True, exist_ok=True)
    if plan is not None:
        (bridge_dir / "feishu-plan-wrapper.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    if live is not None:
        (bridge_dir / "feishu-live-wrapper.json").write_text(json.dumps(live, ensure_ascii=False, indent=2), encoding="utf-8")
    if summary is not None:
        (bridge_dir / "feishu-sync-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        lines = [
            f"# Feishu Sync Summary",
            "",
            f"- run_id: `{summary['run_id']}`",
            f"- status_counter: `{summary['status_counter']}`",
            "",
            "## Stage Contracts",
        ]
        stage_contracts = (summary.get("stage_contracts") or {}).get("stages", {})
        if stage_contracts:
            for stage, contract in stage_contracts.items():
                lines.append(
                    f"- `{stage}`｜manifest={contract['manifest_exists']}｜gate={contract['gate_exists']}｜manifest_path=`{contract['manifest_path']}`"
                )
                if contract.get("gate_path"):
                    lines.append(f"  - gate_path=`{contract['gate_path']}`")
        else:
            lines.append("- none")
        lines.extend([
            "",
            "## Completed URLs",
        ])
        if summary["completed_urls"]:
            lines.extend([f"- `{key}`: {url}" for key, url in summary["completed_urls"].items()])
        else:
            lines.append("- none")
        lines.extend(["", "## Non-completed"])
        if summary["non_completed"]:
            for item in summary["non_completed"]:
                if item.get("note"):
                    note = item["note"]
                elif item.get("error"):
                    err = item["error"]
                    scopes = ", ".join(err.get("required_scopes") or [])
                    parts = [str(err.get("message") or "").strip()]
                    if err.get("code") is not None:
                        parts.append(f"code={err['code']}")
                    if scopes:
                        parts.append(f"scopes={scopes}")
                    if err.get("log_id"):
                        parts.append(f"log_id={err['log_id']}")
                    note = " | ".join(part for part in parts if part)
                else:
                    note = ""
                lines.append(f"- `{item['key']}` / `{item['status']}`: {note}")
        else:
            lines.append("- none")
        (bridge_dir / "feishu-sync-summary.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return bridge_dir


def get_bridge_dir(run_id: str) -> Path:
    return RUNS_ROOT / run_id / "bridge"


def get_progress_file(run_id: str) -> Path:
    return get_bridge_dir(run_id) / "live-execution-progress.json"


def clear_live_outputs(run_id: str) -> None:
    bridge_dir = get_bridge_dir(run_id)
    for name in [
        "live-execution-progress.json",
        "feishu-live-wrapper.json",
        "feishu-sync-summary.json",
        "feishu-sync-summary.md",
    ]:
        target = bridge_dir / name
        if target.exists():
            target.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description="包装 dasheng Feishu live/plan 同步，并生成摘要")
    parser.add_argument("run_id", nargs="?")
    parser.add_argument("--latest", action="store_true", help="自动选择最新 run")
    parser.add_argument("--plan-only", action="store_true", help="只生成同步计划，不执行 live")
    parser.add_argument("--fresh", action="store_true", help="忽略并清理已有 live 进度，重新开始同步")
    parser.add_argument("--resume-only", action="store_true", help="仅基于已有进度继续同步；若无进度则退出")
    args = parser.parse_args()

    if args.fresh and args.resume_only:
        raise SystemExit("--fresh 与 --resume-only 不能同时使用")

    run_id = pick_run(args.run_id, args.latest)
    if args.fresh:
        clear_live_outputs(run_id)
    if args.resume_only and not get_progress_file(run_id).exists():
        raise SystemExit(f"未找到可续跑进度：{get_progress_file(run_id)}")
    plan = run_node(PLAN_SCRIPT, run_id)
    live_args: list[str] = []
    if args.fresh:
        live_args.append("--fresh")
    if args.resume_only:
        live_args.append("--resume-only")
    live = None if args.plan_only else run_node_with_args(LIVE_SCRIPT, run_id, live_args)
    summary = None if args.plan_only else summarize_live(live)
    out_dir = write_outputs(run_id, plan, live, summary)

    result = {
        "run_id": run_id,
        "plan_file": str(out_dir / "feishu-plan-wrapper.json"),
        "live_file": None if args.plan_only else str(out_dir / "feishu-live-wrapper.json"),
        "summary_file": None if args.plan_only else str(out_dir / "feishu-sync-summary.json"),
        "summary_markdown": None if args.plan_only else str(out_dir / "feishu-sync-summary.md"),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
