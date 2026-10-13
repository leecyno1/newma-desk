"""
调研报告管理路由
"""
from fastapi import APIRouter, HTTPException, Query, Body
from typing import List, Optional
import logging
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/research-reports", tags=["调研报告库"])


class ResearchReportCreate(BaseModel):
    manager_id: str = ""
    manager_name: str = ""
    title: str
    report_date: str
    source: str
    content: str
    summary: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    classifications: List[str] = Field(default_factory=list)
    style_labels: List[str] = Field(default_factory=list)
    fund_ids: List[str] = Field(default_factory=list)
    key_points: List[str] = Field(default_factory=list)


@router.get("/")
async def list_reports(
    manager_id: Optional[str] = Query(None),
    fund_id: Optional[str] = Query(None),
    folder_id: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    tags: Optional[str] = Query(None, description="标签, 逗号分隔"),
    viewpoint_topics: Optional[str] = Query(None, description="观点主题, 逗号分隔"),
    research_domain: Optional[str] = Query(None, description="equity / fixed_income"),
    source: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    sort_by: str = Query("report_date"),
    sort_order: str = Query("desc"),
):
    """查询调研报告列表"""
    from repositories.local_research_folder_repo import PostgresLocalResearchFolderRepo

    try:
        result = PostgresLocalResearchFolderRepo().list_reports(
            manager_id=manager_id,
            fund_id=fund_id,
            folder_id=folder_id,
            keyword=keyword,
            tags=[item.strip() for item in tags.split(",") if item.strip()] if tags else None,
            viewpoint_topics=[item.strip() for item in viewpoint_topics.split(",") if item.strip()] if viewpoint_topics else None,
            research_domain=research_domain,
            source=source,
            start_date=start_date,
            end_date=end_date,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        reports = [{
            **doc,
            "summary": str(doc.get("summary") or "")[:300],
            "key_points": (doc.get("key_points") or [])[:3],
            "content": None,
        } for doc in result["reports"]]
        return {"total": result["total"], "page": page, "page_size": page_size, "data": reports}
    except Exception as e:
        logger.error(f"List reports error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/")
async def create_report(payload: ResearchReportCreate = Body(...)):
    """新增调研报告（写 PostgreSQL，与列表/详情读路径同库，上传后立即可检索）"""
    from services.search_service import get_search_service
    from repositories.local_research_folder_repo import PostgresLocalResearchFolderRepo

    try:
        manager_id = payload.manager_id or ""
        manager_name = payload.manager_name or ""
        title = payload.title
        report_date = payload.report_date
        source = payload.source
        content = payload.content
        summary = payload.summary
        if not summary:
            summary = content[:500] if content else ""

        # 生成真实向量；模型/API 不可用时不写入假 embedding，报告仍可通过关键词检索。
        search_service = get_search_service()
        embedding = search_service.compute_report_embedding({
            "title": title, "summary": summary, "content": content[:2000]
        })

        created = PostgresLocalResearchFolderRepo().create_report({
            "manager_id": manager_id,
            "manager_name": manager_name,
            "title": title,
            "report_date": report_date,
            "source": source,
            "content": content,
            "summary": summary,
            "tags": payload.tags,
            "classifications": payload.classifications,
            "style_labels": payload.style_labels,
            "fund_ids": payload.fund_ids,
            "key_points": payload.key_points,
            "embedding_status": "available" if embedding else "unavailable",
            "embedding_source": "openai_compatible" if embedding else "keyword_only_no_mock",
            "extraction_status": "complete",
            "extraction_provider": "manual_upload",
        })
        report_id = str(created.get("id")) if created.get("id") else None
        if not report_id:
            raise HTTPException(status_code=500, detail="报告写入失败")

        return {
            "id": report_id,
            "status": "created",
            "report": {
                "id": report_id,
                "manager_id": manager_id,
                "manager_name": manager_name,
                "title": title,
                "report_date": report_date,
                "source": source,
                "summary": summary,
                "tags": payload.tags,
                "classifications": payload.classifications,
                "style_labels": payload.style_labels,
                "fund_ids": payload.fund_ids,
                "key_points": payload.key_points,
                "embedding_status": "available" if embedding else "unavailable",
                "embedding_source": "openai_compatible" if embedding else "keyword_only_no_mock",
                "created_at": created.get("created_at"),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create report error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{report_id}")
async def get_report(report_id: str):
    """获取报告详情"""
    from repositories.local_research_folder_repo import PostgresLocalResearchFolderRepo

    try:
        doc = PostgresLocalResearchFolderRepo().get_report(report_id)
        if not doc:
            raise HTTPException(status_code=404, detail="报告不存在")
        return doc
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get report error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{report_id}")
async def update_report(
    report_id: str,
    title: Optional[str] = None,
    summary: Optional[str] = None,
    tags: Optional[List[str]] = None,
    content: Optional[str] = None,
):
    """更新报告（PostgreSQL，与读路径同库）"""
    from repositories.local_research_folder_repo import PostgresLocalResearchFolderRepo

    try:
        update_fields = {}
        if title is not None:
            update_fields["title"] = title
        if summary is not None:
            update_fields["summary"] = summary
        if tags is not None:
            update_fields["tags"] = tags
        if content is not None:
            update_fields["content"] = content

        updated = PostgresLocalResearchFolderRepo().update_report(report_id, update_fields)
        if not updated:
            raise HTTPException(status_code=404, detail="报告不存在")

        return {"status": "updated", "id": report_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update report error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{report_id}")
async def delete_report(report_id: str):
    """删除报告（PostgreSQL，与读路径同库）"""
    from repositories.local_research_folder_repo import PostgresLocalResearchFolderRepo

    try:
        deleted = PostgresLocalResearchFolderRepo().delete_report(report_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="报告不存在")
        return {"status": "deleted", "id": report_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete report error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
