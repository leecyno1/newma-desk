#!/usr/bin/env python3
"""Load and query the Newma video tool registry."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY_PATH = PROJECT_ROOT / "configs" / "video" / "tool_registry.json"
LOCAL_SKILLS_DIR = PROJECT_ROOT / "skills"
GLOBAL_SKILLS_DIR = Path.home() / ".codex" / "skills"


def load_tool_registry(path: Path | None = None) -> dict[str, Any]:
    registry_path = path or DEFAULT_REGISTRY_PATH
    return json.loads(registry_path.read_text(encoding="utf-8"))


def tool_index(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(tool["name"]): tool for tool in registry.get("tools", [])}


def get_tool(registry: dict[str, Any], name: str) -> dict[str, Any] | None:
    return tool_index(registry).get(name)


def tools_for_capability(registry: dict[str, Any], capability: str) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for tool in registry.get("tools", []):
        if capability in (tool.get("capabilities") or []):
            matches.append(tool)
    return matches


def unresolved_script_paths(registry: dict[str, Any], *, project_root: Path = PROJECT_ROOT) -> list[dict[str, str]]:
    missing: list[dict[str, str]] = []
    for tool in registry.get("tools", []):
        if tool.get("type") != "script":
            continue
        script_path = str(tool.get("path") or "")
        if not script_path:
            missing.append({"name": str(tool.get("name")), "path": ""})
            continue
        if not (project_root / script_path).exists():
            missing.append({"name": str(tool.get("name")), "path": script_path})
    return missing


def unresolved_skill_paths(
    registry: dict[str, Any],
    *,
    skills_dir: Path = LOCAL_SKILLS_DIR,
    global_skills_dir: Path = GLOBAL_SKILLS_DIR,
) -> list[dict[str, str]]:
    missing: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for tool in registry.get("tools", []):
        if tool.get("type") != "skill":
            continue
        skill_name = str(tool.get("skill") or "")
        if not skill_name:
            missing.append({"name": str(tool.get("name")), "skill": ""})
            continue
        local_skill = skills_dir / skill_name / "SKILL.md"
        global_skill = global_skills_dir / skill_name / "SKILL.md"
        if not local_skill.exists() and not global_skill.exists():
            item = (str(tool.get("name")), skill_name)
            if item not in seen:
                missing.append({"name": item[0], "skill": item[1]})
                seen.add(item)
    for skill in registry.get("skills", []):
        skill_name = str(skill.get("name") or "")
        configured_path = str(skill.get("path") or "")
        if configured_path:
            path = Path(configured_path).expanduser()
            if not path.is_absolute():
                path = PROJECT_ROOT / path
        else:
            local_skill = skills_dir / skill_name / "SKILL.md"
            global_skill = global_skills_dir / skill_name / "SKILL.md"
            path = local_skill if local_skill.exists() else global_skill
        if not path.exists():
            item = (skill_name, configured_path or skill_name)
            if item not in seen:
                missing.append({"name": item[0], "skill": item[1]})
                seen.add(item)
    return missing


def unresolved_project_paths(registry: dict[str, Any], *, project_root: Path = PROJECT_ROOT) -> list[dict[str, str]]:
    source = str((registry.get("catalog_sources") or {}).get("reserved_projects") or "")
    if not source:
        return [{"name": "reserved_projects_registry", "path": ""}]
    source_path = Path(source).expanduser()
    if not source_path.is_absolute():
        source_path = project_root / source_path
    if not source_path.exists():
        return [{"name": "reserved_projects_registry", "path": str(source_path)}]
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    missing: list[dict[str, str]] = []
    for project in payload.get("projects", []):
        configured = str(project.get("local_path") or "")
        path = Path(configured).expanduser()
        if not path.is_absolute():
            path = project_root / path
        if not path.exists():
            missing.append({"name": str(project.get("name")), "path": configured})
    return missing


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect the Newma video tool registry.")
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY_PATH))
    parser.add_argument("--capability", default="", help="List tools matching this capability.")
    parser.add_argument("--check", action="store_true", help="Check referenced script paths.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    registry = load_tool_registry(Path(args.registry).expanduser().resolve())
    if args.capability:
        print(json.dumps(tools_for_capability(registry, args.capability), ensure_ascii=False, indent=2))
        return 0
    if args.check:
        missing = unresolved_script_paths(registry)
        missing_skills = unresolved_skill_paths(registry)
        missing_projects = unresolved_project_paths(registry)
        print(json.dumps({"missing_script_paths": missing, "missing_skill_paths": missing_skills, "missing_project_paths": missing_projects}, ensure_ascii=False, indent=2))
        return 1 if missing or missing_skills or missing_projects else 0
    print(json.dumps(registry, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
