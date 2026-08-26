#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path


def copy_tree(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def stage_section(title: str, dst: Path, src: Path | None) -> str:
    if src is None:
        return f"## {title}\n\n- 状态：未生成\n- 目录：`{dst}`\n"
    return f"## {title}\n\n- 桌面目录：`{dst}`\n- 源目录：`{src}`\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="导出创作交付到桌面目录（兼容工具）")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--desktop-root", default=str(Path.home() / "Desktop" / "自媒体创作"))
    parser.add_argument("--intake-dir")
    parser.add_argument("--brief-dir")
    parser.add_argument("--draft-dir")
    parser.add_argument("--rewrite-dir")
    parser.add_argument("--publish-dir")
    parser.add_argument("--postmortem-dir")
    args = parser.parse_args()

    desktop_root = Path(args.desktop_root).expanduser()
    day_root = desktop_root / args.date
    day_root.mkdir(parents=True, exist_ok=True)

    stages = {
        "01_intake": Path(args.intake_dir) if args.intake_dir else None,
        "02_brief": Path(args.brief_dir) if args.brief_dir else None,
        "03_draft": Path(args.draft_dir) if args.draft_dir else None,
        "04_publish": Path(args.publish_dir) if args.publish_dir else None,
        "05_postmortem": Path(args.postmortem_dir) if args.postmortem_dir else None,
        "optional_rewrite": Path(args.rewrite_dir) if args.rewrite_dir else None,
    }

    manifest: dict[str, dict[str, str | bool]] = {}
    for stage_name, src in stages.items():
        stage_root = day_root / stage_name
        stage_root.mkdir(parents=True, exist_ok=True)
        if src and src.exists():
            dst = stage_root / src.name
            copy_tree(src, dst)
            manifest[stage_name] = {
                "exported": True,
                "source": str(src),
                "desktop_path": str(dst),
            }
        else:
            write_text(stage_root / "README.md", f"# {stage_name}\n\n当前阶段尚未导出交付文件。\n")
            manifest[stage_name] = {
                "exported": False,
                "source": str(src) if src else "",
                "desktop_path": str(stage_root),
            }

    nav_lines = [
        "# 今日创作交付导航",
        "",
        f"- 日期：`{args.date}`",
        f"- 根目录：`{day_root}`",
        "",
        "## 当前工作流顺序",
        "",
        "1. `intake`",
        "2. `brief`",
        "3. `draft`",
        "4. `publish`",
        "5. `postmortem`",
        "",
        "按需工具：`rewrite-variants`",
        "",
        stage_section("01 Intake", day_root / "01_intake", stages["01_intake"]),
        stage_section("02 Brief", day_root / "02_brief", stages["02_brief"]),
        stage_section("03 Draft", day_root / "03_draft", stages["03_draft"]),
        stage_section("04 Publish", day_root / "04_publish", stages["04_publish"]),
        stage_section("05 Postmortem", day_root / "05_postmortem", stages["05_postmortem"]),
        stage_section("Optional Rewrite Variants", day_root / "optional_rewrite", stages["optional_rewrite"]),
    ]
    write_text(day_root / "00_今日交付导航.md", "\n".join(nav_lines).rstrip() + "\n")
    write_text(day_root / "delivery_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
