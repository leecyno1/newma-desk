from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.research_memo_viewpoint_taxonomy import ResearchMemoViewpointTaxonomy  # noqa: E402


def main() -> None:
    equity = "基金经理分享主动权益投资框架，重点关注半导体、算力和创新药。"
    equity_topics = ResearchMemoViewpointTaxonomy.extract(equity, "科技医药投资交流")
    assert {"科技", "医药"}.issubset(equity_topics)
    assert ResearchMemoViewpointTaxonomy.domains(equity_topics, equity) == ["equity"]

    fixed_income = "固定收益组合近期拉长久期，关注利率债和信用利差，同时控制杠杆。"
    fixed_topics = ResearchMemoViewpointTaxonomy.extract(fixed_income, "债市观点")
    assert {"债市", "久期", "利率债", "信用债", "杠杆"}.issubset(fixed_topics)
    assert ResearchMemoViewpointTaxonomy.domains(fixed_topics, fixed_income) == ["fixed_income"]

    incidental = "该经理主要讲消费品的产品周期。" + "其他记录" * 1000 + "文末提到一次科技。"
    incidental_topics = ResearchMemoViewpointTaxonomy.extract(incidental, "消费投资策略")
    assert "消费" in incidental_topics
    assert "科技" not in incidental_topics
    print("research memo viewpoint taxonomy smoke passed")


if __name__ == "__main__":
    main()
