#!/usr/bin/env python3
"""Create a self-media project scaffold under 项目/进行中."""

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path


def slugify(name: str) -> str:
    return name.strip().replace(" ", "_")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True, help="project name, e.g. 2026-02-25_金油再平衡")
    args = parser.parse_args()

    root = Path("项目") / "进行中" / slugify(args.name)
    if root.exists():
        print(f"Project already exists: {root}")
        return 1

    for subdir in ("inputs", "outputs", "research"):
        (root / subdir).mkdir(parents=True)

    stage_files = {
        "01_内容采集/intake_brief.md": "# 内容采集\n\n- 时间窗口：\n- 采集源：\n- 关键词：\n- 采集结论：\n",
        "01_内容采集/source_register.md": "# 来源登记\n\n| 来源 | 标题/主题 | 链接 | 作者/账号 | 时间 | 备注 |\n| --- | --- | --- | --- | --- | --- |\n",
        "02_内容聚合及选题分析/topic_pool.md": "# 主题池\n\n- 聚类结果：\n- TopN 候选：\n- 剔除项：\n",
        "02_内容聚合及选题分析/analysis_notes.md": "# 聚合分析笔记\n\n- 母题：\n- 子题：\n- 为什么现在值得写：\n",
        "03_选题生成/content_brief.md": "# Content Brief\n\n- 核心判断：\n- 目标读者：\n- 文章目标：\n- 可写角度：\n- 推荐角度：\n- 风险边界：\n",
        "03_选题生成/topic_decision.md": "# 选题决策\n\n- 入选主题：\n- 放弃主题：\n- 决策原因：\n",
        "05_初稿生成/draft_generation_log.md": "# 初稿生成记录\n\n- 使用引擎：\n- 数据/图表/配图：\n- 输出版本：A / B / C\n- 主版本候选：\n",
        "06_改写/rewrite_notes.md": "# 改写说明\n\n- 选中版本：\n- 调整目标：\n- 删减内容：\n- 强化内容：\n- 合规检查：\n",
        "07_渠道分发/channel_distribution_plan.md": "# 渠道分发计划\n\n- 公众号：\n- 小红书：\n- 视频号/抖音：\n- 社群/朋友圈：\n",
        "07_渠道分发/publish_log.md": "# 发布记录\n\n| 渠道 | 标题 | 发布时间 | 链接 | 备注 |\n| --- | --- | --- | --- | --- |\n",
        "08_分析复盘/postmortem.md": "# 复盘记录\n\n- 数据表现：\n- 有效动作：\n- 失效动作：\n- 下次调整：\n- 回写 L1：\n",
        "08_分析复盘/performance_metrics.md": "# 表现数据\n\n| 指标 | 数值 | 备注 |\n| --- | --- | --- |\n",
    }

    for rel_path, content in stage_files.items():
        write_text(root / rel_path, content)

    readme = f"""# 项目：{args.name}

- 创建时间：{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- 状态：进行中

## 目标
- 

## SOP 阶段
- `01_内容采集/`
- `02_内容聚合及选题分析/`
- `03_选题生成/`
- `05_初稿生成/`
- `06_改写/`
- `07_渠道分发/`
- `08_分析复盘/`

## 兼容目录
- `inputs/`：旧版素材入口
- `research/`：数据与中间研究文件
- `outputs/`：A/B/C 版本、终稿、标题与渠道包

## 固定交付
- 同一选题输出 A/B/C 三版
- 最终只保留 1 个主终稿
- 渠道分发必须单独打包
- 复盘后回写 L1 风格知识库
"""
    write_text(root / "README.md", readme)

    write_text(root / "inputs" / "evidence_manifest.md", "# 证据清单\n\n- 链接：\n- 数据：\n- 图表：\n- 备注：\n")
    write_text(root / "inputs" / "notes.md", "# 选题笔记\n\n- 核心结论：\n- 争议点：\n- 不写边界：\n")
    write_text(root / "research" / "README.md", "# 研究区\n\n- 存放聚类结果、数据表、图表源文件与中间底稿。\n")
    write_text(root / "outputs" / "A_标准平衡版.md", "# A 标准平衡版\n")
    write_text(root / "outputs" / "B_流量增强版.md", "# B 流量增强版\n")
    write_text(root / "outputs" / "C_专业深度版.md", "# C 专业深度版\n")
    write_text(root / "outputs" / "标题汇总.md", "# 标题汇总\n")
    write_text(root / "outputs" / "终稿_待发布.md", "# 终稿\n")
    write_text(root / "outputs" / "渠道分发包.md", "# 渠道分发包\n")
    write_text(
        root / "run_manifest.md",
        (
            "# Run Manifest\n\n"
            f"- 项目：{args.name}\n"
            "- 当前阶段：01_内容采集\n"
            "- 状态：进行中\n\n"
            "## 阶段状态\n"
            "- [ ] 01 内容采集\n"
            "- [ ] 02 内容聚合及选题分析\n"
            "- [ ] 03 选题生成\n"
            "- [ ] 05 初稿生成\n"
            "- [ ] 06 改写\n"
            "- [ ] 07 渠道分发\n"
            "- [ ] 08 分析复盘\n"
        ),
    )

    print(f"Created project scaffold: {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
