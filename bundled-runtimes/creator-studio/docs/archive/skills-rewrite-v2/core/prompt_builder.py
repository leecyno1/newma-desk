#!/usr/bin/env python3
"""
PromptBuilder: 模块化Prompt组装工具

功能: 将base_rules、platform_rules、tone_rules、constraints组合成完整的Rewrite Prompt
优势: 避免Prompt重复、支持快速增加新平台/新tone、便于版本管理和AB测试
"""

import os
from pathlib import Path
from typing import Dict, List, Optional


class PromptBuilder:
    """
    Prompt模块化构建器

    使用方式:
        builder = PromptBuilder()
        prompt = (builder
            .add_base_rules()
            .add_platform_rule("wechat")
            .add_tone_rule("hot")
            .add_structure_constraint(final_snapshot)
            .build())
    """

    def __init__(self, templates_dir: str = None):
        """
        初始化PromptBuilder

        Args:
            templates_dir: 模板目录路径（默认为当前目录的rewrite_modules）
        """
        if templates_dir is None:
            templates_dir = str(Path(__file__).parent.parent / "templates" / "rewrite_modules")

        self.templates_dir = templates_dir
        self.sections = []
        self.metadata = {}

    def add_base_rules(self) -> "PromptBuilder":
        """添加基础规则（所有版本都需要）"""
        base_file = Path(self.templates_dir) / "base_rules.md"
        if base_file.exists():
            with open(base_file, 'r', encoding='utf-8') as f:
                content = f.read()
            self.sections.append(("base_rules", content))
            self.metadata['has_base_rules'] = True
        return self

    def add_platform_rule(self, platform: str) -> "PromptBuilder":
        """
        添加平台特异性规则

        Args:
            platform: "wechat", "xiaohongshu", "douyin" 等
        """
        platform_file = Path(self.templates_dir) / "platform_rules" / f"{platform}.md"
        if platform_file.exists():
            with open(platform_file, 'r', encoding='utf-8') as f:
                content = f.read()
            self.sections.append((f"platform_{platform}", content))
            self.metadata['platform'] = platform
        else:
            raise FileNotFoundError(f"Platform rule not found: {platform_file}")
        return self

    def add_tone_rule(self, tone: str) -> "PromptBuilder":
        """
        添加语气规则

        Args:
            tone: "hot", "normal", "viral" 等
        """
        tone_file = Path(self.templates_dir) / "tone_rules" / f"{tone}.md"
        if tone_file.exists():
            with open(tone_file, 'r', encoding='utf-8') as f:
                content = f.read()
            self.sections.append((f"tone_{tone}", content))
            self.metadata['tone'] = tone
        else:
            raise FileNotFoundError(f"Tone rule not found: {tone_file}")
        return self

    def add_constraints(self) -> "PromptBuilder":
        """添加约束条件"""
        constraints_file = Path(self.templates_dir) / "constraints.md"
        if constraints_file.exists():
            with open(constraints_file, 'r', encoding='utf-8') as f:
                content = f.read()
            self.sections.append(("constraints", content))
            self.metadata['has_constraints'] = True
        return self

    def add_structure_constraint(self, final_snapshot: Dict) -> "PromptBuilder":
        """
        添加结构约束（基于final_structure_snapshot）

        Args:
            final_snapshot: final_structure_snapshot.json 内容
        """
        h2_list = final_snapshot.get("top_level_sections", [])
        constraint_text = f"""
## 本次改写的结构锁定

### 必须保留的h2标题（顺序不可改变）
"""
        for i, section in enumerate(h2_list, 1):
            constraint_text += f"\n{i}. {section['title']}"

        constraint_text += f"""

### 锚点清单

总锚点数: {len(final_snapshot.get('anchors', []))}

必须保留的锚点:
"""
        for anchor in final_snapshot.get('anchors', []):
            constraint_text += f"- {anchor['type']}: {anchor['description']}\n"

        self.sections.append(("structure_constraint", constraint_text))
        return self

    def build(self) -> str:
        """
        构建最终的Prompt

        Returns:
            完整的Rewrite Prompt
        """
        prompt_parts = [
            self._build_header(),
            "\n\n".join([content for _, content in self.sections]),
            self._build_footer()
        ]

        return "\n\n".join(prompt_parts)

    def _build_header(self) -> str:
        """构建Prompt头部"""
        platform = self.metadata.get('platform', 'unknown')
        tone = self.metadata.get('tone', 'unknown')
        return f"""# Rewrite 任务 Prompt

**版本**: {platform.upper()} - {tone.upper()}
**生成时间**: {self._get_timestamp()}

## 任务描述

你的任务是将初稿改写为特定平台和特定语气的版本。
改写过程中必须遵循以下规则，分别适用于不同的维度:
"""

    def _build_footer(self) -> str:
        """构建Prompt脚注"""
        return """\n\n## 最终检查清单

在提交改写结果前，请确保:

1. ✅ 所有h2标题保留且顺序不变
2. ✅ 所有{{image:}}、{{link:}}、{{ref:}}锚点保留
3. ✅ 字数在目标范围内
4. ✅ 语气与版本定义相符
5. ✅ 所有数据与原文一致
6. ✅ 不包含禁用词汇

---

**提示**: 如有冲突（如字数vs内容完整），按以下优先级:
结构 > 内容完整 > 字数 > 语气微调
"""

    @staticmethod
    def _get_timestamp() -> str:
        """获取当前时间戳"""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


if __name__ == "__main__":
    # 示例使用
    builder = PromptBuilder()

    # 构建 WeChat Hot 版本 Prompt
    try:
        prompt = (builder
            .add_base_rules()
            .add_platform_rule("wechat")
            .add_tone_rule("hot")
            .add_constraints()
            .build())

        print("=" * 70)
        print("WeChat Hot 版本 Prompt (前500字):")
        print("=" * 70)
        print(prompt[:500])
        print("\n... (省略中间部分) ...\n")
        print(prompt[-200:])
        print("\n" + "=" * 70)
        print(f"总长度: {len(prompt)} 字")

    except FileNotFoundError as e:
        print(f"错误: {e}")
        print("\n提示: 请确保rewrite_modules目录结构如下:")
        print("""
        rewrite_modules/
        ├── base_rules.md
        ├── platform_rules/
        │   ├── wechat.md
        │   └── xiaohongshu.md
        ├── tone_rules/
        │   ├── hot.md
        │   └── normal.md
        └── constraints.md
        """)
