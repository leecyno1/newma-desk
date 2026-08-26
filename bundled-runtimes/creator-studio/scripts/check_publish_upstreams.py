#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from path_config import get_project_root


ROOT = get_project_root()
REGISTRY = ROOT / "configs" / "publish" / "upstream_repos.json"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _expand_env_vars(value: str) -> str:
    """展开 ${VAR:-default} 风格的环境变量。"""
    pattern = r"\$\{([^:}]+)(?::-(.*?))?\}"

    def replacer(match: re.Match[str]) -> str:
        var_name, default = match.groups()
        return os.environ.get(var_name, default or "")

    return re.sub(pattern, replacer, value)


def resolve_root(row: dict[str, Any]) -> Path:
    env_name = str(row.get("default_root_env") or "")
    value = os.getenv(env_name) if env_name else None
    return Path(value or _expand_env_vars(str(row.get("default_root") or "")) or "").expanduser()


def git_output(args: list[str], *, cwd: Path | None = None, timeout: int = 20) -> str | None:
    try:
        proc = subprocess.run(args, cwd=str(cwd) if cwd else None, capture_output=True, text=True, check=False, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def local_head(path: Path) -> str | None:
    if not (path / ".git").exists():
        return None
    return git_output(["git", "rev-parse", "HEAD"], cwd=path)


def remote_head(repo: str) -> str | None:
    output = git_output(["git", "ls-remote", repo, "HEAD"])
    if not output:
        return None
    return output.split()[0]


def inspect_repo(row: dict[str, Any], *, check_remote: bool) -> dict[str, Any]:
    root = resolve_root(row)
    exists = root.exists()
    local = local_head(root) if exists else None
    remote = remote_head(str(row["repo"])) if check_remote else None
    return {
        "name": row["name"],
        "repo": row["repo"],
        "root": str(root),
        "exists": exists,
        "local_head": local,
        "remote_head": remote,
        "update_available": bool(local and remote and local != remote),
        "used_by_skills": row.get("used_by_skills") or [],
        "sync_strategy": row.get("sync_strategy"),
        "notes": row.get("notes"),
    }


def build_report(names: set[str] | None, *, check_remote: bool) -> dict[str, Any]:
    registry = read_json(REGISTRY)
    rows = registry.get("repositories") or []
    selected = [row for row in rows if not names or row.get("name") in names]
    return {
        "created_at": now_iso(),
        "registry": str(REGISTRY.resolve()),
        "check_remote": check_remote,
        "repositories": [inspect_repo(row, check_remote=check_remote) for row in selected],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Check Newma Publish external upstream repositories.")
    parser.add_argument("--name", action="append", help="Only check this upstream name; may be repeated.")
    parser.add_argument("--remote", action="store_true", help="Also query remote HEAD with git ls-remote.")
    parser.add_argument("--output", help="Optional JSON report path.")
    args = parser.parse_args()

    report = build_report(set(args.name or []) or None, check_remote=args.remote)
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
