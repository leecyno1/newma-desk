from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANONICAL_REPOSITORY = "leecyno1/newma-media-studio"
CANONICAL_REPOSITORY_SLUG = "newma-media-studio"
LEGACY_REPOSITORY = "leecyno1/" + "dasheng-media-workflow-skills"

FORBIDDEN_EXACT = {
    "configs/image_generation/providers.local.env",
    "configs/feishu/liweis_bot_config.json",
    "configs/feishu/liweis_migration_status_2026-03-28.md",
}
FORBIDDEN_PREFIXES = (
    "openclaw-skill-exports/",
    "data/wechat_scrapes/",
    "data/xiaohongshu_scrapes/",
    "项目/进行中/",
    "vendor/reserved/",
    "vendor/publish/",
)
PERSONAL_PATHS = (
    "/Users/" + "lichengyin",
    "/Volumes/" + "PSSD",
)
OBVIOUS_SECRET_PATTERNS = (
    re.compile(r"\bsk[-_][A-Za-z0-9]{20,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
)


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    return [part.decode("utf-8") for part in result.stdout.split(b"\0") if part]


def text_for(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\0" in data or len(data) > 2_000_000:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def test_local_runtime_and_sensitive_files_are_not_tracked():
    tracked = set(tracked_files())
    assert not (tracked & FORBIDDEN_EXACT)
    leaked = sorted(path for path in tracked if path.startswith(FORBIDDEN_PREFIXES))
    assert leaked == []


def test_tracked_text_has_no_personal_absolute_paths():
    hits: list[str] = []
    for relative in tracked_files():
        text = text_for(ROOT / relative)
        if text is not None and any(marker in text for marker in PERSONAL_PATHS):
            hits.append(relative)
    assert hits == []


def test_tracked_text_has_no_obvious_provider_secrets():
    hits: list[str] = []
    for relative in tracked_files():
        text = text_for(ROOT / relative)
        if text is None:
            continue
        if any(pattern.search(text) for pattern in OBVIOUS_SECRET_PATTERNS):
            hits.append(relative)
    assert hits == []


def test_public_entrypoints_use_newma_repository_name():
    entrypoints = (
        "README.md",
        "INSTALLATION.md",
        "CONTRIBUTING.md",
        "configs/workflow/module_registry.json",
    )
    for relative in entrypoints:
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert CANONICAL_REPOSITORY_SLUG in text
        assert LEGACY_REPOSITORY not in text

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    registry = (ROOT / "configs/workflow/module_registry.json").read_text(encoding="utf-8")
    assert CANONICAL_REPOSITORY in readme
    assert CANONICAL_REPOSITORY in registry
