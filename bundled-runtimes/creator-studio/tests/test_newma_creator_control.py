import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import newma_creator_control as control  # noqa: E402
from newma_creator_control import (  # noqa: E402
    build_handoff,
    build_snapshot,
    init_node_project,
    load_registry,
    run_registered_node,
    validate_node_materials,
)


def test_registry_exposes_six_vertical_stages_with_horizontal_nodes():
    registry = load_registry()

    assert registry["navigation"]["default_view"] == "dashboard"
    assert registry["navigation"]["stage_axis"] == "vertical"
    assert registry["navigation"]["node_axis"] == "horizontal"
    assert [stage["id"] for stage in registry["stages"]] == [
        "intake",
        "brief",
        "draft",
        "transwrite",
        "publish",
        "postmortem",
    ]
    assert all(stage["nodes"] for stage in registry["stages"])
    adapter_ids = {item["id"] for item in registry["execution_adapters"]}
    assert all(node["executor"] in adapter_ids for stage in registry["stages"] for node in stage["nodes"])
    assert "dasheng" not in json.dumps(registry, ensure_ascii=False).lower()


def test_node_material_validation_accepts_manual_and_upstream_inputs():
    registry = load_registry()
    report = validate_node_materials(
        registry,
        "draft",
        "article_draft",
        [
            {"type": "article_outline", "path": "/tmp/outline.md", "source": "manual"},
            {"type": "evidence_ledger", "path": "/tmp/evidence.json", "source": "upstream"},
        ],
        allow_manual_bootstrap=True,
    )

    assert report["status"] == "ready"
    assert not report["missing"]


def test_snapshot_builds_review_and_artifact_notifications():
    registry = load_registry()
    manifest = {
        "run_id": "run_156",
        "title": "DeepSeek 涨价",
        "pipeline_id": "mainline",
        "lane": "article",
        "updated_at": "2026-08-14T20:00:00+08:00",
        "stages": [
            {"name": "intake", "status": "complete"},
            {"name": "brief", "status": "pending_review"},
            {"name": "draft", "status": "pending"},
            {"name": "transwrite", "status": "pending"},
            {"name": "publish", "status": "pending"},
            {"name": "postmortem", "status": "pending"},
        ],
        "artifacts": [
            {
                "id": "selected_topics_001",
                "stage": "brief",
                "type": "selected_topics",
                "path": "/tmp/selected_topics.json",
                "status": "created",
            }
        ],
    }

    snapshot = build_snapshot(manifest, registry)

    assert snapshot["run"]["active_stage_id"] == "brief"
    assert snapshot["counters"]["waiting_review"] == 1
    assert snapshot["counters"]["new_artifacts"] == 1


def test_handoff_and_create_project_at_any_node(tmp_path):
    registry = load_registry()
    source_manifest = {
        "run_id": "source_run",
        "artifacts": [
            {
                "id": "handoff_001",
                "stage": "draft",
                "type": "transwrite_handoff",
                "path": "/tmp/transwrite_handoff.json",
                "status": "approved",
            },
            {
                "id": "dna_001",
                "stage": "transwrite",
                "type": "dna_selection",
                "path": "/tmp/dna_selection.json",
                "status": "approved",
            }
        ],
    }
    handoff = build_handoff(source_manifest, registry, "transwrite", "route_select", [])
    assert handoff["status"] == "ready"

    output_root = tmp_path / "自媒体创作" / "node_project"
    manifest, manifest_path = init_node_project(
        "从初稿节点开始",
        "draft",
        "article_draft",
        [
            {"type": "article_outline", "path": "/tmp/outline.md", "source": "manual"},
            {"type": "evidence_ledger", "path": "/tmp/evidence.json", "source": "manual"},
        ],
        str(output_root),
        "node_project",
    )

    assert manifest_path.exists()
    assert next(row for row in manifest["stages"] if row["name"] == "intake")["status"] == "skipped"
    assert next(row for row in manifest["stages"] if row["name"] == "draft")["current_node"] == "article_draft"


def test_registered_node_executor_writes_real_artifacts_and_review_state(tmp_path, monkeypatch):
    monkeypatch.setattr(control, "get_desktop_root", lambda: tmp_path)

    packaged = run_registered_node(
        {
            "run_id": "creator-test-package",
            "title": "节点执行测试",
            "stage_id": "postmortem",
            "node_id": "next_cycle",
            "materials": [],
            "parameters": {},
        }
    )
    review = run_registered_node(
        {
            "run_id": "creator-test-review",
            "title": "审核执行测试",
            "stage_id": "intake",
            "node_id": "intake_review",
            "materials": [{"type": "intake_manifest", "path": "/tmp/intake_manifest.json", "source": "upstream"}],
            "parameters": {},
        }
    )

    assert packaged["status"] == "succeeded"
    assert {item["type"] for item in packaged["artifacts"]} == {"next_cycle_plan", "postmortem_manifest"}
    assert all(item["origin"] == "system" for item in packaged["artifacts"])
    assert all(Path(item["path"]).exists() for item in packaged["artifacts"])
    assert review["status"] == "waiting_user"
    assert {item["type"] for item in review["artifacts"]} == {"recommended_topics", "intake_review", "brief_handoff"}


def test_marketplace_compiles_projects_skills_pipelines_and_visual_templates():
    catalog = control.compile_marketplace(load_registry())

    assert catalog["schema_version"] == "newma.creator_marketplace.v2"
    assert len([item for item in catalog["pipelines"] if item["category"] == "production"]) == 6

    shotcraft = next(item for item in catalog["projects"] if item["id"] == "video-shotcraft")
    openchatcut = next(item for item in catalog["projects"] if item["id"] == "openchatcut")
    vox_skill = next(item for item in catalog["skills"] if item["id"] == "newma-vox-skills")
    poster = next(item for item in catalog["templates"] if item["id"] == "frame-bold-poster")

    assert "镜头配方库" in shotcraft["summary"]
    assert shotcraft["preview"]["url"].startswith("/api/creator-studio/marketplace/assets/")
    assert shotcraft["stageIds"]
    assert "agent_mcp_editing" in openchatcut["capabilities"]
    assert openchatcut["stageIds"] == ["transwrite"]
    assert vox_skill["status"]["registration"] == "workflow_registered"
    assert "VOX" in vox_skill["summary"]
    assert vox_skill["stageIds"]
    assert poster["categoryLabel"] == "标题与观点呈现"
    assert poster["stageIds"] == ["transwrite"]
    assert poster["preview"]["assetPath"].endswith("preview.png")
    assert all(item["stageIds"] == ["transwrite"] for item in catalog["pipelines"])


def test_openchatcut_editor_adapter_exposes_agent_bridge_and_template_catalog(tmp_path, monkeypatch):
    project = tmp_path / "openchatcut"
    (project / "node_modules").mkdir(parents=True)
    catalog_dir = project / "assets" / "templates"
    thumb_dir = project / "assets" / "thumbnails"
    catalog_dir.mkdir(parents=True)
    thumb_dir.mkdir(parents=True)
    (thumb_dir / "demo.jpg").write_bytes(b"preview")
    (catalog_dir / "openchatcut-templates.json").write_text(
        json.dumps([
            {
                "id": "demo-template",
                "name": "重点词弹出",
                "category": "social-shorts",
                "description": "用于口播重点花字。",
                "width": 1080,
                "height": 1920,
                "thumb": "/thumbnails/demo.jpg",
                "propSchema": [{"key": "keyword"}],
            }
        ], ensure_ascii=False),
        encoding="utf-8",
    )
    (catalog_dir / "koubo-scenes-templates.json").write_text("[]", encoding="utf-8")
    (catalog_dir / "social-shorts-templates.json").write_text("[]", encoding="utf-8")
    monkeypatch.setenv("NEWMA_DESK_OPENCHATCUT_WORKSPACE", str(project))

    registry = load_registry()
    editor = control.describe_editor(registry, "openchatcut", [])
    templates = control.compile_marketplace_templates(registry)
    template = next(item for item in templates if item["id"] == "openchatcut-demo-template")

    assert editor["status"] == "available"
    assert editor["agent_bridge"]["protocol"] == "openchatcut.edit-session.v1"
    assert editor["agent_bridge"]["endpoint"].endswith("/api/external-mcp/mcp")
    assert template["sourceTemplateId"] == "demo-template"
    assert template["aspectRatios"] == ["9:16"]


def test_materialize_openchatcut_export_writes_versionable_artifacts(tmp_path, monkeypatch):
    project = tmp_path / "openchatcut"
    upload_dir = project / "public" / "media" / "uploads"
    upload_dir.mkdir(parents=True)
    source = upload_dir / "openchatcut-export.mp4"
    source.write_bytes(b"export-video")
    monkeypatch.setenv("NEWMA_DESK_OPENCHATCUT_WORKSPACE", str(project))
    monkeypatch.setattr(control, "get_desktop_root", lambda: tmp_path / "outputs")

    payload = control.materialize_editor_export(
        {
            "session_id": "editor-1",
            "run_id": "creator-export-test",
            "stage_id": "transwrite",
            "node_id": "manual_edit",
            "editor_id": "openchatcut",
            "external_project_id": "occ-project-1",
            "external_edit_session_id": "occ-edit-1",
            "proposal": {"status": "applied", "summary": "粗剪完成"},
            "download_url": "/media/uploads/openchatcut-export.mp4",
            "render_id": "render-1",
            "name": "final.mp4",
        },
        load_registry(),
    )

    outputs = {item["type"]: Path(item["path"]) for item in payload["outputs"]}
    assert payload["status"] == "succeeded"
    assert outputs["edited_master"].read_bytes() == b"export-video"
    decisions = json.loads(outputs["edit_decisions"].read_text(encoding="utf-8"))
    timeline = json.loads(outputs["timeline_exchange"].read_text(encoding="utf-8"))
    assert decisions["external_project_id"] == "occ-project-1"
    assert decisions["proposal"]["status"] == "applied"
    assert timeline["format"] == "openchatcut-project-ref"
    assert timeline["project_id"] == "occ-project-1"


def test_publish_adapters_preflight_confirm_execute_and_verify(tmp_path, monkeypatch):
    monkeypatch.setattr(control, "get_desktop_root", lambda: tmp_path / "outputs")
    request_path = tmp_path / "publish" / "execution_request.json"
    request_path.parent.mkdir(parents=True)
    request_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        control,
        "build_publish_execution_plan",
        lambda path: {
            "task_id": "task-1",
            "channel": "wechat",
            "account_slot": "default",
            "status": "ready_for_user_confirmation",
        },
    )
    monkeypatch.setattr(
        control,
        "build_publish_account_report",
        lambda *_args, **_kwargs: {
            "accounts": [
                {
                    "channel": "wechat",
                    "slot": "default",
                    "label": "公众号",
                    "status": "available",
                }
            ],
            "summary": {"available_count": 1},
        },
    )
    request = {
        "job_id": "job-publish-1",
        "run_id": "publish-test",
        "stage_id": "publish",
        "node_id": "publish_preflight",
        "materials": [
            {"type": "account_routes", "path": str(request_path.parent), "source": "upstream"}
        ],
        "parameters": {},
    }
    status, _, artifacts, _, payload = control.execute_publish_preflight({}, request)

    assert status == "succeeded"
    assert payload["accountHealth"]["accounts"][0]["status"] == "available"
    preflight_path = Path(artifacts[0]["path"])
    assert json.loads(preflight_path.read_text(encoding="utf-8"))["will_not_publish"] is True

    monkeypatch.setattr(
        control,
        "execute_publish_request",
        lambda path, confirm_execute: {
            "status": "executed_and_recorded",
            "selected_route": "wechat-api",
            "record": {},
            "will_not_publish": False,
        },
    )
    execute_request = {
        **request,
        "node_id": "publish_execute",
        "materials": [
            {"type": "publish_preflight_report", "path": str(preflight_path), "source": "upstream"}
        ],
        "parameters": {
            "publishConfirmation": {
                "confirmed": True,
                "confirmationText": "确认发布",
                "consumedByJobId": "job-publish-1",
            }
        },
    }
    execute_status, _, execute_artifacts, _, execute_payload = control.execute_confirmed_publish({}, execute_request)

    assert execute_status == "succeeded"
    assert execute_payload["succeeded"] == 1
    receipt_path = next(Path(item["path"]) for item in execute_artifacts if item["type"] == "platform_receipts")

    with pytest.raises(ValueError):
        control.execute_confirmed_publish(
            {},
            {
                **execute_request,
                "job_id": "job-publish-2",
            },
        )

    publish_root = tmp_path / "delivery"
    channel_pack = publish_root / "channel_packs" / "wechat" / "pack.json"
    channel_pack.parent.mkdir(parents=True)
    channel_pack.write_text("{}", encoding="utf-8")
    (publish_root / "publish_manifest.json").write_text(
        json.dumps({"publish_guard": {"passed": True, "status": "passed"}}),
        encoding="utf-8",
    )
    (publish_root / "publish_verification_report.json").write_text(
        json.dumps({"status": "verified"}),
        encoding="utf-8",
    )
    receipts = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipts["receipts"][0]["result"]["record"] = {"channel_pack": str(channel_pack)}
    receipt_path.write_text(json.dumps(receipts), encoding="utf-8")
    verify_status, _, verify_artifacts, _, verify_payload = control.execute_publish_verify(
        {},
        {
            **request,
            "node_id": "receipt_verify",
            "materials": [
                {"type": "platform_receipts", "path": str(receipt_path), "source": "upstream"}
            ],
        },
    )

    assert verify_status == "succeeded"
    assert verify_payload["verificationCount"] == 1
    assert {item["type"] for item in verify_artifacts} == {
        "publish_manifest",
        "publish_verification_report",
        "postmortem_handoff",
    }


def test_write_node_packets_marks_origin_and_discovery_skips_packets(tmp_path, monkeypatch):
    monkeypatch.setattr(
        control,
        "node_execution_dir",
        lambda run_id, stage_id, node_id: tmp_path / "nodes" / stage_id / node_id,
    )
    request = {
        "run_id": "creator-t123",
        "title": "T",
        "stage_id": "postmortem",
        "node_id": "knowledge_writeback",
        "materials": [],
        "parameters": {},
    }
    node = {"outputs": ["dna_updates"], "gate": {"required": True}, "editors": []}
    adapter = {"id": "newma.control.review-gate", "kind": "review_gate"}

    artifacts = control.write_node_packets(request, node, adapter, ["dna_updates"])

    # artifact 带 origin=packet 标记（desk 登记 origin 用）
    assert artifacts[0]["origin"] == "packet"
    assert artifacts[0]["type"] == "dna_updates"

    # Handoff 只负责流转；配置包和执行请求属于后台文件，不进入用户产品层
    assert control.packet_origin_for("review_gate", "brief_handoff") == "handoff"
    assert control.packet_origin_for("package", "source_plan") == "system"
    assert control.packet_origin_for("capability_session", "execution_request") == "system"
    assert control.packet_origin_for("review_gate", "dna_updates") == "packet"
    # packet 文件内容自识别（磁盘可辨识 + discover 防御依据）
    packet_path = Path(artifacts[0]["path"])
    payload = json.loads(packet_path.read_text(encoding="utf-8"))
    assert payload["packet"] is True
    assert control.is_packet_document(payload) is True
    assert not control.is_packet_document({"schema_version": "newma.publish_jobs.v1"})

    # 真实交付物（非 packet schema）不受影响
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    real = real_dir / "dna_updates.json"
    real.write_text(json.dumps({"schema_version": "newma.dna_updates.v1", "items": []}), encoding="utf-8")

    # discover 按名查找：packet 与真实交付物同名时只命中真实交付物
    found = control.discover_named_material_files(
        {
            "materials": [
                {"path": str(packet_path)},
                {"path": str(real_dir)},
            ]
        },
        {"dna_updates.json"},
    )
    assert found == [real]


def test_approve_stage_gate_creates_missing_brief_gate_with_selection(tmp_path, monkeypatch):
    """UI 直批路径：gate 文件缺失 + 带选题选择 → 直接创建 approved gate 文件。"""
    run_id = "creator-test000001"
    brief_dir = tmp_path / "02_选题"
    brief_dir.mkdir(parents=True)
    # 只有 topic_cards.json（无 selected_topics.json 骨架）
    (brief_dir / "topic_cards.json").write_text(
        json.dumps(
            {
                "schema_version": "newma.brief_topic_cards.v1",
                "topic_cards": [
                    {"topic_id": "T01", "title": "选题一"},
                    {"topic_id": "T02", "title": "选题二"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(control, "canonical_stage_dir", lambda stage, rid: brief_dir if stage == "brief" else tmp_path / stage)

    result = control.approve_stage_gate(run_id, "brief", selected_ids="T02")

    assert result["status"] == "created"
    assert result["selected_topic_ids"] == ["T02"]
    gate = json.loads((brief_dir / "selected_topics.json").read_text(encoding="utf-8"))
    assert gate["status"] == "approved"
    assert gate["selected_topic_ids"] == ["T02"]
    assert [card["topic_id"] for card in gate["selected_topics"]] == ["T02"]


def test_approve_stage_gate_missing_without_selection(tmp_path, monkeypatch):
    """gate 文件缺失且无选择 → 保持 missing（不创建空 gate）。"""
    monkeypatch.setattr(control, "canonical_stage_dir", lambda stage, rid: tmp_path)
    result = control.approve_stage_gate("creator-test000002", "brief")
    assert result["status"] == "missing"
