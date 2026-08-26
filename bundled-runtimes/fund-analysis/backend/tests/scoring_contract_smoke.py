import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.scoring_contract import build_scoring_output, grade_for_score, serialize_scoring_output


def main() -> int:
    if grade_for_score(91) != "S" or grade_for_score(80) != "A" or grade_for_score(49) != "E":
        print("Grade boundaries are wrong")
        return 1

    output = build_scoring_output(
        target_type="fund",
        target_id="UNIT.TEST",
        total_score=82.345,
        dimensions={"return": {"score": 90}, "risk": {"score": 75}},
        metric_scores={"annualized_return_raw": 0.12},
        positive_factors=["收益表现较强"],
        negative_factors=["最大回撤偏高"],
        missing_data=["peer_percentile"],
        source_snapshot_ids=["snapshot-1"],
        as_of_date="2026-05-16",
    )
    if output["overall_score"] != 82.35 or output["overall_grade"] != "A":
        print(f"Unexpected output score/grade: {output}")
        return 1
    for key in ["positive_factors", "negative_factors", "missing_data", "data_quality"]:
        if key not in output:
            print(f"Missing {key}: {output}")
            return 1
    serialized = serialize_scoring_output(output)
    if serialized["overall_score"] != 82.35:
        print(f"Unexpected serialized output: {serialized}")
        return 1
    print("OK scoring contract output")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
