"""Deterministic topic tags for fund-manager research memos.

These tags describe what a memo discusses. They are intentionally separate
from manager style labels and never feed fund scoring.
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple


class ResearchMemoViewpointTaxonomy:
    TOPIC_ORDER = (
        "A股",
        "港股",
        "债市",
        "科技",
        "医药",
        "消费",
        "周期",
        "新能源",
        "金融地产",
        "信用债",
        "利率债",
        "久期",
        "杠杆",
        "资金利率",
        "政策",
        "转债",
    )

    PATTERNS: Dict[str, Tuple[str, ...]] = {
        "A股": (
            r"(?<![A-Za-z])A股(?![A-Za-z])",
            r"沪深\s*\d+",
            r"中证\s*(?:A?500|1000|2000|300|800)",
            r"上证(?:指数|综指)?",
            r"深证(?:指数|成指)?",
            r"创业板",
            r"科创板",
        ),
        "港股": (
            r"港股",
            r"恒生(?:指数|科技|国企)?",
            r"南下资金",
        ),
        "债市": (
            r"债市",
            r"债券市场",
            r"固定收益",
            r"固收(?:\+|加)?",
            r"债基",
        ),
        "科技": (
            r"科技",
            r"(?<![A-Za-z])TMT(?![A-Za-z])",
            r"人工智能",
            r"(?<![A-Za-z])AI(?![A-Za-z])",
            r"算力",
            r"半导体",
            r"芯片",
            r"光模块",
            r"通信",
            r"软件",
        ),
        "医药": (
            r"医药",
            r"医疗",
            r"创新药",
            r"(?<![A-Za-z])CXO(?![A-Za-z])",
            r"生物制药",
        ),
        "消费": (
            r"(?<!煤炭)(?<!能源)(?<!电力)(?<!原油)(?<!汽油)(?<!天然气)消费(?:品|行业|板块|出海|升级|复苏|需求|场景|投资|方向|赛道|龙头)?(?!绝对量|总量|量|税|贷|金融|者)",
            r"食品饮料",
            r"白酒",
            r"家电",
            r"零售",
            r"纺织服装",
        ),
        "周期": (
            r"周期(?:资源|行业|板块|品种|股|投资)",
            r"资源品",
            r"大宗商品",
            r"有色金属",
            r"煤炭",
            r"钢铁",
            r"化工",
        ),
        "新能源": (
            r"新能源",
            r"光伏",
            r"风电",
            r"储能",
            r"锂电",
            r"动力电池",
        ),
        "金融地产": (
            r"金融地产",
            r"银行(?:板块|股|行业)?",
            r"保险(?:板块|股|行业)?",
            r"券商(?:板块|股|行业)?",
            r"房地产",
            r"地产(?:板块|股|行业|链)?",
        ),
        "信用债": (r"信用债", r"信用利差", r"信用下沉"),
        "利率债": (r"利率债", r"国债", r"政金债", r"政策性金融债"),
        "久期": (r"久期", r"拉长久期", r"缩短久期"),
        "杠杆": (r"杠杆(?:率|策略|水平|交易|仓位)?",),
        "资金利率": (r"资金利率", r"隔夜利率", r"回购利率", r"DR007", r"R007"),
        "政策": (r"货币政策", r"财政政策", r"产业政策", r"监管政策", r"政策面", r"政策周期"),
        "转债": (r"可转债", r"转债(?:市场|策略|估值|基金|品种)?"),
    }

    @classmethod
    def extract(cls, content: str, title: str = "") -> List[str]:
        normalized_title = re.sub(r"\s+", " ", str(title or "")).strip()
        normalized_content = re.sub(r"\s+", " ", str(content or "")).strip()
        opening = normalized_content[:2200]

        candidates: List[Tuple[str, int, int]] = []
        opinion_cue = r"重点关注|重点看好|持续看好|看好|关注|布局|配置|超配|低配|控制|维持|调整|降低|提高|投资机会|板块观点|行业观点"
        for order, topic in enumerate(cls.TOPIC_ORDER):
            patterns = cls.PATTERNS[topic]
            title_hits = sum(
                len(re.findall(pattern, normalized_title, re.IGNORECASE))
                for pattern in patterns
            )
            opening_hits = sum(
                len(re.findall(pattern, opening, re.IGNORECASE))
                for pattern in patterns
            )
            hit_count = sum(
                len(re.findall(pattern, normalized_content, re.IGNORECASE))
                for pattern in patterns
            )
            explicit_opinion = any(
                re.search(rf"(?:{opinion_cue})[^，。；;]{{0,18}}(?:{pattern})", opening, re.IGNORECASE)
                or re.search(rf"(?:{pattern})[^，。；;]{{0,18}}(?:{opinion_cue})", opening, re.IGNORECASE)
                for pattern in patterns
            )
            if topic == "杠杆":
                explicit_opinion = cls._has_portfolio_leverage_context(opening)
                if not explicit_opinion:
                    opening_hits = 0
                    hit_count = 0
            if not (title_hits or explicit_opinion or opening_hits >= 2 or hit_count >= 3):
                continue
            score = title_hits * 8 + int(explicit_opinion) * 6 + min(opening_hits, 4) * 2 + min(hit_count, 6)
            candidates.append((topic, score, order))

        selected = sorted(candidates, key=lambda item: (-item[1], item[2]))[:8]
        selected_topics = {item[0] for item in selected}
        return [topic for topic in cls.TOPIC_ORDER if topic in selected_topics]

    @staticmethod
    def _has_portfolio_leverage_context(text: str) -> bool:
        normalized = re.sub(r"\s+", " ", str(text or ""))
        for match in re.finditer(r"杠杆", normalized):
            context = normalized[max(0, match.start() - 28):match.end() + 28]
            prefix = normalized[max(0, match.start() - 8):match.start()]
            if re.search(r"央企|企业|政府|居民|地方|宏观", prefix):
                continue
            if re.search(r"组合|产品|基金|债券|债市|回购|仓位|ETF|质押|久期|跟踪误差", context, re.IGNORECASE):
                return True
            if re.search(r"控制|维持|调整|降低|提高|增加|减少|不加|去杠杆", context):
                return True
        return False

    @classmethod
    def domains(cls, topics: List[str], content: str = "", title: str = "") -> List[str]:
        values = set(topics or [])
        opening = re.sub(r"\s+", " ", f"{title} {content[:2200]}").strip()
        equity_topics = {"A股", "港股", "科技", "医药", "消费", "周期", "新能源", "金融地产"}
        fixed_income_topics = {"债市", "信用债", "利率债", "久期", "资金利率", "转债"}
        domains: List[str] = []
        if values.intersection(equity_topics) or re.search(
            r"主动权益|权益投资|股票投资|偏股混合|股票型基金|权益类基金",
            opening,
        ):
            domains.append("equity")
        if values.intersection(fixed_income_topics) or re.search(
            r"固定收益|固收(?:\+|加)?|纯债|一级债基|二级债基|债券型基金",
            opening,
        ):
            domains.append("fixed_income")
        return domains
