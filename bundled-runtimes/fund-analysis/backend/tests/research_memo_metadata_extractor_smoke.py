import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.research_memo_metadata_extractor import ResearchMemoMetadataExtractor  # noqa: E402


class FakeGenerator:
    provider = "test-provider"
    model = "test-model"

    def extract_research_memo_metadata(self, content, filename):
        if filename == "invalid.md":
            return "not json"
        if filename == "explained.md":
            return '''提取结果如下：
            {"manager_names": [], "fund_ids": [], "classifications": [],
             "style_labels": [{"value": "成长", "confidence": 0.82, "excerpt": "风格偏成长"}]}
            以上候选均来自原文。'''
        if filename == "stringified.md":
            return '{"result":"{\\"manager_names\\":[],\\"fund_ids\\":[],\\"classifications\\":[],\\"style_labels\\":[{\\"value\\":\\"成长\\",\\"confidence\\":0.82,\\"excerpt\\":\\"风格偏成长\\"}]}"}'
        return """```json
        {
          "manager_names": [
            {"value": "张三", "confidence": 0.93, "excerpt": "基金经理：张三"},
            {"value": "不存在的人", "confidence": 0.99, "excerpt": "原文里没有这句话"}
          ],
          "fund_ids": [
            {"value": "000001.OF", "confidence": 0.88, "excerpt": "代表基金：000001.OF"},
            {"value": "不是基金代码", "confidence": 0.97, "excerpt": "风格偏成长"}
          ],
          "classifications": [
            {"value": "主动权益", "confidence": 0.84, "excerpt": "基金分类：主动权益"}
          ],
          "style_labels": [
            {"value": "成长", "confidence": 0.82, "excerpt": "风格偏成长"}
          ]
        }
        ```"""


def main() -> int:
    content = "基金经理：张三\n代表基金：000001.OF\n基金分类：主动权益\n风格偏成长，重视现金流。"
    extractor = ResearchMemoMetadataExtractor(generator=FakeGenerator())
    result = extractor.extract(content, "访谈.md")

    if result.get("status") != "complete":
        raise AssertionError(f"Configured model extraction should complete: {result}")
    if result.get("provider") != "test-provider" or result.get("model") != "test-model":
        raise AssertionError(f"Model provenance must be preserved: {result}")

    proposals = result.get("proposals", [])
    expected = {
        ("manager", "张三"),
        ("fund", "000001.OF"),
        ("classification", "主动权益"),
        ("style_label", "成长"),
    }
    actual = {(item.get("kind"), item.get("value")) for item in proposals}
    if actual != expected:
        raise AssertionError(f"Unexpected model proposals: {proposals}")
    if any(item.get("value") == "不存在的人" for item in proposals):
        raise AssertionError("A model proposal whose excerpt is absent from source must be rejected")
    if any(not 0 <= item.get("confidence", -1) <= 1 for item in proposals):
        raise AssertionError(f"Confidence must be bounded: {proposals}")

    invalid = extractor.extract(content, "invalid.md")
    if invalid.get("status") != "failed" or invalid.get("proposals"):
        raise AssertionError(f"Invalid model output must fail closed: {invalid}")

    explained = extractor.extract(content, "explained.md")
    if {(item.get("kind"), item.get("value")) for item in explained.get("proposals", [])} != {("style_label", "成长")}:
        raise AssertionError(f"JSON surrounded by model explanation must be parsed: {explained}")

    stringified = extractor.extract(content, "stringified.md")
    if {(item.get("kind"), item.get("value")) for item in stringified.get("proposals", [])} != {("style_label", "成长")}:
        raise AssertionError(f"Stringified JSON payload must be parsed: {stringified}")

    unavailable = ResearchMemoMetadataExtractor(generator=None).extract(content, "访谈.md")
    if unavailable.get("status") != "unavailable" or unavailable.get("proposals"):
        raise AssertionError(f"Missing model must degrade without fabricated proposals: {unavailable}")

    print("OK memo LLM extraction is evidence-bound, auditable and fail-closed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
