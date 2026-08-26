#!/usr/bin/env python3
"""Inspect, clone, or fast-forward external projects from the reserve registry."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "configs/external/reserved_projects.json"
VENDOR_ROOT = (ROOT / "vendor").resolve()


def read_registry() -> dict[str, Any]:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def run_git(args: list[str], *, cwd: Path | None = None, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def target_path(row: dict[str, Any]) -> Path:
    raw = str(row.get("local_path") or "").strip()
    if not raw:
        raw = f"vendor/reserved/{row.get('category', 'other')}/{row['name']}"
    target = (ROOT / raw).resolve()
    if target != VENDOR_ROOT and VENDOR_ROOT not in target.parents:
        raise ValueError(f"external project target must stay under vendor/: {raw}")
    return target


def select_rows(
    registry: dict[str, Any],
    *,
    names: set[str],
    categories: set[str],
    include_candidates: bool,
) -> list[dict[str, Any]]:
    rows = [dict(row, registry_section="projects") for row in registry.get("projects") or []]
    if include_candidates:
        rows.extend(dict(row, registry_section="reserve_candidates") for row in registry.get("reserve_candidates") or [])
    selected = [
        row
        for row in rows
        if (not names or str(row.get("name")) in names)
        and (not categories or str(row.get("category")) in categories)
    ]
    selected_names = {str(row.get("name")) for row in selected}
    missing_names = sorted(names - selected_names)
    if missing_names:
        raise SystemExit(f"unknown reserved project(s): {', '.join(missing_names)}")
    return selected


def inspect(row: dict[str, Any]) -> dict[str, Any]:
    target = target_path(row)
    git_dir = target / ".git"
    result: dict[str, Any] = {
        "name": row["name"],
        "category": row.get("category"),
        "tier": row.get("tier"),
        "registry_section": row.get("registry_section"),
        "repo": row.get("repo"),
        "path": str(target.relative_to(ROOT)),
        "status": "missing",
    }
    if target.exists() and not git_dir.exists():
        result["status"] = "not_git"
        return result
    if not git_dir.exists():
        return result

    head = run_git(["rev-parse", "HEAD"], cwd=target)
    branch = run_git(["branch", "--show-current"], cwd=target)
    dirty = run_git(["status", "--porcelain"], cwd=target)
    remote = run_git(["remote", "get-url", "origin"], cwd=target)
    result.update(
        {
            "status": "present",
            "head": head.stdout.strip() if head.returncode == 0 else None,
            "branch": branch.stdout.strip() if branch.returncode == 0 else None,
            "dirty": bool(dirty.stdout.strip()) if dirty.returncode == 0 else None,
            "origin": remote.stdout.strip() if remote.returncode == 0 else None,
            "recorded_head": row.get("git_head"),
        }
    )
    return result


def clone(row: dict[str, Any]) -> dict[str, Any]:
    before = inspect(row)
    if before["status"] == "present":
        return dict(before, action="kept")
    if before["status"] == "not_git":
        return dict(before, action="blocked", error="target exists but is not a Git repository")
    repo = str(row.get("repo") or "").strip()
    if not repo:
        return dict(before, action="blocked", error="registry entry has no upstream repository")
    target = target_path(row)
    target.parent.mkdir(parents=True, exist_ok=True)
    args = ["clone"]
    branch = str(row.get("selected_branch") or "").strip()
    if branch:
        args.extend(["--branch", branch])
    args.extend([repo, str(target)])
    proc = run_git(args, timeout=600)
    if proc.returncode != 0:
        return dict(before, action="failed", error=(proc.stderr or proc.stdout).strip())
    return dict(inspect(row), action="cloned")


def update(row: dict[str, Any]) -> dict[str, Any]:
    current = inspect(row)
    if current["status"] == "missing":
        return clone(row)
    if current["status"] != "present":
        return dict(current, action="blocked", error="target is not a Git repository")
    if current.get("dirty"):
        return dict(current, action="blocked", error="working tree has local changes; export or revert them before update")
    target = target_path(row)
    proc = run_git(["pull", "--ff-only"], cwd=target, timeout=600)
    if proc.returncode != 0:
        return dict(current, action="failed", error=(proc.stderr or proc.stdout).strip())
    return dict(inspect(row), action="updated", message=proc.stdout.strip())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("check", "clone", "update"), default="check")
    parser.add_argument("--name", action="append", default=[], help="Select one project; may be repeated.")
    parser.add_argument("--category", action="append", default=[], help="Select one category; may be repeated.")
    parser.add_argument(
        "--include-candidates",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include reserve_candidates as well as retained projects (default: true).",
    )
    parser.add_argument("--strict", action="store_true", help="Fail check mode when a selected checkout is missing or invalid.")
    parser.add_argument("--output", help="Optional JSON report path.")
    args = parser.parse_args()

    rows = select_rows(
        read_registry(),
        names=set(args.name),
        categories=set(args.category),
        include_candidates=args.include_candidates,
    )
    handler = {"check": inspect, "clone": clone, "update": update}[args.mode]
    results = [handler(row) for row in rows]
    report = {
        "schema_version": "dasheng.reserved_sync_report.v1",
        "mode": args.mode,
        "registry": str(REGISTRY.relative_to(ROOT)),
        "selected": len(rows),
        "summary": {
            status: sum(1 for row in results if row.get("status") == status)
            for status in ("present", "missing", "not_git")
        },
        "results": results,
    }
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    print(text, end="")

    actions_failed = any(row.get("action") in {"failed", "blocked"} for row in results)
    strict_check_failed = args.mode == "check" and args.strict and any(row.get("status") != "present" for row in results)
    if actions_failed or strict_check_failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
