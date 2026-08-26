#!/usr/bin/env python3
"""Repository hygiene guards for generated outputs and local-only files."""

import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def test_no_local_or_generated_files_are_tracked():
    blocked_exact = {
        ".DS_Store",
    }
    blocked_parts = {
        "__pycache__",
        ".pytest_cache",
        ".venv",
        ".venv_media",
        ".tmp",
        ".tmp_test",
        ".codex_work",
        "tmp",
        "产物",
        "素材",
        "交付镜像",
    }

    offenders = []
    for tracked in _tracked_files():
        parts = set(Path(tracked).parts)
        if tracked in blocked_exact or Path(tracked).name in blocked_exact:
            offenders.append(tracked)
            continue
        if parts & blocked_parts:
            offenders.append(tracked)

    assert offenders == []


def test_path_config_cli_output_is_not_duplicated():
    source = (PROJECT_ROOT / "scripts" / "path_config.py").read_text(encoding="utf-8")
    assert source.count('print(f"  Feishu Bot Config: {get_feishu_bot_config_path()}")') == 1
    assert source.count("print(ENV_VARS_HELP)") == 1


def test_tracked_skill_dirs_have_skill_md_or_are_explicit_runtime_dirs():
    allowed_runtime_dirs = {
        "skills/dasheng-daily-shared",
        "skills/dasheng-daily-shared/runtime-data",
        "skills/dasheng-media-rewrite-v2",
    }
    allowed_root_files = {
        "skills/SKILL_ALIASES.md",
    }

    offenders = []
    for tracked in _tracked_files():
        if not tracked.startswith("skills/"):
            continue
        if tracked in allowed_root_files:
            continue
        parts = Path(tracked).parts
        if len(parts) < 2:
            continue
        skill_root = Path(parts[0]) / parts[1]
        if str(skill_root) in allowed_runtime_dirs:
            continue
        if skill_root.name == ".archive" and len(parts) >= 3:
            skill_root = Path(parts[0]) / parts[1] / parts[2]

        if not (PROJECT_ROOT / skill_root / "SKILL.md").exists():
            offenders.append(tracked)

    assert offenders == []
