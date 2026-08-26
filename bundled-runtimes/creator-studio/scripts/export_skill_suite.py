#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def copytree_filtered(src: Path, dst: Path, exclude_dirs: list[str] | None = None) -> None:
    """Copy directory tree, excluding specified directories and backup files."""
    if exclude_dirs is None:
        exclude_dirs = ["__pycache__", ".pytest_cache", ".git"]
    exclude_set = set(exclude_dirs)
    exclude_patterns = [".backup.", ".pyc", ".pyo"]

    dst.mkdir(parents=True, exist_ok=True)
    for item in src.rglob("*"):
        if item.is_file():
            # Skip excluded directories
            if any(excluded in item.parts for excluded in exclude_set):
                continue
            # Skip files matching exclude patterns
            if any(pattern in item.name for pattern in exclude_patterns):
                continue
            rel_path = item.relative_to(src)
            dst_file = dst / rel_path
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, dst_file)
        elif item.is_dir():
            if item.name in exclude_set:
                continue
            rel_path = item.relative_to(src)
            (dst / rel_path).mkdir(parents=True, exist_ok=True)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXPORT_ROOT = ROOT / "openclaw-skill-exports"
FORMAL_SKILLS = [
    "dasheng-media-sop",
    "dasheng-paradigm-profiler",
    "dasheng-stage-publish",
    "dasheng-publish-operations-bridge",
    "dasheng-daily-intake",
    "dasheng-daily-phase2",
    "dasheng-daily-postmortem",
    "dasheng-finance-data",
    "dasheng-html-video-bridge",
    "dasheng-html-anything-bridge",
    "dasheng-lemon-illustrations",
    "dasheng-video-talking-head",
    "dasheng-digital-human-talking-head",
    "dasheng-video-explainer-html",
    "dasheng-style-profiler",
    "feishu-doc-creator",
]
LEGACY_REDIRECT_SKILLS = [
    "dasheng-daily-brief",
    "dasheng-daily-final",
    "dasheng-stage-rewrite",
    "dasheng-stage-intake-brief-draft",
    "dasheng-stage-publish-video",
    "dasheng-stage-distribute",
    "dasheng-collection-workflow",
    "dasheng-sop-orchestrator",
    "dasheng-style-profiler",
    "dasheng-daily-draft",
]
DOC_FILES = [
    ROOT / "引擎/03_全链路SOP工作流/STAGE_INTERFACES.md",
]
BUNDLED_DIRECTORIES = [
    "scripts",
    "configs/creative",
]


def export_suite(target_dir: Path) -> Path:
    if target_dir.exists():
        shutil.rmtree(target_dir)

    # Export skills
    (target_dir / "skills").mkdir(parents=True, exist_ok=True)
    exported: list[str] = []
    for skill_name in FORMAL_SKILLS:
        src = ROOT / "skills" / skill_name
        dst = target_dir / "skills" / skill_name
        if src.exists():
            copytree_filtered(src, dst)
            exported.append(str(dst))

    # Export README.md to root
    readme_src = ROOT / "README.md"
    if readme_src.exists():
        shutil.copy2(readme_src, target_dir / "README.md")
        exported.append(str(target_dir / "README.md"))

    # Export docs
    docs_dir = target_dir / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    for doc in DOC_FILES:
        if doc.exists():
            shutil.copy2(doc, docs_dir / doc.name)
            exported.append(str(docs_dir / doc.name))

    # Export bundled directories (with __pycache__ filtering)
    for dir_name in BUNDLED_DIRECTORIES:
        src_dir = ROOT / dir_name
        if src_dir.exists():
            copytree_filtered(src_dir, target_dir / dir_name)
            exported.append(str(target_dir / dir_name))

    # Export root files
    root_files = ["ENV_TEMPLATE.env", "install_to_openclaw.sh"]
    for fname in root_files:
        src = ROOT / fname
        if src.exists():
            shutil.copy2(src, target_dir / fname)
            exported.append(str(target_dir / fname))

    # Generate manifest
    manifest = {
        "source_repo": str(ROOT),
        "formal_skills": FORMAL_SKILLS,
        "legacy_redirect_skills": LEGACY_REDIRECT_SKILLS,
        "docs": [path.name for path in DOC_FILES if path.exists()],
        "bundled_directories": BUNDLED_DIRECTORIES,
        "exported": exported,
        "installation": {
            "openclaw": {
                "script": "install_to_openclaw.sh",
                "instructions": "bash install_to_openclaw.sh"
            }
        }
    }
    (target_dir / "EXPORT_MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return target_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="导出 Newma Media Studio 正式 Skill 套件")
    parser.add_argument("--target-dir", help="目标目录；默认 openclaw-skill-exports/newma-media-studio-current")
    args = parser.parse_args()

    target_dir = (
        Path(args.target_dir).expanduser().resolve()
        if args.target_dir
        else (DEFAULT_EXPORT_ROOT / "newma-media-studio-current")
    )
    exported_dir = export_suite(target_dir)
    print(str(exported_dir))


if __name__ == "__main__":
    main()
