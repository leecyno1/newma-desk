#!/usr/bin/env python3
"""
QualityScorer: 多维度质量评分系统

功能: 对改写版本进行6维度评分，生成质量报告
维度: 语气一致性、结构保真度、可读性、平台适配度、字数合规、锚点保留
输出: 单一综合评分 + 维度拆分 + 改进建议
"""

import re
import json
from dataclasses import dataclass, asdict
from typing import Dict, List, Tuple, Optional
from collections import Counter


@dataclass
class DimensionScore:
    """单个维度的评分"""
    name: str
    score: float  # 0-10
    weight: float  # 权重
    details: str  # 详细说明
    suggestions: List[str]  # 改进建议


@dataclass
class QualityReport:
    """质量评分报告"""
    overall_score: float  # 综合评分
    dimension_scores: List[DimensionScore]
    status: str  # "✅ Ready", "⚠️ Review", "❌ Needs Work"
    is_passed: bool  # 是否通过硬门槛
    summary: str


class QualityScorer:
    """
    质量评分器

    使用方式:
        scorer = QualityScorer(
            platform="wechat",
            tone="hot",
            original_doc={...},
            final_snapshot={...}
        )
        report = scorer.score(rewritten_text)
    """

    # 字数目标
    WORD_COUNT_TARGETS = {
        ("wechat", "hot"): (1100, 1500, 1300),
        ("wechat", "normal"): (800, 1200, 1000),
        ("xiaohongshu", "hot"): (750, 1050, 900),
        ("xiaohongshu", "normal"): (500, 800, 650),
    }

    # 语气关键词
    HOT_KEYWORDS = {
        "strong_verbs": ["暴露", "颠覆", "潜伏", "入侵", "破冰", "逆袭", "翻盘",
                         "突破", "内卷", "打破", "瓦解", "重塑", "洗牌", "逆转"],
        "impact_words": ["意想不到的", "违反直觉的", "出乎意料的", "黑天鹅级的",
                        "系统性的", "致命的", "不可逆的", "临界点的"],
        "soft_words": ["据悉", "有报道", "听说", "好像", "可能"],  # 禁用
    }

    NORMAL_KEYWORDS = {
        "structure_words": ["首先", "其次", "最后", "一方面", "另一方面", "虽然", "但同时"],
        "soft_words": ["据悉", "有报道", "听说", "好像", "可能"],  # 禁用
    }

    def __init__(
        self,
        platform: str,
        tone: str,
        original_doc: str,
        final_snapshot: Dict
    ):
        """
        初始化评分器

        Args:
            platform: "wechat" or "xiaohongshu"
            tone: "hot" or "normal"
            original_doc: 原始初稿文本
            final_snapshot: final_structure_snapshot.json
        """
        self.platform = platform
        self.tone = tone
        self.original_doc = original_doc
        self.final_snapshot = final_snapshot

        self.original_h2_list = self._extract_h2_titles(original_doc)
        self.original_anchors = self._extract_anchors(original_doc)

    def score(self, rewritten_text: str) -> QualityReport:
        """
        对改写文本进行评分

        Returns:
            QualityReport: 详细评分报告
        """
        scores = [
            self._score_tone_consistency(rewritten_text),
            self._score_structure_fidelity(rewritten_text),
            self._score_readability(rewritten_text),
            self._score_platform_fit(rewritten_text),
            self._score_word_count(rewritten_text),
            self._score_anchor_preservation(rewritten_text),
        ]

        # 计算加权综合评分
        overall_score = sum(s.score * s.weight for s in scores) / sum(s.weight for s in scores)

        # 判断是否通过硬门槛
        is_passed = self._check_hard_gates(rewritten_text, scores)

        # 生成状态
        if is_passed and overall_score >= 8.0:
            status = "✅ Ready"
        elif is_passed and overall_score >= 7.0:
            status = "⚠️ Review"
        else:
            status = "❌ Needs Work"

        summary = self._generate_summary(overall_score, scores, is_passed)

        return QualityReport(
            overall_score=round(overall_score, 1),
            dimension_scores=scores,
            status=status,
            is_passed=is_passed,
            summary=summary
        )

    def _score_tone_consistency(self, text: str) -> DimensionScore:
        """评分：语气一致性"""
        score = 5.0
        details = ""
        suggestions = []

        if self.tone == "hot":
            # 检查强动词
            strong_verb_count = sum(text.count(verb) for verb in self.HOT_KEYWORDS["strong_verbs"])
            strong_verb_density = strong_verb_count / (len(text) / 500)  # per 500字

            if strong_verb_density >= 3:
                score += 2.0
                details = f"✓ 强动词密度良好 ({strong_verb_density:.1f}/500字)"
            elif strong_verb_density >= 1:
                score += 1.0
                details = f"⚠ 强动词密度偏低 ({strong_verb_density:.1f}/500字，目标≥3)"
                suggestions.append("增加强动词使用，如'暴露''颠覆''潜伏'等")
            else:
                details = f"✗ 强动词缺失 ({strong_verb_density:.1f}/500字)"
                suggestions.append("文本过于平和，添加冲击力较强的动词")

            # 检查禁用软词汇
            soft_word_count = sum(text.count(w) for w in self.HOT_KEYWORDS["soft_words"])
            if soft_word_count > 0:
                score -= 1.0 * min(soft_word_count, 3)  # 最多扣3分
                suggestions.append(f"删除'{self.HOT_KEYWORDS['soft_words']}'等软词汇 (发现{soft_word_count}处)")

            # 检查开篇Hook
            first_100_chars = text[:100]
            has_hook = any(signal in first_100_chars for signal in ["但是", "然而", "错了", "意想不到"])
            if has_hook:
                score += 1.0
                details += "\n✓ 开篇Hook设置良好"
            else:
                suggestions.append("强化开篇Hook（冲突/数据/反常信号）")

        else:  # normal
            # 检查权衡表述
            balance_phrases = ["一方面", "另一方面", "虽然", "但同时", "固然", "不过"]
            balance_count = sum(text.count(p) for p in balance_phrases)
            if balance_count >= 2:
                score += 2.0
                details = f"✓ 权衡表述充分 ({balance_count}处)"
            elif balance_count >= 1:
                score += 1.0
                details = f"⚠ 权衡表述有限 ({balance_count}处，目标≥2)"
                suggestions.append("添加更多权衡表述，显示理性分析")
            else:
                details = "✗ 权衡表述缺失"
                suggestions.append("添加'一方面...另一方面'等权衡表述")

            # 检查禁用词汇
            soft_word_count = sum(text.count(w) for w in self.HOT_KEYWORDS["soft_words"])
            if soft_word_count > 0:
                score -= 0.5 * min(soft_word_count, 3)
                suggestions.append(f"减少模糊表述 (发现{soft_word_count}处)")

        return DimensionScore(
            name="语气一致性",
            score=min(10.0, max(0.0, score)),
            weight=0.2,
            details=details,
            suggestions=suggestions
        )

    def _score_structure_fidelity(self, text: str) -> DimensionScore:
        """评分：结构保真度"""
        rewritten_h2_list = self._extract_h2_titles(text)

        # 检查h2数量
        h2_match = len(rewritten_h2_list) == len(self.original_h2_list)
        h2_order_match = rewritten_h2_list == self.original_h2_list

        score = 10.0
        details = ""
        suggestions = []

        if not h2_match:
            score -= 3.0
            details += f"✗ h2数量不符 (原文:{len(self.original_h2_list)}个, 改写:{len(rewritten_h2_list)}个)\n"
            suggestions.append(f"h2数量必须匹配原文 (原文{len(self.original_h2_list)}个)")

        if h2_match and not h2_order_match:
            score -= 2.0
            details += f"✗ h2顺序改变\n"
            suggestions.append("h2标题顺序必须保持不变")
        elif h2_match and h2_order_match:
            details = "✓ h2完全保留且顺序正确\n"

        return DimensionScore(
            name="结构保真度",
            score=min(10.0, max(0.0, score)),
            weight=0.25,  # 权重最高
            details=details.strip(),
            suggestions=suggestions
        )

    def _score_readability(self, text: str) -> DimensionScore:
        """评分：可读性"""
        # 计算平均段落长度
        paragraphs = [p.strip() for p in text.split('\n\n') if p.strip() and not p.startswith('#')]
        if not paragraphs:
            return DimensionScore("可读性", 5.0, 0.15, "无法计算段落", [])

        avg_para_length = sum(len(p) for p in paragraphs) / len(paragraphs)

        # 计算平均句子长度
        sentences = re.split(r'[。！？]', text)
        avg_sentence_length = sum(len(s) for s in sentences) / len(sentences) if sentences else 0

        score = 7.0
        details = f"平均段落长度: {avg_para_length:.0f}字\n平均句子长度: {avg_sentence_length:.0f}字"
        suggestions = []

        # 根据平台调整可读性标准
        if self.platform == "wechat":
            target_para = 200
            if 150 <= avg_para_length <= 250:
                score += 2.0
                details += "\n✓ 段落长度适中"
            elif avg_para_length < 150:
                details += "\n⚠ 段落偏短"
                suggestions.append("段落长度150-250字较佳")
            else:
                score -= 1.0
                details += "\n✗ 段落过长"
                suggestions.append("段落超250字，建议拆分")
        else:  # xiaohongshu
            if 100 <= avg_para_length <= 150:
                score += 2.0
                details += "\n✓ 短段落设置良好"
            elif avg_para_length > 200:
                score -= 2.0
                details += "\n✗ XHS需要更短的段落"
                suggestions.append("XHS偏好100-150字短段落，请拆分")
            else:
                score += 1.0

        # 检查连续被动句（禁止连续3个）
        passive_pattern = r'被[^，。]*[，。]'
        passive_count = len(re.findall(passive_pattern, text))
        if passive_count > 3:
            score -= 1.0
            suggestions.append(f"减少被动句使用 (检测到{passive_count}个)")

        return DimensionScore(
            name="可读性",
            score=min(10.0, max(0.0, score)),
            weight=0.15,
            details=details,
            suggestions=suggestions
        )

    def _score_platform_fit(self, text: str) -> DimensionScore:
        """评分：平台适配度"""
        score = 7.0
        details = ""
        suggestions = []

        if self.platform == "wechat":
            # 检查加粗关键词
            bold_count = len(re.findall(r'\*\*[^*]+\*\*', text))
            if 1 <= bold_count <= 5:
                score += 1.5
                details = f"✓ 加粗关键词数合理 ({bold_count}个)"
            elif bold_count > 5:
                details = f"⚠ 加粗过多 ({bold_count}个，建议≤3/段)"
                suggestions.append("减少加粗使用，保持视觉简洁")
            else:
                details = "⚠ 缺少加粗关键词"
                suggestions.append("适度使用**加粗**突出关键概念")

            # 检查emoji
            emoji_count = len(re.findall(r'[😊-🙏🎉-🎊✨-✿]', text))  # 简化emoji检测
            if self.tone == "hot":
                if 4 <= emoji_count <= 6:
                    score += 1.0
                    details += f"\n✓ Emoji密度适当 ({emoji_count}个)"
                elif emoji_count > 6:
                    score -= 0.5
                    details += f"\n⚠ Emoji过多 ({emoji_count}个，目标4-6)"
                    suggestions.append("减少emoji数量至4-6个")

        else:  # xiaohongshu
            # 检查标签
            hashtag_count = len(re.findall(r'#\w+', text))
            if self.tone == "hot":
                if 3 <= hashtag_count <= 5:
                    score += 1.5
                    details = f"✓ 标签数量合理 ({hashtag_count}个)"
                else:
                    score -= 1.0
                    details = f"✗ 标签数量不符 ({hashtag_count}个，目标3-5)"
                    suggestions.append(f"调整标签数至3-5个")

            # 检查段落长度（XHS需要短段）
            paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
            long_paras = [p for p in paragraphs if len(p) > 200]
            if long_paras:
                score -= 1.0
                details += f"\n✗ 发现{len(long_paras)}个超长段落"
                suggestions.append("XHS偏好短段落（100-150字），请优化")

        return DimensionScore(
            name="平台适配度",
            score=min(10.0, max(0.0, score)),
            weight=0.15,
            details=details,
            suggestions=suggestions
        )

    def _score_word_count(self, text: str) -> DimensionScore:
        """评分：字数合规"""
        word_count = len(text)

        key = (self.platform, self.tone)
        if key not in self.WORD_COUNT_TARGETS:
            return DimensionScore("字数合规", 8.0, 0.1, "无目标范围", [])

        min_count, max_count, target = self.WORD_COUNT_TARGETS[key]

        if min_count <= word_count <= max_count:
            score = 10.0
            deviation = abs(word_count - target) / target
            if deviation < 0.05:
                details = f"✓ 字数完美 ({word_count}字，目标{target})"
            else:
                score -= deviation * 2  # 偏差越大扣分越多
                details = f"✓ 字数符合 ({word_count}字，范围{min_count}-{max_count})"
        else:
            score = max(0.0, 10.0 - abs(word_count - target) / target * 5)
            details = f"✗ 字数超范围 ({word_count}字，目标范围{min_count}-{max_count})"

        suggestions = [] if score >= 8.0 else [f"调整字数至{min_count}-{max_count}字"]

        return DimensionScore(
            name="字数合规",
            score=min(10.0, max(0.0, score)),
            weight=0.1,
            details=details,
            suggestions=suggestions
        )

    def _score_anchor_preservation(self, text: str) -> DimensionScore:
        """评分：锚点保留"""
        rewritten_anchors = self._extract_anchors(text)

        # 检查每种锚点
        original_image_count = len([a for a in self.original_anchors if a[0] == "image"])
        rewritten_image_count = len([a for a in rewritten_anchors if a[0] == "image"])

        original_link_count = len([a for a in self.original_anchors if a[0] == "link"])
        rewritten_link_count = len([a for a in rewritten_anchors if a[0] == "link"])

        score = 10.0
        details = ""
        suggestions = []

        if rewritten_image_count == original_image_count:
            details += f"✓ 图片锚点完整 ({rewritten_image_count}个)"
        else:
            score -= 2.0
            details += f"✗ 图片锚点缺失 (原文{original_image_count}个, 改写{rewritten_image_count}个)"
            suggestions.append(f"必须保留所有{original_image_count}个{{{{image:}}}}锚点")

        if rewritten_link_count == original_link_count:
            details += f"\n✓ 链接锚点完整 ({rewritten_link_count}个)"
        else:
            score -= 1.5
            details += f"\n⚠ 链接锚点缺失 (原文{original_link_count}个, 改写{rewritten_link_count}个)"
            suggestions.append(f"保留所有{{{{link:}}}}锚点")

        return DimensionScore(
            name="锚点保留",
            score=min(10.0, max(0.0, score)),
            weight=0.15,
            details=details,
            suggestions=suggestions
        )

    def _check_hard_gates(self, text: str, scores: List[DimensionScore]) -> bool:
        """检查硬门槛（必须通过）"""
        # 结构和锚点必须100%正确
        structure_score = next(s for s in scores if s.name == "结构保真度")
        anchor_score = next(s for s in scores if s.name == "锚点保留")

        return structure_score.score >= 7.0 and anchor_score.score >= 8.0

    def _generate_summary(self, overall_score: float, scores: List[DimensionScore], is_passed: bool) -> str:
        """生成评分摘要"""
        if overall_score >= 8.5:
            base = "优秀，可直接发布"
        elif overall_score >= 8.0:
            base = "良好，可以发布"
        elif overall_score >= 7.0:
            base = "及格，建议轻微修改后发布"
        else:
            base = "不及格，需要重写"

        worst_dimension = min(scores, key=lambda x: x.score)
        return f"{base}。主要改进方向：{worst_dimension.name} (当前{worst_dimension.score}/10)"

    @staticmethod
    def _extract_h2_titles(text: str) -> List[str]:
        """提取h2标题"""
        pattern = r'^## (.+)$'
        matches = re.findall(pattern, text, re.MULTILINE)
        return matches

    @staticmethod
    def _extract_anchors(text: str) -> List[Tuple[str, str]]:
        """提取锚点"""
        anchors = []
        # 提取{{image: ...}}
        image_pattern = r'{{image: ([^}]+)}}'
        anchors.extend([("image", m) for m in re.findall(image_pattern, text)])
        # 提取{{link: ...}}
        link_pattern = r'{{link: ([^}]+)}}'
        anchors.extend([("link", m) for m in re.findall(link_pattern, text)])
        # 提取{{ref: ...}}
        ref_pattern = r'{{ref: ([^}]+)}}'
        anchors.extend([("ref", m) for m in re.findall(ref_pattern, text)])
        return anchors


if __name__ == "__main__":
    # 示例
    original = """# 稳定币牌照落地

## 一、现状

2024年...{{image: 配图1}}

## 二、分析

机构入场...{{link: 链接|url}}

## 三、展望

未来...{{image: 配图2}}
    """

    rewritten = """# 稳定币牌照落地

## 一、现状

2024年，一个重要转折点来临了。{{image: 配图1}}
稳定币牌照正式落地，加密市场迎来大洗牌。

## 二、分析

这意味着什么？机构开始大举入场。{{link: 链接|url}}
传统金融巨头纷纷布局。这是前所未有的机会。

## 三、展望

未来3个月会发生什么？{{image: 配图2}}
投资者需要做好准备。这个信号不容忽视。
    """

    final_snapshot = {
        "top_level_sections": [
            {"title": "一、现状"},
            {"title": "二、分析"},
            {"title": "三、展望"}
        ],
        "anchors": [
            {"type": "image", "description": "配图1"},
            {"type": "link", "description": "链接"},
            {"type": "image", "description": "配图2"}
        ]
    }

    scorer = QualityScorer(
        platform="wechat",
        tone="hot",
        original_doc=original,
        final_snapshot=final_snapshot
    )

    report = scorer.score(rewritten)

    print("\n" + "="*70)
    print(f"质量评分报告 | {report.status}")
    print("="*70)
    print(f"\n综合评分: {report.overall_score}/10")
    print(f"\n{report.summary}")
    print(f"\n硬门槛: {'✅ 通过' if report.is_passed else '❌ 未通过'}")

    print(f"\n维度评分:\n")
    for score in report.dimension_scores:
        print(f"  {score.name}: {score.score}/10 (权重{score.weight})")
        print(f"    {score.details}")
        if score.suggestions:
            for suggestion in score.suggestions:
                print(f"    💡 {suggestion}")
        print()
