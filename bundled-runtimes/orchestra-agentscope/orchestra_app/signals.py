from __future__ import annotations

import re
from typing import Literal, TypedDict


InvestmentStance = Literal["bullish", "cautious", "bearish", "abstain"]
ConfidenceLevel = Literal["high", "medium", "low"]


class VoteSignal(TypedDict, total=False):
    stance: InvestmentStance
    vote: str
    confidence: ConfidenceLevel
    source: str


def extract_vote_signal(text: str) -> VoteSignal | None:
    match = re.search(r"【投票】\s*([^\r\n]+)", text)
    vote = match.group(1).strip() if match else ""
    normalized = re.sub(r"\s+", "", vote)
    if not normalized:
        return None

    stance: InvestmentStance | None = None
    if re.search(r"弃权|回避|不投票", normalized):
        stance = "abstain"
    elif re.search(r"有条件赞成|谨慎|中性|观望|小仓位", normalized):
        stance = "cautious"
    elif re.search(r"反对|看空|否决|减持|不配置", normalized):
        stance = "bearish"
    elif re.search(r"赞成|看多|支持|增持|超配", normalized):
        stance = "bullish"
    if stance is None:
        return None

    signal: VoteSignal = {
        "stance": stance,
        "vote": vote,
        "source": "report",
    }
    confidence_match = re.search(r"【置信度】\s*([^\r\n]+)", text)
    confidence = confidence_match.group(1) if confidence_match else ""
    if "高" in confidence:
        signal["confidence"] = "high"
    elif "中" in confidence:
        signal["confidence"] = "medium"
    elif "低" in confidence:
        signal["confidence"] = "low"
    return signal
