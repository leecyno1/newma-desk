#!/usr/bin/env python3
"""Backfill memo viewpoint topics without calling an LLM."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from database import init_database  # noqa: E402
from repositories.local_research_folder_repo import PostgresLocalResearchFolderRepo  # noqa: E402
from services.research_memo_viewpoint_taxonomy import ResearchMemoViewpointTaxonomy  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="回填调研纪要观点主题")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--folder-id", default="")
    args = parser.parse_args()

    init_database()
    repo = PostgresLocalResearchFolderRepo()
    page = 1
    reports = []
    while True:
        result = repo.list_reports(
            folder_id=args.folder_id.strip() or None,
            page=page,
            page_size=50,
            sort_by="title",
            sort_order="asc",
        )
        batch = result.get("reports") or []
        reports.extend(batch)
        if not batch or len(reports) >= int(result.get("total") or 0):
            break
        page += 1

    changed = []
    topic_counts = {}
    domain_counts = {}
    for report in reports:
        content = str(report.get("content") or "")
        title = str(report.get("title") or "")
        topics = ResearchMemoViewpointTaxonomy.extract(content, title)
        domains = ResearchMemoViewpointTaxonomy.domains(topics, content, title)
        for value in topics:
            topic_counts[value] = topic_counts.get(value, 0) + 1
        for value in domains:
            domain_counts[value] = domain_counts.get(value, 0) + 1
        if topics == (report.get("viewpoint_topics") or []) and domains == (report.get("research_domains") or []):
            continue
        changed.append({
            "id": report.get("id"),
            "title": title,
            "viewpoint_topics": topics,
            "research_domains": domains,
        })
        if args.apply:
            repo.update_report(str(report["id"]), {
                "viewpoint_topics": topics,
                "research_domains": domains,
            })

    print(json.dumps({
        "mode": "apply" if args.apply else "preview",
        "report_count": len(reports),
        "changed_report_count": len(changed),
        "topic_counts": dict(sorted(topic_counts.items(), key=lambda item: (-item[1], item[0]))),
        "domain_counts": domain_counts,
        "sample": changed[:10],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
