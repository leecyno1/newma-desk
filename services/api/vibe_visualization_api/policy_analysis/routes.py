import asyncio
from copy import deepcopy
from datetime import date
import json

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from vibe_visualization_api.agent_gateway.models import AgentTaskCreate
from vibe_visualization_api.agent_gateway.routes import get_agent_task_service
from vibe_visualization_api.config import Settings, get_settings
from vibe_visualization_api.control_plane.repository import ModuleRepositoryError
from vibe_visualization_api.model_gateway.errors import ModelGatewayError
from vibe_visualization_api.model_gateway.models import ModelResponseCreate
from vibe_visualization_api.policy_analysis.service import build_policy_interpretation, policy_dashboard

router = APIRouter(prefix="/api/policy-analysis", tags=["policy-analysis"])


class PolicyAssessmentReview(BaseModel):
    level: int = Field(ge=1, le=3)
    note: str = Field(default="", max_length=300)


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

def _model_payload(answer: str) -> dict | None:
    candidate = answer.strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        candidate = "\n".join(lines[1:-1]).strip()
    try:
        payload = json.loads(candidate)
    except (TypeError, ValueError):
        payload = {
            key: value
            for key in ("impactAnalysis", "historicalComparison", "transcriptComparison")
            if (value := _extract_json_section(candidate, key)) is not None
        }
    sections = {"impactAnalysis", "historicalComparison", "transcriptComparison"}
    return payload if isinstance(payload, dict) and sections.intersection(payload) else None


def _extract_json_section(text: str, key: str) -> dict | None:
    """Recover one object when a CLI Agent emits valid sections in invalid outer JSON."""
    marker = f'"{key}"'
    marker_index = text.find(marker)
    if marker_index < 0:
        return None
    colon_index = text.find(":", marker_index + len(marker))
    if colon_index < 0:
        return None
    start = colon_index + 1
    while start < len(text) and text[start].isspace():
        start += 1
    if start >= len(text) or text[start] != "{":
        return None
    depth = 0
    quoted = False
    escaped = False
    for index in range(start, len(text)):
        character = text[index]
        if quoted:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                quoted = False
            continue
        if character == '"':
            quoted = True
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                try:
                    value = json.loads(text[start:index + 1])
                except (TypeError, ValueError):
                    return None
                return value if isinstance(value, dict) else None
    return None


def _text_items(value: object) -> list[str] | None:
    if not isinstance(value, list):
        return None
    items: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            items.append(item.strip())
            continue
        if not isinstance(item, dict):
            continue
        field = item.get("field")
        field_value = item.get("value")
        claim = item.get("claim")
        basis = item.get("basis")
        statement = item.get("statement")
        sector = item.get("sector")
        direction = item.get("direction")
        reasoning = item.get("reasoning")
        text = item.get("text") or item.get("summary") or item.get("reason") or item.get("description")
        if isinstance(field, str) and isinstance(field_value, (str, int, float)):
            source = item.get("source")
            suffix = f"（{source.strip()}）" if isinstance(source, str) and source.strip() else ""
            items.append(f"{field.strip()}：{field_value}{suffix}")
        elif isinstance(claim, str) and claim.strip():
            suffix = f"（依据：{basis.strip()}）" if isinstance(basis, str) and basis.strip() else ""
            items.append(f"{claim.strip()}{suffix}")
        elif isinstance(statement, str) and statement.strip():
            items.append(statement.strip())
        elif isinstance(reasoning, str) and reasoning.strip():
            prefix = " · ".join(
                value.strip()
                for value in (sector, direction)
                if isinstance(value, str) and value.strip()
            )
            items.append(f"{prefix}：{reasoning.strip()}" if prefix else reasoning.strip())
        elif isinstance(text, str) and text.strip():
            items.append(text.strip())
    return items


def _normalize_interpretation(payload: dict, fallback: dict) -> dict:
    """Keep the page contract stable when a lightweight Agent varies its JSON shape."""
    result = deepcopy(fallback)
    impact = payload.get("impactAnalysis")
    if isinstance(impact, dict):
        for key in ("facts", "inferences", "uncertainties"):
            value = impact.get(key)
            if key == "uncertainties" and value is None:
                value = impact.get("risks") or payload.get("uncertaintyNotes")
            items = _text_items(value)
            if items is not None:
                result["impactAnalysis"][key] = items

    history = payload.get("historicalComparison")
    if isinstance(history, dict):
        matches = history.get("matchedPolicies")
        if isinstance(matches, list):
            result["historicalComparison"]["matchedPolicies"] = [
                item for item in matches if isinstance(item, dict)
            ]
        for key in ("added", "removed", "shared"):
            items = _text_items(history.get(key))
            if items is not None:
                result["historicalComparison"][key] = items
        note = history.get("note") or history.get("conclusion")
        if not note:
            evidence = (_text_items(history.get("facts")) or []) + (
                _text_items(history.get("uncertainties")) or []
            )
            note = "；".join(evidence)
        if isinstance(note, str) and note.strip():
            result["historicalComparison"]["note"] = note.strip()

    transcript = payload.get("transcriptComparison")
    if isinstance(transcript, dict):
        status = transcript.get("status")
        if status in {"available", "unavailable"}:
            result["transcriptComparison"]["status"] = status
        basis = transcript.get("basis")
        if isinstance(basis, str) and basis.strip():
            result["transcriptComparison"]["basis"] = basis.strip()
        note = transcript.get("note") or transcript.get("reason")
        if isinstance(note, str) and note.strip():
            result["transcriptComparison"]["note"] = note.strip()
    return result


async def _policy_agent_enabled(request: Request) -> bool:
    repository = await run_in_threadpool(request.app.state.resolve_module_repository)
    try:
        module = await run_in_threadpool(
            repository.get_published,
            "policy-interpretation",
        )
    except ModuleRepositoryError:
        return False
    actions = module.manifest.get("actions")
    action = actions.get("policy.interpret") if isinstance(actions, dict) else None
    binding = action.get("binding") if isinstance(action, dict) else None
    return isinstance(binding, dict) and binding.get("type") == "agent"


async def _agent_interpretation(
    request: Request,
    settings: Settings,
    event: dict,
    related: list[dict],
    *,
    user_id: str,
    workspace_id: str,
) -> dict | None:
    if not await _policy_agent_enabled(request):
        return None
    service = await get_agent_task_service(request)
    task = await service.create(
        AgentTaskCreate(
            user_id=user_id,
            module_id="policy-interpretation",
            capability="policy.interpret",
            profile="batch",
            command_profile="batch",
            memory_scope="task",
            prompt=(
                "仅根据动作输入中的官方政策摘要与历史关联文件生成政策解读。"
                "只返回 JSON，不要代码块；必须包含 impactAnalysis、"
                "historicalComparison、transcriptComparison。区分事实、推断与"
                "不确定性；impactAnalysis 的 facts、inferences、uncertainties"
                " 必须是字符串数组；没有两份官方正文时 transcriptComparison.status"
                " 必须为 unavailable。"
            ),
            input={"policy": event, "relatedPolicies": related},
        ),
        workspace_id=workspace_id,
    )
    deadline = asyncio.get_running_loop().time() + min(
        settings.agent_timeout_seconds,
        300,
    )
    while asyncio.get_running_loop().time() < deadline:
        current = await service.get(task.id)
        if current.status == "completed":
            result = current.result or {}
            answer = result.get("answer") or result.get("message")
            payload = _model_payload(answer) if isinstance(answer, str) else None
            if payload is None:
                return None
            return {
                **_normalize_interpretation(payload, build_policy_interpretation(event, related)),
                "mode": "ai",
                "model": current.request.model or "CLI",
                "adapter": result.get("agentId") or current.request.adapter,
            }
        if current.status in {"failed", "cancelled"}:
            return None
        await asyncio.sleep(0.2)
    await service.cancel(task.id)
    return None

@router.post("/events/{event_id}/interpretation")
async def interpret_policy_event(
    event_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
    user_id: str = Header(default="local-user", alias="X-User-Id"),
    workspace_id: str = Header(default="local-workspace", alias="X-Workspace-Id"),
) -> dict:
    dashboard = await policy_dashboard(database_path=settings.database_path, rsshub_base_url=settings.policy_rsshub_base_url, timeout_seconds=settings.policy_collector_timeout_seconds)
    event = next((item for item in dashboard["events"] if item["id"] == event_id), None)
    if event is None:
        raise HTTPException(status_code=404, detail="政策不存在")
    if event["status"] != "published":
        raise HTTPException(status_code=409, detail="只有已发布政策可以进行解读")
    related = [item for item in dashboard["events"] if item["id"] in event.get("relatedPolicyIds", [])]
    fallback = build_policy_interpretation(event, related)
    prompt = "仅根据官方政策摘要和历史关联文件输出 JSON，区分事实、推断和不确定性；没有两份官方正文时 transcriptComparison.status 必须为 unavailable。"
    try:
        agent_payload = await _agent_interpretation(
            request,
            settings,
            event,
            related,
            user_id=user_id,
            workspace_id=workspace_id,
        )
        if agent_payload is not None:
            return agent_payload
    except Exception:
        pass
    try:
        response = await request.app.state.model_gateway_service.create_response(ModelResponseCreate(module_id="policy-analysis", capability="policy.interpret", prompt=prompt, context={"policy": event, "relatedPolicies": related}))
        model_payload = _model_payload(response.answer)
        if model_payload is None:
            return fallback
        return {
            **_normalize_interpretation(model_payload, fallback),
            "mode": "ai",
            "model": response.model,
            "adapter": response.adapter,
        }
    except (ModelGatewayError, RuntimeError, AttributeError):
        return fallback
