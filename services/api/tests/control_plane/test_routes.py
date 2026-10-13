from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vibe_visualization_api.config import Settings
from vibe_visualization_api.main import create_app


MANIFEST = {
    "schemaVersion": "1.0",
    "id": "market-daily",
    "name": "市场行情",
    "version": "0.1.0",
    "category": "market",
    "entry": {"type": "structured", "url": "/mods/market-daily/"},
    "permissions": ["market.read"],
    "dataServices": ["market-data"],
    "agentCapabilities": [],
    "events": {"emits": [], "accepts": []},
}


def test_default_desk_app_mounts_the_standalone_agent_and_model_gateways(
    tmp_path: Path,
) -> None:
    application = create_app(
        Settings(
            runtime_dir=tmp_path,
            database_path=tmp_path / "desk.db",
        )
    )

    with TestClient(application) as client:
        schema_paths = client.get("/openapi.json").json()["paths"]
        assert "/api/agent/tasks" in schema_paths
        assert "/api/model/responses" in schema_paths
        assert "/api/agent/preferences" in schema_paths

    assert hasattr(application.state, "agent_task_service")
    assert hasattr(application.state, "agent_task_service_factory")
    assert hasattr(application.state, "model_gateway_service")


def _path_snapshot(path: Path) -> tuple[int, int, int, int] | None:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)


def test_module_must_be_published_before_sidebar_listing(
    client: TestClient,
) -> None:
    draft_response = client.post("/api/modules/drafts", json=MANIFEST)

    assert draft_response.status_code == 201
    draft = draft_response.json()
    assert client.get("/api/modules").json() == []

    response = client.post(
        f"/api/modules/market-daily/revisions/{draft['revision']}/publish"
    )

    assert response.status_code == 200
    assert client.get("/api/modules").json()[0]["manifest"]["id"] == (
        "market-daily"
    )


def test_sidebar_listing_exposes_newma_desk_copilot_prompts(
    client: TestClient,
) -> None:
    draft = client.post("/api/mods/drafts", json=MANIFEST).json()
    client.post(
        f"/api/mods/market-daily/revisions/{draft['revision']}/publish"
    )

    row = client.get("/api/mods").json()[0]
    groups = row["copilotPrompts"]["ask"]
    suggestions = [
        suggestion
        for group in groups
        for suggestion in group["suggestions"]
    ]

    assert [group["label"] for group in groups] == [
        "提炼与核验",
        "风险与推演",
        "延伸与行动",
    ]
    assert [suggestion["intent"] for suggestion in suggestions] == [
        "summary",
        "evidence",
        "risk",
        "scenario",
        "extension",
        "next-step",
    ]
    assert all("当前「市场行情」Mod" in item["prompt"] for item in suggestions)
    assert "行情源" in suggestions[1]["prompt"]
    assert [group["label"] for group in row["copilotPrompts"]["edit"]] == [
        "修改与优化",
        "验证与回归",
    ]

    exact = client.get(
        f"/api/mods/market-daily/revisions/{draft['revision']}"
    ).json()
    assert "copilotPrompts" not in exact


def test_catalyst_calendar_exposes_specialized_copilot_prompts(
    client: TestClient,
) -> None:
    manifest = {
        **MANIFEST,
        "id": "catalyst-calendar",
        "name": "催化剂日历",
        "category": "research",
        "dataServices": ["market-data"],
    }
    draft = client.post("/api/mods/drafts", json=manifest).json()
    client.post(
        f"/api/mods/catalyst-calendar/revisions/{draft['revision']}/publish"
    )

    row = client.get("/api/mods").json()[0]
    groups = row["copilotPrompts"]["ask"]
    suggestions = [
        suggestion
        for group in groups
        for suggestion in group["suggestions"]
    ]
    prompts = "\n".join(item["prompt"] for item in suggestions)

    assert [group["label"] for group in groups] == [
        "日历研判",
        "条件与复盘",
        "补充与跟踪",
    ]
    assert [suggestion["intent"] for suggestion in suggestions] == [
        "summary",
        "evidence",
        "risk",
        "scenario",
        "extension",
        "next-step",
    ]
    assert "已确认日期事件与不确定观察窗" in prompts
    assert "原始催化假设、确认条件、失效条件" in prompts
    assert "不得转换成精确转折日期" in prompts
    assert "财报预期与历史财务" in prompts
    assert "公司、行业和宏观事件" in prompts


def test_macro_monitor_exposes_specialized_copilot_prompts(
    client: TestClient,
) -> None:
    manifest = {
        **MANIFEST,
        "id": "macro-monitor",
        "name": "宏观观察",
        "category": "research",
        "dataServices": ["market-data"],
    }
    draft = client.post("/api/mods/drafts", json=manifest).json()
    client.post(
        f"/api/mods/macro-monitor/revisions/{draft['revision']}/publish"
    )

    row = client.get("/api/mods").json()[0]
    groups = row["copilotPrompts"]["ask"]
    prompts = "\n".join(
        suggestion["prompt"]
        for group in groups
        for suggestion in group["suggestions"]
    )

    assert [group["label"] for group in groups] == [
        "宏观状态",
        "事件与传导",
        "补充与跟踪",
    ]
    assert "增长、价格和流动性" in prompts
    assert "聚合源和原始源" in prompts
    assert "超预期、符合预期和低于预期" in prompts
    assert "就业、信用、贸易、利率、汇率和商品" in prompts


def test_fund_project_metadata_prevents_industry_research_prompt_drift(
    client: TestClient,
) -> None:
    manifest = {
        **MANIFEST,
        "id": "fund-ai-analysis",
        "name": "AI 分析",
        "category": "research",
        "navigation": {
            "groupLabel": "基金",
            "groupOrder": 70,
            "itemOrder": 10,
            "project": {
                "id": "professional-fund-research",
                "name": "基金",
                "order": 70,
                "description": "基金净值、持仓、归因与同类比较。",
            },
            "icon": "research",
        },
    }
    draft = client.post("/api/mods/drafts", json=manifest).json()
    client.post(
        f"/api/mods/fund-ai-analysis/revisions/{draft['revision']}/publish"
    )

    prompts = "\n".join(
        suggestion["prompt"]
        for group in client.get("/api/mods").json()[0]["copilotPrompts"]["ask"]
        for suggestion in group["suggestions"]
    )
    assert "基金代码、名称、类型" in prompts
    assert "净值日期、业绩区间" in prompts
    assert "不要套用产业链公司分析模板" in prompts
    assert "补充产业链上下游、关键公司" not in prompts


def test_workflow_project_metadata_generates_node_edge_and_audit_prompts(
    client: TestClient,
) -> None:
    manifest = {
        **MANIFEST,
        "id": "workflow-designer",
        "name": "流程编排",
        "category": "workflow",
        "navigation": {
            "groupLabel": "工作流",
            "groupOrder": 170,
            "itemOrder": 0,
            "project": {
                "id": "workflow-center",
                "name": "工作流",
                "order": 170,
                "description": "组织节点、授权、运行和交付审计。",
            },
            "icon": "module",
        },
    }
    draft = client.post("/api/mods/drafts", json=manifest).json()
    client.post(
        f"/api/mods/workflow-designer/revisions/{draft['revision']}/publish"
    )

    prompts = "\n".join(
        suggestion["prompt"]
        for group in client.get("/api/mods").json()[0]["copilotPrompts"]["ask"]
        for suggestion in group["suggestions"]
    )
    assert "节点、连线、过程参数" in prompts
    assert "多人覆盖冲突" in prompts
    assert "交付物归档" in prompts


@pytest.mark.parametrize(
    ("module_id", "name", "category", "navigation", "description", "expected", "rejected"),
    [
        (
            "deepsee-ai-insights",
            "Deepsee AI 分析",
            "deepsee",
            {
                "groupLabel": "深瞳",
                "project": {
                    "id": "deepsee",
                    "name": "深瞳",
                    "description": "消息、邮件、会议与外部信息分析。",
                },
            },
            "摘要、观点、趋势和风险机会分析页面。",
            "同步时间、消息时间",
            "参会角色、证据包",
        ),
        (
            "event-timeline",
            "日线时间轴",
            "event",
            {
                "groupLabel": "市场",
                "project": {"id": "market-surface", "name": "市场"},
            },
            "把股票、ETF 与开放式基金按交易日对齐。",
            "行情源、时间戳",
            "基金代码、名称、类型",
        ),
        (
            "factor-correlation",
            "相关性分析",
            "quant",
            {
                "groupLabel": "量化",
                "project": {"id": "quant-research", "name": "量化"},
            },
            "分析因子重复度并用于组合构建。",
            "前视偏差、幸存者偏差",
            "真实成交、持仓、申赎",
        ),
        (
            "orchestra-workspace",
            "Orchestra 账户与组合",
            "decision",
            {
                "groupLabel": "投决",
                "project": {
                    "id": "investment-committee",
                    "name": "投决",
                },
            },
            "管理研究账户、基金组合、交易流水与估值快照。",
            "参会角色、证据包",
            "基金代码、名称、类型",
        ),
        (
            "capital-sectors",
            "行业轮动",
            "market",
            {
                "groupLabel": "行业",
                "project": {"id": "industry-research", "name": "行业"},
            },
            "行业板块资金、价格强弱与轮动状态。",
            "产业链传导断点",
            "真实成交、持仓、申赎",
        ),
        (
            "orchestra-settings",
            "Orchestra 运行设置",
            "decision",
            {
                "groupLabel": "投决",
                "role": "settings",
                "project": {
                    "id": "investment-committee",
                    "name": "投决",
                },
            },
            "配置执行模式、输出、密钥与运行环境。",
            "配置来源、默认值",
            "参会角色、证据包",
        ),
        (
            "fed-rates",
            "联储加息",
            "research",
            {
                "groupLabel": "全球",
                "project": {
                    "id": "global-intelligence",
                    "name": "全球",
                },
            },
            "跟踪利率、通胀与就业传导。",
            "指标发布机构、统计口径",
            "每条新闻的真实标题",
        ),
    ],
)
def test_copilot_profile_routing_uses_structured_mod_ownership(
    client: TestClient,
    module_id: str,
    name: str,
    category: str,
    navigation: dict[str, object],
    description: str,
    expected: str,
    rejected: str,
) -> None:
    manifest = {
        **MANIFEST,
        "id": module_id,
        "name": name,
        "category": category,
        "presentation": {
            "englishName": name,
            "description": description,
            "titleOwner": "host",
        },
        "navigation": {
            "groupOrder": 10,
            "itemOrder": 10,
            "icon": "module",
            **navigation,
        },
    }
    draft = client.post("/api/mods/drafts", json=manifest).json()
    client.post(f"/api/mods/{module_id}/revisions/{draft['revision']}/publish")

    prompts = "\n".join(
        suggestion["prompt"]
        for group in client.get("/api/mods").json()[0]["copilotPrompts"]["ask"]
        for suggestion in group["suggestions"]
    )
    assert expected in prompts
    assert rejected not in prompts


def test_cycle_research_exposes_view_aware_copilot_prompts(
    client: TestClient,
) -> None:
    manifest = {
        **MANIFEST,
        "id": "seven-cycle-research",
        "name": "周期叠加",
        "category": "research",
        "navigation": {
            "groupLabel": "宏观",
            "groupOrder": 10,
            "itemOrder": 10,
            "project": {"id": "fundamentals", "name": "宏观"},
            "icon": "research",
        },
    }
    draft = client.post("/api/mods/drafts", json=manifest).json()
    client.post(
        f"/api/mods/seven-cycle-research/revisions/{draft['revision']}/publish"
    )

    groups = client.get("/api/mods").json()[0]["copilotPrompts"]["ask"]
    prompts = "\n".join(
        suggestion["prompt"]
        for group in groups
        for suggestion in group["suggestions"]
    )
    assert [group["label"] for group in groups] == [
        "当前曲面",
        "背离与路径",
        "补证与跟踪",
    ]
    assert "2D/3D、时间范围、历史或预测图层、聚焦轨道" in prompts
    assert "结构化页面字段、视觉快照读取与研究推断" in prompts
    assert "页面没有提供的数据必须标记为未知" in prompts


def test_specialized_page_prompts_do_not_leak_from_project_description(
    client: TestClient,
) -> None:
    manifest = {
        **MANIFEST,
        "id": "research-library",
        "name": "研究档案",
        "category": "research",
        "navigation": {
            "groupLabel": "公司",
            "groupOrder": 10,
            "itemOrder": 10,
            "project": {
                "id": "equity-research",
                "name": "公司",
                "description": "覆盖投资逻辑、研究备忘录和财报研究。",
            },
            "icon": "research",
        },
    }
    draft = client.post("/api/mods/drafts", json=manifest).json()
    client.post(
        f"/api/mods/research-library/revisions/{draft['revision']}/publish"
    )

    groups = client.get("/api/mods").json()[0]["copilotPrompts"]["ask"]
    assert [group["label"] for group in groups] == [
        "提炼与核验",
        "风险与推演",
        "延伸与行动",
    ]


def test_thesis_tracker_exposes_specialized_copilot_prompts(
    client: TestClient,
) -> None:
    manifest = {
        **MANIFEST,
        "id": "thesis-tracker",
        "name": "投资逻辑",
        "category": "research",
        "dataServices": ["market-data"],
    }
    draft = client.post("/api/mods/drafts", json=manifest).json()
    client.post(
        f"/api/mods/thesis-tracker/revisions/{draft['revision']}/publish"
    )

    row = client.get("/api/mods").json()[0]
    groups = row["copilotPrompts"]["ask"]
    suggestions = [
        suggestion
        for group in groups
        for suggestion in group["suggestions"]
    ]
    prompts = "\n".join(item["prompt"] for item in suggestions)

    assert [group["label"] for group in groups] == [
        "逻辑校验",
        "反证与情景",
        "复盘与跟踪",
    ]
    assert [suggestion["intent"] for suggestion in suggestions] == [
        "summary",
        "evidence",
        "risk",
        "scenario",
        "extension",
        "next-step",
    ]
    assert "是否仍然完整且可证伪" in prompts
    assert "原始预期、当前状态、趋势与关联证据" in prompts
    assert "当前档案未记录的反例与冲突证据" in prompts
    assert "更长时间区间的行情与财务数据" in prompts
    assert "不要给出买卖或仓位建议" in prompts


def test_earnings_workbench_exposes_specialized_copilot_prompts(
    client: TestClient,
) -> None:
    manifest = {
        **MANIFEST,
        "id": "earnings-workbench",
        "name": "财报研究",
        "category": "research",
        "dataServices": ["market-data"],
    }
    draft = client.post("/api/mods/drafts", json=manifest).json()
    client.post(
        f"/api/mods/earnings-workbench/revisions/{draft['revision']}/publish"
    )

    row = client.get("/api/mods").json()[0]
    groups = row["copilotPrompts"]["ask"]
    prompts = "\n".join(
        suggestion["prompt"]
        for group in groups
        for suggestion in group["suggestions"]
    )

    assert [group["label"] for group in groups] == [
        "财报前准备",
        "结果与预期差",
        "指引与逻辑更新",
    ]
    assert "核验最新待披露报告期" in prompts
    assert "实际、内部预期和一致预期" in prompts
    assert "累计/单季/年度/TTM" in prompts
    assert "公告列表不等于原文已核验" in prompts
    assert "未知或不一致时列为待核对" in prompts
    assert "当前指引与上次指引" in prompts
    assert "增强、削弱、不改变或证伪" in prompts
    assert "不要生成评级、目标价或交易动作" in prompts


def test_peer_comparison_exposes_specialized_copilot_prompts(
    client: TestClient,
) -> None:
    manifest = {
        **MANIFEST,
        "id": "peer-comparison",
        "name": "同业比较",
        "category": "research",
        "dataServices": ["market-data"],
    }
    draft = client.post("/api/mods/drafts", json=manifest).json()
    client.post(
        f"/api/mods/peer-comparison/revisions/{draft['revision']}/publish"
    )

    row = client.get("/api/mods").json()[0]
    groups = row["copilotPrompts"]["ask"]
    prompts = "\n".join(
        suggestion["prompt"]
        for group in groups
        for suggestion in group["suggestions"]
    )

    assert [group["label"] for group in groups] == [
        "同业与口径",
        "指标与差异",
        "竞争与跟踪",
    ]
    assert "审计同业集合" in prompts
    assert "报告期、财年结束日、币种" in prompts
    assert "目标值、同业中位数与 25/75 分位" in prompts
    assert "不得直接得出高估、低估或买卖结论" in prompts
    assert "网络效应、转换成本、规模经济" in prompts


def test_valuation_workbench_exposes_specialized_copilot_prompts(
    client: TestClient,
) -> None:
    manifest = {
        **MANIFEST,
        "id": "valuation-workbench",
        "name": "预测与估值",
        "category": "research",
        "dataServices": ["market-data"],
    }
    draft = client.post("/api/mods/drafts", json=manifest).json()
    client.post(
        f"/api/mods/valuation-workbench/revisions/{draft['revision']}/publish"
    )

    row = client.get("/api/mods").json()[0]
    groups = row["copilotPrompts"]["ask"]
    prompts = "\n".join(
        suggestion["prompt"]
        for group in groups
        for suggestion in group["suggestions"]
    )

    assert [group["label"] for group in groups] == [
        "假设与口径",
        "估值与敏感性",
        "审计与更新",
    ]
    assert "历史事实、管理层指引和研究假设" in prompts
    assert "显式期 FCF 现值、终值、企业价值" in prompts
    assert "reviewStatus.ready" in prompts
    assert "不得绕过页面确认计算每股价值或目标价" in prompts
    assert "equityBridgePolicy" in prompts
    assert "不重复扣 excludedCashM" in prompts
    assert "账面值不是估值" in prompts
    assert "用户粘贴摘录不代表系统已读取或审计原文" in prompts
    assert "5×5 敏感性矩阵" in prompts
    assert "终值占比过高" in prompts
    assert "不得把模型差异直接转换为买卖建议" in prompts


def test_research_memo_exposes_specialized_copilot_prompts(
    client: TestClient,
) -> None:
    manifest = {
        **MANIFEST,
        "id": "research-memo",
        "name": "研究备忘录",
        "category": "research",
        "dataServices": ["market-data"],
    }
    draft = client.post("/api/mods/drafts", json=manifest).json()
    client.post(
        f"/api/mods/research-memo/revisions/{draft['revision']}/publish"
    )

    row = client.get("/api/mods").json()[0]
    groups = row["copilotPrompts"]["ask"]
    prompts = "\n".join(
        suggestion["prompt"]
        for group in groups
        for suggestion in group["suggestions"]
    )

    assert [group["label"] for group in groups] == [
        "结论与证据",
        "反方与情景",
        "补充与版本",
    ]
    assert "已报告事实、管理层指引、市场一致预期和研究推断" in prompts
    assert "关联 Mod 与档案 ID" in prompts
    assert "概率是否合计 100%" in prompts
    assert "新增、删除和改变了哪些判断" in prompts
    assert "不要输出买卖评级、仓位或个性化建议" in prompts


def test_idea_funnel_exposes_specialized_copilot_prompts(
    client: TestClient,
) -> None:
    manifest = {
        **MANIFEST,
        "id": "idea-funnel",
        "name": "研究机会池",
        "category": "research",
        "dataServices": ["market-data"],
    }
    draft = client.post("/api/mods/drafts", json=manifest).json()
    client.post(
        f"/api/mods/idea-funnel/revisions/{draft['revision']}/publish"
    )

    row = client.get("/api/mods").json()[0]
    groups = row["copilotPrompts"]["ask"]
    prompts = "\n".join(
        suggestion["prompt"]
        for group in groups
        for suggestion in group["suggestions"]
    )

    assert [group["label"] for group in groups] == [
        "筛选与排序",
        "双向假设",
        "补证与交接",
    ]
    assert "样本偏差、过拟合或重复暴露" in prompts
    assert "初始假设和反方假设" in prompts
    assert "所有权与拥挤度" in prompts
    assert "投资逻辑、财报研究、同业比较、预测与估值或研究备忘录" in prompts
    assert "复核到期、任务逾期、来源陈旧和档案缺口" in prompts
    assert "立即处理、本周处理、等待披露和条件触发" in prompts
    assert "不要输出买卖、目标价或仓位建议" in prompts


def test_mod_api_is_canonical_and_legacy_module_routes_remain_compatible(
    client: TestClient,
) -> None:
    draft = client.post("/api/mods/drafts", json=MANIFEST).json()
    published = client.post(
        f"/api/mods/market-daily/revisions/{draft['revision']}/publish"
    )

    assert published.status_code == 200
    assert client.get("/api/mods").json() == client.get("/api/modules").json()


def test_app_factory_settings_drive_repository_dependency(
    tmp_path: Path,
) -> None:
    default_database_path = Path("runtime/vibe-visualization.db")
    default_database_before = _path_snapshot(default_database_path)
    database_path = tmp_path / "factory-settings.db"
    application = create_app(
        Settings(runtime_dir=tmp_path, database_path=database_path)
    )

    try:
        with TestClient(application) as client:
            response = client.post("/api/modules/drafts", json=MANIFEST)
    finally:
        application.dependency_overrides.clear()

    assert response.status_code == 201
    assert database_path.exists()
    assert _path_snapshot(default_database_path) == default_database_before


def test_parallel_registry_reads_and_writes_do_not_lock_database(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "parallel-registry.db"
    application = create_app(
        Settings(runtime_dir=tmp_path, database_path=database_path)
    )

    def request(client: TestClient, index: int) -> int:
        if index % 3:
            return client.get("/api/mods").status_code
        manifest = {
            **MANIFEST,
            "id": f"parallel-mod-{index}",
            "name": f"Parallel Mod {index}",
        }
        return client.post("/api/mods/drafts", json=manifest).status_code

    with TestClient(application) as client:
        with ThreadPoolExecutor(max_workers=12) as executor:
            statuses = list(
                executor.map(lambda index: request(client, index), range(60))
            )

    assert set(statuses) <= {200, 201}
    assert database_path.exists()


def test_get_exact_revision_preserves_camel_case_manifest(
    client: TestClient,
) -> None:
    draft = client.post("/api/modules/drafts", json=MANIFEST).json()

    response = client.get(
        f"/api/modules/market-daily/revisions/{draft['revision']}"
    )

    assert response.status_code == 200
    assert response.json() == draft
    assert response.json()["moduleId"] == "market-daily"
    assert response.json()["manifest"]["schemaVersion"] == "1.0"
    assert response.json()["manifest"]["dataServices"] == ["market-data"]
    assert response.json()["manifest"]["agentCapabilities"] == []
    assert "schema_version" not in response.json()["manifest"]


def test_navigation_metadata_survives_draft_storage(client: TestClient) -> None:
    navigation = {
        "groupLabel": "市场",
        "groupOrder": 20,
        "itemOrder": 10,
        "label": "行情",
        "directory": {
            "id": "market-suite",
            "label": "市场工具",
            "order": 5,
        },
        "icon": "market",
        "project": {
            "id": "market-suite",
            "name": "市场工具",
            "order": 5,
            "description": "统一行情与市场分析入口。",
            "logo": {"type": "letter", "text": "市"},
        },
    }

    response = client.post(
        "/api/modules/drafts",
        json={**MANIFEST, "navigation": navigation},
    )

    assert response.status_code == 201
    assert response.json()["manifest"]["navigation"] == navigation


@pytest.mark.parametrize(
    ("src", "expected_status"),
    [
        ("/assets/project-logo.svg", 201),
        ("https://assets.example/project-logo.svg", 201),
        ("javascript:alert(1)", 422),
        ("/assets/%252e%252e/secret.svg", 422),
    ],
)
def test_project_image_logo_uses_safe_module_urls(
    client: TestClient,
    src: str,
    expected_status: int,
) -> None:
    response = client.post(
        "/api/mods/drafts",
        json={
            **MANIFEST,
            "navigation": {
                "groupLabel": "市场",
                "project": {
                    "id": "market-suite",
                    "name": "市场工具",
                    "logo": {"type": "image", "src": src, "alt": "市场工具"},
                },
            },
        },
    )

    assert response.status_code == expected_status


@pytest.mark.parametrize("icon", ["today", "trading", "settings"])
def test_first_party_navigation_icons_are_accepted(
    client: TestClient, icon: str
) -> None:
    response = client.post(
        "/api/mods/drafts",
        json={
            **MANIFEST,
            "id": f"{icon}-workspace",
            "navigation": {
                "groupLabel": "工作区",
                "groupOrder": 10,
                "itemOrder": 10,
                "icon": icon,
            },
        },
    )

    assert response.status_code == 201
    assert response.json()["manifest"]["navigation"]["icon"] == icon


def test_disable_removes_module_from_sidebar_listing(client: TestClient) -> None:
    draft = client.post("/api/modules/drafts", json=MANIFEST).json()
    client.post(
        f"/api/modules/market-daily/revisions/{draft['revision']}/publish"
    )

    response = client.post("/api/modules/market-daily/disable")

    assert response.status_code == 200
    assert response.json()["status"] == "disabled"
    assert client.get("/api/modules").json() == []


def test_rollback_republishes_disabled_prior_revision(
    client: TestClient,
) -> None:
    first = client.post("/api/modules/drafts", json=MANIFEST).json()
    client.post(
        f"/api/modules/market-daily/revisions/{first['revision']}/publish"
    )
    second = client.post(
        "/api/modules/drafts",
        json={**MANIFEST, "version": "0.2.0"},
    ).json()
    client.post(
        f"/api/modules/market-daily/revisions/{second['revision']}/publish"
    )

    response = client.post(
        f"/api/modules/market-daily/revisions/{first['revision']}/rollback"
    )

    assert response.status_code == 200
    assert response.json()["revision"] == first["revision"]
    assert response.json()["status"] == "published"
    assert client.get("/api/modules").json()[0]["revision"] == first["revision"]


def test_rollback_recovers_module_after_disable(client: TestClient) -> None:
    first = client.post("/api/modules/drafts", json=MANIFEST).json()
    client.post(
        f"/api/modules/market-daily/revisions/{first['revision']}/publish"
    )
    second = client.post(
        "/api/modules/drafts",
        json={**MANIFEST, "version": "0.2.0"},
    ).json()
    client.post(
        f"/api/modules/market-daily/revisions/{second['revision']}/publish"
    )
    client.post("/api/modules/market-daily/disable")

    response = client.post(
        f"/api/modules/market-daily/revisions/{first['revision']}/rollback"
    )

    assert response.status_code == 200
    assert response.json()["status"] == "published"
    assert response.json()["revision"] == first["revision"]
    listed = client.get("/api/modules").json()
    assert len(listed) == 1
    assert {
        key: value
        for key, value in listed[0].items()
        if key != "copilotPrompts"
    } == response.json()


def test_missing_revision_returns_not_found(client: TestClient) -> None:
    response = client.get("/api/modules/missing/revisions/999")

    assert response.status_code == 404
    assert response.json() == {"detail": "module revision not found"}


def test_publish_missing_target_returns_not_found(client: TestClient) -> None:
    response = client.post("/api/modules/missing/revisions/999/publish")

    assert response.status_code == 404
    assert response.json() == {"detail": "module revision not found"}


def test_disable_missing_module_returns_not_found(client: TestClient) -> None:
    response = client.post("/api/modules/missing/disable")

    assert response.status_code == 404
    assert response.json() == {"detail": "module revision not found"}


def test_rollback_missing_target_returns_not_found(client: TestClient) -> None:
    response = client.post("/api/modules/missing/revisions/999/rollback")

    assert response.status_code == 404
    assert response.json() == {"detail": "module revision not found"}


def test_invalid_publish_state_returns_conflict(client: TestClient) -> None:
    draft = client.post("/api/modules/drafts", json=MANIFEST).json()
    url = (
        f"/api/modules/market-daily/revisions/{draft['revision']}/publish"
    )
    client.post(url)

    response = client.post(url)

    assert response.status_code == 409
    assert response.json() == {"detail": "invalid module state"}


def test_invalid_disable_state_returns_conflict(client: TestClient) -> None:
    client.post("/api/modules/drafts", json=MANIFEST)

    response = client.post("/api/modules/market-daily/disable")

    assert response.status_code == 409
    assert response.json() == {"detail": "invalid module state"}


def test_disabled_module_cannot_be_disabled_again(client: TestClient) -> None:
    draft = client.post("/api/modules/drafts", json=MANIFEST).json()
    client.post(
        f"/api/modules/market-daily/revisions/{draft['revision']}/publish"
    )
    client.post("/api/modules/market-daily/disable")

    response = client.post("/api/modules/market-daily/disable")

    assert response.status_code == 409
    assert response.json() == {"detail": "invalid module state"}


def test_invalid_rollback_state_returns_conflict(client: TestClient) -> None:
    draft = client.post("/api/modules/drafts", json=MANIFEST).json()

    response = client.post(
        f"/api/modules/market-daily/revisions/{draft['revision']}/rollback"
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "invalid module state"}


@pytest.mark.parametrize(
    ("change", "value"),
    [
        ("version", "1.0"),
        ("entry", {"type": "static", "url": "../secret"}),
        ("entry", {"type": "static", "url": "//evil.example/app"}),
        ("entry", {"type": "static", "url": "/%2e%2e/secret"}),
        ("entry", {"type": "static", "url": "/%252e%252e/secret"}),
        ("entry", {"type": "static", "url": "/%ZZ"}),
        ("entry", {"type": "external", "url": "ftp://example.com/app"}),
        ("entry", {"type": "external", "url": "http://exa mple.com"}),
        ("events", {"emits": ["selected"], "accepts": []}),
        ("refresh", {"mode": "schedule"}),
        ("refresh", {"mode": "manual", "cron": "* * * * *"}),
        ("icon", None),
        ("refresh", None),
        (
            "entry",
            {
                "type": "structured",
                "url": "/modules/market-daily/",
                "sandbox": False,
            },
        ),
    ],
    ids=[
        "semantic-version",
        "relative-url",
        "network-path-url",
        "encoded-traversal-url",
        "repeatedly-encoded-traversal-url",
        "malformed-encoded-url",
        "non-http-external-url",
        "malformed-external-url",
        "unnamespaced-event",
        "scheduled-refresh-without-cron",
        "manual-refresh-with-cron",
        "null-icon",
        "null-refresh",
        "unknown-nested-field",
    ],
)
def test_invalid_manifest_returns_unprocessable_entity(
    client: TestClient,
    change: str,
    value: object,
) -> None:
    response = client.post(
        "/api/modules/drafts",
        json={**MANIFEST, change: value},
    )

    assert response.status_code == 422


def test_unknown_top_level_manifest_field_returns_unprocessable_entity(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/modules/drafts",
        json={**MANIFEST, "unexpected": True},
    )

    assert response.status_code == 422


def test_python_field_names_are_not_accepted_as_json_aliases(
    client: TestClient,
) -> None:
    manifest = {
        key: value for key, value in MANIFEST.items() if key != "schemaVersion"
    }
    manifest["schema_version"] = "1.0"

    response = client.post("/api/modules/drafts", json=manifest)

    assert response.status_code == 422


def test_manifest_defaults_are_returned_with_camel_case_aliases(
    client: TestClient,
) -> None:
    minimal_manifest = {
        key: value
        for key, value in MANIFEST.items()
        if key
        not in {"permissions", "dataServices", "agentCapabilities", "events"}
    }

    response = client.post("/api/modules/drafts", json=minimal_manifest)

    assert response.status_code == 201
    assert response.json()["manifest"] == {
        **minimal_manifest,
        "permissions": [],
        "dataServices": [],
        "agentCapabilities": [],
        "events": {"emits": [], "accepts": []},
    }
    assert "refresh" not in response.json()["manifest"]


def test_manifest_1_1_accepts_explicit_action_bindings(
    client: TestClient,
) -> None:
    manifest = {
        "schemaVersion": "1.1",
        "id": "factor-lab",
        "name": "因子实验室",
        "version": "1.0.0",
        "category": "quant",
        "entry": {"type": "external", "url": "https://quant.example/mod"},
        "compatibility": {
            "level": 2,
            "bridgeProtocol": "1.0",
            "sdkVersion": "^0.2.0",
        },
        "permissions": ["quant.execute", "research.read"],
        "dataServices": ["vibe-trading"],
        "actions": {
            "factor.backtest": {
                "binding": {
                    "type": "data",
                    "service": "vibe-trading",
                },
                "execution": "task",
                "permission": "quant.execute",
            },
            "research.explain": {
                "binding": {
                    "type": "agent",
                    "memoryScope": "user-agent-mod",
                },
                "execution": "task",
                "permission": "research.read",
            },
        },
    }

    response = client.post("/api/modules/drafts", json=manifest)

    assert response.status_code == 201
    stored = response.json()["manifest"]
    assert stored["schemaVersion"] == "1.1"
    assert "agentCapabilities" not in stored
    assert stored["actions"]["research.explain"]["confirmation"] == "none"


@pytest.mark.parametrize(
    "update",
    [
        {
            "compatibility": {
                "level": 3,
                "bridgeProtocol": "1.0",
            }
        },
        {"permissions": []},
        {"dataServices": []},
        {"agentCapabilities": ["research.explain"]},
    ],
)
def test_manifest_1_1_rejects_incomplete_or_legacy_declarations(
    client: TestClient,
    update: dict[str, object],
) -> None:
    manifest = {
        "schemaVersion": "1.1",
        "id": "factor-lab",
        "name": "因子实验室",
        "version": "1.0.0",
        "category": "quant",
        "entry": {"type": "external", "url": "https://quant.example/mod"},
        "compatibility": {
            "level": 3,
            "bridgeProtocol": "1.0",
            "viewSpecVersion": "1.0",
        },
        "permissions": ["quant.execute"],
        "dataServices": ["vibe-trading"],
        "actions": {
            "factor.backtest": {
                "binding": {
                    "type": "data",
                    "service": "vibe-trading",
                },
                "execution": "task",
                "permission": "quant.execute",
            }
        },
        **update,
    }

    response = client.post("/api/modules/drafts", json=manifest)

    assert response.status_code == 422


@pytest.mark.parametrize(
    "entry",
    [
        {"type": "structured", "url": "/modules/market-daily/"},
        {"type": "static", "url": "/modules/market-daily/index.html"},
        {"type": "external", "url": "https://example.com/module"},
        {"type": "external", "url": "http:example.com"},
    ],
)
def test_supported_entry_types_are_accepted(
    client: TestClient, entry: dict[str, str]
) -> None:
    response = client.post(
        "/api/modules/drafts", json={**MANIFEST, "entry": entry}
    )

    assert response.status_code == 201
    assert response.json()["manifest"]["entry"] == entry
