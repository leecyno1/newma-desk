#!/usr/bin/env python3
"""把桌面交付目录从「按环节分顶层目录」迁移到「按任务建文件夹」结构。

旧结构：
    ~/Desktop/自媒体创作/01_内容采集/<run>/...
    ~/Desktop/自媒体创作/02_内容聚合及选题分析/<run>/...
    ~/Desktop/自媒体创作/05_初稿生成/<run>/...
    ~/Desktop/自媒体创作/06_转写生产/<run>/...
    ~/Desktop/自媒体创作/07_发布执行/<run>/...
    ~/Desktop/自媒体创作/08_分析复盘/<run>/...
    ~/Desktop/自媒体创作/<run>/creator-xxx__*.md  （desktop_delivery 平铺复制件，废除）
    ~/Desktop/自媒体创作/<run>/creator_nodes/      （节点工作区）

新结构：
    ~/Desktop/自媒体创作/<run>/01_采集/
    ~/Desktop/自媒体创作/<run>/02_选题/
    ~/Desktop/自媒体创作/<run>/03_初稿/
    ~/Desktop/自媒体创作/<run>/04_转写/
    ~/Desktop/自媒体创作/<run>/05_发布/
    ~/Desktop/自媒体创作/<run>/06_复盘/
    ~/Desktop/自媒体创作/<run>/nodes/<stage>/<node>/

用法：
    python3 scripts/migrate_desktop_layout.py            # dry-run，仅打印计划
    python3 scripts/migrate_desktop_layout.py --apply    # 执行迁移
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from path_config import get_desktop_root  # noqa: E402

# 旧环节目录名 -> 新任务文件夹内环节目录名
OLD_STAGE_MAP = {
    "01_内容采集": "01_采集",
    "02_内容聚合及选题分析": "02_选题",
    "05_初稿生成": "03_初稿",
    "06_转写生产": "04_转写",
    "07_发布执行": "05_发布",
    "08_分析复盘": "06_复盘",
}

# 保留在桌面根的全局目录（非任务）
KEEP_ROOT_ENTRIES = {"00_范式学习", "00_热点捕捉", "00_改写", "_tmp"}

RUN_ID_CHARS = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_."
)


def is_run_dir_name(name: str) -> bool:
    """旧环节目录下的子目录都视为 run 目录；顶层散落的 run 目录按名字特征识别。"""
    if not name or name.startswith("."):
        return False
    if name in KEEP_ROOT_ENTRIES or name in OLD_STAGE_MAP:
        return False
    return all(ch in RUN_ID_CHARS for ch in name)


def move_tree(src: Path, dst: Path, ops: list[str], apply: bool) -> None:
    if not src.exists():
        return
    if dst.exists():
        ops.append(f"SKIP（目标已存在，需人工合并）: {src} -> {dst}")
        return
    ops.append(f"MOVE: {src} -> {dst}")
    if apply:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))


def migrate_old_stage_dirs(root: Path, ops: list[str], apply: bool) -> None:
    for old_name, new_name in OLD_STAGE_MAP.items():
        stage_root = root / old_name
        if not stage_root.is_dir():
            continue
        for entry in sorted(stage_root.iterdir()):
            if entry.name == ".DS_Store" or not entry.is_dir():
                ops.append(f"CLEAN: 删除杂物 {entry}")
                if apply:
                    entry.unlink(missing_ok=True)
                continue
            move_tree(entry, root / entry.name / new_name, ops, apply)
        # 环节目录收尾：仅剩 .DS_Store/空时删除
        leftover = [p for p in stage_root.iterdir() if p.name != ".DS_Store"]
        if not leftover:
            ops.append(f"RMDIR: 清空旧环节目录 {stage_root}")
            if apply:
                shutil.rmtree(stage_root, ignore_errors=True)
        else:
            ops.append(f"KEEP（仍有内容）: {stage_root} 剩 {len(leftover)} 项")


def migrate_root_run_dirs(root: Path, ops: list[str], apply: bool) -> None:
    for entry in sorted(root.iterdir()):
        if not entry.is_dir() or not is_run_dir_name(entry.name):
            continue
        # 1) creator_nodes/ -> nodes/
        old_nodes = entry / "creator_nodes"
        if old_nodes.is_dir():
            move_tree(old_nodes, entry / "nodes", ops, apply)
        # 2) desktop_delivery 平铺复制件与导出清单：删除（原件在各环节目录）
        flat_files = [
            p
            for p in entry.iterdir()
            if p.is_file()
            and (p.name.startswith(f"{entry.name}__") or p.name.endswith("__desktop_export_manifest.json"))
        ]
        for flat in flat_files:
            ops.append(f"DELETE: 平铺复制件 {flat.name}")
            if apply:
                flat.unlink(missing_ok=True)
        # 3) 空任务文件夹（既无环节目录也无 nodes）删除
        if not any(p.is_dir() for p in entry.iterdir()):
            ops.append(f"RMDIR: 空任务文件夹 {entry}")
            if apply:
                shutil.rmtree(entry, ignore_errors=True)


def migrate_stray_dirs(root: Path, ops: list[str], apply: bool) -> None:
    stray = root / "07_发布与增长"
    if stray.is_dir():
        # 目录树内无普通文件（.DS_Store 除外）即视为空
        files = [p for p in stray.rglob("*") if p.is_file() and p.name != ".DS_Store"]
        empty = not files
        ops.append(f"RMDIR: 空野目录（AI 误建） {stray}" + ("（确认空）" if empty else "（非空，警告）"))
        if apply and empty:
            shutil.rmtree(stray, ignore_errors=True)


def fix_embedded_paths(root: Path, ops: list[str], apply: bool) -> None:
    """改写 run 目录内文件内容中内嵌的旧结构绝对路径（纯文本替换，不重排 JSON）。"""
    stage_pattern = re.compile(
        r"(自媒体创作/)(01_内容采集|02_内容聚合及选题分析|05_初稿生成|06_转写生产|07_发布执行|08_分析复盘)/([^\/\"'\\ ]+)/"
    )
    nodes_pattern = re.compile(r"(自媒体创作/)([^\/\"'\\ ]+)/creator_nodes/")
    # 无尾斜杠形态：.../06_转写生产/<run> 后紧跟引号/空白/行尾
    stage_tail_pattern = re.compile(
        r"(自媒体创作/)(01_内容采集|02_内容聚合及选题分析|05_初稿生成|06_转写生产|07_发布执行|08_分析复盘)/([^\/\"'\\ ]+)(?![\w/.-])"
    )
    text_suffixes = {".json", ".md", ".html", ".yaml", ".yml", ".txt"}
    for run_dir in sorted(p for p in root.iterdir() if p.is_dir() and is_run_dir_name(p.name)):
        file_count = 0
        hit_count = 0
        for path in run_dir.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in text_suffixes:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            new_text, n1 = stage_pattern.subn(
                lambda m: f"{m.group(1)}{m.group(3)}/{OLD_STAGE_MAP[m.group(2)]}/", text
            )
            new_text, n2 = nodes_pattern.subn(lambda m: f"{m.group(1)}{m.group(2)}/nodes/", new_text)
            new_text, n3 = stage_tail_pattern.subn(
                lambda m: f"{m.group(1)}{m.group(3)}/{OLD_STAGE_MAP[m.group(2)]}", new_text
            )
            hits = n1 + n2 + n3
            if hits:
                file_count += 1
                hit_count += hits
                if apply:
                    path.write_text(new_text, encoding="utf-8")
        if file_count:
            ops.append(f"FIX-PATHS: {run_dir.name} -> {file_count} 个文件 / {hit_count} 处")


def main() -> None:
    parser = argparse.ArgumentParser(description="迁移桌面交付目录到按任务结构")
    parser.add_argument("--apply", action="store_true", help="实际执行（默认 dry-run）")
    parser.add_argument(
        "--fix-paths",
        action="store_true",
        help="只执行内嵌路径改写阶段（迁移目录后修复 manifest 内的绝对路径）",
    )
    args = parser.parse_args()

    root = get_desktop_root()
    ops: list[str] = []
    if not root.is_dir():
        print(f"桌面根目录不存在：{root}")
        raise SystemExit(1)

    if args.fix_paths:
        fix_embedded_paths(root, ops, args.apply)
    else:
        migrate_stray_dirs(root, ops, args.apply)
        migrate_old_stage_dirs(root, ops, args.apply)
        migrate_root_run_dirs(root, ops, args.apply)

    print(f"桌面根：{root}")
    print(f"模式：{'APPLY（执行）' if args.apply else 'DRY-RUN（预览）'}")
    print(f"操作数：{len(ops)}\n")
    for op in ops:
        print(f"  {op}")

    # 迁移后结构快照
    print("\n迁移后桌面根：")
    if args.apply:
        for entry in sorted(root.iterdir()):
            print(f"  {entry.name}{'/' if entry.is_dir() else ''}")


if __name__ == "__main__":
    main()
