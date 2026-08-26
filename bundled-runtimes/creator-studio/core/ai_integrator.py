#!/usr/bin/env python3
"""
AI Integrator - AI能力集成模块

功能：
1. 推理能力（Reasoning）
2. 写作能力（Writing）
3. 图片生成（Image Generation）
4. 视频脚本生成（Video Script）
"""

import anthropic
import openai
from typing import Dict, List, Optional
from pathlib import Path


class AIIntegrator:
    """AI能力集成器"""

    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.anthropic_client = anthropic.Anthropic()
        self.openai_client = openai.OpenAI()

    def reason(self, prompt: str, context: Dict = None) -> Dict:
        """
        推理能力

        用途：
        - 选题分析
        - 冲突识别
        - 论证结构生成
        - 逻辑检查
        """
        system_prompt = """你是一个专业的内容分析师，擅长：
1. 识别主题的核心冲突点
2. 构建严密的论证结构
3. 评估论据的充分性
4. 发现逻辑漏洞
"""

        message = self.anthropic_client.messages.create(
            model=self.config.get("reasoning_model", "claude-opus-4-6"),
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt}]
        )

        return {
            "reasoning": message.content[0].text,
            "model": message.model,
            "usage": message.usage
        }

    def write(self, prompt: str, style: str = "normal", max_tokens: int = 4096) -> Dict:
        """
        写作能力

        用途：
        - 初稿生成
        - 改写
        - 标题优化
        - 摘要生成
        """
        message = self.anthropic_client.messages.create(
            model=self.config.get("writing_model", "claude-sonnet-4-6"),
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}]
        )

        return {
            "content": message.content[0].text,
            "model": message.model,
            "usage": message.usage
        }

    def generate_image(self, prompt: str, style: str = "flat_illustration") -> Dict:
        """
        图片生成

        用途：
        - 配图生成
        - 封面生成
        - 图表可视化
        """
        style_prompts = {
            "flat_illustration": "flat design, minimalist, vector art, clean lines",
            "realistic": "photorealistic, high quality, detailed",
            "comic": "comic style, cartoon, humorous, expressive",
            "data_chart": "infographic, data visualization, clean, professional"
        }

        full_prompt = f"{prompt}, {style_prompts.get(style, '')}"

        response = self.openai_client.images.generate(
            model=self.config.get("image_model", "dall-e-3"),
            prompt=full_prompt,
            size="1792x1024",
            quality="standard",
            n=1
        )

        return {
            "url": response.data[0].url,
            "revised_prompt": response.data[0].revised_prompt
        }

    def generate_video_script(self, article: str, duration: int = 60) -> Dict:
        """
        视频脚本生成

        用途：
        - 短视频脚本
        - 分镜头脚本
        - 旁白文案
        """
        prompt = f"""基于以下文章，生成一个{duration}秒的短视频脚本。

文章内容：
{article}

要求：
1. 提取核心观点（3-5个）
2. 设计吸引人的开场（前3秒）
3. 分镜头描述（每个镜头5-10秒）
4. 旁白文案（口语化、节奏感强）
5. 视觉元素建议（图片、动画、文字）

输出格式：
```json
{{
  "title": "视频标题",
  "duration": {duration},
  "scenes": [
    {{
      "scene_number": 1,
      "duration": 5,
      "visual": "视觉描述",
      "narration": "旁白文案",
      "text_overlay": "屏幕文字"
    }}
  ]
}}
```
"""

        message = self.anthropic_client.messages.create(
            model=self.config.get("video_script_model", "claude-sonnet-4-6"),
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}]
        )

        return {
            "script": message.content[0].text,
            "model": message.model
        }

    def analyze_topic_conflict(self, topic: str, sources: List[str]) -> Dict:
        """
        分析主题冲突点

        用途：Brief环节的冲突分析
        """
        prompt = f"""分析以下主题的核心冲突点：

主题：{topic}

相关信息源：
{chr(10).join(f"- {s}" for s in sources)}

请识别：
1. 主要冲突轴（对立双方）
2. 冲突的本质（利益/价值观/认知）
3. 冲突的影响范围
4. 可能的发展方向

输出JSON格式。
"""

        result = self.reason(prompt)
        return {
            "conflict_analysis": result["reasoning"],
            "usage": result["usage"]
        }

    def generate_reasoning_chain(self, claim: str, evidence: List[str]) -> Dict:
        """
        生成论证链

        用途：Draft环节的ReasoningSheet生成
        """
        prompt = f"""构建严密的论证链：

核心论点：{claim}

可用证据：
{chr(10).join(f"- {e}" for e in evidence)}

请生成：
1. 论证步骤（逻辑递进）
2. 每步的支撑证据
3. 可能的反驳及回应
4. 论证强度评估

输出JSON格式。
"""

        result = self.reason(prompt)
        return {
            "reasoning_chain": result["reasoning"],
            "usage": result["usage"]
        }

    def optimize_title(self, article: str, platform: str, tone: str) -> List[str]:
        """
        标题优化

        用途：Publish环节的标题生成
        """
        platform_rules = {
            "wechat": "微信公众号标题：15-25字，包含关键词，吸引点击",
            "xiaohongshu": "小红书标题：20-35字，emoji适量，话题标签",
            "douyin": "抖音标题：10-20字，简短有力，悬念感"
        }

        tone_rules = {
            "hot": "热点风格：冲突词、数据、反常现象",
            "normal": "常规风格：平衡理性、信息明确"
        }

        prompt = f"""为以下文章生成5个标题候选：

文章摘要：
{article[:500]}...

平台：{platform}
风格：{tone}

规则：
- {platform_rules.get(platform, '')}
- {tone_rules.get(tone, '')}

输出5个标题，每个标题单独一行。
"""

        result = self.write(prompt, max_tokens=512)
        titles = [line.strip() for line in result["content"].split("\n") if line.strip()]
        return titles[:5]


if __name__ == "__main__":
    # 测试AI集成器
    integrator = AIIntegrator()

    # 测试推理能力
    print("测试推理能力...")
    result = integrator.analyze_topic_conflict(
        topic="稳定币牌照落地",
        sources=["监管加强", "市场需求", "传统金融入场"]
    )
    print(f"冲突分析: {result['conflict_analysis'][:200]}...")

    # 测试标题优化
    print("\n测试标题优化...")
    titles = integrator.optimize_title(
        article="稳定币牌照正式发放，传统金融机构纷纷入场...",
        platform="wechat",
        tone="hot"
    )
    print(f"生成标题: {titles}")
