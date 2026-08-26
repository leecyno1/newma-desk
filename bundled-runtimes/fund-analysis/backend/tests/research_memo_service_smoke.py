import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import init_database
from services.research_memo_service import ResearchMemoService


def main() -> int:
    init_database()

    memo = ResearchMemoService().build_fund_memo("000002.OF")
    evidence_ids = {item["id"] for item in memo.get("evidence_table", [])}

    if memo.get("memo_type") != "fund_research":
        raise AssertionError(f"Unexpected memo type: {memo}")
    for key in ["facts", "inferences", "counter_thesis", "watchlist", "research_memo_markdown"]:
        if not memo.get(key):
            raise AssertionError(f"Missing memo section {key}: {memo}")
    for fact in memo["facts"]:
        for evidence_id in fact.get("evidence_ids", []):
            if evidence_id not in evidence_ids:
                raise AssertionError(f"Fact references unknown evidence {evidence_id}: {memo}")

    markdown = memo["research_memo_markdown"]
    for heading in ["事实", "推断", "反证", "研究观察清单"]:
        if heading not in markdown:
            raise AssertionError(f"Markdown missing heading {heading}: {markdown}")

    if memo.get("audit", {}).get("source_count", 0) < 4:
        raise AssertionError(f"Expected at least 4 evidence sources, got {memo}")

    print("OK evidence-backed research memo with facts, inferences and counter-thesis")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
