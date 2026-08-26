#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MODULE_REGISTRY = ROOT / "configs/workflow/module_registry.json"
RESERVED_REGISTRY = ROOT / "configs/external/reserved_projects.json"
STAGE_RESERVE_REGISTRY = ROOT / "configs/workflow/stage_reserve_registry.json"
CREATOR_CANDIDATE_REGISTRY = ROOT / "configs/workflow/creator_technology_candidates.json"
SKILL_REGISTRY = ROOT / "skills/SKILL_ALIASES.md"
DEFAULT_OUTPUT = ROOT / "docs/PROJECT_CATALOG.md"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def requirements(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def skill_rows() -> list[dict[str, str]]:
    text = SKILL_REGISTRY.read_text(encoding="utf-8")
    rows = []
    for line in text.splitlines():
        match = re.match(r"\| `([^`]+)` \| ([^|]+) \| ([^|]+) \| ([^|]+) \|", line)
        if not match:
            continue
        name, version, status, description = [part.strip() for part in match.groups()]
        rows.append({"name": name, "version": version, "status": status, "description": description})
    return rows


def md_cell(value: Any) -> str:
    return (
        str(value or "")
        .replace("dasheng-", "newma-")
        .replace("dasheng_", "newma_")
        .replace("Dasheng", "Newma")
        .replace("大圣", "Newma")
        .replace("|", "\\|")
        .replace("\n", " ")
    )


def build_catalog() -> str:
    module_registry = read_json(MODULE_REGISTRY)
    reserve = read_json(RESERVED_REGISTRY)
    stage_reserve_registry = read_json(STAGE_RESERVE_REGISTRY)
    creator_candidates = read_json(CREATOR_CANDIDATE_REGISTRY)
    projects = reserve.get("projects") or []
    candidates = reserve.get("reserve_candidates") or []
    rejected = reserve.get("rejected") or []
    skills = skill_rows()
    category_counts = Counter(str(row.get("category") or "other") for row in projects)
    tier_counts = Counter(str(row.get("tier") or "unclassified") for row in projects)

    lines = [
        "# Newma Media Studio项目目录",
        "",
        "> 本文件由 `scripts/build_project_catalog.py` 根据机器注册表生成，请不要手工维护列表。",
        "",
        f"更新日期：`{module_registry.get('updated_at')}`",
        "",
        "## 总览",
        "",
        f"- 正式主链：`intake -> brief -> draft -> transwrite -> publish -> postmortem`",
        f"- 正式/按需 Skill 登记：`{len(skills)}`",
        f"- 已保留上游项目：`{len(projects)}`",
        f"- 候选储备：`{len(candidates)}`",
        f"- 已剔除项目：`{len(rejected)}`",
        f"- 内部功能模块：`{len(module_registry.get('modules') or [])}`",
        "",
        "### 储备分布",
        "",
        "| 类别 | 数量 |",
        "| --- | ---: |",
    ]
    for category, count in sorted(category_counts.items()):
        lines.append(f"| `{md_cell(category)}` | {count} |")
    lines.extend(["", "### 级别分布", "", "| 级别 | 数量 |", "| --- | ---: |"])
    for tier, count in sorted(tier_counts.items()):
        lines.append(f"| `{md_cell(tier)}` | {count} |")

    lines.extend(["", "## 六阶段处理流程", ""])
    for stage in module_registry.get("stages") or []:
        lines.extend(
            [
                f"### {stage['order']}. {stage['name']} (`{stage['id']}`)",
                "",
                f"- 入口：`{stage['entry_skill']}` / `{stage['builder']}`",
                f"- 输入：{' 、'.join(stage.get('inputs') or [])}",
                f"- 处理：{' -> '.join(stage.get('process') or [])}",
                f"- 输出：{' 、'.join(stage.get('outputs') or [])}",
                f"- 门禁：{stage.get('gate') or '无'}",
                "",
            ]
        )

    lines.extend(
        [
            "## 六阶段储备路由",
            "",
            "> 储备路由只表示对应环节可以发现该项目；`cloned_not_promoted`、`blocked` 和 `methodology_only` 不会取代生产主路由。",
            "",
            "| 环节 | 项目 | 角色 | 可用性 | 执行方式 | 回退 | 阻断/约束 |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    stage_names = {str(stage["id"]): str(stage["name"]) for stage in module_registry.get("stages") or []}
    for stage_id in stage_reserve_registry.get("valid_stages") or []:
        rows = (stage_reserve_registry.get("stages") or {}).get(stage_id) or []
        for row in rows:
            constraints = list(row.get("blockers") or [])
            if row.get("clone_allowed") is False:
                constraints.append("禁止克隆")
            if row.get("license_status") == "missing":
                constraints.append("上游无许可证")
            lines.append(
                f"| {md_cell(stage_names.get(stage_id, stage_id))} (`{md_cell(stage_id)}`) | `{md_cell(row.get('project'))}` | "
                f"`{md_cell(row.get('role'))}` | `{md_cell(row.get('availability'))}` | `{md_cell(row.get('execution_mode'))}` | "
                f"{md_cell('、'.join(row.get('fallback') or []))} | {md_cell('、'.join(constraints))} |"
            )
        if not rows:
            lines.append(f"| {md_cell(stage_names.get(stage_id, stage_id))} (`{md_cell(stage_id)}`) | — | — | — | — | 未强行登记 | — |")
    lines.append("")

    lines.extend(
        [
            "## 高分自媒体创作备选技术",
            "",
            "> 候选项目供各环节导演发现与安排适配，不会绕过依赖、许可证、质量门禁或人工复核成为生产主路由。",
            "",
            "| 项目 | 评分 | 类别 | 环节 | 可用性 | 依赖 | 阻断项 |",
            "| --- | ---: | --- | --- | --- | --- | --- |",
        ]
    )
    for row in creator_candidates.get("candidates") or []:
        lines.append(
            f"| `{md_cell(row.get('name'))}` | {md_cell(row.get('score'))}/100 | `{md_cell(row.get('category'))}` | "
            f"{md_cell('、'.join(row.get('route_stages') or []))} | `{md_cell(row.get('availability'))}` | "
            f"{md_cell('、'.join(row.get('dependencies') or []))} | {md_cell('、'.join(row.get('blockers') or []))} |"
        )
    lines.append("")

    lines.extend(["## 功能模块", "", "| 模块 | 主要路径 | 职责 |", "| --- | --- | --- |"])
    for module in module_registry.get("modules") or []:
        paths = "<br>".join(f"`{md_cell(path)}`" for path in module.get("paths") or [])
        duties = "、".join(module.get("responsibilities") or [])
        lines.append(f"| {md_cell(module['name'])} | {paths} | {md_cell(duties)} |")

    lines.extend(["", "## Skill 注册表", "", "| Skill | 版本 | 状态 | 职责 |", "| --- | --- | --- | --- |"])
    for row in skills:
        lines.append(f"| `{md_cell(row['name'])}` | {md_cell(row['version'])} | {md_cell(row['status'])} | {md_cell(row['description'])} |")

    lines.extend(["", "## 保留上游项目", "", "第三方源码默认克隆到 `vendor/reserved/` 或 `vendor/publish/`，不进入主仓库 Git 历史。", "", "| 项目 | 类别 | 级别 | 依赖状态 | 本地路径 | 上游 |", "| --- | --- | --- | --- | --- | --- |"])
    for row in sorted(projects, key=lambda item: (str(item.get("category")), str(item.get("name")))):
        repo = str(row.get("repo") or "")
        repo_link = f"[upstream]({repo})" if repo else ""
        lines.append(
            f"| `{md_cell(row.get('name'))}` | `{md_cell(row.get('category'))}` | `{md_cell(row.get('tier'))}` | "
            f"`{md_cell(row.get('dependency_status'))}` | `{md_cell(row.get('local_path'))}` | {repo_link} |"
        )

    lines.extend(["", "## 候选储备", "", "| 项目 | 类别 | 级别 | 下一步 | 阻断项 |", "| --- | --- | --- | --- | --- |"])
    for row in candidates:
        lines.append(
            f"| `{md_cell(row.get('name'))}` | `{md_cell(row.get('category'))}` | `{md_cell(row.get('tier'))}` | "
            f"{md_cell(row.get('recommended_action'))} | {md_cell('、'.join(row.get('blockers') or []))} |"
        )

    lines.extend(["", "## 已剔除项目", "", "| 项目 | 原因 |", "| --- | --- |"])
    for row in rejected:
        lines.append(f"| `{md_cell(row.get('name'))}` | {md_cell(row.get('reason'))} |")

    lines.extend(["", "## 依赖", "", "### 系统依赖", "", "| 依赖 | 最低版本 | 必需 |", "| --- | --- | --- |"])
    for row in module_registry.get("system_dependencies") or []:
        lines.append(f"| {md_cell(row['name'])} | `{md_cell(row['minimum'])}` | {'是' if row.get('required') else '否'} |")
    lines.extend(["", "### Python 核心依赖", "", "```text", *requirements(ROOT / "requirements.txt"), "```", "", "### Python 媒体扩展", "", "```text", *requirements(ROOT / "requirements-media.txt"), "```"])

    lines.extend(["", "## 发布技术路线", "", "| 优先级 | 路线 | 状态 | 技术路径 |", "| ---: | --- | --- | --- |"])
    for row in module_registry.get("publish_routes") or []:
        lines.append(f"| {row['priority']} | `{row['id']}` | `{row['status']}` | `{md_cell(row['path'])}` |")

    lines.extend(
        [
            "",
            "## 克隆、安装和检查",
            "",
            "```bash",
            "./scripts/install.sh",
            "source .venv/bin/activate",
            "python scripts/sync_reserved_projects.py --mode check",
            "python scripts/sync_reserved_projects.py --mode clone --category video",
            "python scripts/apply_upstream_patches.py --mode check",
            "python scripts/ensure_video_external_deps.py --dep all --mode check",
            "python scripts/check_publish_upstreams.py",
            "python -m pytest tests -q",
            "```",
            "",
            "## 公开仓库边界",
            "",
            "- 提交：自研 Skills、脚本、非敏感配置、契约、测试、文档、上游注册表和兼容补丁。",
            "- 不提交：第三方源码副本、虚拟环境、`node_modules`、Cookie/浏览器 Profile、API 密钥、验证码、抓取快照、视频成品和每日运行产物。",
            "- 外部项目许可证与使用条款以各自上游仓库为准。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the public Newma project catalog.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--check", action="store_true", help="Fail when the generated document is stale.")
    args = parser.parse_args()
    output = Path(args.output).expanduser().resolve()
    content = build_catalog().rstrip() + "\n"
    if args.check:
        if not output.exists() or output.read_text(encoding="utf-8") != content:
            raise SystemExit(f"project catalog is stale: {output}")
        print(str(output))
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    print(str(output))


if __name__ == "__main__":
    main()
