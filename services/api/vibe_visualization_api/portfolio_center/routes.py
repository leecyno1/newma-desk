from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Path, Query, Request, status
from starlette.concurrency import run_in_threadpool

from vibe_visualization_api.portfolio_center.models import (
    LegacyImportResult,
    PortfolioAccount,
    PortfolioAccountCreate,
    PortfolioActivity,
    PortfolioActivityCreate,
    PortfolioDashboard,
    PortfolioOrder,
    PortfolioOrderCreate,
    PortfolioOrderUpdate,
    PortfolioOptimizationRequest,
    PortfolioOptimizationResult,
    PortfolioPerformanceRequest,
    PortfolioPerformanceResult,
    PortfolioResearchCoverage,
    PortfolioRiskAction,
    PortfolioRiskActionCreate,
    PortfolioRiskActionUpdate,
    SnapshotRiskActionInput,
    PortfolioRiskPolicy,
    PortfolioRiskPolicyInput,
    PortfolioRiskReport,
    PortfolioRiskReportCreate,
    StrategicAllocationRequest,
    StrategicAllocationResult,
)
from vibe_visualization_api.portfolio_center.research import (
    compile_portfolio_research_coverage,
)
from vibe_visualization_api.portfolio_center.diagnosis import ImportValidationError, PortfolioImportInput, PortfolioSnapshotInput, diagnose, parse_import
from vibe_visualization_api.portfolio_center.evidence import read_fund_evidence


router = APIRouter(prefix="/api/portfolio-center", tags=["portfolio-center"])

UserId = Annotated[
    str,
    Header(alias="X-User-Id", min_length=1, max_length=128),
]
WorkspaceId = Annotated[
    str,
    Header(alias="X-Workspace-Id", min_length=1, max_length=128),
]
ActivityId = Annotated[
    str,
    Path(pattern=r"^[A-Za-z0-9][A-Za-z0-9-]{0,63}$"),
]
OrderId = Annotated[
    str,
    Path(pattern=r"^[A-Za-z0-9][A-Za-z0-9-]{0,63}$"),
]
RiskActionId = Annotated[
    str,
    Path(pattern=r"^[A-Za-z0-9][A-Za-z0-9-]{0,63}$"),
]


@router.post('/import-previews')
async def preview_portfolio_import(data: PortfolioImportInput | PortfolioSnapshotInput, request: Request, user_id: UserId = 'local-user', workspace_id: WorkspaceId = 'local-workspace'):
    try:
        snapshot = parse_import(data) if isinstance(data, PortfolioImportInput) else data
    except ImportValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.issues) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    archive = await run_in_threadpool(request.app.state.research_archive_service.list, user_id=user_id, workspace_id=workspace_id)
    return {"snapshot": snapshot.model_dump(mode='json', by_alias=True), "report": diagnose(snapshot, archive)}


@router.get('/import-snapshots')
async def list_portfolio_imports(request: Request, user_id: UserId = 'local-user', workspace_id: WorkspaceId = 'local-workspace'):
    return await run_in_threadpool(request.app.state.portfolio_center_service.list_import_snapshots, user_id=user_id, workspace_id=workspace_id)


@router.post('/import-snapshots', status_code=201)
async def save_portfolio_import(snapshot: PortfolioSnapshotInput, request: Request, user_id: UserId = 'local-user', workspace_id: WorkspaceId = 'local-workspace'):
    archive = await run_in_threadpool(request.app.state.research_archive_service.list, user_id=user_id, workspace_id=workspace_id)
    return await run_in_threadpool(request.app.state.portfolio_center_service.save_import_snapshot, user_id=user_id, workspace_id=workspace_id, snapshot=snapshot.model_dump(mode='json', by_alias=True), report=diagnose(snapshot, archive))


@router.get('/import-products')
async def list_portfolio_import_products(request: Request, user_id: UserId = 'local-user', workspace_id: WorkspaceId = 'local-workspace'):
    return await run_in_threadpool(request.app.state.portfolio_center_service.list_import_products, user_id=user_id, workspace_id=workspace_id)


@router.get('/import-snapshots/{snapshot_id}')
async def get_portfolio_import(snapshot_id: RiskActionId, request: Request, user_id: UserId = 'local-user', workspace_id: WorkspaceId = 'local-workspace'):
    return await run_in_threadpool(request.app.state.portfolio_center_service.get_import_snapshot, user_id=user_id, workspace_id=workspace_id, snapshot_id=snapshot_id)


@router.get('/import-snapshots/{snapshot_id}/risk-actions', response_model=list[PortfolioRiskAction])
async def list_snapshot_actions(snapshot_id: RiskActionId, request: Request, user_id: UserId = 'local-user', workspace_id: WorkspaceId = 'local-workspace'):
    return await run_in_threadpool(request.app.state.portfolio_center_service.list_snapshot_risk_actions, user_id=user_id, workspace_id=workspace_id, snapshot_id=snapshot_id)


@router.post('/import-snapshots/{snapshot_id}/risk-actions', response_model=PortfolioRiskAction, status_code=201)
async def register_snapshot_action(snapshot_id: RiskActionId, data: SnapshotRiskActionInput, request: Request, user_id: UserId = 'local-user', workspace_id: WorkspaceId = 'local-workspace'):
    return await run_in_threadpool(request.app.state.portfolio_center_service.register_snapshot_risk_action, user_id=user_id, workspace_id=workspace_id, snapshot_id=snapshot_id, category=data.category, index=data.index)


@router.post('/import-snapshots/{snapshot_id}/research-evaluations', status_code=201)
async def evaluate_import_research(snapshot_id: RiskActionId, request: Request, user_id: UserId = 'local-user', workspace_id: WorkspaceId = 'local-workspace'):
    service = request.app.state.portfolio_center_service
    saved = await run_in_threadpool(service.get_import_snapshot, user_id=user_id, workspace_id=workspace_id, snapshot_id=snapshot_id)
    snapshot = PortfolioSnapshotInput.model_validate(saved['snapshot'])
    evidence = await read_fund_evidence(snapshot, request.app.state.data_service_client, request.app.state.data_service_registry)
    # 不接收客户端研究数值；保留原测算及参数，新证据单独留档。
    report = {**saved['report'], 'researchEvidence': evidence}
    return await run_in_threadpool(service.save_import_snapshot, user_id=user_id, workspace_id=workspace_id, snapshot=saved['snapshot'], report=report)


@router.get('/risk-reports', response_model=list[PortfolioRiskReport])
async def list_risk_reports(request: Request, user_id: UserId = 'local-user', workspace_id: WorkspaceId = 'local-workspace'):
    return await run_in_threadpool(request.app.state.portfolio_center_service.list_risk_reports, user_id=user_id, workspace_id=workspace_id)


@router.post('/risk-reports', response_model=PortfolioRiskReport, status_code=201)
async def save_risk_report(report: PortfolioRiskReportCreate, request: Request, user_id: UserId = 'local-user', workspace_id: WorkspaceId = 'local-workspace'):
    return await request.app.state.portfolio_center_service.save_risk_report(user_id=user_id, workspace_id=workspace_id, performance_report_id=report.performance_report_id, analysis_input=report.analysis_input)


@router.get('/risk-reports/{report_id}', response_model=PortfolioRiskReport)
async def get_risk_report(report_id: RiskActionId, request: Request, user_id: UserId = 'local-user', workspace_id: WorkspaceId = 'local-workspace'):
    return await run_in_threadpool(request.app.state.portfolio_center_service.get_risk_report, user_id=user_id, workspace_id=workspace_id, report_id=report_id)


@router.post(
    "/asset-allocation/optimize",
    response_model=StrategicAllocationResult,
)
async def optimize_strategic_asset_allocation(
    allocation: StrategicAllocationRequest,
    request: Request,
):
    return await request.app.state.portfolio_center_service.strategic_allocation(
        allocation
    )


@router.get("", response_model=PortfolioDashboard)
async def get_portfolio_dashboard(
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
    include_quotes: Annotated[bool, Query(alias="includeQuotes")] = True,
):
    return await request.app.state.portfolio_center_service.dashboard(
        user_id=user_id,
        workspace_id=workspace_id,
        include_quotes=include_quotes,
    )


@router.get("/research-coverage", response_model=PortfolioResearchCoverage)
async def get_portfolio_research_coverage(
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
):
    dashboard = await request.app.state.portfolio_center_service.dashboard(
        user_id=user_id,
        workspace_id=workspace_id,
        include_quotes=False,
    )
    archive = await run_in_threadpool(
        request.app.state.research_archive_service.list,
        user_id=user_id,
        workspace_id=workspace_id,
    )
    return compile_portfolio_research_coverage(
        user_id=user_id,
        workspace_id=workspace_id,
        positions=dashboard.positions,
        archive=archive,
    )


@router.post(
    "/allocations/optimize",
    response_model=PortfolioOptimizationResult,
)
async def optimize_portfolio_allocation(
    optimization: PortfolioOptimizationRequest,
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
):
    return await request.app.state.portfolio_center_service.optimize_allocation(
        user_id=user_id,
        workspace_id=workspace_id,
        request=optimization,
    )


@router.post(
    "/performance/analyze",
    response_model=PortfolioPerformanceResult,
)
async def analyze_portfolio_performance(
    analysis: PortfolioPerformanceRequest,
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
):
    return await request.app.state.portfolio_center_service.analyze_historical_performance(
        user_id=user_id,
        workspace_id=workspace_id,
        request=analysis,
    )


@router.post(
    "/accounts",
    response_model=PortfolioAccount,
    status_code=status.HTTP_201_CREATED,
)
async def create_portfolio_account(
    account: PortfolioAccountCreate,
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
):
    return await run_in_threadpool(
        request.app.state.portfolio_center_service.create_account,
        user_id=user_id,
        workspace_id=workspace_id,
        account=account,
    )


@router.post(
    "/activities",
    response_model=PortfolioActivity,
    status_code=status.HTTP_201_CREATED,
)
async def create_portfolio_activity(
    activity: PortfolioActivityCreate,
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
):
    return await run_in_threadpool(
        request.app.state.portfolio_center_service.add_activity,
        user_id=user_id,
        workspace_id=workspace_id,
        activity=activity,
    )


@router.post(
    "/orders",
    response_model=PortfolioOrder,
    status_code=status.HTTP_201_CREATED,
)
async def create_portfolio_order(
    order: PortfolioOrderCreate,
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
):
    return await run_in_threadpool(
        request.app.state.portfolio_center_service.create_order,
        user_id=user_id,
        workspace_id=workspace_id,
        order=order,
    )


@router.patch("/orders/{order_id}", response_model=PortfolioOrder)
async def update_portfolio_order(
    update: PortfolioOrderUpdate,
    request: Request,
    order_id: OrderId,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
):
    return await run_in_threadpool(
        request.app.state.portfolio_center_service.update_order,
        user_id=user_id,
        workspace_id=workspace_id,
        order_id=order_id,
        update=update,
    )


@router.put("/risk-policy", response_model=PortfolioRiskPolicy)
async def update_portfolio_risk_policy(
    policy: PortfolioRiskPolicyInput,
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
):
    return await run_in_threadpool(
        request.app.state.portfolio_center_service.update_risk_policy,
        user_id=user_id,
        workspace_id=workspace_id,
        policy=policy,
    )


@router.post(
    "/risk-actions",
    response_model=PortfolioRiskAction,
    status_code=status.HTTP_201_CREATED,
)
async def create_portfolio_risk_action(
    action: PortfolioRiskActionCreate,
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
):
    return await run_in_threadpool(
        request.app.state.portfolio_center_service.create_risk_action,
        user_id=user_id,
        workspace_id=workspace_id,
        action=action,
    )


@router.patch(
    "/risk-actions/{action_id}",
    response_model=PortfolioRiskAction,
)
async def update_portfolio_risk_action(
    update: PortfolioRiskActionUpdate,
    request: Request,
    action_id: RiskActionId,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
):
    return await run_in_threadpool(
        request.app.state.portfolio_center_service.update_risk_action,
        user_id=user_id,
        workspace_id=workspace_id,
        action_id=action_id,
        update=update,
    )


@router.delete(
    "/activities/{activity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_portfolio_activity(
    activity_id: ActivityId,
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
):
    await run_in_threadpool(
        request.app.state.portfolio_center_service.delete_activity,
        user_id=user_id,
        workspace_id=workspace_id,
        activity_id=activity_id,
    )


@router.post("/import/legacy", response_model=LegacyImportResult)
async def import_legacy_portfolio(
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
):
    return await run_in_threadpool(
        request.app.state.portfolio_center_service.import_legacy,
        user_id=user_id,
        workspace_id=workspace_id,
    )
