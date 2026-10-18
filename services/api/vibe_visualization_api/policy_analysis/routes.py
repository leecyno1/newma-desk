from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
import hashlib
from urllib.parse import urlsplit

from vibe_visualization_api.config import Settings, get_settings
from vibe_visualization_api.policy_analysis.service import OFFICIAL_SOURCES, build_policy_interpretation, policy_dashboard
from vibe_visualization_api.policy_analysis.documents import fetch_official_document
from vibe_visualization_api.policy_analysis.store import PolicyStore
from vibe_visualization_api.policy_analysis.collector import assess_policy, classify_document_type, classify_lifecycle, classify_policy, extract_policy_entities, clean_policy_text
import httpx

router = APIRouter(prefix="/api/policy-analysis", tags=["policy-analysis"])


class PolicyAssessmentReview(BaseModel):
    level: int = Field(ge=1, le=3)
    note: str = Field(default="", max_length=300)


class OfficialPolicyImport(BaseModel):
    url: str = Field(min_length=1, max_length=2048)


@router.post("/import")
async def import_official_policy(body: OfficialPolicyImport, settings: Settings = Depends(get_settings)) -> dict:
    try:
        document = await fetch_official_document(body.url.strip())
    except (httpx.HTTPError, ValueError, LookupError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)[:240] if isinstance(exc, ValueError)
                            else "官方正文暂时无法取得，未导入摘要替代品。") from exc
    if not document["title"] or not document["publishedAt"]:
        raise HTTPException(status_code=422, detail="官方标题或网页发布日期未识别，请先核验原文。")
    host = (urlsplit(document["sourceUrl"]).hostname or "").removeprefix("www.")
    source = next((item for item in OFFICIAL_SOURCES
                   if host == (urlsplit(item["url"]).hostname or "").removeprefix("www.")), OFFICIAL_SOURCES[0])
    summary = clean_policy_text(document["text"])
    document_type = classify_document_type(document["title"])
    level, confidence, rationale = assess_policy(document["title"], summary, document_type)
    lifecycle, series = classify_lifecycle(document["title"], document_type)
    category, scope = classify_policy(document["title"], summary, source)
    event = {
        "id": "official-" + hashlib.sha1(document["sourceUrl"].encode()).hexdigest()[:16],
        "title": document["title"], "date": document["publishedAt"],
        "institution": document["issuer"] or "官方来源（发文机关待核验）",
        "category": category, "level": level, "status": "published", "certainty": "official",
        "summary": summary, "rationale": rationale, "sourceUrl": document["sourceUrl"],
        "marketScope": scope, "assessmentStatus": "machine", "assessmentConfidence": confidence,
        "documentType": document_type, "lifecycleStage": lifecycle, "policySeriesKey": series,
        "entities": extract_policy_entities(document["title"], document["text"]), "discoveredBy": "official-import",
    }
    store = PolicyStore(settings.database_path)
    # Reuse an existing identity for an official URL already found by RSSHub.
    existing = next((item for item in store.list_events() if item["sourceUrl"] == event["sourceUrl"]), None)
    if existing:
        event["id"] = existing["id"]
    store.upsert_events([event])
    document = store.save_document(event["id"], document)
    return {"event": event, "document": document}


@router.get("/events/{event_id}/document")
async def get_policy_document(event_id: str, settings: Settings = Depends(get_settings)) -> dict:
    versions = PolicyStore(settings.database_path).document_versions(event_id)
    return versions[0] if versions else {"status": "missing", "note": "尚未保存官方正文。"}


@router.post("/events/{event_id}/document")
async def read_policy_document(event_id: str, settings: Settings = Depends(get_settings)) -> dict:
    store = PolicyStore(settings.database_path)
    event = next((item for item in store.list_events() if item["id"] == event_id), None)
    if event is None:
        raise HTTPException(status_code=404, detail="政策不存在")
    if event["status"] != "published":
        raise HTTPException(status_code=409, detail="预期窗口不能当作已发布政策正文读取")
    try:
        document = await fetch_official_document(event["sourceUrl"])
    except (httpx.HTTPError, ValueError, LookupError) as exc:
        message = str(exc)[:240] if isinstance(exc, (ValueError, LookupError)) else "官方来源暂时不可访问，请重试或核验原文链接。"
        raise HTTPException(status_code=502, detail=message) from exc
    return store.save_document(event_id, document)


@router.get("")
async def get_policy_dashboard(
    as_of: date | None = Query(default=None),
    settings: Settings = Depends(get_settings),
) -> dict:
    return await policy_dashboard(
        as_of,
        database_path=settings.database_path,
        rsshub_base_url=settings.policy_rsshub_base_url,
        timeout_seconds=settings.policy_collector_timeout_seconds,
    )


@router.post("/refresh")
async def refresh_policy_dashboard(
    settings: Settings = Depends(get_settings),
) -> dict:
    return await policy_dashboard(
        database_path=settings.database_path,
        rsshub_base_url=settings.policy_rsshub_base_url,
        timeout_seconds=settings.policy_collector_timeout_seconds,
        refresh=True,
    )


@router.patch("/events/{event_id}/assessment")
async def review_policy_assessment(
    event_id: str,
    review: PolicyAssessmentReview,
    settings: Settings = Depends(get_settings),
) -> dict:
    from vibe_visualization_api.policy_analysis.store import PolicyStore

    event = PolicyStore(settings.database_path).review_assessment(
        event_id, review.level, review.note
    )
    if event is None:
        raise HTTPException(status_code=404, detail="政策不存在")
    return event


@router.post("/events/{event_id}/interpretation")
async def interpret_policy_event(
    event_id: str,
    settings: Settings = Depends(get_settings),
) -> dict:
    dashboard = await policy_dashboard(
        database_path=settings.database_path,
        rsshub_base_url=settings.policy_rsshub_base_url,
        timeout_seconds=settings.policy_collector_timeout_seconds,
    )
    event = next((item for item in dashboard["events"] if item["id"] == event_id), None)
    if event is None:
        raise HTTPException(status_code=404, detail="政策不存在")
    if event["status"] != "published":
        raise HTTPException(status_code=409, detail="只有已发布政策可以进行解读")
    related = [
        item
        for item in dashboard["events"]
        if item["id"] in event.get("relatedPolicyIds", [])
    ]
    store = PolicyStore(settings.database_path)
    versions = store.document_versions(event_id)
    base = versions[1] if len(versions) > 1 else None
    relation = "same-page-revision" if base else "same-series-reference"
    if not base:
        for candidate in sorted(related, key=lambda item: item["date"], reverse=True):
            if candidate["date"] < event["date"] and candidate["documentType"] == "formal-policy":
                previous = store.document_versions(candidate["id"], limit=1)
                if previous:
                    base = previous[0]
                    break
    return build_policy_interpretation(event, related, versions[0] if versions else None, base, relation)
