#!/usr/bin/env python3
"""
DNA Engine - 核心引擎实现

功能：
1. 风格DNA管理和应用
2. 结构DNA模板生成
3. 质量DNA评分
4. DNA智能选择
"""

import yaml
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum


class StyleType(Enum):
    """风格类型枚举"""
    LUXUN = "luxun"
    LEMON = "lemon"
    ACADEMIC = "academic"
    HOT = "hot"
    NORMAL = "normal"


class StructureType(Enum):
    """结构类型枚举"""
    PAS = "PAS"
    PCIS = "PCIS"
    CCS = "CCS"
    TIMELINE = "Timeline"
    MULTI_DIMENSION = "MultiDimension"
    CASE_DRIVEN = "CaseDriven"
    DATA_DRIVEN = "DataDriven"
    OPINION_CLASH = "OpinionClash"
    DEEP_DIVE = "DeepDive"
    QUICK_SCAN = "QuickScan"


@dataclass
class StyleDNAConfig:
    """风格DNA配置"""
    style_id: str
    name: str
    sentence_length: str
    tone_keywords: List[str]
    rhetoric: List[str]
    opening_style: str
    closing_style: str
    emoji_usage: str
    characteristics: List[str] = field(default_factory=list)


@dataclass
class StructureDNAConfig:
    """结构DNA配置"""
    template_id: str
    name: str
    sections: List[Dict]
    total_word_ratio: float = 1.0


@dataclass
class QualityScore:
    """质量评分"""
    dimension: str
    score: float
    weight: float
    details: str = ""


@dataclass
class QualityReport:
    """质量报告"""
    overall_score: float
    quality_level: str
    dimension_scores: List[QualityScore]
    suggestions: List[str]
    is_passed: bool


class DNAEngine:
    """DNA引擎主类"""

    def __init__(self, dna_dir: str = None):
        if dna_dir is None:
            dna_dir = str(Path(__file__).parent.parent / "dna")
        self.dna_dir = Path(dna_dir)
        self.config = self._load_config()
        self.styles = self._load_styles()
        self.structures = self._load_structures()

    def _load_config(self) -> Dict:
        """加载DNA配置"""
        config_file = self.dna_dir / "dna_config.yaml"
        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        return {}

    def _load_styles(self) -> Dict[str, StyleDNAConfig]:
        """加载所有风格DNA"""
        styles = {}
        style_dir = self.dna_dir / "style_dna"

        # 定义5种基础风格
        style_configs = {
            "luxun": StyleDNAConfig(
                style_id="luxun",
                name="鲁迅风",
                sentence_length="短句为主（8-15字）",
                tone_keywords=["揭露", "暴露", "撕开", "刺破", "戳穿"],
                rhetoric=["反讽", "对比", "排比"],
                opening_style="直击痛点",
                closing_style="留白反思",
                emoji_usage="极少（≤1个/文）",
                characteristics=["犀利批判", "一针见血", "短句紧凑"]
            ),
            "lemon": StyleDNAConfig(
                style_id="lemon",
                name="柠檬风",
                sentence_length="中等（12-20字）",
                tone_keywords=["其实", "说白了", "简单来说", "打个比方"],
                rhetoric=["类比", "比喻", "拟人"],
                opening_style="轻松引入",
                closing_style="友好互动",
                emoji_usage="适中（3-5个/文）",
                characteristics=["轻松幽默", "亲和力强", "口语化"]
            ),
            "academic": StyleDNAConfig(
                style_id="academic",
                name="学术风",
                sentence_length="长句（20-35字）",
                tone_keywords=["根据", "研究表明", "数据显示", "分析认为"],
                rhetoric=["因果论证", "对比分析", "归纳演绎"],
                opening_style="问题陈述",
                closing_style="结论总结",
                emoji_usage="无",
                characteristics=["严谨专业", "逻辑清晰", "数据支撑"]
            ),
            "hot": StyleDNAConfig(
                style_id="hot",
                name="热点风",
                sentence_length="短中结合（10-18字）",
                tone_keywords=["突然", "紧急", "首次", "罕见", "暴露", "颠覆"],
                rhetoric=["冲突对比", "数据冲击", "悬念设置"],
                opening_style="冲突/数据/反常",
                closing_style="转发激励",
                emoji_usage="适中（2-4个/文）",
                characteristics=["激情澎湃", "冲突强烈", "传播导向"]
            ),
            "normal": StyleDNAConfig(
                style_id="normal",
                name="常规风",
                sentence_length="中等（15-25字）",
                tone_keywords=["值得注意", "需要关注", "可以看到", "实际上"],
                rhetoric=["SPA结构", "分点论述", "逻辑递进"],
                opening_style="背景+问题",
                closing_style="总结+展望",
                emoji_usage="少量（1-2个/文）",
                characteristics=["平衡理性", "可读性强", "信息密度适中"]
            )
        }

        return style_configs

    def _load_structures(self) -> Dict[str, StructureDNAConfig]:
        """加载所有结构DNA"""
        structures = {
            "PAS": StructureDNAConfig(
                template_id="PAS",
                name="问题-分析-方案",
                sections=[
                    {"name": "问题陈述", "word_ratio": 0.15},
                    {"name": "深度分析", "word_ratio": 0.60},
                    {"name": "解决方案", "word_ratio": 0.25}
                ]
            ),
            "PCIS": StructureDNAConfig(
                template_id="PCIS",
                name="现象-原因-影响-对策",
                sections=[
                    {"name": "现象描述", "word_ratio": 0.20},
                    {"name": "原因剖析", "word_ratio": 0.30},
                    {"name": "影响分析", "word_ratio": 0.30},
                    {"name": "应对策略", "word_ratio": 0.20}
                ]
            ),
            "CCS": StructureDNAConfig(
                template_id="CCS",
                name="对比-冲突-解决",
                sections=[
                    {"name": "对比呈现", "word_ratio": 0.25},
                    {"name": "冲突揭示", "word_ratio": 0.50},
                    {"name": "解决路径", "word_ratio": 0.25}
                ]
            ),
            "Timeline": StructureDNAConfig(
                template_id="Timeline",
                name="时间线叙事",
                sections=[
                    {"name": "背景铺垫", "word_ratio": 0.15},
                    {"name": "事件演进", "word_ratio": 0.60},
                    {"name": "当前状态与展望", "word_ratio": 0.25}
                ]
            ),
            "MultiDimension": StructureDNAConfig(
                template_id="MultiDimension",
                name="多维度分析",
                sections=[
                    {"name": "引言", "word_ratio": 0.10},
                    {"name": "维度1", "word_ratio": 0.25},
                    {"name": "维度2", "word_ratio": 0.25},
                    {"name": "维度3", "word_ratio": 0.25},
                    {"name": "综合结论", "word_ratio": 0.15}
                ]
            )
        }
        return structures

    def get_style(self, style_id: str) -> Optional[StyleDNAConfig]:
        """获取风格DNA"""
        return self.styles.get(style_id)

    def get_structure(self, structure_id: str) -> Optional[StructureDNAConfig]:
        """获取结构DNA"""
        return self.structures.get(structure_id)

    def select_style(self, topic_type: str, audience: str, platform: str) -> str:
        """智能选择风格"""
        rules = {
            ("政治", "知识精英", "微信"): "luxun",
            ("科技", "年轻人", "小红书"): "lemon",
            ("金融", "投资者", "微信"): "academic",
            ("热点", "大众", "抖音"): "hot",
        }
        return rules.get((topic_type, audience, platform), "normal")

    def select_structure(self, content_type: str, word_count: int) -> str:
        """智能选择结构"""
        if content_type == "分析":
            return "PCIS" if word_count > 1500 else "PAS"
        elif content_type == "对比":
            return "CCS"
        elif content_type == "叙事":
            return "Timeline"
        else:
            return "MultiDimension"

    def generate_structure_prompt(self, structure_id: str, word_count: int) -> str:
        """生成结构化Prompt"""
        structure = self.get_structure(structure_id)
        if not structure:
            return ""

        prompt = f"# 文章结构要求\n\n"
        prompt += f"结构模板：{structure.name}\n"
        prompt += f"总字数：{word_count}字\n\n"
        prompt += f"## 各部分字数分配\n\n"

        for section in structure.sections:
            section_words = int(word_count * section["word_ratio"])
            prompt += f"- {section['name']}：约{section_words}字\n"

        return prompt

    def evaluate_quality(
        self,
        text: str,
        target_style: str,
        target_structure: str,
        target_word_count: int,
        anchors_original: int,
        anchors_preserved: int
    ) -> QualityReport:
        """评估质量"""
        scores = []

        # 维度1: 结构完整性（简化评估）
        structure_score = self._evaluate_structure(text, target_structure)
        scores.append(QualityScore("结构完整性", structure_score, 0.25))

        # 维度2: 内容质量（简化评估）
        content_score = self._evaluate_content(text)
        scores.append(QualityScore("内容质量", content_score, 0.25))

        # 维度3: 文风一致性（简化评估）
        tone_score = self._evaluate_tone(text, target_style)
        scores.append(QualityScore("文风一致性", tone_score, 0.20))

        # 维度4: 可读性（简化评估）
        readability_score = self._evaluate_readability(text)
        scores.append(QualityScore("可读性", readability_score, 0.15))

        # 维度5: 锚点完整性
        anchor_score = (anchors_preserved / anchors_original * 10) if anchors_original > 0 else 10.0
        scores.append(QualityScore("锚点完整性", anchor_score, 0.10))

        # 维度6: 字数合规性
        actual_count = len(text)
        deviation = abs(actual_count - target_word_count) / target_word_count
        wordcount_score = max(0, 10 - deviation * 50)
        scores.append(QualityScore("字数合规性", wordcount_score, 0.05))

        # 计算总分
        overall = sum(s.score * s.weight for s in scores)

        # 判定等级
        if overall >= 9.0:
            level = "Excellent"
        elif overall >= 8.0:
            level = "Ready"
        elif overall >= 7.0:
            level = "Review"
        elif overall >= 6.0:
            level = "Needs Work"
        else:
            level = "Reject"

        # 生成建议
        suggestions = []
        for score in scores:
            if score.score < 7.0:
                suggestions.append(f"改进{score.dimension}")

        return QualityReport(
            overall_score=overall,
            quality_level=level,
            dimension_scores=scores,
            suggestions=suggestions,
            is_passed=(overall >= 7.0)
        )

    def _evaluate_structure(self, text: str, target_structure: str) -> float:
        """评估结构（简化版）"""
        # 简化：检查h2数量
        h2_count = text.count("\n## ")
        if 3 <= h2_count <= 5:
            return 9.0
        elif 2 <= h2_count <= 6:
            return 7.0
        else:
            return 5.0

    def _evaluate_content(self, text: str) -> float:
        """评估内容（简化版）"""
        # 简化：检查是否有数据、引用
        has_data = any(char.isdigit() for char in text)
        has_quotes = "{{" in text or "「" in text

        score = 6.0
        if has_data:
            score += 2.0
        if has_quotes:
            score += 2.0
        return min(score, 10.0)

    def _evaluate_tone(self, text: str, target_style: str) -> float:
        """评估文风（简化版）"""
        style = self.get_style(target_style)
        if not style:
            return 7.0

        # 简化：检查关键词出现
        keyword_count = sum(1 for kw in style.tone_keywords if kw in text)
        return min(6.0 + keyword_count * 0.5, 10.0)

    def _evaluate_readability(self, text: str) -> float:
        """评估可读性（简化版）"""
        # 简化：检查段落数量
        paragraphs = text.split("\n\n")
        para_count = len([p for p in paragraphs if len(p) > 50])

        if 5 <= para_count <= 15:
            return 8.0
        elif 3 <= para_count <= 20:
            return 7.0
        else:
            return 6.0


if __name__ == "__main__":
    # 测试DNA引擎
    engine = DNAEngine()

    # 测试风格选择
    style_id = engine.select_style("金融", "投资者", "微信")
    print(f"推荐风格: {style_id}")

    style = engine.get_style(style_id)
    print(f"风格名称: {style.name}")
    print(f"特征: {style.characteristics}")

    # 测试结构选择
    structure_id = engine.select_structure("分析", 1500)
    print(f"\n推荐结构: {structure_id}")

    structure = engine.get_structure(structure_id)
    print(f"结构名称: {structure.name}")

    # 生成结构Prompt
    prompt = engine.generate_structure_prompt(structure_id, 1500)
    print(f"\n结构Prompt:\n{prompt}")
