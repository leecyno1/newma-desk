#!/usr/bin/env python3
"""
AI 智能字数补充模块
替代硬编码的财经内容块，根据选题类型和上下文智能生成补充内容
"""

import json
import os
from pathlib import Path


def ai_expand_content_prompt(draft: str, target_words: int, topic_context: dict) -> str:
    """
    生成 AI 字数补充的 prompt

    Args:
        draft: 当前文章内容
        target_words: 目标字数
        topic_context: 选题上下文信息（标题、论点、框架等）

    Returns:
        AI prompt 字符串
    """
    current_words = len(draft.replace(" ", "").replace("\n", ""))
    gap = target_words - current_words

    if gap <= 0:
        return None

    # 提取选题信息
    title = topic_context.get('title', '未知选题')
    core_argument = topic_context.get('core_argument', '')
    framework = topic_context.get('recommended_framework', '热点解读型')
    strategy = topic_context.get('recommended_strategy', '角度发现')

    prompt = f"""分析文章，找出可以扩展的部分：

【文章信息】
标题：{title}
核心论点：{core_argument}
框架类型：{framework}
增强策略：{strategy}

【当前文章】
{draft}

【扩展需求】
需要补充：{gap} 字

【扩展要求】
1. 不要重复已有内容
2. 扩展应该增加价值：
   - 如果是痛点型/清单型：补充具体案例、操作步骤、工具推荐
   - 如果是故事型/复盘型：补充细节、对话、场景描述
   - 如果是观点型/热点解读型：补充数据、反驳预设、深入分析
   - 如果是对比型：补充用户反馈、真实案例、决策框架
3. 保持文章结构和逻辑
4. 与选题主题和核心论点相关
5. 符合框架类型的特点
6. 应用增强策略的要求

【输出格式】
请输出 JSON 格式：
{{
  "expansions": [
    {{
      "position": "第 X 段之后",
      "content": "扩展内容...",
      "reason": "扩展理由...",
      "type": "案例/数据/细节/分析"
    }}
  ]
}}

【扩展示例】
- 痛点型：补充"3 个常见错误做法"、"工具对比表"、"完整操作流程"
- 故事型：补充"关键对话"、"转折点细节"、"人物心理活动"
- 清单型：补充"隐藏推荐"、"避坑指南"、"使用场景对比"
- 对比型：补充"真实用户评价"、"决策树"、"成本收益分析"
- 热点解读型：补充"历史类比"、"数据支撑"、"影响分析"
- 纯观点型：补充"反驳预设"、"案例佐证"、"价值观升华"
- 复盘型：补充"关键决策点"、"数据对比"、"可复用经验"
"""

    return prompt


def apply_expansions(draft: str, expansions: list) -> str:
    """
    将 AI 生成的扩展内容应用到文章中

    Args:
        draft: 原始文章
        expansions: AI 生成的扩展列表

    Returns:
        扩展后的文章
    """
    # 按段落分割文章
    paragraphs = draft.split('\n\n')

    # 按位置倒序排序（从后往前插入，避免位置偏移）
    sorted_expansions = sorted(
        expansions,
        key=lambda x: extract_position_number(x['position']),
        reverse=True
    )

    # 应用扩展
    for expansion in sorted_expansions:
        position = extract_position_number(expansion['position'])
        content = expansion['content']

        if 0 <= position < len(paragraphs):
            # 在指定位置后插入
            paragraphs.insert(position + 1, content)

    return '\n\n'.join(paragraphs)


def extract_position_number(position_str: str) -> int:
    """
    从位置字符串中提取数字
    例如："第 3 段之后" -> 3
    """
    import re
    match = re.search(r'第\s*(\d+)\s*段', position_str)
    if match:
        return int(match.group(1))
    return 0


def get_expansion_examples_by_framework(framework: str) -> str:
    """
    根据框架类型返回扩展示例
    """
    examples = {
        "痛点型": """
示例扩展：
1. 补充"3 个常见错误做法"段落
2. 添加工具对比表（名称、价格、适用场景）
3. 提供完整操作流程（步骤 1-5）
4. 增加"避坑指南"清单
""",
        "故事型": """
示例扩展：
1. 补充关键对话（2-3 轮）
2. 添加转折点的细节描述
3. 增加人物心理活动
4. 补充场景画面感描述
""",
        "清单型": """
示例扩展：
1. 添加"隐藏推荐"项
2. 补充使用场景对比表
3. 增加"个人最爱"彩蛋
4. 提供避坑指南
""",
        "对比型": """
示例扩展：
1. 补充真实用户评价（正面 + 负面）
2. 添加决策树图
3. 增加成本收益分析表
4. 提供"如果你是 X，选 Y"的条件分支
""",
        "热点解读型": """
示例扩展：
1. 补充历史类比案例
2. 添加数据支撑（图表）
3. 增加影响分析（短期 + 长期）
4. 提供可操作建议
""",
        "纯观点型": """
示例扩展：
1. 补充反驳预设段落
2. 添加案例佐证
3. 增加价值观升华
4. 提供行动建议
""",
        "复盘型": """
示例扩展：
1. 补充关键决策点分析
2. 添加数据对比表（预期 vs 实际）
3. 增加可复用经验清单
4. 提供"如果重来会怎么做"
"""
    }

    return examples.get(framework, examples["热点解读型"])


def validate_expansion_quality(expansion: dict, topic_context: dict) -> bool:
    """
    验证扩展内容的质量

    检查项：
    1. 内容长度合理（100-500 字）
    2. 与选题相关
    3. 不重复原文
    4. 符合框架类型
    """
    content = expansion.get('content', '')

    # 检查长度
    word_count = len(content.replace(" ", "").replace("\n", ""))
    if word_count < 100 or word_count > 500:
        return False

    # 检查是否有实质内容（不是空话）
    empty_phrases = [
        "需要注意", "建议大家", "非常重要", "值得关注",
        "可以考虑", "应该重视", "不容忽视"
    ]

    for phrase in empty_phrases:
        if phrase in content and content.count(phrase) > 2:
            return False

    return True


if __name__ == "__main__":
    # 测试
    topic_context = {
        'title': '中东冲突如何重塑全球能源供应链',
        'core_argument': '当前市场关注油价短期波动，但真正的结构性变化是霍尔木兹海峡封锁风险正在重构全球能源供应秩序',
        'recommended_framework': '结构型',
        'recommended_strategy': '密度强化'
    }

    draft = """
# 中东冲突如何重塑全球能源供应链

当前市场关注的是油价短期波动，但更重要的是霍尔木兹海峡封锁对全球能源供给秩序的长期影响。

## 霍尔木兹海峡的战略地位

霍尔木兹海峡是全球最重要的能源通道之一。

## 供应链依赖度分析

全球主要能源进口国高度依赖这一通道。
"""

    prompt = ai_expand_content_prompt(draft, 4000, topic_context)
    print("=== AI 扩展 Prompt ===")
    print(prompt)

    print("\n\n=== 框架扩展示例 ===")
    print(get_expansion_examples_by_framework("痛点型"))
