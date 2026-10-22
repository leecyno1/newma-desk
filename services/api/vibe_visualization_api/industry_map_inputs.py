"""Read a selected saved graph fragment for research in the same signed workspace."""
import json
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field, ValidationError
from starlette.concurrency import run_in_threadpool

from vibe_visualization_api.artifacts.models import GraphArtifactCreate, GraphNode, GraphEdge
from vibe_visualization_api.control_plane.repository import ModuleRepository
from vibe_visualization_api.control_plane.routes import get_repository
from vibe_visualization_api.mod_storage.routes import _claims
from vibe_visualization_api.mod_storage.store import ModStorageCorruptError

router = APIRouter(tags=["industry research inputs"])


class ReviewReason(BaseModel):
    targetLabel: str = Field(min_length=1, max_length=600)
    reason: str = Field(min_length=1, max_length=2000)


class GraphEvidence(BaseModel):
    id: str = Field(min_length=1, max_length=160)
    target: str = Field(min_length=1, max_length=600)
    title: str = Field(min_length=1, max_length=160)
    url: str = Field(default="", max_length=2000)
    locator: str = Field(min_length=1, max_length=240)
    excerpt: str = Field(min_length=1, max_length=4000)
    publishedAt: str = Field(default="", max_length=10)
    nextReview: str = Field(default="", max_length=10)
    judgment: Literal["supports", "refutes", "unclear"]
    note: str = Field(default="", max_length=2000)
    recordedAt: str = Field(max_length=80)
    reviewRequired: ReviewReason | None = None


class SavedGraphInput(BaseModel):
    schemaVersion: Literal["newma-desk.industry-map-input.v1"]
    sectorKey: str = Field(min_length=1, max_length=64)
    documentRevision: int = Field(ge=1)
    versionNumber: int = Field(ge=1, le=20)
    savedAt: str = Field(max_length=80)
    title: str = Field(min_length=1, max_length=160)
    provenance: str = Field(max_length=2000)
    selectedNode: GraphNode
    nodes: list[GraphNode] = Field(min_length=1, max_length=80)
    edges: list[GraphEdge] = Field(max_length=160)
    evidence: list[GraphEvidence] = Field(max_length=80)
    claimVerified: Literal[False]
    boundary: str = Field(max_length=2000)


class ResearchOrigin(BaseModel):
    schemaVersion: Literal["newma-desk.research-origin.v1"]
    snapshotId: str = Field(min_length=1, max_length=128)
    theme: str = Field(min_length=1, max_length=160)
    market: str = Field(min_length=1, max_length=20)
    asOf: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    input: SavedGraphInput


@router.get("/{module_id}/research-origins/{archive_id}")
async def read_research_origin(
    module_id: str, archive_id: str, request: Request,
    snapshotId: str = Query(min_length=1, max_length=128),
    theme: str = Query(min_length=1, max_length=160), market: str = Query(min_length=1, max_length=20),
    asOf: str = Query(pattern=r"^\d{4}-\d{2}-\d{2}$"),
    sourceUserId: str = Query(min_length=1, max_length=128),
    sourceWorkspaceId: str = Query(min_length=1, max_length=128),
    authorization: str | None = Header(default=None),
    instance_id: str | None = Header(default=None, alias="X-Newma-Desk-Instance-Id"),
    repository: ModuleRepository = Depends(get_repository),
):
    claims = _claims(request, authorization, instance_id)
    if module_id not in {"instock-stock-research", "instock-research-book"} or claims.module_id != module_id or "analysis.read" not in claims.permissions:
        raise HTTPException(403, "当前会话不能读取此研究起点")
    module = await run_in_threadpool(repository.get_published, claims.module_id)
    if claims.revision != module.revision:
        raise HTTPException(403, "模组版本变化，请刷新后重新读取")
    if (sourceUserId, sourceWorkspaceId) != (claims.user_id, claims.workspace_id):
        raise HTTPException(403, "研究起点不属于当前用户或工作区")
    if len(archive_id) != 32 or any(char not in "0123456789abcdef" for char in archive_id):
        raise HTTPException(422, "研究起点标识无效")
    try:
        document = await run_in_threadpool(request.app.state.mod_storage_store.get,
            user_id=claims.user_id, workspace_id=claims.workspace_id, module_id="instock-industry-chain",
            namespace="research-origins", key=archive_id)
        origin = ResearchOrigin.model_validate(document["value"])
    except (ModStorageCorruptError, ValidationError) as exc:
        raise HTTPException(422, "研究起点记录不完整，请返回产业链核对") from exc
    if (origin.snapshotId, origin.theme, origin.market, origin.asOf) != (snapshotId, theme, market, asOf):
        raise HTTPException(409, "研究起点与当前产业链快照、主题、市场或日期不符")
    return {"archiveId": archive_id, "archivedAt": document["createdAt"], "record": origin.model_dump(by_alias=True),
        "boundary": "工作区保存的研究起点快照，不是最新图谱或模型使用证明，不证明该公司的供货、收入与业绩。未知日期、晚于研究截止日及待复核记录不能当作已验证事实。"}


def graph_fragment(document: dict, sector: str, version_number: int, revision: int, node_id: str) -> dict:
    if document["revision"] != revision:
        raise HTTPException(409, "源图谱已更新，请回产业图谱重新交接；未改用最新版本")
    book = document["value"]
    try:
        if book["schemaVersion"] != "newma-desk.industry-map.v1" or book["sectorKey"] != sector:
            raise ValueError("wrong book")
        version = next((item for item in book["versions"] if item["number"] == version_number), None)
        if version is None:
            raise HTTPException(404, "所选图谱版本不存在，未改用其他版本")
        graph = GraphArtifactCreate.model_validate(version["spec"])
        if graph.module_id != "industry-map":
            raise ValueError("wrong module")
        all_evidence = [GraphEvidence.model_validate(item) for item in version["evidence"]]
        if len(all_evidence) > 80 or len({item.id for item in all_evidence}) != len(all_evidence):
            raise ValueError("invalid evidence collection")
        saved_at, provenance = version["savedAt"], version["provenance"]
        if not isinstance(saved_at, str) or not isinstance(provenance, str):
            raise ValueError("invalid version metadata")
    except (KeyError, TypeError, ValueError, ValidationError) as exc:
        raise HTTPException(422, "源图谱格式不完整，请先在产业图谱核对；未创建空白替代") from exc
    selected = next((node for node in graph.nodes if node.id == node_id), None)
    if selected is None:
        raise HTTPException(404, "选中节点不存在，未改选其他节点")
    edges = [edge for edge in graph.edges if node_id in (edge.source, edge.target)]
    ids = {node_id} | {edge.source for edge in edges} | {edge.target for edge in edges}
    def related(item: GraphEvidence) -> bool:
        if item.target == "node:" + node_id:
            return True
        try:
            target = json.loads(item.target)
            # Include old, withdrawn relations involving this node as explicit review warnings.
            return isinstance(target, list) and len(target) == 5 and target[0] == "edge" and node_id in target[1:3]
        except (TypeError, ValueError):
            return False
    return {
        "schemaVersion": "newma-desk.industry-map-input.v1", "sectorKey": sector,
        "documentRevision": revision, "versionNumber": version_number, "savedAt": saved_at,
        "title": graph.title, "provenance": provenance, "selectedNode": selected.model_dump(by_alias=True),
        "nodes": [node.model_dump(by_alias=True) for node in graph.nodes if node.id in ids],
        "edges": [edge.model_dump(by_alias=True) for edge in edges],
        "evidence": [item.model_dump(exclude_none=True) for item in all_evidence if related(item)],
        "claimVerified": False,
        "boundary": "仅所选节点及直接关系的已保存研究线索。人工支持、反证与待复核记录均不是系统认证；不证明企业收入、供货、订单或估值。保存时间不是披露日期。",
    }


@router.get("/instock-industry-chain/industry-map-inputs")
async def read_industry_map_input(
    request: Request,
    sector: str = Query(pattern=r"^[a-z][a-z0-9-]{0,63}$"),
    node: str = Query(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,63}$"),
    version: int = Query(ge=1, le=20), revision: int = Query(ge=1),
    source_user: str = Query(alias="sourceUserId", min_length=1, max_length=128),
    source_workspace: str = Query(alias="sourceWorkspaceId", min_length=1, max_length=128),
    authorization: str | None = Header(default=None),
    instance_id: str | None = Header(default=None, alias="X-Newma-Desk-Instance-Id"),
    repository: ModuleRepository = Depends(get_repository),
):
    claims = _claims(request, authorization, instance_id)
    if claims.module_id != "instock-industry-chain" or "analysis.read" not in claims.permissions:
        raise HTTPException(403, "当前会话不允许读取产业图谱研究输入")
    module = await run_in_threadpool(repository.get_published, claims.module_id)
    if claims.revision != module.revision:
        raise HTTPException(403, "模组版本变化，请刷新后重新交接")
    if source_user != claims.user_id or source_workspace != claims.workspace_id:
        raise HTTPException(403, "交接来源与当前用户或工作区不一致")
    try:
        document = await run_in_threadpool(request.app.state.mod_storage_store.get,
            user_id=claims.user_id, workspace_id=claims.workspace_id, module_id="industry-map",
            namespace="industry-maps", key=sector)
    except ModStorageCorruptError as exc:
        raise HTTPException(503, "源图谱无法读取，请先回原模块核对") from exc
    return graph_fragment(document, sector, version, revision, node)
