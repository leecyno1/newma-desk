import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INTEGRATION_ROOT = ROOT / "integrations" / "vibedesk"
NEWMA_ROOT = ROOT / "integrations" / "newma-desk"


def test_level_two_manifests_declare_connected_analysis_actions():
    expected_actions = {
        "czsc": ("instock-czsc", {"analysis.czsc", "analysis.czsc.scan"}),
        "rotation": ("instock-rotation", {
            "analysis.rotation", "analysis.rotation.experiment",
        }),
        "industry-chain": ("instock-industry-chain", {"analysis.industry-chain"}),
        "stock-candidates": ("instock-stock-candidates", {"analysis.stock-candidates"}),
        "stock-research": ("instock-stock-research", {"analysis.stock-research"}),
        "strategy-validation": ("instock-strategy-validation", {"analysis.strategy-validation"}),
        "event-flow": ("instock-event-flow", {"analysis.event-flow"}),
        "research-book": ("instock-research-book", {"analysis.research-book"}),
        "market-workbench": ("instock-market-workbench", {"analysis.market-workbench"}),
        "market-map": ("instock-market-map", {"analysis.market-map"}),
        "technical-signals": ("instock-technical-signals", {"analysis.technical-signals"}),
    }
    for name, (expected_id, action_ids) in expected_actions.items():
        manifest = json.loads((INTEGRATION_ROOT / name / "module.json").read_text("utf-8"))
        store_entry = json.loads((INTEGRATION_ROOT / name / "mod.json").read_text("utf-8"))

        assert manifest["schemaVersion"] == "1.1"
        assert manifest["id"] == expected_id
        assert manifest["compatibility"] == {"level": 2, "bridgeProtocol": "1.0"}
        assert set(manifest["actions"]) == action_ids
        for action_id in action_ids:
            assert manifest["actions"][action_id]["binding"]["capability"] == action_id
            assert manifest["actions"][action_id]["permission"] == "analysis.read"
            if action_id in {
                "analysis.czsc", "analysis.market-workbench", "analysis.market-map",
                "analysis.stock-candidates", "analysis.stock-research",
                "analysis.technical-signals",
            }:
                refresh = manifest["actions"][action_id]["inputSchema"]["properties"]["refresh"]
                assert refresh["enum"] == ["0", "1"]
        assert manifest["entry"]["type"] == "external"
        assert store_entry["runtime"]["route"].startswith("/mods/")
        assert set(store_entry["manifest"]["actions"]) == action_ids
        navigation = store_entry["manifest"]["navigation"]
        assert navigation["project"]["id"] == "quant-research"
        assert navigation["directory"]["id"] == "instock-suite"
        expected_events = {
            "czsc": {"emits": [], "accepts": ["security.selected"]},
            "rotation": {"emits": ["security.selected"], "accepts": []},
            "industry-chain": {"emits": [], "accepts": []},
            "stock-candidates": {"emits": ["security.selected"], "accepts": []},
            "stock-research": {"emits": ["security.selected"], "accepts": ["security.selected"]},
            "strategy-validation": {"emits": [], "accepts": []},
            "event-flow": {"emits": ["security.selected"], "accepts": ["security.selected"]},
            "research-book": {"emits": ["security.selected"], "accepts": ["security.selected"]},
            "market-workbench": {"emits": ["security.selected"], "accepts": []},
            "market-map": {"emits": ["security.selected"], "accepts": []},
            "technical-signals": {"emits": ["security.selected"], "accepts": ["security.selected"]},
        }[name]
        assert manifest["events"] == expected_events
        assert store_entry["manifest"]["events"] == expected_events


def test_newma_suite_is_the_canonical_eleven_page_descriptor():
    suite = json.loads((NEWMA_ROOT / "instock-suite" / "suite.json").read_text("utf-8"))

    assert suite["schemaVersion"] == "1.0"
    assert suite["id"] == "instock-suite"
    assert suite["version"] == "0.17.0"
    for name in ("czsc", "rotation", "industry-chain", "stock-candidates", "stock-research", "strategy-validation", "event-flow", "research-book", "market-workbench", "market-map", "technical-signals"):
        manifest = json.loads((INTEGRATION_ROOT / name / "module.json").read_text("utf-8"))
        store_entry = json.loads((INTEGRATION_ROOT / name / "mod.json").read_text("utf-8"))
        assert manifest["version"] == suite["version"]
        assert store_entry["version"] == suite["version"]
    assert suite["agentWorkspace"] == {
        "type": "runtime", "runtimeId": "instock", "workspaceName": "source",
    }
    assert suite["runtime"]["baseUrlEnv"] == "NEWMA_DESK_INSTOCK_WEB_URL"
    assert suite["manifest"]["compatibility"] == {"level": 2, "bridgeProtocol": "1.0"}
    navigation = suite["manifest"]["navigation"]
    assert navigation["groupLabel"] == "选股"
    assert navigation["groupOrder"] == 15
    assert navigation["project"]["id"] == "equity-research"
    assert navigation["directory"] == {
        "id": "instock-suite", "label": "股票研究", "order": 10,
    }
    pages = {page["id"]: page for page in suite["pages"]}
    assert set(pages) == {"instock-czsc", "instock-rotation", "instock-industry-chain", "instock-stock-candidates", "instock-stock-research", "instock-strategy-validation", "instock-event-flow", "instock-research-book", "instock-market-workbench", "instock-market-map", "instock-technical-signals"}
    assert set(pages["instock-czsc"]["manifest"]["actions"]) == {
        "analysis.czsc", "analysis.czsc.scan",
    }
    assert set(pages["instock-rotation"]["manifest"]["actions"]) == {
        "analysis.rotation", "analysis.rotation.experiment",
    }
    assert set(pages["instock-industry-chain"]["manifest"]["actions"]) == {
        "analysis.industry-chain",
    }
    assert set(pages["instock-stock-candidates"]["manifest"]["actions"]) == {
        "analysis.stock-candidates",
    }
    assert set(pages["instock-stock-research"]["manifest"]["actions"]) == {
        "analysis.stock-research",
    }
    assert set(pages["instock-strategy-validation"]["manifest"]["actions"]) == {
        "analysis.strategy-validation",
    }
    assert set(pages["instock-event-flow"]["manifest"]["actions"]) == {
        "analysis.event-flow",
    }
    assert set(pages["instock-research-book"]["manifest"]["actions"]) == {
        "analysis.research-book",
    }
    assert set(pages["instock-market-workbench"]["manifest"]["actions"]) == {
        "analysis.market-workbench",
    }
    assert set(pages["instock-market-map"]["manifest"]["actions"]) == {
        "analysis.market-map",
    }
    assert set(pages["instock-technical-signals"]["manifest"]["actions"]) == {
        "analysis.technical-signals",
    }
    for page in suite["pages"]:
        for action_id, action in page["manifest"]["actions"].items():
            if action_id == "analysis.industry-chain":
                assert action["inputSchema"]["properties"]["schema_version"]["const"] == "2.0"
                assert action["inputSchema"]["properties"]["chain"]["properties"]["nodes"]["maxItems"] == 60
            elif action_id not in {"analysis.stock-candidates", "analysis.strategy-validation", "analysis.event-flow", "analysis.research-book", "analysis.market-workbench", "analysis.market-map", "analysis.technical-signals"}:
                assert action["inputSchema"]["properties"]["asOf"]["format"] == "date"
    assert pages["instock-czsc"]["manifest"]["events"]["accepts"] == ["security.selected"]
    assert pages["instock-rotation"]["manifest"]["events"]["emits"] == ["security.selected"]
    assert pages["instock-stock-candidates"]["manifest"]["events"]["emits"] == ["security.selected"]
    assert pages["instock-stock-research"]["manifest"]["events"] == {
        "emits": ["security.selected"], "accepts": ["security.selected"],
    }
    assert pages["instock-strategy-validation"]["manifest"]["events"] == {
        "emits": [], "accepts": [],
    }
    assert pages["instock-event-flow"]["manifest"]["events"] == {
        "emits": ["security.selected"], "accepts": ["security.selected"],
    }
    assert pages["instock-research-book"]["manifest"]["events"] == {
        "emits": ["security.selected"], "accepts": ["security.selected"],
    }
    assert pages["instock-market-workbench"]["manifest"]["events"] == {
        "emits": ["security.selected"], "accepts": [],
    }
    assert pages["instock-market-map"]["manifest"]["events"] == {
        "emits": ["security.selected"], "accepts": [],
    }
    assert pages["instock-technical-signals"]["manifest"]["events"] == {
        "emits": ["security.selected"], "accepts": ["security.selected"],
    }


def test_project_delivery_is_newma_attached_runtime_without_docker_assets():
    assert not (ROOT / "docker").exists()
    assert not (ROOT / ".github" / "workflows" / "docker-image.yml").exists()
    assert not (ROOT / ".github" / "workflows" / "azure-container-webapp.yml").exists()

    readme = (ROOT / "README.md").read_text("utf-8")
    integration_readme = (NEWMA_ROOT / "README.md").read_text("utf-8")
    evolution = (ROOT / "docs" / "newma-desk-evolution.md").read_text("utf-8")

    assert "Newma-Desk 附属模组" in readme
    assert "npm run dev:stack" in readme
    assert "Desk 托管运行时" in integration_readme
    assert "不提供 Dockerfile、Compose、容器镜像" in evolution


def test_attached_dependency_contract_excludes_upstream_runtime_stacks():
    attached = (ROOT / "requirements-attached.txt").read_text("utf-8").lower()
    constraints = (ROOT / "requirements-attached.constraints.txt").read_text("utf-8").lower()
    development = (ROOT / "requirements-dev.txt").read_text("utf-8").lower()

    assert "czsc==0.10.12" in attached
    assert "rs-czsc==0.1.26.post260402" in attached
    assert "czsc==0.10.12" in constraints
    assert "ta-lib==0.6.8" in constraints
    assert "rs-czsc==0.1.26.post260402" in constraints
    for dependency in (
        "pymysql", "sqlalchemy", "easytrader", "bokeh", "py_mini_racer",
    ):
        assert dependency not in attached
    assert "-r requirements-attached.txt" in development
    assert "-r requirements.txt" not in development


def test_data_service_contract_uses_versioned_endpoints_and_inline_schemas():
    descriptor = json.loads((NEWMA_ROOT / "data-service.json").read_text("utf-8"))
    compatibility_descriptor = json.loads(
        (INTEGRATION_ROOT / "data-service.json").read_text("utf-8")
    )

    assert descriptor["id"] == "instock-analysis"
    assert descriptor["priority"] == 30
    assert descriptor["baseUrl"].endswith("/api/v1")
    assert descriptor["healthPath"] == "/health"
    assert set(descriptor["capabilities"]) == {
        "analysis.czsc", "analysis.czsc.scan", "analysis.rotation",
        "analysis.rotation.experiment", "analysis.industry-chain",
        "analysis.rotation.supply-chain", "analysis.stock-candidates",
        "analysis.stock-research",
        "analysis.strategy-validation",
        "analysis.event-flow",
        "analysis.research-book",
        "analysis.market-workbench",
        "analysis.market-map",
        "analysis.technical-signals",
    }
    assert descriptor["timeoutSeconds"] == 120
    assert descriptor["capabilities"]["analysis.czsc.scan"]["method"] == "POST"
    rotation_schema = descriptor["capabilities"]["analysis.rotation"]["outputSchema"]
    assert "market_breadth" in rotation_schema["properties"]["data"]["required"]
    breadth_schema = rotation_schema["properties"]["data"]["properties"]["market_breadth"]
    assert set(breadth_schema["required"]) >= {"state", "breadth", "up", "down", "up_ratio"}
    assert descriptor["capabilities"]["analysis.czsc.scan"]["path"] == "/czsc/scans"
    for action_id, capability in descriptor["capabilities"].items():
        assert capability["method"] == (
            "POST" if action_id in {
                "analysis.czsc.scan", "analysis.industry-chain",
                "analysis.rotation.supply-chain", "analysis.strategy-validation", "analysis.event-flow", "analysis.research-book",
            } else "GET"
        )
        assert capability["permission"] == "analysis.read"
        assert capability["inputSchema"]["$schema"].endswith("2020-12/schema")
        assert "$ref" not in capability["inputSchema"]
        assert capability["outputSchema"]["$schema"].endswith("2020-12/schema")
        assert "meta" in capability["outputSchema"]["required"]
        if action_id == "analysis.industry-chain":
            assert capability["inputSchema"]["properties"]["schema_version"]["const"] == "2.0"
            assert capability["inputSchema"]["properties"]["chain"]["properties"]["links"]["maxItems"] == 120
        elif action_id not in {"analysis.stock-candidates", "analysis.strategy-validation", "analysis.event-flow", "analysis.research-book", "analysis.market-workbench", "analysis.market-map", "analysis.technical-signals"}:
            date_field = "as_of" if action_id == "analysis.rotation.supply-chain" else "asOf"
            assert capability["inputSchema"]["properties"][date_field]["format"] == "date"
        if action_id == "analysis.czsc.scan":
            assert capability["inputSchema"]["properties"]["symbols"]["maxItems"] == 20
            assert "scan_id" in capability["outputSchema"]["properties"]["data"]["required"]
        else:
            assert "snapshot" in capability["outputSchema"]["properties"]["data"]["required"]
    experiment = descriptor["capabilities"]["analysis.rotation.experiment"]
    assert experiment["path"] == "/rotations/experiments"
    assert experiment["inputSchema"]["properties"]["rebalanceDays"]["enum"] == [5, 10, 20]
    assert experiment["inputSchema"]["properties"]["costBps"]["enum"] == [10, 25, 50]
    industry_chain = descriptor["capabilities"]["analysis.industry-chain"]
    assert industry_chain["path"] == "/industry-chain/research"
    assert "chain" in industry_chain["outputSchema"]["properties"]["data"]["required"]
    legacy = descriptor["capabilities"]["analysis.rotation.supply-chain"]
    assert legacy["path"] == "/rotations/supply-chain-research"
    candidates = descriptor["capabilities"]["analysis.stock-candidates"]
    assert candidates["path"] == "/stock-candidates/snapshots"
    assert candidates["inputSchema"]["properties"]["market"]["enum"] == ["CN", "HK", "CN_HK"]
    assert candidates["inputSchema"]["properties"]["universeMode"]["enum"] == ["broad", "quick"]
    assert candidates["inputSchema"]["properties"]["universeSize"]["enum"] == [30, 50, 100, 200]
    assert candidates["inputSchema"]["properties"]["profile"]["enum"] == ["balanced", "trend", "value", "defensive"]
    assert candidates["inputSchema"]["properties"]["industries"]["type"] == "string"
    assert candidates["inputSchema"]["properties"]["eventFlowSnapshotId"]["type"] == "string"
    assert "screening_model" in candidates["outputSchema"]["properties"]["data"]["required"]
    assert "factor_model" in candidates["outputSchema"]["properties"]["data"]["required"]
    assert "evidence_quality" in candidates["outputSchema"]["properties"]["data"]["required"]
    assert "candidate_lifecycle" in candidates["outputSchema"]["properties"]["data"]["required"]
    compatibility_candidates = compatibility_descriptor["capabilities"]["analysis.stock-candidates"]
    assert "evidence_quality" in compatibility_candidates["outputSchema"]["properties"]["data"]["required"]
    assert "candidate_lifecycle" in compatibility_candidates["outputSchema"]["properties"]["data"]["required"]
    stock_research = descriptor["capabilities"]["analysis.stock-research"]
    assert stock_research["path"] == "/stock-research/dossiers"
    assert stock_research["inputSchema"]["properties"]["bars"]["enum"] == [120, 240, 480, 800]
    assert stock_research["inputSchema"]["properties"]["eventFlowSnapshotId"]["type"] == "string"
    assert "event_flow" in stock_research["outputSchema"]["properties"]["data"]["required"]
    assert "fundamentals" in stock_research["outputSchema"]["properties"]["data"]["required"]
    validation = descriptor["capabilities"]["analysis.strategy-validation"]
    assert validation["path"] == "/strategy-validations"
    assert validation["inputSchema"]["properties"]["strategy"]["properties"]["source_module"]["enum"] == ["stock-candidates", "czsc", "rotation"]
    assert "out_of_sample" in validation["outputSchema"]["properties"]["data"]["required"]
    event_flow = descriptor["capabilities"]["analysis.event-flow"]
    assert event_flow["path"] == "/event-flows"
    symbol_mode, packet_mode = event_flow["inputSchema"]["oneOf"]
    assert symbol_mode["required"] == ["symbol"]
    assert symbol_mode["properties"]["symbol"]["pattern"].startswith("^[0-9]{6}")
    assert packet_mode["properties"]["events"]["maxItems"] == 500
    assert "margin" in packet_mode["properties"]["events"]["items"]["properties"]["type"]["enum"]
    assert "coverage" in event_flow["outputSchema"]["properties"]["data"]["required"]
    assert "alerts" in event_flow["outputSchema"]["properties"]["data"]["required"]
    research_book = descriptor["capabilities"]["analysis.research-book"]
    assert research_book["path"] == "/research-books"
    assert research_book["inputSchema"]["properties"]["items"]["maxItems"] == 100
    assert "exposures" in research_book["outputSchema"]["properties"]["data"]["required"]
    market_workbench = descriptor["capabilities"]["analysis.market-workbench"]
    assert market_workbench["path"] == "/market-workbench/snapshots"
    assert market_workbench["inputSchema"]["properties"]["scanLimit"]["enum"] == [50, 100, 200]
    assert "leaderboards" in market_workbench["outputSchema"]["properties"]["data"]["required"]
    assert "market_emotion" in market_workbench["outputSchema"]["properties"]["data"]["required"]
    compatibility_market = compatibility_descriptor["capabilities"]["analysis.market-workbench"]
    assert "market_emotion" in compatibility_market["outputSchema"]["properties"]["data"]["required"]
    assert "market_map" not in market_workbench["outputSchema"]["properties"]["data"]["required"]
    market_map = descriptor["capabilities"]["analysis.market-map"]
    assert market_map["path"] == "/market-maps/snapshots"
    assert market_map["inputSchema"]["properties"]["capacity"]["enum"] == [100, 500]
    assert "groups" in market_map["outputSchema"]["properties"]["data"]["required"]
    technical_signals = descriptor["capabilities"]["analysis.technical-signals"]
    assert technical_signals["path"] == "/technical-signals/snapshots"
    assert technical_signals["inputSchema"]["properties"]["bars"]["enum"] == [120, 260]
    assert {"minROE", "minRevenueGrowth", "minNetProfitGrowth"} <= set(
        technical_signals["inputSchema"]["properties"]
    )
    assert "catalog" in technical_signals["outputSchema"]["properties"]["data"]["required"]
    for action_id in (
        "analysis.czsc", "analysis.market-workbench", "analysis.market-map", "analysis.stock-candidates",
        "analysis.stock-research", "analysis.technical-signals",
    ):
        assert descriptor["capabilities"][action_id]["inputSchema"]["properties"]["refresh"]["enum"] == ["0", "1"]


def test_bridge_uses_exact_origin_handshake_and_context_protocol():
    bridge = (ROOT / "instock" / "web" / "static" / "js" / "vibedesk-bridge.js").read_text("utf-8")

    assert "event.source !== window.parent" in bridge
    assert "event.origin !== parentOrigin" in bridge
    assert "vibedesk:hello" in bridge
    assert "vibedesk:init" in bridge
    assert "vibedesk:ack" in bridge
    assert "vibedesk:context-request" in bridge
    assert "vibedesk:context" in bridge
    assert "vibedesk:action-request" in bridge
    assert "vibedesk:action-result" in bridge
    assert "postMessage(message, parentOrigin)" in bridge
    assert "postMessage(message, '*')" not in bridge
    assert "applyTheme(environment.theme, 'vibedesk:init', compatibleAppearance)" in bridge
    assert "applyAppearance(appearance)" in bridge
    assert "appearance.cssVars" in bridge
    assert "root.dataset.vibedeskTheme = theme" in bridge
    assert "root.dataset.theme = theme" in bridge
    assert "root.dataset.bsTheme = theme" in bridge
    assert "instock:themechange" in bridge
    assert "newma:themechange" in bridge
    assert "window.InStockNewmaDesk = bridge" in bridge
    assert "window.InStockVibeDesk = bridge" in bridge
    assert "canInvokeAction" in bridge
    assert "invokeAction" in bridge
    assert "emit: emitEvent" in bridge
    assert "subscribe: subscribeEvent" in bridge
    assert "vibe-visualization-events" in bridge
    assert "validModEvent" in bridge
    assert "vibedesk-theme-pending" in bridge
    assert "standalone-fallback" in bridge


def test_embed_pages_use_versioned_api_and_publish_semantic_context():
    czsc = (ROOT / "instock" / "web" / "templates" / "czsc_chart.html").read_text("utf-8")
    rotation = (ROOT / "instock" / "web" / "templates" / "rotation.html").read_text("utf-8")
    industry_chain = (ROOT / "instock" / "web" / "templates" / "industry_chain.html").read_text("utf-8")
    stock_candidates = (ROOT / "instock" / "web" / "templates" / "stock_candidates.html").read_text("utf-8")
    stock_research = (ROOT / "instock" / "web" / "templates" / "stock_research.html").read_text("utf-8")
    market_map = (ROOT / "instock" / "web" / "templates" / "market_map.html").read_text("utf-8")

    assert "/api/v1/czsc/analyses" in czsc
    assert "setContextProvider(buildContext)" in czsc
    assert "invokeAction(analysisActionId, input)" in czsc
    assert "invokeAction(scanActionId, input)" in czsc
    assert "/api/v1/czsc/scans" in czsc
    assert "requestScanCancellation" in czsc
    assert "batchScan" in czsc
    assert "officialSignals" in czsc
    assert "官方信号适配降级" in czsc
    assert "snapshot" in czsc
    context_builder = czsc.split("function buildContext()", 1)[1].split("function publishContext()", 1)[0]
    context_data_fields = context_builder.split("data: {", 1)[1].split("summary: {", 1)[0]
    assert "snapshot," not in context_data_fields
    assert "snapshotId: snapshot ? snapshot.snapshot_id : null" in context_builder
    assert "asOf" in czsc
    assert "handleSecuritySelected" in czsc
    assert "structureStability" in czsc
    assert "provenance.upstream_source" in czsc
    assert "provenance.upstream_as_of" in czsc
    assert "实际上游" in czsc
    assert "前复权" in czsc
    assert "/api/v1/rotations/snapshots" in rotation
    assert "/api/v1/rotations/experiments" in rotation
    assert "setContextProvider(buildContext)" in rotation
    assert "invokeAction(analysisActionId, input)" in rotation
    assert "invokeAction(experimentActionId, input)" in rotation
    assert "analysis.rotation.supply-chain" not in rotation
    assert "window.InStockSupplyChainResearch" not in rotation
    assert 'href="/mods/industry-chain"' in rotation
    assert "analysis.industry-chain" in industry_chain
    assert "/api/v1/industry-chain/research" in industry_chain
    assert "window.InStockIndustryChainResearch" in industry_chain
    assert "instock:industry-chain-result" in industry_chain
    assert "normalizeAgentPacket" in industry_chain
    assert "所有 evidence_ids 必须至少包含 1 个" in industry_chain
    assert "invalidation 必须是 1 至 8 条字符串数组" in industry_chain
    assert "robustnessExperiment" in rotation
    assert "leadingIndustry" in rotation
    assert "snapshot" in rotation
    assert "asOf" in rotation
    assert "deskBridge.emit('security.selected'" in rotation
    assert "provenance.upstream_source" in rotation
    assert "provenance.upstream_as_of" in rotation
    assert "实际上游" in rotation
    assert "前复权" in rotation
    assert "marketBreadth" in rotation
    assert "市场宽度" in rotation
    assert "const insight = row.insight" in rotation
    assert "setText('rotation-headline', insight.headline)" in rotation
    assert "selectedRotation" in rotation
    assert "rotationEnvironment" in rotation
    assert "row.rotation_signal || row.regime" in rotation
    assert "data-sort=\"persistence_score\"" in rotation
    assert "analysis.stock-candidates" in stock_candidates
    assert "/api/v1/stock-candidates/snapshots" in stock_candidates
    assert "setContextProvider(buildContext)" in stock_candidates
    assert "deskBridge.emit('security.selected'" in stock_candidates
    assert "factorContributions" in stock_candidates
    assert "historyExclusions" in stock_candidates
    assert "candidateLifecycle" in stock_candidates
    assert "candidate-lifecycle-filters" in stock_candidates
    assert "lifecycleEvidence" in stock_candidates
    assert "hasComparableLifecycle" in stock_candidates
    assert "同一筛选口径" in stock_candidates
    assert "不是买卖信号" in stock_candidates
    assert "analysis.stock-research" in stock_research
    assert "/api/v1/stock-research/dossiers" in stock_research
    assert "setContextProvider(buildContext)" in stock_research
    assert "handleSecuritySelected" in stock_research
    assert "不是评级或买卖建议" in stock_research
    assert "analysis.market-map" in market_map
    assert "/api/v1/market-maps/snapshots" in market_map
    assert "setContextProvider(buildContext)" in market_map
    assert "multi_rank_union" in market_map
    assert "window.location.assign(researchUrl(row))" in market_map


def test_research_handoff_links_keep_source_and_evidence_snapshots_distinct():
    pages = {
        name: (ROOT / "instock" / "web" / "templates" / f"{name}.html").read_text("utf-8")
        for name in (
            "market_workbench", "market_map", "stock_candidates", "technical_signals",
            "czsc_chart", "event_flow", "industry_chain", "rotation",
            "stock_research",
        )
    }

    for name in ("market_workbench", "market_map", "stock_candidates", "technical_signals", "czsc_chart"):
        assert "/mods/stock-research" in pages[name]
        assert "sourceModule" in pages[name]
        assert "sourceSnapshotId" in pages[name]

    assert "eventFlowSnapshotId" in pages["event_flow"]
    assert "带事件证据进入公司档案" in pages["event_flow"]
    assert "industryChainSnapshotId" in pages["industry_chain"]
    assert "带产业链证据进入股票研究" in pages["industry_chain"]
    assert "/mods/stock-candidates" in pages["rotation"]
    assert "industries: row.industry" in pages["rotation"]

    stock_research = pages["stock_research"]
    assert "deskBridge.subscribe(handleSecuritySelected)" in stock_research
    assert "deskBridge.subscribe('security.selected'" not in stock_research
    assert "query.get('sourceModule')" in stock_research
    assert "query.get('sourceSnapshotId')" in stock_research
    assert "value = cleanParam(payload.eventFlowSnapshotId, 160)" in stock_research
    assert "value = cleanParam(payload.industryChainSnapshotId, 160)" in stock_research
    assert "仅用于追溯，不进入本次计算" in stock_research
    assert "将参与档案计算" in stock_research
    assert "已进入本次计算" in stock_research
    assert "未解析，未进入本次计算" in stock_research
    assert "加入研究组合" in stock_research
    assert "researchBookUrl" in stock_research
    assert "snapshotIds" in stock_research
    research_book = (ROOT / "instock" / "web" / "templates" / "research_book.html").read_text("utf-8")
    assert "applyUrlPrefill" in research_book
    assert "query.get('thesis')" in research_book
    assert "query.get('snapshotIds')" in research_book
    assert "instock.research-book.draft.v1" in research_book
    assert "restoreDraft()" in research_book
    assert "saveDraft()" in research_book
    for name in ("market_workbench", "market_map", "stock_candidates", "technical_signals", "industry_chain"):
        assert "industry" in pages[name]
    assert "['etf', 'index', 'fund'].includes" in stock_research
    assert "assetType: 'etf'" in pages["rotation"]
    for name in ("czsc_chart", "event_flow", "rotation"):
        assert 'target="_blank"' in pages[name]
    for name in ("market_workbench", "stock_candidates", "technical_signals", "industry_chain"):
        assert "target = '_blank'" in pages[name]


def test_embed_pages_share_verdigris_theme_and_repaint_echarts():
    css = (ROOT / "instock" / "web" / "static" / "css" / "vibedesk-theme.css").read_text("utf-8")
    czsc = (ROOT / "instock" / "web" / "templates" / "czsc_chart.html").read_text("utf-8")
    rotation = (ROOT / "instock" / "web" / "templates" / "rotation.html").read_text("utf-8")
    industry_chain = (ROOT / "instock" / "web" / "templates" / "industry_chain.html").read_text("utf-8")

    for declaration in (
        "--instock-bg: #f4efe3",
        "--instock-surface: #fbf7ef",
        "--instock-text: #173128",
        "--instock-accent: #a87432",
        "--instock-bg: #0f1714",
        "--instock-surface: #16211c",
        "--instock-text: #f3ecdd",
        "--instock-accent: #c89a5a",
    ):
        assert declaration in css
    assert ':root[data-vibedesk-theme="dark"]' in css
    assert "prefers-color-scheme: dark" in css

    for page in (czsc, rotation):
        assert page.count("vibedesk-theme.css") == 1
        assert page.count("vibedesk-bridge.js") == 1
        assert "cssToken('--instock-text')" in page
        assert "cssToken('--instock-accent')" in page
        assert "instock:themechange" in page

    assert industry_chain.count("vibedesk-theme.css") == 1
    assert industry_chain.count("vibedesk-bridge.js") == 1

    assert "chart.setOption(chartOptionForViewport(currentPayload.chart), true)" in czsc
    assert "renderChart(state.data.industry_rankings || [])" in rotation
    assert "renderHistory(state.data)" in rotation
    assert "rotation-row-select" in rotation
    assert "当前筛选条件下暂无可用候选" in rotation


def test_rotation_template_redirects_direct_file_open_to_running_service():
    rotation = (ROOT / "instock" / "web" / "templates" / "rotation.html").read_text("utf-8")

    assert "window.location.protocol === 'file:'" in rotation
    assert "http://127.0.0.1:9988/mods/rotation/" in rotation
