"""Local research folder configuration, scanning and human review API."""

from functools import lru_cache
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services.local_research_folder_service import FolderValidationError, LocalResearchFolderService
from services.research_memo_manager_matcher import ResearchMemoManagerMatcher
from services.research_memo_manager_profile_projection_service import ResearchMemoManagerProfileProjectionService
from services.research_memo_profile_projection_service import ResearchMemoProfileProjectionService


router = APIRouter(prefix="/api/research-folders", tags=["本地调研纪要文件夹"])


class FolderConnectRequest(BaseModel):
    path: str = Field(min_length=1, max_length=2048)


class ReviewDecisionRequest(BaseModel):
    action: Literal["confirmed", "rejected"]


class BulkManagerReviewRequest(BaseModel):
    folder_id: Optional[str] = None
    min_confidence: float = Field(default=0.88, ge=0, le=1)


class BulkLabelReviewRequest(BaseModel):
    folder_id: Optional[str] = None
    min_confidence: float = Field(default=0.9, ge=0, le=1)


@lru_cache(maxsize=1)
def _get_service() -> LocalResearchFolderService:
    from repositories.local_research_folder_repo import PostgresLocalResearchFolderRepo
    from repositories.manager_repo import ManagerRepo
    from services.research_memo_metadata_extractor import get_research_memo_metadata_extractor
    from services.research_memo_manager_fund_resolver import ResearchMemoManagerFundResolver

    repo = PostgresLocalResearchFolderRepo()
    repo.ensure_indexes()
    extractor = get_research_memo_metadata_extractor()
    manager_repo = ManagerRepo()
    manager_matcher = ResearchMemoManagerMatcher(
        manager_repo.list_identity_catalog(),
        company_names=manager_repo.list_fund_company_catalog(),
    )
    manager_fund_resolver = ResearchMemoManagerFundResolver()
    fund_projector = ResearchMemoProfileProjectionService(report_repo=repo)
    manager_projector = ResearchMemoManagerProfileProjectionService(
        report_repo=repo,
        manager_repo=manager_repo,
    )

    def resolve_manager(manager_name: str):
        manager = manager_repo.get_manager(manager_name)
        if not manager:
            return None
        return {
            "manager_id": manager.get("wind_code"),
            "manager_name": manager.get("name"),
            "company": manager.get("company"),
        }

    return LocalResearchFolderService(
        repo=repo,
        manager_resolver=resolve_manager,
        metadata_extractor=extractor.extract,
        manager_matcher=manager_matcher,
        manager_fund_resolver=manager_fund_resolver.resolve,
        profile_projector=fund_projector.project_report,
        manager_profile_projector=manager_projector.project_report,
    )


@router.get("/")
async def list_folders():
    return {"data": _get_service().list_folders()}


@router.post("/", status_code=201)
async def connect_folder(payload: FolderConnectRequest):
    try:
        return {"status": "connected", "folder": _get_service().add_folder(payload.path)}
    except FolderValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{folder_id}/scan")
async def scan_folder(folder_id: str, retry_llm: bool = Query(False)):
    try:
        return _get_service().scan_folder(folder_id, retry_llm=retry_llm)
    except FolderValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/reviews")
async def list_pending_reviews(folder_id: Optional[str] = Query(None)):
    data = _get_service().list_pending_reviews(folder_id)
    return {"total": len(data), "data": data}


@router.post("/reviews/confirm-managers")
async def confirm_manager_reviews(payload: BulkManagerReviewRequest):
    return _get_service().confirm_manager_proposals(
        folder_id=payload.folder_id,
        min_confidence=payload.min_confidence,
    )


@router.post("/reviews/confirm-labels")
async def confirm_label_reviews(payload: BulkLabelReviewRequest):
    return _get_service().confirm_label_proposals(
        folder_id=payload.folder_id,
        min_confidence=payload.min_confidence,
    )


@router.patch("/reviews/{report_id}/{proposal_id}")
async def review_proposal(report_id: str, proposal_id: str, payload: ReviewDecisionRequest):
    try:
        return _get_service().review_proposal(report_id, proposal_id, payload.action)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
