#!/usr/bin/env python3
"""Check or apply Newma compatibility patches to ignored upstream checkouts."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "configs/external/upstream_patches.json"
VENDOR_ROOT = (ROOT / "vendor").resolve()


def run_git(args: list[str], *, cwd: Path, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def resolve_under(root: Path, raw: str) -> Path:
    target = (ROOT / raw).resolve()
    if target != root and root not in target.parents:
        raise ValueError(f"path escapes allowed root: {raw}")
    return target


def patch_state(row: dict[str, Any]) -> dict[str, Any]:
    checkout = resolve_under(VENDOR_ROOT, str(row["root"]))
    patch = resolve_under((ROOT / "patches").resolve(), str(row["patch_file"]))
    result = {
        "id": row["id"],
        "project": row["project"],
        "root": str(checkout.relative_to(ROOT)),
        "patch_file": str(patch.relative_to(ROOT)),
        "state": "missing_checkout",
    }
    if not (checkout / ".git").exists():
        return result
    if not patch.exists():
        return dict(result, state="missing_patch")
    reverse = run_git(["apply", "--reverse", "--check", str(patch)], cwd=checkout)
    if reverse.returncode == 0:
        return dict(result, state="applied")
    forward = run_git(["apply", "--check", str(patch)], cwd=checkout)
    if forward.returncode == 0:
        return dict(result, state="pending")
    detail = (forward.stderr or forward.stdout or reverse.stderr or reverse.stdout).strip()
    return dict(result, state="conflict", error=detail)


def apply_patch(row: dict[str, Any]) -> dict[str, Any]:
    state = patch_state(row)
    if state["state"] == "applied":
        return dict(state, action="kept")
    if state["state"] != "pending":
        return dict(state, action="blocked")
    checkout = ROOT / str(row["root"])
    patch = ROOT / str(row["patch_file"])
    proc = run_git(["apply", str(patch)], cwd=checkout)
    if proc.returncode != 0:
        return dict(state, action="failed", error=(proc.stderr or proc.stdout).strip())
    return dict(patch_state(row), action="applied")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("check", "apply"), default="check")
    parser.add_argument("--name", action="append", default=[], help="Select a patch id or project; may be repeated.")
    parser.add_argument("--strict", action="store_true", help="Fail check mode unless every selected patch is applied.")
    parser.add_argument("--output", help="Optional JSON report path.")
    args = parser.parse_args()

    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    names = set(args.name)
    rows = [
        row
        for row in registry.get("patches") or []
        if not names or row.get("id") in names or row.get("project") in names
    ]
    matched = {str(row.get("id")) for row in rows} | {str(row.get("project")) for row in rows}
    if names - matched:
        raise SystemExit(f"unknown patch selection: {', '.join(sorted(names - matched))}")

    results = [(apply_patch(row) if args.mode == "apply" else patch_state(row)) for row in rows]
    report = {
        "schema_version": "dasheng.upstream_patch_report.v1",
        "mode": args.mode,
        "registry": str(REGISTRY.relative_to(ROOT)),
        "selected": len(rows),
        "results": results,
    }
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    print(text, end="")

    action_failed = any(row.get("action") in {"failed", "blocked"} for row in results)
    strict_failed = args.mode == "check" and args.strict and any(row.get("state") != "applied" for row in results)
    if action_failed or strict_failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
