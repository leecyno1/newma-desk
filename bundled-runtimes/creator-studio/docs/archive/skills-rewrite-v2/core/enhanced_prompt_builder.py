#!/usr/bin/env python3
"""
EnhancedPromptBuilder: 增强版Prompt生成器

改进内容：
1. 字数严格控制（分段预算）
2. 锚点强制保留
3. h2绝对保留
4. 详细质量检查清单
"""

import re
from pathlib import Path
from typing import Dict, List, Tuple
from dataclasses import dataclass


@dataclass
class SegmentBudget:
    """分段字数预算"""
    segment_name: str
    target_words: int
    min_words: int
    max_words: int


class EnhancedPromptBuilder:
    """增强版Prompt生成器"""

    def __init__(self, templates_dir: str = None):
        if templates_dir is None:
            templates_dir = str(Path(__file__).parent.parent / "templates")
        self.templates_dir = templates_dir
        self.enhanced_template_file = Path(templates_dir) / "REWRITE_PROMPT_ENHANCED.md"

    def build_enhanced_prompt(
        self,
        platform: str,
        tone: str,
        original_text: str,
        target_word_count: int,
        min_word_count: int,
        max_word_count: int,
        primary_audience: str = ""
    ) -> str:
        """
        生成完整的增强版Prompt

        Args:
            platform: 平台名称
            tone: 语气
            original_text: 原始文稿
            target_word_count: 目标字数
            min_word_count: 最小字数
            max_word_count: 最大字数
            primary_audience: 目标受众

        Returns:
            完整的改写Prompt
        """
        # 提取原文信息
        h2_list = self._extract_h2_titles(original_text)
        anchors = self._extract_anchors(original_text)

        # 计算分段预算
        segment_budgets = self._calculate_segment_budgets(
            target_word_count,
            len(h2_list)
        )

        # 加载基础Prompt规则
        base_rules = self._load_rules_content("base_rules.md")
        platform_rules = self._load_rules_content(f"platform_rules/{platform}.md")
        tone_rules = self._load_rules_content(f"tone_rules/{tone}.md")
        rules_combined = f"{base_rules}\n\n{platform_rules}\n\n{tone_rules}"

        # 生成h2映射表
        h2_mapping = self._generate_h2_mapping_table(h2_list)

        # 生成锚点列表
        anchor_list = self._generate_anchor_list(anchors)

        # 生成分段预算表
        budget_table = self._generate_budget_table(segment_budgets)

        # 生成检查清单
        checklist = self._generate_quality_checklist(
            target_word_count,
            min_word_count,
            max_word_count,
            len(h2_list),
            len(anchors),
            segment_budgets
        )

        # 组装最终Prompt
        tolerance_pct = int(((max_word_count - target_word_count) / target_word_count) * 100)

        prompt = f"""你是一名专业的内容改写专家，擅长为不同平台和受众改写文章。

========== 任务定义 ==========

改写任务：将以下文章改写为{platform}的{tone}版本

平台：{platform}（微信公众号/小红书/抖音）
语气：{tone}（热点版/常规版）
目标受众：{primary_audience}

========== 字数约束（严格执行）==========

⚠️ CRITICAL: 字数控制是本次改写的首要约束

整体目标：{target_word_count}字（中文字符）
允许范围：{min_word_count}-{max_word_count}字（偏差±{tolerance_pct}%）

❌ 超出范围的改写无效，必须重做
❌ 字数超标将导致质量评分直接降低2分

分段字数预算：
{budget_table}

✅ 确保每个分段都在预算范围内
✅ 如果某段内容不足，宁可删减次要细节，也不要超出字数上限
✅ 优先保留：核心论点 > 关键数据 > 支撑论据 > 修辞润色

========== 锚点保留（强制）==========

原文中以下{len(anchors)}个锚点必须原样保留在改写后的文章中：

{anchor_list}

锚点保留规则：
✅ 同一类型的锚点（如image）在改写后仍然存在
✅ 位置可以在相同h2内移动，但不能跨越h2
✅ {{{{}}}}标记的内容必须原文照抄，不能修改
❌ 绝对禁止删除任何锚点
❌ 绝对禁止修改锚点内容

⚠️ 锚点保留率要求：≥80%（低于此标准将导致质量评分降低）

========== h2标题映射（绝对保留）==========

原文h2数量：{len(h2_list)}个
改写后h2数量：必须保持{len(h2_list)}个

h2标题保留映射表（顺序不可变）：

{h2_mapping}

❌ 禁止操作：
- 删除任何h2
- 合并h2
- 重新排列h2顺序
- 修改h2标题文本

========== 改写规则 ==========

### 规则集合：{platform} + {tone}

{rules_combined}

### 内容完整性

✅ 必须保留的内容：
- 所有关键事实
- 所有数据和统计
- 所有引用和论据
- 所有论点的因果关系

❌ 禁止删除：
- 原文中的关键论点
- 任何h2级别的主观点
- 支撑论点的具体数据
- 引用的权威观点

### 语气转换

✅ 在改写时调整以下内容：
- 用词选择（弱词→强词，或反之）
- 修辞手法（比喻、对比等）
- 句式结构（长句→短句，或反之）
- 段落长度（根据平台特性调整）
- 开篇和结尾风格

❌ 禁止改变：
- 核心观点
- 立场和态度
- 逻辑关系
- 结构层级

========== 质量检查清单 ==========

完成改写后，必须逐项检查：

{checklist}

⚠️ 质量目标：≥8.0分（满分10分）
- 字数控制：±{tolerance_pct}%以内（权重30%）
- 锚点保留：≥80%（权重20%）
- 结构完整：h2数量一致（权重20%）
- 内容质量：论证逻辑清晰（权重30%）

========== 原始文稿 ==========

{original_text}

========== 开始改写 ==========

请执行上述改写任务。记住：
- 字数必须符合范围
- 所有h2必须保留
- 所有锚点必须保留
- 内容完整性不能被破坏
- 语气必须符合定义

改写完成后，仅输出改写后的完整文稿，不包含任何解释或检查结果。
"""

        return prompt

    def _extract_h2_titles(self, text: str) -> List[str]:
        """提取文本中的h2标题"""
        pattern = r"^## (.+?)$"
        matches = re.findall(pattern, text, re.MULTILINE)
        return matches

    def _extract_anchors(self, text: str) -> List[Tuple[str, str]]:
        """提取所有锚点：返回(类型, 内容)元组"""
        pattern = r"{{(image|link|ref):\s*(.+?)}}"
        matches = re.findall(pattern, text, re.DOTALL)
        return matches

    def _load_rules_content(self, rule_file: str) -> str:
        """加载规则文件内容"""
        rule_path = Path(self.templates_dir) / "rewrite_modules" / rule_file
        if rule_path.exists():
            with open(rule_path, 'r', encoding='utf-8') as f:
                return f.read()
        return f"// {rule_file} 规则文件未找到"

    def _calculate_segment_budgets(
        self,
        total_words: int,
        h2_count: int
    ) -> List[SegmentBudget]:
        """计算分段字数预算"""
        budgets = []

        # 开篇
        intro_target = int(total_words * 0.1)  # 10%
        budgets.append(SegmentBudget(
            "开篇",
            intro_target,
            int(intro_target * 0.8),
            int(intro_target * 1.2)
        ))

        # 各h2段
        h2_target = int((total_words * 0.8) / h2_count)  # 80% 平均分配
        for i in range(h2_count):
            budgets.append(SegmentBudget(
                f"第{i+1}个h2",
                h2_target,
                int(h2_target * 0.8),
                int(h2_target * 1.2)
            ))

        # 结尾
        conclusion_target = int(total_words * 0.1)  # 10%
        budgets.append(SegmentBudget(
            "结尾",
            conclusion_target,
            int(conclusion_target * 0.8),
            int(conclusion_target * 1.2)
        ))

        return budgets

    def _generate_h2_mapping_table(self, h2_list: List[str]) -> str:
        """生成h2映射表"""
        table = "| 序号 | 原文h2 | 改写后h2 | 必须保留？ |\n"
        table += "|------|--------|---------|----------|\n"
        for i, h2 in enumerate(h2_list, 1):
            table += f"| {i} | {h2} | {h2} | ✅ 原样保留 |\n"
        return table

    def _generate_anchor_list(self, anchors: List[Tuple[str, str]]) -> str:
        """生成锚点列表"""
        if not anchors:
            return "（无锚点）"

        anchor_list = ""
        for anchor_type, content in anchors:
            anchor_list += f"- {{{{{anchor_type}: {content.strip()}}}}}  → 必须保留\n"
        return anchor_list

    def _generate_budget_table(self, budgets: List[SegmentBudget]) -> str:
        """生成分段预算表"""
        table = "| 段落 | 目标字数 | 范围 |\n"
        table += "|------|--------|------|\n"
        for budget in budgets:
            table += f"| {budget.segment_name} | {budget.target_words} | {budget.min_words}-{budget.max_words} |\n"
        return table

    def _generate_quality_checklist(
        self,
        target_words: int,
        min_words: int,
        max_words: int,
        h2_count: int,
        anchor_count: int,
        budgets: List[SegmentBudget]
    ) -> str:
        """生成质量检查清单"""
        checklist = "### 字数检查\n"
        checklist += f"- [ ] 整体字数：______字（范围：{min_words}-{max_words}）✅/❌\n"

        for budget in budgets:
            checklist += f"- [ ] {budget.segment_name}：______字（范围：{budget.min_words}-{budget.max_words}）✅/❌\n"

        checklist += f"\n### h2保留检查\n"
        checklist += f"- [ ] h2数量：原稿{h2_count}个 = 改写[___]个 ✅/❌\n"
        checklist += f"- [ ] h2顺序：完全保持 ✅/❌\n"
        checklist += f"- [ ] h2文本：完全相同 ✅/❌\n"

        checklist += f"\n### 锚点保留检查\n"
        checklist += f"- [ ] 锚点总数：原稿{anchor_count}个 = 改写[___]个 ✅/❌\n"
        checklist += f"- [ ] 所有锚点内容是否被修改：✅ 未修改 / ❌ 被修改\n"

        checklist += f"\n### 内容完整性检查\n"
        checklist += f"- [ ] 所有关键事实已保留 ✅/❌\n"
        checklist += f"- [ ] 所有数据和统计已保留 ✅/❌\n"
        checklist += f"- [ ] 所有论点映射关系已保留 ✅/❌\n"
        checklist += f"- [ ] 没有删除任何h2级别的主观点 ✅/❌\n"

        return checklist


if __name__ == "__main__":
    # 示例用法
    builder = EnhancedPromptBuilder()

    sample_text = """# 示例文章

这是开篇内容。

## 第一个h2

这是第一个h2下的内容。{{image: 示例图片}}

## 第二个h2

这是第二个h2下的内容。{{link: https://example.com|示例链接}}

## 第三个h2

这是第三个h2下的内容。{{ref: 参考来源}}
"""

    prompt = builder.build_enhanced_prompt(
        platform="微信公众号",
        tone="热点版",
        original_text=sample_text,
        target_word_count=1300,
        min_word_count=1100,
        max_word_count=1500,
        primary_audience="知识精英、投资者"
    )

    print("Generated Prompt:")
    print("=" * 80)
    print(prompt[:500] + "...")
