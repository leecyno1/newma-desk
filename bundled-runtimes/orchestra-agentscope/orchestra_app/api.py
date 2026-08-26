from __future__ import annotations

from contextlib import asynccontextmanager
from urllib.parse import quote

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .exports import build_docx, build_pdf
from .models import (
    AgentInterventionRequest,
    AgentInterventionResponse,
    CreatePortfolioRequest,
    CreatePortfolioTransactionRequest,
    CreatePortfolioValuationRequest,
    CreateRunRequest,
    CreateRunResponse,
    CreateSecretRequest,
    CreateUserRequest,
    CreateUserResponse,
    CreateSessionRequest,
    CreateAgentRequest,
    AuthSessionResponse,
    Portfolio,
    PortfolioDetail,
    PortfolioNavSnapshot,
    PortfolioTransaction,
    ProfileUpdate,
    ReconsiderRunRequest,
    RunComparisonRequest,
    RunSnapshot,
    RunSummary,
    SecretMetadata,
    UserProfile,
)
from .registry import (
    create_profile,
    delete_profile,
    public_profiles,
    public_skill_catalog,
    skill_catalog,
    update_profile,
)
from .service import committee_service
from .settings import settings


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await committee_service.startup()
    try:
        yield
    finally:
        await committee_service.shutdown()


app = FastAPI(
    title="Orchestra Investment Committee",
    version="0.6.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SESSION_COOKIE = "orchestra_session"


def current_user(
    x_orchestra_user: str | None = Header(default=None, alias="X-Orchestra-User"),
    authorization: str | None = Header(default=None, alias="Authorization"),
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> UserProfile:
    if session_token:
        user = committee_service.authenticate_session(session_token)
        if user is None:
            raise HTTPException(status_code=401, detail="用户会话已失效。")
        return user
    user_id = x_orchestra_user or settings.default_user_id
    try:
        user = committee_service.current_user(user_id)
    except KeyError as error:
        raise HTTPException(status_code=401, detail="用户身份无效。") from error
    if user_id != settings.default_user_id:
        scheme, _, token = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not token or not committee_service.verify_user_token(
            user_id,
            token,
        ):
            raise HTTPException(status_code=401, detail="用户令牌无效。")
    return user


def require_writer(user: UserProfile) -> None:
    if user.role == "viewer":
        raise HTTPException(status_code=403, detail="只读用户不能执行该操作。")


def require_owner(user: UserProfile) -> None:
    if user.role != "owner":
        raise HTTPException(status_code=403, detail="仅管理员可以执行该操作。")


@app.get("/healthz")
async def healthz() -> dict[str, object]:
    return {
        "status": "ok",
        "agents": len(public_profiles()),
        "default_mode": settings.default_mode,
        "live_ready": bool(settings.openai_api_key),
        "model": settings.openai_model if settings.openai_api_key else None,
        "data_tools": {
            "tushare": bool(settings.tushare_token),
            "a_stock": True,
            "global_stock": True,
            "tavily": bool(settings.tavily_api_key),
            "ima": bool(settings.ima_client_id and settings.ima_api_key),
        },
    }


@app.get("/api/users/me", response_model=UserProfile)
async def get_me(user: UserProfile = Depends(current_user)) -> UserProfile:
    return user


@app.post("/api/auth/session", response_model=AuthSessionResponse, status_code=201)
async def create_auth_session(
    request: CreateSessionRequest,
    response: Response,
) -> AuthSessionResponse:
    try:
        user, session_token, expires_at = committee_service.create_session(
            request.user_id.strip(),
            request.api_token,
        )
    except (KeyError, PermissionError) as error:
        raise HTTPException(status_code=401, detail="用户ID或API Token无效。") from error
    response.set_cookie(
        key=SESSION_COOKIE,
        value=session_token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="strict",
        path="/",
    )
    return AuthSessionResponse(user=user, expires_at=expires_at)


@app.delete("/api/auth/session", status_code=204)
async def delete_auth_session(
    response: Response,
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> Response:
    if session_token:
        committee_service.revoke_session(session_token)
    response.delete_cookie(
        key=SESSION_COOKIE,
        path="/",
        secure=settings.session_cookie_secure,
        samesite="strict",
    )
    response.status_code = 204
    return response


@app.get("/api/users", response_model=list[UserProfile])
async def list_users(user: UserProfile = Depends(current_user)) -> list[UserProfile]:
    require_owner(user)
    return committee_service.list_users()


@app.post("/api/users", response_model=CreateUserResponse, status_code=201)
async def create_user(
    request: CreateUserRequest,
    user: UserProfile = Depends(current_user),
) -> CreateUserResponse:
    require_owner(user)
    created, api_token = committee_service.create_user(request.name.strip(), request.role)
    return CreateUserResponse(user=created, api_token=api_token)


@app.get("/api/portfolios", response_model=list[Portfolio])
async def list_portfolios(user: UserProfile = Depends(current_user)) -> list[Portfolio]:
    return committee_service.list_portfolios(user.id)


@app.post("/api/portfolios", response_model=Portfolio, status_code=201)
async def create_portfolio(
    request: CreatePortfolioRequest,
    user: UserProfile = Depends(current_user),
) -> Portfolio:
    require_writer(user)
    return committee_service.create_portfolio(
        user.id,
        request.name.strip(),
        request.description.strip(),
        request.base_currency,
    )


@app.get("/api/portfolios/{portfolio_id}", response_model=PortfolioDetail)
async def get_portfolio_detail(
    portfolio_id: str,
    user: UserProfile = Depends(current_user),
) -> PortfolioDetail:
    try:
        return committee_service.get_portfolio_detail(portfolio_id, user.id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="基金组合不存在。") from error


@app.post(
    "/api/portfolios/{portfolio_id}/transactions",
    response_model=PortfolioTransaction,
    status_code=201,
)
async def create_portfolio_transaction(
    portfolio_id: str,
    request: CreatePortfolioTransactionRequest,
    user: UserProfile = Depends(current_user),
) -> PortfolioTransaction:
    require_writer(user)
    try:
        return committee_service.create_portfolio_transaction(
            portfolio_id,
            user.id,
            request,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail="基金组合不存在。") from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post(
    "/api/portfolios/{portfolio_id}/valuations",
    response_model=PortfolioNavSnapshot,
    status_code=201,
)
async def create_portfolio_valuation(
    portfolio_id: str,
    request: CreatePortfolioValuationRequest,
    user: UserProfile = Depends(current_user),
) -> PortfolioNavSnapshot:
    require_writer(user)
    try:
        return committee_service.create_portfolio_valuation(
            portfolio_id,
            user.id,
            request.as_of,
            request.marks,
            request.unit_count,
            request.note,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail="基金组合不存在。") from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/api/secrets", response_model=list[SecretMetadata])
async def list_secrets(user: UserProfile = Depends(current_user)) -> list[SecretMetadata]:
    return committee_service.list_secrets(user.id)


@app.post("/api/secrets", response_model=SecretMetadata, status_code=201)
async def create_secret(
    request: CreateSecretRequest,
    user: UserProfile = Depends(current_user),
) -> SecretMetadata:
    require_writer(user)
    return committee_service.create_secret(
        user.id,
        request.provider,
        request.label.strip(),
        request.value,
    )


@app.delete("/api/secrets/{secret_id}", status_code=204)
async def delete_secret(
    secret_id: str,
    user: UserProfile = Depends(current_user),
) -> Response:
    require_writer(user)
    if not committee_service.delete_secret(secret_id, user.id):
        raise HTTPException(status_code=404, detail="密钥不存在。")
    return Response(status_code=204)


@app.get("/api/agents")
async def agents():
    return public_profiles()


@app.post("/api/agents", status_code=201)
async def create_agent(
    request: CreateAgentRequest,
    user: UserProfile = Depends(current_user),
):
    require_writer(user)
    try:
        return create_profile(request.model_dump(mode="json"))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.patch("/api/agents/{agent_id}")
async def patch_agent(
    agent_id: str,
    request: ProfileUpdate,
    user: UserProfile = Depends(current_user),
):
    require_writer(user)
    try:
        return update_profile(agent_id, request.model_dump(exclude_none=True))
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Agent 不存在。") from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.delete("/api/agents/{agent_id}", status_code=204)
async def remove_agent(
    agent_id: str,
    user: UserProfile = Depends(current_user),
) -> Response:
    require_writer(user)
    try:
        delete_profile(agent_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Agent 不存在。") from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return Response(status_code=204)


@app.get("/api/skills")
async def skills():
    return public_skill_catalog()


@app.get("/api/system/overview")
async def system_overview(user: UserProfile = Depends(current_user)) -> dict[str, object]:
    profiles = public_profiles()
    queue = await committee_service.queue_stats()
    assigned_skills = {skill for profile in profiles for skill in profile.skills}
    missing_skills = {skill for profile in profiles for skill in profile.missing_skills}
    groups: dict[str, int] = {}
    endpoints: set[str] = set()
    for profile in profiles:
        groups[profile.group] = groups.get(profile.group, 0) + 1
        endpoints.update(profile.tushare_endpoints)
    return {
        "version": app.version,
        "persistence": committee_service.store.backend_name,
        "database_path": committee_service.store.location,
        "schema_version": committee_service.store.schema_version(),
        "queue_backend": queue["backend"],
        "queue": queue,
        "redis_configured": bool(settings.redis_url),
        "secret_vault": committee_service.vault.describe() if committee_service.vault else None,
        "max_concurrency": settings.max_concurrency,
        "run_history_limit": settings.max_run_history,
        "runs": committee_service.run_metrics(user.id),
        "groups": groups,
        "skills": {
            "installed": len(set(skill_catalog().values())),
            "assigned": len(assigned_skills),
            "missing": len(missing_skills),
        },
        "data": {
            "tushare_endpoints": len(endpoints),
            "tushare_ready": bool(settings.tushare_token),
            "a_stock_ready": True,
            "global_stock_ready": True,
            "tavily_ready": bool(settings.tavily_api_key),
            "ima_ready": bool(settings.ima_client_id and settings.ima_api_key),
            "llm_ready": bool(settings.openai_api_key),
        },
    }


@app.get("/api/system/queue")
async def queue_overview(user: UserProfile = Depends(current_user)) -> dict[str, object]:
    require_owner(user)
    return await committee_service.queue_stats()


@app.get("/api/system/queue/jobs")
async def queue_jobs(
    limit: int = Query(default=30, ge=1, le=100),
    user: UserProfile = Depends(current_user),
) -> list[dict[str, object]]:
    require_owner(user)
    return await committee_service.list_queue_jobs(limit)


@app.post("/api/runs", response_model=CreateRunResponse, status_code=202)
async def create_run(
    request: CreateRunRequest,
    user: UserProfile = Depends(current_user),
) -> CreateRunResponse:
    require_writer(user)
    if request.mode == "live" and not settings.openai_api_key and "openai" not in request.secret_refs:
        raise HTTPException(status_code=409, detail="live模式尚未配置LLM密钥。")
    if request.portfolio_id and committee_service.store.get_portfolio(
        request.portfolio_id,
        user.id,
    ) is None:
        raise HTTPException(status_code=404, detail="基金组合不存在。")
    if set(request.secret_refs) - {"openai", "tushare", "tavily", "ima"}:
        raise HTTPException(status_code=422, detail="secret_refs 包含未知服务。")
    snapshot = await committee_service.create_run(
        request.topic.strip(),
        request.mode,
        owner_id=user.id,
        portfolio_id=request.portfolio_id,
        secret_refs=request.secret_refs,
    )
    return CreateRunResponse(run_id=snapshot.id, status=snapshot.status, mode=snapshot.mode)


@app.get("/api/runs", response_model=list[RunSummary])
async def list_runs(
    limit: int = Query(default=20, ge=1, le=100),
    user: UserProfile = Depends(current_user),
) -> list[RunSummary]:
    return committee_service.list_runs(limit, user.id)


@app.post("/api/run-comparisons")
async def compare_runs(
    request: RunComparisonRequest,
    user: UserProfile = Depends(current_user),
):
    if len(set(request.run_ids)) != len(request.run_ids):
        raise HTTPException(status_code=422, detail="对比运行不能重复。")
    try:
        return committee_service.compare_runs(request.run_ids, user.id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="对比运行不存在。") from error


@app.get("/api/runs/{run_id}", response_model=RunSnapshot)
async def get_run(
    run_id: str,
    user: UserProfile = Depends(current_user),
) -> RunSnapshot:
    try:
        return committee_service.get_run(run_id, user.id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="投委会运行不存在。") from error


@app.get("/api/runs/{run_id}/artifacts")
async def run_artifacts(run_id: str, user: UserProfile = Depends(current_user)):
    try:
        return committee_service.list_artifacts(run_id, user.id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="投委会运行不存在。") from error


@app.get("/api/runs/{run_id}/evidence")
async def run_evidence(run_id: str, user: UserProfile = Depends(current_user)):
    try:
        return committee_service.list_evidence(run_id, user.id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="投委会运行不存在。") from error


@app.post("/api/runs/{run_id}/revisions", response_model=CreateRunResponse, status_code=202)
async def reconsider_run(
    run_id: str,
    request: ReconsiderRunRequest,
    user: UserProfile = Depends(current_user),
) -> CreateRunResponse:
    require_writer(user)
    try:
        snapshot = await committee_service.reconsider_run(
            run_id,
            user.id,
            request.note.strip(),
            request.mode,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail="投委会运行不存在。") from error
    return CreateRunResponse(run_id=snapshot.id, status=snapshot.status, mode=snapshot.mode)


@app.post(
    "/api/runs/{run_id}/agents/{agent_id}/interventions",
    response_model=AgentInterventionResponse,
    status_code=202,
)
async def start_agent_intervention(
    run_id: str,
    agent_id: str,
    request: AgentInterventionRequest,
    user: UserProfile = Depends(current_user),
) -> AgentInterventionResponse:
    require_writer(user)
    try:
        result = await committee_service.start_agent_intervention(
            run_id,
            agent_id,
            user.id,
            request.action,
            request.instruction.strip(),
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail="运行或 Agent 不存在。") from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return AgentInterventionResponse.model_validate(result)


@app.get("/api/runs/{run_id}/exports/{format_name}")
async def export_run(
    run_id: str,
    format_name: str,
    user: UserProfile = Depends(current_user),
) -> Response:
    try:
        snapshot = committee_service.get_run(run_id, user.id)
        artifacts = committee_service.list_artifacts(run_id, user.id)
        evidence = committee_service.list_evidence(run_id, user.id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="投委会运行不存在。") from error
    if format_name == "pdf":
        content = build_pdf(snapshot, artifacts, evidence)
        media_type = "application/pdf"
        extension = "pdf"
    elif format_name in {"docx", "word"}:
        content = build_docx(snapshot, artifacts, evidence)
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        extension = "docx"
    else:
        raise HTTPException(status_code=404, detail="不支持的导出格式。")
    filename = quote(f"Orchestra-{snapshot.topic[:36]}-v{snapshot.revision}.{extension}")
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@app.get("/api/runs/{run_id}/events")
async def run_events(
    run_id: str,
    after: int = Query(default=0, ge=0),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    user: UserProfile = Depends(current_user),
):
    try:
        committee_service.get_run(run_id, user.id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="投委会运行不存在。") from error
    header_cursor = int(last_event_id) if last_event_id and last_event_id.isdigit() else 0
    cursor = max(after, header_cursor)
    return StreamingResponse(
        committee_service.stream(run_id, cursor, user.id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/runs/{run_id}/event-log")
async def run_event_log(
    run_id: str,
    limit: int = Query(default=600, ge=20, le=1200),
    user: UserProfile = Depends(current_user),
):
    try:
        return committee_service.recent_events(run_id, limit, user.id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="投委会运行不存在。") from error


@app.get("/api/runs/{run_id}/replay-log")
async def run_replay_log(
    run_id: str,
    user: UserProfile = Depends(current_user),
):
    try:
        return committee_service.replay_events(run_id, user.id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="投委会运行不存在。") from error


@app.post("/api/runs/{run_id}/cancel", status_code=202)
async def cancel_run(
    run_id: str,
    user: UserProfile = Depends(current_user),
) -> dict[str, str]:
    require_writer(user)
    try:
        await committee_service.cancel_run(run_id, user.id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="投委会运行不存在。") from error
    return {"status": "cancelled"}
