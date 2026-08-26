import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.vector_db_service import get_vector_db


def main() -> int:
    os.environ.setdefault("QDRANT_HOST", "localhost")
    os.environ.setdefault("QDRANT_PORT", "6333")

    vector_db = get_vector_db()
    info = vector_db.get_collection_info()
    if info.get("name") != "research_reports":
        print(f"Expected research_reports collection, got: {info}")
        return 1

    report_id = str(uuid.uuid4())
    vector_db.add_report(
        report_id=report_id,
        title="Smoke report for value investing",
        content="This manager prefers value investing and long-term fundamental research.",
        metadata={"manager_name": "smoke-manager", "date": "2026-05-02"},
    )

    results = vector_db.search_similar("value investing manager", top_k=3)
    if not any(str(item.get("id")) == report_id for item in results):
        print(f"Expected to find inserted report {report_id}, got: {results}")
        return 1

    vector_db.delete_report(report_id)
    print("OK vector db")
    return 0


if __name__ == "__main__":
    sys.exit(main())
