"""
经理画像提取服务 - 从 AI 报告和调研纪要中提取结构化画像数据
"""
import os
import json
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class ProfileExtractor:
    """从 AI 报告和调研纪要中提取基金经理的结构化画像"""

    # 风格标签映射（基于因子暴露）
    STYLE_MAPPING = {
        "growth": ["growth", "growth_style", "风格:成长"],
        "value": ["value", "value_style", "风格:价值"],
        "blend": ["blend", "平衡", "风格:均衡"],
        "quality": ["quality", "质量", "质量因子"],
        "momentum": ["momentum", "动量", "动量因子"],
        "small_cap": ["small_cap", "小盘", "规模:小盘"],
        "large_cap": ["large_cap", "大盘", "规模:大盘"],
    }

    # 能力圈行业关键词
    INDUSTRY_KEYWORDS = [
        "新能源", "光伏", "风电", "储能", "锂电", "电池",
        "半导体", "芯片", "集成电路", "半导体设备",
        "消费电子", "汽车电子", "人工智能", "AI", "算力",
        "医药", "医疗", "生物医药", "医疗器械", "CXO",
        "白酒", "食品饮料", "消费", "餐饮",
        "银行", "券商", "保险", "非银金融",
        "房地产", "建筑", "建材", "家电",
        "化工", "新材料", "钢铁", "煤炭", "有色",
        "军工", "国防", "航空航天",
        "互联网", "软件", "云计算", "SaaS",
        "港股", "海外", "美国", "全球",
    ]

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._client = None

    @property
    def client(self):
        if self._client is None and self.api_key:
            try:
                from anthropic import Anthropic
                self._client = Anthropic(api_key=self.api_key)
            except ImportError:
                logger.warning("Anthropic SDK not available")
        return self._client

    def extract_profile(self, report_content: str, manager_data: Dict[str, Any] = None, style_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        从基金经理研究报告内容中提取结构化画像数据

        Args:
            report_content: 基金经理研究报告内容
            manager_data: 基金经理基本信息
            style_data: 风格数据（Barra 因子暴露）

        Returns:
            结构化的画像字典
        """
        profile = {
            "core_philosophy": "",           # 核心投资理念
            "stock_selection_logic": "",     # 选股逻辑
            "position_management": "",        # 持仓管理方式
            "competence_advantages": "",      # 能力优势
            "competence_boundaries": "",     # 能力边界
            "focus_industries": [],          # 能力圈行业
            "style_label": "",               # 风格标签
            "philosophy_behavior_consistency": 0,  # 理念-行为一致性 (0-100)
            "risk_awareness": "",            # 风险意识
            "key_insights": [],              # 关键洞察
            "suitable_investors": "",       # 适合投资者类型
            "investment_horizon": "",         # 建议投资周期
        }

        if not self.client:
            # 使用规则提取
            profile = self._rule_based_extraction(report_content, manager_data, style_data)
        else:
            # 使用 AI 提取
            profile = self._ai_extraction(report_content)

        # 从风格数据补充
        if style_data:
            profile["style_label"] = self._infer_style_from_factors(style_data)

        return profile

    def _rule_based_extraction(self, content: str, manager_data: Dict, style_data: Dict) -> Dict[str, Any]:
        """基于规则的提取（当 AI 不可用时）"""
        profile = {
            "core_philosophy": self._extract_section(content, ["投资理念", "投资哲学", "核心理念"]),
            "stock_selection_logic": self._extract_section(content, ["选股逻辑", "选股方法", "股票选择"]),
            "position_management": self._extract_section(content, ["持仓管理", "仓位管理", "组合管理"]),
            "competence_advantages": self._extract_section(content, ["优势", "擅长", "能力优势"]),
            "competence_boundaries": self._extract_section(content, ["劣势", "不足", "能力边界", "风险点"]),
            "focus_industries": self._extract_industries(content),
            "style_label": "",
            "philosophy_behavior_consistency": 70,  # 默认值
            "risk_awareness": self._extract_section(content, ["风险", "回撤", "风险控制"]),
            "key_insights": self._extract_key_points(content),
            "suitable_investors": self._extract_section(content, ["适合投资者", "适用人群"]),
            "investment_horizon": self._extract_section(content, ["投资周期", "建议持有", "持有期限"]),
        }

        # 提取一致性评分
        consistency = self._extract_number(content, ["一致性", "理念行为", "知行合一"])
        if consistency:
            profile["philosophy_behavior_consistency"] = consistency

        return profile

    def _ai_extraction(self, content: str) -> Dict[str, Any]:
        """使用 AI 从报告中提取画像"""
        prompt = """请从以下基金经理分析报告中提取结构化画像数据。

请以 JSON 格式返回，字段说明：
- core_philosophy: 核心投资理念（一句话概括，50字以内）
- stock_selection_logic: 选股逻辑和方法（100字以内）
- position_management: 持仓管理方式（50字以内）
- competence_advantages: 能力优势（2-3个要点，100字以内）
- competence_boundaries: 能力边界和劣势（2-3个要点，100字以内）
- focus_industries: 能力圈行业列表（数组，最多5个）
- style_label: 风格标签（growth/value/blend/quality/momentum）
- philosophy_behavior_consistency: 理念-行为一致性评分（0-100整数）
- risk_awareness: 风险意识描述（50字以内）
- suitable_investors: 适合投资者类型（50字以内）
- investment_horizon: 建议投资周期（30字以内）

报告内容：
{}

请直接返回 JSON，不要有其他内容：""".format(content[:8000])

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-7-20250514",
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            result_text = response.content[0].text.strip()
            # 尝试解析 JSON
            if result_text.startswith("```"):
                result_text = result_text.split("```")[1]
                if result_text.startswith("json"):
                    result_text = result_text[4:]
            return json.loads(result_text)
        except Exception as e:
            logger.error(f"AI extraction failed: {e}")
            return self._rule_based_extraction(content, None, None)

    def _extract_section(self, content: str, keywords: List[str]) -> str:
        """提取包含关键词的段落"""
        lines = content.split("\n")
        for i, line in enumerate(lines):
            for kw in keywords:
                if kw in line:
                    # 获取后续几行作为内容
                    section_lines = [line]
                    for j in range(i + 1, min(i + 5, len(lines))):
                        next_line = lines[j].strip()
                        if not next_line:
                            break
                        if next_line.startswith("#"):
                            break
                        section_lines.append(next_line)
                    return " ".join(section_lines).strip()
        return ""

    def _extract_industries(self, content: str) -> List[str]:
        """提取关注的行业"""
        industries = []
        for ind in self.INDUSTRY_KEYWORDS:
            if ind in content:
                industries.append(ind)
        return list(set(industries))[:5]

    def _extract_number(self, content: str, keywords: List[str]) -> Optional[int]:
        """提取数字（用于一致性评分等）"""
        import re
        for kw in keywords:
            if kw in content:
                match = re.search(r"(\d+)\s*%", content)
                if match:
                    return min(100, max(0, int(match.group(1))))
                match = re.search(r"(\d+)\s*[分/]100", content)
                if match:
                    return min(100, max(0, int(match.group(1))))
        return None

    def _extract_key_points(self, content: str) -> List[str]:
        """提取关键洞察"""
        points = []
        lines = content.split("\n")
        for line in lines:
            line = line.strip()
            if line.startswith("-") or line.startswith("•"):
                point = line.lstrip("-•").strip()
                if len(point) > 10 and len(point) < 100:
                    points.append(point)
            if len(points) >= 5:
                break
        return points[:5]

    def _infer_style_from_factors(self, style_data: Dict[str, Any]) -> str:
        """从 Barra 因子暴露推断风格"""
        factor_scores = {}

        # 常见因子
        factor_names = [
            ("size", "small_cap", "large_cap"),
            ("bp", "value", "growth"),
            ("growth", "growth", "value"),
            ("momentum", "momentum", None),
            ("quality", "quality", None),
            ("volatility", "low_vol", "high_vol"),
        ]

        for factor, positive, negative in factor_names:
            value = style_data.get(factor, style_data.get(factor.lower(), 0))
            if value is None:
                continue
            try:
                val = float(value)
                if positive and val > 0.3:
                    factor_scores[positive] = val
                if negative and val < -0.3:
                    factor_scores[negative] = -val
            except (ValueError, TypeError):
                continue

        # 确定主导风格
        if not factor_scores:
            return "blend"

        dominant = max(factor_scores.items(), key=lambda x: abs(x[1]))
        if abs(dominant[1]) < 0.2:
            return "blend"
        return dominant[0]

    def generate_profile_summary(self, profile: Dict[str, Any]) -> str:
        """生成画像摘要文本"""
        parts = []

        if profile.get("core_philosophy"):
            parts.append("投资理念: " + profile["core_philosophy"])

        if profile.get("style_label"):
            style_names = {
                "growth": "成长型", "value": "价值型", "blend": "均衡型",
                "quality": "质量型", "momentum": "动量型",
                "small_cap": "小盘型", "large_cap": "大盘型"
            }
            parts.append("风格: " + style_names.get(profile["style_label"], profile["style_label"]))

        if profile.get("focus_industries"):
            industries = ", ".join(profile["focus_industries"][:3])
            parts.append("能力圈: " + industries)

        if profile.get("competence_advantages"):
            parts.append("优势: " + profile["competence_advantages"][:50] + "...")

        return "\n".join(parts)


# 全局单例
_profile_extractor: Optional[ProfileExtractor] = None


def get_profile_extractor() -> ProfileExtractor:
    global _profile_extractor
    if _profile_extractor is None:
        _profile_extractor = ProfileExtractor()
    return _profile_extractor
