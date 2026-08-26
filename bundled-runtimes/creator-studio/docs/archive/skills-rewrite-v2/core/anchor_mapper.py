#!/usr/bin/env python3
"""
AnchorMapper: 素材锚点智能映射系统

功能: 检测初稿中的锚点，在改写版本中自动映射到语义相似的位置，
      生成详细的对账报告，标识缺失/移位的锚点

输出:
  1. 锚点映射表
  2. Anchor Reconciliation Report
  3. 缺失锚点警告
"""

import re
import json
from dataclasses import dataclass, asdict
from typing import Dict, List, Tuple, Optional
from enum import Enum


class AnchorStatus(Enum):
    """锚点状态"""
    PRESERVED = "保留"  # 位置基本不变
    RELOCATED = "移位"  # 位置改变但找到相似内容
    MISSING = "缺失"    # 未找到对应内容
    DUPLICATED = "重复"  # 多次出现


@dataclass
class AnchorMapping:
    """单个锚点的映射关系"""
    anchor_type: str  # "image", "link", "ref"
    anchor_desc: str  # 锚点描述
    original_position: int  # 原文位置（段落号）
    rewritten_position: Optional[int]  # 改写版本位置
    status: AnchorStatus  # 映射状态
    similarity_score: float  # 语义相似度（0-1）
    suggestion: str  # 建议


@dataclass
class AnchorReport:
    """锚点对账报告"""
    total_anchors: int
    preserved_count: int
    relocated_count: int
    missing_count: int
    preserved_rate: float  # 保留率（%）
    mappings: List[AnchorMapping]
    summary: str


class AnchorMapper:
    """
    素材锚点智能映射器

    使用方式:
        mapper = AnchorMapper(original_doc, rewritten_doc)
        report = mapper.generate_report()
    """

    def __init__(self, original_doc: str, rewritten_doc: str):
        """
        初始化AnchorMapper

        Args:
            original_doc: 原始初稿
            rewritten_doc: 改写版本
        """
        self.original_doc = original_doc
        self.rewritten_doc = rewritten_doc

        self.original_anchors = self._extract_anchors_with_context(original_doc)
        self.rewritten_anchors = self._extract_anchors_with_context(rewritten_doc)

    def generate_report(self) -> AnchorReport:
        """
        生成锚点对账报告

        Returns:
            AnchorReport: 详细对账报告
        """
        mappings = []

        # 对于每个原文锚点，尝试在改写版本中找到对应
        for orig_anchor in self.original_anchors:
            mapping = self._map_single_anchor(orig_anchor)
            mappings.append(mapping)

        # 统计
        preserved = len([m for m in mappings if m.status == AnchorStatus.PRESERVED])
        relocated = len([m for m in mappings if m.status == AnchorStatus.RELOCATED])
        missing = len([m for m in mappings if m.status == AnchorStatus.MISSING])
        total = len(mappings)

        preserved_rate = (preserved + relocated) / total * 100 if total > 0 else 0

        summary = self._generate_summary(preserved, relocated, missing, total)

        return AnchorReport(
            total_anchors=total,
            preserved_count=preserved,
            relocated_count=relocated,
            missing_count=missing,
            preserved_rate=round(preserved_rate, 1),
            mappings=mappings,
            summary=summary
        )

    def _map_single_anchor(self, orig_anchor: Dict) -> AnchorMapping:
        """
        映射单个锚点

        Args:
            orig_anchor: 原文锚点（包含位置和上下文信息）

        Returns:
            AnchorMapping: 映射关系
        """
        anchor_type = orig_anchor["type"]
        anchor_desc = orig_anchor["description"]
        original_position = orig_anchor["paragraph_idx"]
        original_context = orig_anchor["context"]

        # 在改写版本中搜索最相似的段落
        best_match = None
        best_score = 0.0
        best_position = None

        for rewrit_anchor in self.rewritten_anchors:
            if rewrit_anchor["type"] == anchor_type:
                # 计算相似度
                similarity = self._calculate_similarity(
                    original_context,
                    rewrit_anchor["context"]
                )

                if similarity > best_score:
                    best_score = similarity
                    best_match = rewrit_anchor
                    best_position = rewrit_anchor["paragraph_idx"]

        # 判断映射状态
        if best_score >= 0.7:  # 高相似度
            position_diff = abs(original_position - best_position) if best_position else 999

            if position_diff == 0:
                status = AnchorStatus.PRESERVED
                suggestion = "✓ 锚点保留在原位置"
            elif position_diff <= 2:
                status = AnchorStatus.RELOCATED
                suggestion = f"⚠️ 锚点移位{position_diff}段，但内容相关"
            else:
                status = AnchorStatus.RELOCATED
                suggestion = f"⚠️ 锚点移位{position_diff}段，需要手工验证"
        elif best_score >= 0.5:  # 中等相似度
            status = AnchorStatus.RELOCATED
            suggestion = "⚠️ 找到相关内容但相似度一般，建议手工检查"
        else:  # 无匹配
            status = AnchorStatus.MISSING
            suggestion = "❌ 未找到对应内容，需要手工补充或删除"
            best_position = None

        return AnchorMapping(
            anchor_type=anchor_type,
            anchor_desc=anchor_desc,
            original_position=original_position,
            rewritten_position=best_position,
            status=status,
            similarity_score=round(best_score, 2),
            suggestion=suggestion
        )

    def _calculate_similarity(self, context1: str, context2: str) -> float:
        """
        计算两段文本的语义相似度（简化版本，基于词汇重叠）

        Args:
            context1: 第一段上下文
            context2: 第二段上下文

        Returns:
            相似度得分（0-1）
        """
        # 分词（简单按空格和标点分割）
        def tokenize(text):
            # 移除标点和特殊符号，转小写
            import string
            translator = str.maketrans('', '', string.punctuation + '：；，。！？「」『』【】（）')
            text = text.translate(translator)
            return set(text.lower().split())

        tokens1 = tokenize(context1)
        tokens2 = tokenize(context2)

        if not tokens1 or not tokens2:
            return 0.0

        # Jaccard相似度
        intersection = len(tokens1 & tokens2)
        union = len(tokens1 | tokens2)

        return intersection / union if union > 0 else 0.0

    def _extract_anchors_with_context(self, doc: str) -> List[Dict]:
        """
        提取锚点及其上下文信息

        Args:
            doc: 文档

        Returns:
            锚点列表（包含位置和上下文）
        """
        anchors = []
        paragraphs = doc.split('\n\n')

        for para_idx, para in enumerate(paragraphs):
            if not para.strip():
                continue

            # 提取image锚点
            image_pattern = r'{{image: ([^}]+)}}'
            for match in re.finditer(image_pattern, para):
                anchors.append({
                    "type": "image",
                    "description": match.group(1),
                    "paragraph_idx": para_idx,
                    "context": para[:200]  # 前200字作为上下文
                })

            # 提取link锚点
            link_pattern = r'{{link: ([^}]+)}}'
            for match in re.finditer(link_pattern, para):
                anchors.append({
                    "type": "link",
                    "description": match.group(1),
                    "paragraph_idx": para_idx,
                    "context": para[:200]
                })

            # 提取ref锚点
            ref_pattern = r'{{ref: ([^}]+)}}'
            for match in re.finditer(ref_pattern, para):
                anchors.append({
                    "type": "ref",
                    "description": match.group(1),
                    "paragraph_idx": para_idx,
                    "context": para[:200]
                })

        return anchors

    def _generate_summary(self, preserved: int, relocated: int, missing: int, total: int) -> str:
        """
        生成对账报告摘要
        """
        if missing == 0:
            return f"✅ 完美：所有{total}个锚点保留或成功映射"
        elif missing <= total * 0.1:  # ≤10%缺失
            return f"⚠️ 良好：{total-missing}个锚点已保留/映射，{missing}个缺失（需手工补充）"
        else:
            return f"❌ 警告：{missing}个锚点缺失（占{missing/total*100:.0f}%），影响排版"


def print_reconciliation_report(report: AnchorReport):
    """
    打印格式化的锚点对账报告
    """
    print("\n" + "="*70)
    print("📌 素材锚点对账报告")
    print("="*70)

    print(f"\n总锚点数: {report.total_anchors}")
    print(f"保留率: {report.preserved_rate}%")
    print(f"  ✓ 保留: {report.preserved_count}")
    print(f"  ⚠️  移位: {report.relocated_count}")
    print(f"  ❌ 缺失: {report.missing_count}")

    print(f"\n摘要: {report.summary}")

    print(f"\n详细映射:\n")

    for mapping in report.mappings:
        status_emoji = {
            AnchorStatus.PRESERVED: "✓",
            AnchorStatus.RELOCATED: "⚠️ ",
            AnchorStatus.MISSING: "❌",
            AnchorStatus.DUPLICATED: "⚠️ "
        }[mapping.status]

        print(f"{status_emoji} {{{{  {mapping.anchor_type}: {mapping.anchor_desc}}}}}")
        print(f"   原位: 第{mapping.original_position}段", end="")
        if mapping.rewritten_position is not None:
            print(f" → 新位: 第{mapping.rewritten_position}段", end="")
            if mapping.rewritten_position != mapping.original_position:
                print(f" (移位{abs(mapping.rewritten_position - mapping.original_position)}段)", end="")
        else:
            print(" → 未找到", end="")
        print(f"\n   相似度: {mapping.similarity_score}")
        print(f"   建议: {mapping.suggestion}\n")

    print("="*70)


if __name__ == "__main__":
    # 示例
    original = """第1段：介绍AI新模型
这是关于新模型的介绍。
{{image: AI芯片配图}}

第2段：华尔街反应
华尔街对此反应热烈。{{link: 新闻链接|url}}

第3段：金融风险
这带来了三大风险。
{{image: 风险传导链条图}}
{{ref: Reuters报道}}
"""

    rewritten = """第1段：新模型冲击金融业
新AI模型引发华尔街紧急会议。
{{image: AI芯片配图}}

第2段：机构反应
多家机构表示关注。{{link: 新闻链接|url}}

第3段：深层分析
背后的三大风险值得关注。
监管困局、交易风险、系统性危机。
{{image: 风险传导链条图}}
"""

    mapper = AnchorMapper(original, rewritten)
    report = mapper.generate_report()
    print_reconciliation_report(report)
