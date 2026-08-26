import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from repositories.report_chunk_repo import ReportChunkRepo


def main() -> int:
    repo = ReportChunkRepo()
    report_id = repo.create_test_report(title="chunk smoke report")
    chunks = repo.replace_chunks(report_id, [
        {
            "chunk_index": 0,
            "content": "第一段基金经理访谈，强调长期主义。",
            "token_count": 18,
            "embedding_id": f"{report_id}:0",
            "entities": {"managers": ["张三"]},
            "metadata": {"section": "interview"},
        },
        {
            "chunk_index": 1,
            "content": "第二段讨论风险控制和回撤管理。",
            "token_count": 16,
            "embedding_id": f"{report_id}:1",
        },
    ])
    if len(chunks) != 2:
        print(f"Expected 2 chunks, got: {chunks}")
        return 1

    replaced = repo.replace_chunks(report_id, [
        {"chunk_index": 0, "content": "替换后的唯一切片", "embedding_id": f"{report_id}:new"}
    ])
    if len(replaced) != 1:
        print(f"Expected 1 replacement chunk, got: {replaced}")
        return 1

    by_report = repo.list_by_report(report_id)
    if len(by_report) != 1 or by_report[0].get("content") != "替换后的唯一切片":
        print(f"Expected replaced report chunks, got: {by_report}")
        return 1

    by_embedding = repo.get_by_embedding_id(f"{report_id}:new")
    if not by_embedding or by_embedding.get("report_id") != report_id:
        print(f"Expected lookup by embedding id, got: {by_embedding}")
        return 1

    print("OK report chunk repository replace/list/lookup")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
