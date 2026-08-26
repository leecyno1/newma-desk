#!/usr/bin/env python3
"""
标准化所有 SKILL.md 的 YAML frontmatter

确保每个 SKILL.md 包含必需的标准字段：
- name
- description
- version
- stage
- updated_at

用法:
  python3 scripts/normalize_skill_frontmatter.py [--check-only]
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()
REQUIRED_FIELDS = ["name", "description", "version", "stage", "updated_at"]
STAGE_VALUES = ["intake", "brief", "draft", "rewrite", "publish", "postmortem", "utility", "sop"]

def get_skill_dir_name(skill_dir: Path) -> str:
    """从目录名推导 skill name"""
    return skill_dir.name.replace("dasheng-", "").replace("-", "_")

def guess_stage(skill_dir: Path) -> str:
    """从目录名猜测 stage"""
    name = skill_dir.name.lower()
    if "intake" in name:
        return "intake"
    elif "brief" in name or "phase2" in name:
        return "brief"
    elif "draft" in name:
        return "draft"
    elif "rewrite" in name:
        return "rewrite"
    elif "publish" in name or "distribute" in name:
        return "publish"
    elif "postmortem" in name or "postmortem" in name:
        return "postmortem"
    elif "sop" in name or "media-sop" in name:
        return "sop"
    elif "style" in name or "profiler" in name:
        return "utility"
    elif "feishu" in name or "jiebang" in name:
        return "utility"
    return "utility"

def normalize_frontmatter(skill_dir: Path, check_only: bool = False) -> tuple[bool, list[str]]:
    """标准化单个 SKILL.md 的 frontmatter

    Returns:
        (changed, missing_fields): 是否更改，缺失的字段列表
    """
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return False, ["SKILL.md missing"]

    content = skill_md.read_text(encoding="utf-8")
    if not content.startswith("---"):
        if check_only:
            return False, ["no frontmatter"]
        # 添加 frontmatter
        frontmatter = "---\n"
        frontmatter += f"name: {skill_dir.name}\n"
        frontmatter += f"description: <TODO: description>\n"
        frontmatter += 'version: "1.0.0"\n'
        frontmatter += f"stage: {guess_stage(skill_dir)}\n"
        frontmatter += 'updated_at: "2026-04-23"\n'
        frontmatter += "---\n\n"
        skill_md.write_text(frontmatter + content, encoding="utf-8")
        return True, []

    # 解析现有 frontmatter
    parts = content.split("---", 2)
    if len(parts) < 3:
        return False, ["malformed frontmatter"]

    fm_text = parts[1]
    fm: dict[str, str] = {}
    for line in fm_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip().strip('"\'')

    missing = [f for f in REQUIRED_FIELDS if f not in fm or not fm[f]]

    if check_only:
        return False, missing

    if missing:
        # 补全缺失字段
        for field in missing:
            if field == "name":
                fm[field] = skill_dir.name
            elif field == "description":
                fm[field] = "<TODO: description>"
            elif field == "version":
                fm[field] = '"1.0.0"'
            elif field == "stage":
                fm[field] = guess_stage(skill_dir)
            elif field == "updated_at":
                fm[field] = '"2026-04-23"'

        fm_lines = "\n".join(f"{k}: {v}" for k, v in fm.items())
        new_content = f"---\n{fm_lines}\n---\n" + parts[2]
        skill_md.write_text(new_content, encoding="utf-8")
        return True, []

    return False, []

def main():
    parser = argparse.ArgumentParser(description="标准化 SKILL.md frontmatter")
    parser.add_argument("--check-only", action="store_true", help="仅检查，不修改")
    args = parser.parse_args()

    results = []
    total_changed = 0
    total_issues = 0

    for skill_dir in sorted((ROOT / "skills").iterdir()):
        if not skill_dir.is_dir() or skill_dir.name.startswith("."):
            continue
        # 只检查有 index.js 或 config.json 的 skill 目录
        if not (skill_dir / "index.js").exists() and not (skill_dir / "config.json").exists():
            continue

        changed, issues = normalize_frontmatter(skill_dir, args.check_only)

        if changed:
            status = "✅ 已标准化"
            total_changed += 1
        elif issues:
            status = f"⚠️  问题: {', '.join(issues)}"
            total_issues += len(issues)
        else:
            status = "✓ 正常"

        results.append(f"  {skill_dir.name}: {status}")

    print("SKILL.md Frontmatter 标准化检查：")
    print("-" * 50)
    for r in results:
        print(r)
    print("-" * 50)
    print(f"总计: {len(results)} 个 skills")
    if args.check_only:
        print(f"问题: {total_issues} 个字段缺失")
    else:
        print(f"已标准化: {total_changed} 个")

    if total_issues > 0 and args.check_only:
        sys.exit(1)

if __name__ == "__main__":
    main()
