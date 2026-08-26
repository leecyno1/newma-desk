#!/usr/bin/env python3
"""Refresh memo candidates, backfill unique manager identities, then confirm safe links."""

import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BASE_DIR.parent
sys.path.insert(0, str(BASE_DIR))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT_DIR / ".env.local")
    load_dotenv(ROOT_DIR / ".env")
    load_dotenv(BASE_DIR / ".env")
except Exception:
    pass

from database import init_database
from repositories import get_fund_repo, get_manager_repo
from repositories.local_research_folder_repo import PostgresLocalResearchFolderRepo
from service_registry import get_strict_tushare_service
from services.local_research_folder_service import LocalResearchFolderService
from services.research_memo_manager_fund_resolver import ResearchMemoManagerFundResolver
from services.research_memo_manager_identity_sync_service import ResearchMemoManagerIdentitySyncService
from services.research_memo_manager_matcher import ResearchMemoManagerMatcher
from services.research_memo_manager_profile_projection_service import ResearchMemoManagerProfileProjectionService
from services.research_memo_profile_projection_service import ResearchMemoProfileProjectionService


def main() -> int:
    parser = argparse.ArgumentParser(description="同步纪要中的基金经理唯一身份")
    parser.add_argument("--folder-id", default="")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--min-confidence", type=float, default=0.84)
    parser.add_argument("--skip-refresh", action="store_true")
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()

    init_database()
    repo = PostgresLocalResearchFolderRepo()
    repo.ensure_indexes()
    manager_repo = get_manager_repo()
    fund_repo = get_fund_repo()
    data_service = get_strict_tushare_service()
    folder_id = args.folder_id.strip() or None

    scan_summaries = []
    if not args.skip_refresh:
        matcher = ResearchMemoManagerMatcher(
            manager_repo.list_identity_catalog(),
            company_names=manager_repo.list_fund_company_catalog(),
        )
        scanner = LocalResearchFolderService(
            repo=repo,
            manager_matcher=matcher,
            manager_fund_resolver=ResearchMemoManagerFundResolver(data_service=data_service).resolve,
        )
        folders = [item for item in repo.list_folders() if not folder_id or item.get("id") == folder_id]
        for folder in folders:
            result = scanner.scan_folder(str(folder["id"]))
            scan_summaries.append({
                "folder": folder.get("name"),
                "counts": result.get("counts"),
            })

    identity_result = ResearchMemoManagerIdentitySyncService(
        data_service=data_service,
        report_repo=repo,
        manager_repo=manager_repo,
        fund_repo=fund_repo,
        company_names=manager_repo.list_fund_company_catalog(),
    ).sync_pending(
        folder_id=folder_id,
        limit=args.limit,
        apply=not args.preview,
    )

    confirmation = None
    identity_audit = None
    profile_rebuild = None
    if not args.preview:
        manager_projector = ResearchMemoManagerProfileProjectionService(
            report_repo=repo,
            manager_repo=manager_repo,
        )
        reviewer = LocalResearchFolderService(
            repo=repo,
            profile_projector=ResearchMemoProfileProjectionService(report_repo=repo).project_report,
            manager_profile_projector=manager_projector.project_report,
        )
        confirmation = reviewer.confirm_manager_proposals(
            folder_id=folder_id,
            min_confidence=max(0, min(1, args.min_confidence)),
        )
        identity_audit = ResearchMemoManagerIdentitySyncService(
            data_service=data_service,
            report_repo=repo,
            manager_repo=manager_repo,
            fund_repo=fund_repo,
            company_names=manager_repo.list_fund_company_catalog(),
        ).audit_confirmed(
            folder_id=folder_id,
            apply=True,
        )
        profile_rebuild = manager_projector.rebuild_managers(
            list(dict.fromkeys([
                *repo.list_confirmed_manager_ids(folder_id),
                *(identity_audit.get("affected_manager_ids") or []),
            ])),
        )
    else:
        identity_audit = ResearchMemoManagerIdentitySyncService(
            data_service=data_service,
            report_repo=repo,
            manager_repo=manager_repo,
            fund_repo=fund_repo,
            company_names=manager_repo.list_fund_company_catalog(),
        ).audit_confirmed(
            folder_id=folder_id,
            apply=False,
        )

    print(json.dumps({
        "scan": scan_summaries,
        "identity_sync": identity_result,
        "confirmation": confirmation,
        "identity_audit": identity_audit,
        "manager_profile_rebuild": {
            key: (profile_rebuild or {}).get(key, 0)
            for key in ("projected_count", "deleted_count", "skipped_count")
        } if profile_rebuild is not None else None,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
