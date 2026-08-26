import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from routes.reports import _brief_memo_summary


def main():
    summary = _brief_memo_summary({"summary": "观点 " * 200})
    assert len(summary) <= 221
    assert summary.endswith("…")
    key_point = _brief_memo_summary({"key_points": ["更短的关键观点"], "summary": "很长" * 200})
    assert key_point == "更短的关键观点"
    print("OK fund evaluation keeps memo evidence concise and prefers key points")


if __name__ == "__main__":
    main()
