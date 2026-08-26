#!/usr/bin/env python3
"""Preview or apply evidence-bound memo classification and style labels."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Dict, Iterable, List, Tuple


BASE_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BASE_DIR.parent
sys.path.insert(0, str(BASE_DIR))

try:
    from dotenv import load_dotenv

    # Match the running backend. Existing process environment still wins.
    load_dotenv(BASE_DIR / ".env", override=False)
    load_dotenv(ROOT_DIR / ".env.local", override=False)
    load_dotenv(ROOT_DIR / ".env", override=False)
except Exception:
    pass

from database import init_database  # noqa: E402
from repositories import get_manager_repo  # noqa: E402
from repositories.local_research_folder_repo import PostgresLocalResearchFolderRepo  # noqa: E402
from services.local_research_folder_service import LocalResearchFolderService  # noqa: E402
from services.research_memo_manager_profile_projection_service import (  # noqa: E402
    ResearchMemoManagerProfileProjectionService,
)
from services.research_memo_profile_projection_service import (  # noqa: E402
    ResearchMemoProfileProjectionService,
)


LABEL_KINDS = {"classification", "style_label", "tag"}


def _report_rows(repo: PostgresLocalResearchFolderRepo, folder_id: str | None) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    page = 1
    while True:
        result = repo.list_reports(
            folder_id=folder_id,
            page=page,
            page_size=50,
            sort_by="title",
            sort_order="asc",
        )
        batch = result.get("reports") or []
        rows.extend(batch)
        if len(rows) >= int(result.get("total") or 0) or not batch:
            return rows
        page += 1


def _proposal_rank(item: Dict[str, Any]) -> Tuple[float, int, int]:
    source = str(item.get("extraction_source") or "")
    source_rank = {
        "explicit_field": 3,
        "deterministic_profile_rule": 2,
        "llm": 1,
    }.get(source, 0)
    excerpt = str((item.get("source_ref") or {}).get("excerpt") or "")
    return float(item.get("confidence") or 0), source_rank, len(excerpt)


def _deduplicate(items: Iterable[Dict[str, Any]]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    output: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for raw in items:
        item = deepcopy(raw)
        key = (str(item.get("kind") or ""), str(item.get("value") or "").strip())
        if not all(key):
            continue
        current = output.get(key)
        if current is None or _proposal_rank(item) > _proposal_rank(current):
            output[key] = item
    return output


def _refresh_report(
    service: LocalResearchFolderService,
    repo: PostgresLocalResearchFolderRepo,
    report: Dict[str, Any],
) -> Dict[str, Any]:
    folder_id = str(report.get("local_folder_id") or "").strip()
    folder = repo.get_folder(folder_id) if folder_id else None
    root_text = str((folder or {}).get("path") or "").strip()
    source_text = str(report.get("local_source_path") or "").strip()
    if not root_text or not source_text:
        return {"status": "skipped", "reason": "local_source_unavailable", "report": report}

    root = Path(root_text)
    source_path = Path(source_text)
    try:
        source_path.relative_to(root)
    except ValueError:
        return {"status": "skipped", "reason": "source_outside_folder", "report": report}

    content = str(report.get("content") or "")
    fresh = [
        item
        for item in service._extract_proposals(content, root, source_path)
        if item.get("kind") in LABEL_KINDS
    ]
    existing = list(report.get("review_proposals") or [])
    fund_proposals = [item for item in existing if item.get("kind") == "fund"]
    scoped = service._scope_profile_proposals([*fund_proposals, *fresh], content)
    fresh_by_key = _deduplicate(item for item in scoped if item.get("kind") in LABEL_KINDS)
    old_by_key = _deduplicate(item for item in existing if item.get("kind") in LABEL_KINDS)

    merged_labels: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for key, proposal in fresh_by_key.items():
        old = old_by_key.get(key)
        if old and old.get("review_status") in {"confirmed", "rejected"}:
            proposal["review_status"] = old.get("review_status")
            proposal["reviewed_at"] = old.get("reviewed_at")
        merged_labels[key] = proposal

    for key, old in old_by_key.items():
        if key in merged_labels:
            continue
        if old.get("review_status") in {"confirmed", "rejected"} or old.get("extraction_source") == "llm":
            merged_labels[key] = old

    proposals = [item for item in existing if item.get("kind") not in LABEL_KINDS]
    proposals.extend(merged_labels.values())
    proposals.sort(key=lambda item: (
        {"manager": 0, "fund": 1, "classification": 2, "style_label": 3, "tag": 4}.get(str(item.get("kind")), 9),
        str(item.get("value") or ""),
    ))

    pending = [item for item in merged_labels.values() if item.get("review_status") == "pending"]
    auto_confirmable = [
        item for item in pending
        if float(item.get("confidence") or 0) >= 0.9
        and service._confirmable_label_proposal(item, report)
    ]
    manual_review = [item for item in pending if item not in auto_confirmable]
    changed = proposals != existing
    return {
        "status": "ready",
        "report": report,
        "proposals": proposals,
        "changed": changed,
        "auto_confirmable": auto_confirmable,
        "manual_review": manual_review,
    }


def _summary_item(report: Dict[str, Any], proposal: Dict[str, Any]) -> Dict[str, Any]:
    source_ref = proposal.get("source_ref") or {}
    return {
        "report_id": str(report.get("id") or ""),
        "report_title": report.get("title"),
        "manager_name": report.get("manager_name") or None,
        "kind": proposal.get("kind"),
        "value": proposal.get("value"),
        "scope": proposal.get("scope") or "manager",
        "target_fund_ids": proposal.get("target_fund_ids") or [],
        "confidence": proposal.get("confidence"),
        "excerpt": source_ref.get("excerpt"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="回填有原文证据的纪要分类和风格标签")
    parser.add_argument("--folder-id", default="", help="仅处理指定本地纪要文件夹")
    parser.add_argument("--min-confidence", type=float, default=0.9)
    parser.add_argument("--apply", action="store_true", help="写入候选并确认无歧义高置信项")
    args = parser.parse_args()

    min_confidence = max(0.0, min(1.0, float(args.min_confidence)))
    folder_id = args.folder_id.strip() or None
    if args.apply:
        init_database()

    repo = PostgresLocalResearchFolderRepo()
    manager_repo = get_manager_repo()
    manager_projector = ResearchMemoManagerProfileProjectionService(repo, manager_repo)
    fund_projector = ResearchMemoProfileProjectionService(report_repo=repo)
    service = LocalResearchFolderService(
        repo=repo,
        profile_projector=fund_projector.project_report,
        manager_profile_projector=manager_projector.project_report,
    )

    results = [_refresh_report(service, repo, report) for report in _report_rows(repo, folder_id)]
    ready = [item for item in results if item.get("status") == "ready"]
    skipped = [item for item in results if item.get("status") == "skipped"]
    auto_items = [
        _summary_item(item["report"], proposal)
        for item in ready
        for proposal in item.get("auto_confirmable") or []
        if float(proposal.get("confidence") or 0) >= min_confidence
    ]
    manual_items = [
        _summary_item(item["report"], proposal)
        for item in ready
        for proposal in item.get("manual_review") or []
    ]

    confirmation = None
    manager_rebuild = None
    fund_rebuild = None
    if args.apply:
        now = datetime.now(timezone.utc).isoformat()
        for item in ready:
            if not item.get("changed"):
                continue
            proposals = item.get("proposals") or []
            repo.update_report(str(item["report"].get("id") or ""), {
                "review_proposals": proposals,
                "review_status": "pending" if any(
                    proposal.get("review_status") == "pending" for proposal in proposals
                ) else "reviewed",
                "updated_at": now,
            })

        confirmation = service.confirm_label_proposals(folder_id, min_confidence)
        manager_rebuild = manager_projector.rebuild_managers(repo.list_confirmed_manager_ids(folder_id))

        affected_funds = sorted({
            str(fund_id or "").strip().upper()
            for item in ready
            for proposal in item.get("proposals") or []
            if proposal.get("review_status") == "confirmed"
            and proposal.get("scope") == "fund"
            for fund_id in proposal.get("target_fund_ids") or []
            if str(fund_id or "").strip()
        })
        if affected_funds:
            fund_rebuild = fund_projector.project_report({}, affected_funds)

    print(json.dumps({
        "mode": "apply" if args.apply else "preview",
        "report_count": len(results),
        "changed_report_count": sum(bool(item.get("changed")) for item in ready),
        "skipped_report_count": len(skipped),
        "auto_confirmable_count": len(auto_items),
        "manual_review_count": len(manual_items),
        "auto_confirmable": auto_items,
        "confirmation": confirmation,
        "manager_profile_rebuild": {
            key: (manager_rebuild or {}).get(key, 0)
            for key in ("projected_count", "deleted_count", "skipped_count", "orphaned_deleted_count")
        } if manager_rebuild is not None else None,
        "fund_profile_rebuild": {
            key: (fund_rebuild or {}).get(key, 0)
            for key in ("projected_count", "deleted_count", "cleared_count", "skipped_count")
        } if fund_rebuild is not None else None,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
