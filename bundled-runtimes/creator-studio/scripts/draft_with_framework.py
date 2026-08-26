#!/usr/bin/env python3
"""
框架驱动的 Draft 生成脚本
根据 brief 推荐的框架生成结构化初稿
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime

# 导入框架和策略加载器
sys.path.insert(0, str(Path(__file__).parent))
from framework_strategy_loader import load_framework_guide, load_strategy_guide


def load_selected_topics(brief_dir: str) -> dict:
    """
    加载 brief 环节选择的选题

    Args:
        brief_dir: brief 输出目录

    Returns:
        selected_topics.json 的内容
    """
    topics_file = Path(brief_dir) / "selected_topics.json"

    if not topics_file.exists():
        raise FileNotFoundError(f"找不到选题文件: {topics_file}")

    with open(topics_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def generate_draft_prompt(topic: dict) -> str:
    """
    生成 Draft 的 AI prompt

    Args:
        topic: 选题信息

    Returns:
        AI prompt 字符串
    """
    # 提取选题信息
    title = topic.get('title', '')
    core_argument = topic.get('core_argument', '')
    why_now = topic.get('why_now', '')
    target_audience = topic.get('target_audience', '')
    evidence_needs = topic.get('evidence_needs', [])
    evidence_sources = topic.get('evidence_sources', [])
    framework = topic.get('recommended_framework', '热点解读型')
    strategy = topic.get('recommended_strategy', '角度发现')

    # 加载框架和策略指南
    framework_guide = load_framework_guide(framework)
    strategy_guide = load_strategy_guide(strategy)

    prompt = f"""使用 {framework} 框架写一篇财经/科技分析文章：

【选题信息】
标题：{title}
核心论点：{core_argument}
为什么值得写：{why_now}
目标读者：{target_audience}

【框架结构】
{framework_guide}

【内容增强策略】
{strategy_guide}

【证据需求】
{chr(10).join(f"- {need}" for need in evidence_needs)}

【证据来源】
{chr(10).join(f"- {source}" for source in evidence_sources)}

【写作要求】
1. 严格遵循 {framework} 框架的结构
2. 应用 {strategy} 策略增强内容
3. 每段都有具体证据和数据支撑
4. 字数：3000-5000 字
5. 事实准确，所有数据和引用可追溯
6. 使用 Markdown 格式，H2 标题分段
7. 语言风格：专业、客观、有洞察力

【框架应用要点】
- 开头：按框架要求设置钩子（痛点共鸣/悬念/价值承诺等）
- 主体：按框架结构展开（2-4 个 H2 段落）
- 结尾：按框架要求收束（行动引导/情绪共振/总结等）

【策略应用要点】
- 如果是"角度发现"：确保有独特的切入点，不重复主流观点
- 如果是"密度强化"：每段都有具体工具/数字/步骤，避免空话
- 如果是"细节锚定"：用真实细节（对话/数字/画面）增强代入感
- 如果是"真实体感"：引用真实用户反馈和评价

【输出格式】
# {title}

[开头段落，按框架要求]

## [第一部分标题]

[内容...]

## [第二部分标题]

[内容...]

## [第三部分标题]

[内容...]

[结尾段落，按框架要求]

---

【引用清单】
1. [数据/观点来源]
2. [数据/观点来源]
...
"""

    return prompt


def validate_draft_quality(draft: str, topic: dict) -> dict:
    """
    验证 draft 质量

    Args:
        draft: 生成的初稿
        topic: 选题信息

    Returns:
        验证结果字典
    """
    results = {
        'passed': True,
        'issues': [],
        'warnings': []
    }

    # 检查字数
    word_count = len(draft.replace(" ", "").replace("\n", ""))
    if word_count < 3000:
        results['passed'] = False
        results['issues'].append(f"字数不足：{word_count} < 3000")
    elif word_count > 6000:
        results['warnings'].append(f"字数过多：{word_count} > 6000，建议精简")

    # 检查结构
    h2_count = draft.count('\n## ')
    if h2_count < 2:
        results['passed'] = False
        results['issues'].append(f"H2 标题过少：{h2_count} < 2，结构不完整")
    elif h2_count > 6:
        results['warnings'].append(f"H2 标题过多：{h2_count} > 6，可能过于分散")

    # 检查是否有引用清单
    if '【引用清单】' not in draft and '引用清单' not in draft:
        results['warnings'].append("缺少引用清单，建议补充数据来源")

    # 检查是否有空话
    empty_phrases = [
        "需要注意", "建议大家", "非常重要", "值得关注",
        "可以考虑", "应该重视", "不容忽视"
    ]

    empty_count = sum(draft.count(phrase) for phrase in empty_phrases)
    if empty_count > 5:
        results['warnings'].append(f"空话过多（{empty_count}处），建议增加具体内容")

    return results


def save_draft(draft: str, topic: dict, output_dir: str) -> str:
    """
    保存 draft 到文件

    Args:
        draft: 生成的初稿
        topic: 选题信息
        output_dir: 输出目录

    Returns:
        保存的文件路径
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # 生成文件名（使用 topic_id）
    topic_id = topic.get('topic_id', 'unknown')
    filename = f"{topic_id}_draft.md"
    filepath = output_path / filename

    # 保存文件
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(draft)

    return str(filepath)


def save_draft_manifest(topic: dict, draft_path: str, validation: dict, output_dir: str):
    """
    保存 draft manifest

    Args:
        topic: 选题信息
        draft_path: draft 文件路径
        validation: 验证结果
        output_dir: 输出目录
    """
    manifest = {
        'topic_id': topic.get('topic_id'),
        'title': topic.get('title'),
        'framework': topic.get('recommended_framework'),
        'strategy': topic.get('recommended_strategy'),
        'draft_path': draft_path,
        'generated_at': datetime.now().isoformat(),
        'validation': validation,
        'word_count': len(open(draft_path, 'r', encoding='utf-8').read().replace(" ", "").replace("\n", "")),
        'status': 'pending_editor_review'
    }

    manifest_path = Path(output_dir) / f"{topic.get('topic_id')}_draft_manifest.json"
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


def generate_draft_for_topic(topic: dict, output_dir: str) -> dict:
    """
    为单个选题生成 draft

    Args:
        topic: 选题信息
        output_dir: 输出目录

    Returns:
        生成结果
    """
    print(f"\n正在生成 draft：{topic.get('title')}")
    print(f"框架：{topic.get('recommended_framework')}")
    print(f"策略：{topic.get('recommended_strategy')}")

    # 生成 prompt
    prompt = generate_draft_prompt(topic)

    print("\n=== AI Prompt ===")
    print(prompt)
    print("\n=== 请使用 Claude 生成 draft ===")
    print("将上面的 prompt 发送给 Claude，然后将生成的内容粘贴到下面：")
    print("（输入 'skip' 跳过此选题）")
    print("-" * 80)

    # 读取用户输入的 draft
    lines = []
    while True:
        try:
            line = input()
            if line.strip().lower() == 'skip':
                return {'status': 'skipped', 'topic_id': topic.get('topic_id')}
            if line.strip() == '---END---':
                break
            lines.append(line)
        except EOFError:
            break

    draft = '\n'.join(lines)

    if not draft.strip():
        print("错误：draft 内容为空")
        return {'status': 'error', 'topic_id': topic.get('topic_id'), 'error': 'empty_draft'}

    # 验证质量
    validation = validate_draft_quality(draft, topic)

    print("\n=== 质量验证 ===")
    print(f"通过：{validation['passed']}")
    if validation['issues']:
        print("问题：")
        for issue in validation['issues']:
            print(f"  - {issue}")
    if validation['warnings']:
        print("警告：")
        for warning in validation['warnings']:
            print(f"  - {warning}")

    # 保存 draft
    draft_path = save_draft(draft, topic, output_dir)
    print(f"\nDraft 已保存：{draft_path}")

    # 保存 manifest
    save_draft_manifest(topic, draft_path, validation, output_dir)

    return {
        'status': 'success',
        'topic_id': topic.get('topic_id'),
        'draft_path': draft_path,
        'validation': validation
    }


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='框架驱动的 Draft 生成')
    parser.add_argument('--brief-dir', required=True, help='Brief 输出目录')
    parser.add_argument('--output-dir', required=True, help='Draft 输出目录')
    parser.add_argument('--topic-id', help='只生成指定 topic_id 的 draft')

    args = parser.parse_args()

    # 加载选题
    print(f"加载选题：{args.brief_dir}")
    topics_data = load_selected_topics(args.brief_dir)

    # 获取已选择的选题
    selected_topic_ids = topics_data.get('selected_topics', [])
    candidate_topics = topics_data.get('candidate_topics', [])

    # 如果 selected_topics 是 topic_id 数组，从 candidate_topics 中查找
    if selected_topic_ids and isinstance(selected_topic_ids[0], str):
        selected_topics = [t for t in candidate_topics if t.get('topic_id') in selected_topic_ids]
    else:
        # 如果 selected_topics 已经是 topic 对象数组，直接使用
        selected_topics = selected_topic_ids if selected_topic_ids else candidate_topics

    if not selected_topics:
        print("错误：没有找到任何选题")
        return

    print(f"找到 {len(selected_topics)} 个选题")

    # 过滤选题
    if args.topic_id:
        selected_topics = [t for t in selected_topics if t.get('topic_id') == args.topic_id]
        if not selected_topics:
            print(f"错误：找不到 topic_id={args.topic_id} 的选题")
            return

    # 生成 draft
    results = []
    for topic in selected_topics:
        result = generate_draft_for_topic(topic, args.output_dir)
        results.append(result)

    # 总结
    print("\n" + "=" * 80)
    print("Draft 生成完成")
    print("=" * 80)

    success_count = sum(1 for r in results if r['status'] == 'success')
    skipped_count = sum(1 for r in results if r['status'] == 'skipped')
    error_count = sum(1 for r in results if r['status'] == 'error')

    print(f"成功：{success_count}")
    print(f"跳过：{skipped_count}")
    print(f"错误：{error_count}")

    if success_count > 0:
        print(f"\nDraft 文件保存在：{args.output_dir}")


if __name__ == "__main__":
    main()
