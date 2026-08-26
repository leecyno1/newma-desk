import json
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from contextlib import contextmanager
from pathlib import Path


# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from path_config import get_project_root

ROOT = get_project_root()
PYTHON = sys.executable


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def project_tempdir():
    return tempfile.TemporaryDirectory(prefix="dasheng-mainline-test-")


@contextmanager
def load_script_module(name: str, path: Path):
    scripts_dir = str(path.parent)
    inserted = False
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
        inserted = True
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        sys.modules[name] = module
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(name, None)
        if inserted:
            sys.path.remove(scripts_dir)


class MainlineHardeningTests(unittest.TestCase):
    def test_runtime_outputs_reject_skills_directory(self):
        with load_script_module("canonical_workflow_for_output_guard", ROOT / "scripts/canonical_workflow.py") as module:
            forbidden = ROOT / "skills" / "dasheng-stage-transwrite" / "runtime-output"
            with self.assertRaises(module.WorkflowContractError):
                module.ensure_runtime_output_dir(forbidden, label="test output_dir")

    def test_build_stage3_draft_emits_final_structure_gate(self):
        with project_tempdir() as tmpdir:
            tmp = Path(tmpdir)
            selected_topics = tmp / "selected_topics.json"
            topic_cards = tmp / "topic_cards.json"
            out_dir = tmp / "draft_out"
            fake_draft = tmp / "fake_draft.md"

            write_json(
                selected_topics,
                {
                    "run_id": "run-hardening-001",
                    "status": "approved",
                    "selected_topics": [
                        {
                            "topic_id": "topic1",
                            "title": "测试选题",
                            "selection_reason": "用于验证 gate",
                            "editor_note": "",
                        }
                    ],
                },
            )
            write_json(
                topic_cards,
                [
                    {
                        "topic_id": "topic1",
                        "title": "测试选题",
                        "core_thesis": "验证主链硬化是否会生成 final gate。",
                        "counterintuitive_angle": "不是先猜目录，而是先锁 gate。",
                        "audience": "编辑团队",
                        "proof_requirements": ["证明 gate 是否生成", "证明 draft_manifest 正常落盘", "证明下游可读取"],
                        "chart_needs": ["图表A", "图表B", "图表C"],
                        "existing_evidence": [
                            {"title": "证据1", "url": "https://example.com/1", "source_tier": "official"},
                            {"title": "证据2", "url": "https://example.com/2", "source_tier": "official"},
                        ],
                        "missing_evidence": ["需要编辑确认结构"],
                        "structure_hint": {
                            "opening": "解释为什么 gate 比模板更重要",
                            "part_1": "说明 canonical manifest 的意义",
                            "part_2": "说明 gate 的作用",
                            "part_3": "说明下游如何继承",
                            "ending": "回到结构化主链",
                        },
                        "meta": {"id": "topic-card:topic1"},
                    }
                ],
            )
            fake_draft.write_text("# 测试选题\n\n" + ("这是一段用于测试的中文正文。" * 450), encoding="utf-8")
            env = os.environ.copy()
            env["DASHENG_DRAFT_FAKE_RESPONSE_FILE"] = str(fake_draft)

            proc = subprocess.run(
                [
                    PYTHON,
                    str(ROOT / "scripts/build_stage3_draft.py"),
                    str(selected_topics),
                    str(topic_cards),
                    "--output-dir",
                    str(out_dir),
                ],
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stderr)
            gate_file = out_dir / "final_structure_snapshot.json"
            self.assertTrue(gate_file.exists())
            payload = json.loads(gate_file.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "pending_editor_review")
            self.assertEqual(payload["gate"], "Final Structure Gate")
            manifest = json.loads((out_dir / "draft_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(len(manifest["drafts"]), 1)
            html_file = Path(manifest["drafts"][0]["html_file"])
            self.assertTrue(html_file.exists())
            self.assertIn("03_HTML草稿_", html_file.name)
            html_text = html_file.read_text(encoding="utf-8")
            self.assertIn('contenteditable="true"', html_text)
            self.assertIn("免责声明", html_text)
            stdout_payload = json.loads(proc.stdout)
            self.assertEqual(stdout_payload["html_files"], [str(html_file)])

    def test_material_entrypoints_are_removed(self):
        for rel_path in [
            "scripts/material_execute_pack.py",
            "scripts/material_parallel_launcher.py",
            "skills/dasheng-daily-material/SKILL.md",
        ]:
            self.assertFalse((ROOT / rel_path).exists(), rel_path)

    def test_publish_requires_publish_decision_gate_from_draft_manifest(self):
        with project_tempdir() as tmpdir:
            tmp = Path(tmpdir)
            draft_file = tmp / "03_标准初稿_topic-demo.md"
            draft_file.write_text("## 标题\n\n正文", encoding="utf-8")
            write_json(
                tmp / "draft_manifest.json",
                {
                    "run_id": "run-hardening-004",
                    "stage": "draft",
                    "drafts": [
                        {
                            "topic_id": "topic-demo",
                            "title": "发布决策门测试",
                            "draft_file": str(draft_file),
                        }
                    ],
                },
            )
            proc = subprocess.run(
                [
                    PYTHON,
                    str(ROOT / "scripts/publish_video_supplement.py"),
                    "--draft-manifest",
                    str(tmp / "draft_manifest.json"),
                    "--publish-decision",
                    str(tmp / "missing_publish_decision.json"),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("Channel Gate", proc.stderr or proc.stdout)

    def test_legacy_entrypoints_redirect_to_dasheng_media_sop(self):
        proc = subprocess.run(
            ["node", str(ROOT / "skills/dasheng-daily-draft/index.js")],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("dasheng-media-sop", proc.stderr or proc.stdout)

    def test_more_legacy_entrypoints_redirect_to_dasheng_media_sop(self):
        for target in [
            ROOT / "skills/dasheng-daily-clustering/index.js",
            ROOT / "skills/dasheng-daily-outline/index.js",
        ]:
            proc = subprocess.run(
                ["node", str(target)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("dasheng-media-sop", proc.stderr or proc.stdout)

    def test_mainline_brief_requires_explicit_run_id_or_input(self):
        proc = subprocess.run(
            [
                PYTHON,
                str(ROOT / "scripts/run_mainline_stage.py"),
                "brief",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("不再允许猜最新目录", proc.stderr or proc.stdout)

    def test_mainline_paradigm_builds_optional_asset_command(self):
        with load_script_module("run_mainline_stage_test", ROOT / "scripts/run_mainline_stage.py") as module:
            command = module.build_paradigm_command(
                Namespace(
                    samples=["sample-a.md", "sample-b.md"],
                    run_id="2026-05-06_150000",
                    profile_name="结构变化解读",
                    sample_type="standard_article",
                    scenario=["行业解读"],
                    channel=["公众号", "小红书"],
                    bind_style_dna="none",
                    output_dir="/tmp/paradigm-out",
                    no_ai=True,
                )
            )

        self.assertIn(str(ROOT / "scripts/build_paradigm_profile.py"), command)
        self.assertIn("sample-a.md", command)
        self.assertIn("--run-id", command)
        self.assertIn("2026-05-06_150000", command)
        self.assertIn("--profile-name", command)
        self.assertIn("结构变化解读", command)
        self.assertIn("--no-ai", command)

    def test_mainline_paradigm_requires_sample_file(self):
        with load_script_module("run_mainline_stage_test", ROOT / "scripts/run_mainline_stage.py") as module:
            with self.assertRaises(module.WorkflowContractError):
                module.build_paradigm_command(
                    Namespace(
                        samples=[],
                        run_id="2026-05-06_150000",
                        profile_name=None,
                        sample_type="standard_article",
                        scenario=[],
                        channel=[],
                        bind_style_dna="none",
                        output_dir=None,
                        no_ai=False,
                    )
                )

    def test_mainline_runner_no_longer_exposes_material_or_rewrite_stages(self):
        for retired_stage in ["material", "rewrite"]:
            proc = subprocess.run(
                [
                    PYTHON,
                    str(ROOT / "scripts/run_mainline_stage.py"),
                    retired_stage,
                    "--run-id",
                    "run-retired-stage",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("invalid choice", proc.stderr or proc.stdout)

    def test_transwrite_builds_three_lane_package(self):
        with project_tempdir() as tmpdir:
            tmp = Path(tmpdir)
            draft_file = tmp / "03_标准初稿_topic-demo.md"
            html_file = tmp / "03_HTML草稿_topic-demo.html"
            draft_file.write_text("# 测试题\n\n## 第一部分\n\n这是用于转写测试的正文。", encoding="utf-8")
            html_file.write_text("<html><body contenteditable=\"true\">正文</body></html>", encoding="utf-8")
            write_json(
                tmp / "draft_manifest.json",
                {
                    "run_id": "run-hardening-transwrite",
                    "stage": "draft",
                    "drafts": [
                        {
                            "topic_id": "topic-demo",
                            "title": "转写测试题",
                            "draft_file": str(draft_file),
                            "html_file": str(html_file),
                        }
                    ],
                },
            )
            write_json(
                tmp / "final_structure_snapshot.json",
                {
                    "run_id": "run-hardening-transwrite",
                    "gate": "Final Structure Gate",
                    "status": "approved",
                    "topics": [{"topic_id": "topic-demo"}],
                },
            )
            write_json(
                tmp / "transwrite_decision.json",
                {
                    "run_id": "run-hardening-transwrite",
                    "gate": "Transwrite Gate",
                    "status": "approved",
                    "topics": [
                        {
                            "topic_id": "topic-demo",
                            "lanes": ["wechat_article", "explainer_html_video", "podcast"],
                            "wechat_article": {"humanize": True, "cover_generation": {"enabled": True}},
                            "explainer_html_video": {
                                "visual_layer": {"background": "opaque"},
                                "audio": {"mode": "synthetic_audio"},
                            },
                            "podcast": {"enabled": True, "provider": "minimax", "mode": "solo"},
                        }
                    ],
                },
            )

            proc = subprocess.run(
                [
                    PYTHON,
                    str(ROOT / "scripts/build_stage4_transwrite.py"),
                    "--draft-manifest",
                    str(tmp / "draft_manifest.json"),
                    "--transwrite-decision",
                    str(tmp / "transwrite_decision.json"),
                    "--output-dir",
                    str(tmp / "transwrite_out"),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stderr)
            payload = json.loads(proc.stdout)
            manifest = json.loads(Path(payload["manifest_file"]).read_text(encoding="utf-8"))
            lanes = manifest["topics"][0]["lanes"]
            self.assertIn("wechat_article", lanes)
            self.assertIn("explainer_html_video", lanes)
            self.assertIn("podcast", lanes)
            self.assertEqual(manifest["status"], "prepared_for_skill_execution")
            self.assertEqual(lanes["wechat_article"]["status"], "ready_for_agent_execution")
            self.assertEqual(lanes["explainer_html_video"]["status"], "pending_director_review")
            self.assertIn("execution_contract", lanes["wechat_article"])
            self.assertIn("execution_contract", lanes["explainer_html_video"])
            self.assertIn("execution_contract", lanes["podcast"])
            self.assertEqual(
                lanes["explainer_html_video"]["execution_contract"]["final_artifacts"]["video"],
                str((tmp / "transwrite_out" / "topic-demo" / "explainer_html_video" / "delivery" / "topic-demo.mp4").resolve()),
            )
            self.assertTrue(Path(lanes["explainer_html_video"]["html_overlay"]).exists())
            self.assertEqual(lanes["explainer_html_video"]["renderer"]["default"], "remotion")
            self.assertEqual(lanes["explainer_html_video"]["renderer"]["aspect"], "16:9")
            self.assertTrue(Path(lanes["explainer_html_video"]["html_video_project_plan"]).exists())
            self.assertTrue(Path(lanes["explainer_html_video"]["html_video_project_vars"]).exists())
            self.assertTrue(Path(lanes["explainer_html_video"]["html_video_commands"]).exists())
            html_video_plan = json.loads(Path(lanes["explainer_html_video"]["html_video_project_plan"]).read_text(encoding="utf-8"))
            self.assertEqual(html_video_plan["renderer"], "html-video")
            self.assertEqual(html_video_plan["renderer_role"], "scene_renderer")
            self.assertEqual(html_video_plan["master_timeline"], "remotion")
            self.assertEqual(html_video_plan["template_id"], "frame-liquid-bg-hero")
            bridge_proc = subprocess.run(
                [
                    PYTHON,
                    str(ROOT / "scripts/transwrite_html_video_bridge.py"),
                    "--video-manifest",
                    lanes["explainer_html_video"]["manifest"],
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(bridge_proc.returncode, 0, msg=bridge_proc.stderr)
            bridge_payload = json.loads(bridge_proc.stdout)
            self.assertEqual(bridge_payload["status"], "planned")
            self.assertEqual(bridge_payload["plan"]["renderer"], "html-video")
            self.assertEqual(manifest["next_stage"], "publish")

    def test_publish_builds_slim_execution_pack_from_transwrite_manifest(self):
        with project_tempdir() as tmpdir:
            tmp = Path(tmpdir)
            wechat_manifest = tmp / "wechat_article_manifest.json"
            video_manifest = tmp / "talking_head_video_manifest.json"
            wechat_md = tmp / "wechat.md"
            wechat_md.write_text("公众号正文", encoding="utf-8")
            write_json(
                wechat_manifest,
                {
                    "lane": "wechat_article",
                    "status": "ready_base_package",
                    "base_markdown": str(wechat_md),
                    "final_html": str(tmp / "wechat.html"),
                },
            )
            write_json(
                video_manifest,
                {
                    "lane": "talking_head_video",
                    "status": "planned_for_render",
                    "render_plan": str(tmp / "render_plan.json"),
                },
            )
            write_json(
                tmp / "transwrite_manifest.json",
                {
                    "run_id": "run-hardening-publish-slim",
                    "stage": "transwrite",
                    "status": "prepared_for_skill_execution",
                    "topics": [
                        {
                            "topic_id": "topic-demo",
                            "title": "发布执行测试",
                            "lanes": {
                                "wechat_article": {
                                    "status": "ready_base_package",
                                    "manifest": str(wechat_manifest),
                                    "base_markdown": str(wechat_md),
                                },
                                "talking_head_video": {
                                    "status": "ready_for_skill_execution",
                                    "manifest": str(video_manifest),
                                    "render_plan": str(tmp / "render_plan.json"),
                                },
                            },
                        }
                    ],
                },
            )
            write_json(
                tmp / "publish_decision.json",
                {
                    "run_id": "run-hardening-publish-slim",
                    "gate": "Channel Gate",
                    "status": "approved",
                    "topics": [{"topic_id": "topic-demo", "channels": ["wechat_article", "douyin_video"]}],
                },
            )

            proc = subprocess.run(
                [
                    PYTHON,
                    str(ROOT / "scripts/build_stage5_publish.py"),
                    "--transwrite-manifest",
                    str(tmp / "transwrite_manifest.json"),
                    "--publish-decision",
                    str(tmp / "publish_decision.json"),
                    "--output-dir",
                    str(tmp / "publish_out"),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["stage"], "publish")
            self.assertEqual(payload["next_stage"], "postmortem")
            self.assertEqual([pack["channel"] for pack in payload["channel_packs"]], ["wechat_article", "douyin_video"])
            wechat_pack = next(pack for pack in payload["channel_packs"] if pack["channel"] == "wechat_article")
            self.assertTrue(Path(wechat_pack["readme"]).exists())
            wechat_readme = Path(wechat_pack["readme"]).read_text(encoding="utf-8")
            self.assertIn("安全执行命令", wechat_readme)
            self.assertIn("execute_publish_request.py", wechat_readme)
            self.assertIn("--confirm-execute", wechat_readme)
            video_pack = next(pack for pack in payload["channel_packs"] if pack["channel"] == "douyin_video")
            self.assertEqual(video_pack["status"], "blocked_or_waiting")
            self.assertEqual(video_pack["blocking_reason"], "lane_status_not_publish_ready:ready_for_skill_execution")
            self.assertTrue(Path(video_pack["pack_manifest"]).exists())
            self.assertTrue(Path(video_pack["readme"]).exists())
            self.assertTrue((tmp / "publish_out" / "07_发布包.md").exists())

    def test_publish_accepts_completed_transwrite_lane(self):
        with project_tempdir() as tmpdir:
            tmp = Path(tmpdir)
            video_manifest = tmp / "talking_head_video_manifest.json"
            final_video = tmp / "final.mp4"
            final_video.write_bytes(b"fake mp4")
            write_json(video_manifest, {"lane": "talking_head_video", "status": "completed"})
            write_json(
                tmp / "transwrite_manifest.json",
                {
                    "run_id": "run-hardening-publish-completed",
                    "stage": "transwrite",
                    "status": "prepared_for_skill_execution",
                    "topics": [
                        {
                            "topic_id": "topic-demo",
                            "title": "完成态发布测试",
                            "lanes": {
                                "talking_head_video": {
                                    "status": "completed",
                                    "manifest": str(video_manifest),
                                    "final_video": str(final_video),
                                },
                            },
                        }
                    ],
                },
            )
            write_json(
                tmp / "publish_decision.json",
                {
                    "run_id": "run-hardening-publish-completed",
                    "gate": "Channel Gate",
                    "status": "approved",
                    "topics": [{"topic_id": "topic-demo", "channels": ["douyin_video"]}],
                },
            )

            proc = subprocess.run(
                [
                    PYTHON,
                    str(ROOT / "scripts/build_stage5_publish.py"),
                    "--transwrite-manifest",
                    str(tmp / "transwrite_manifest.json"),
                    "--publish-decision",
                    str(tmp / "publish_decision.json"),
                    "--output-dir",
                    str(tmp / "publish_out"),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["channel_packs"][0]["status"], "ready_for_execution")
            self.assertIsNone(payload["channel_packs"][0]["blocking_reason"])
            self.assertTrue(Path(payload["channel_packs"][0]["pack_manifest"]).exists())
            browser_profile = payload["channel_packs"][0]["browser_profile"]
            self.assertEqual(browser_profile["platform"], "douyin")
            self.assertIn("NewmaPublishProfiles/douyin", browser_profile["profile_dir"])
            self.assertEqual(browser_profile["open_command"], "python3 scripts/open_publish_browser.py douyin_video")
            pack_payload = json.loads(Path(payload["channel_packs"][0]["pack_manifest"]).read_text(encoding="utf-8"))
            self.assertEqual(pack_payload["browser_profile"]["platform"], "douyin")
            self.assertTrue(payload["channel_packs"][0]["execution_commands"]["confirm_execute_supported"])
            self.assertIsNotNone(payload["channel_packs"][0]["execution_commands"]["confirmed_executor_command"])
            execution_manifest = json.loads((tmp / "publish_out" / "channel_execution_manifest.json").read_text(encoding="utf-8"))
            invocation = execution_manifest["executions"][0]["executor_invocation"]
            self.assertIn("execute_publish_request.py", invocation["safe_executor_command"])
            self.assertTrue(invocation["confirm_execute_supported"])
            self.assertIsNotNone(invocation["confirmed_executor_command"])

    def test_mainline_publish_dry_run_prepares_channel_execution_plans(self):
        with project_tempdir() as tmpdir:
            tmp = Path(tmpdir)
            wechat_manifest = tmp / "wechat_article_manifest.json"
            video_manifest = tmp / "talking_head_video_manifest.json"
            wechat_html = tmp / "wechat.html"
            final_video = tmp / "final.mp4"
            wechat_html.write_text("<html><body>公众号正文</body></html>", encoding="utf-8")
            final_video.write_bytes(b"fake mp4")
            write_json(wechat_manifest, {"lane": "wechat_article", "status": "completed"})
            write_json(video_manifest, {"lane": "talking_head_video", "status": "completed"})
            write_json(
                tmp / "transwrite_manifest.json",
                {
                    "run_id": "run-hardening-publish-dry-run",
                    "stage": "transwrite",
                    "status": "prepared_for_skill_execution",
                    "topics": [
                        {
                            "topic_id": "topic-demo",
                            "title": "发布 dry-run 测试",
                            "lanes": {
                                "wechat_article": {
                                    "status": "completed",
                                    "manifest": str(wechat_manifest),
                                    "final_html": str(wechat_html),
                                },
                                "talking_head_video": {
                                    "status": "completed",
                                    "manifest": str(video_manifest),
                                    "final_video": str(final_video),
                                },
                            },
                        }
                    ],
                },
            )
            write_json(
                tmp / "publish_decision.json",
                {
                    "run_id": "run-hardening-publish-dry-run",
                    "gate": "Channel Gate",
                    "status": "approved",
                    "topics": [
                        {
                            "topic_id": "topic-demo",
                            "channels": ["wechat_article", "douyin_video", "bilibili_video"],
                        }
                    ],
                },
            )

            proc = subprocess.run(
                [
                    PYTHON,
                    str(ROOT / "scripts/run_mainline_stage.py"),
                    "publish",
                    "--transwrite-manifest",
                    str(tmp / "transwrite_manifest.json"),
                    "--publish-decision",
                    str(tmp / "publish_decision.json"),
                    "--output-dir",
                    str(tmp / "publish_out"),
                    "--dry-run",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(proc.returncode, 0, msg=proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["mode"], "dry_run")
            self.assertTrue(payload["will_not_publish"])
            self.assertEqual(len(payload["plans"]), 3)
            self.assertTrue(Path(payload["report_file"]).exists())
            self.assertTrue(Path(payload["preflight_report"]).exists())
            self.assertEqual(payload["summary"]["total_channels"], 3)
            self.assertGreaterEqual(payload["summary"]["missing_dependency_count"], 0)
            preflight_text = Path(payload["preflight_report"]).read_text(encoding="utf-8")
            self.assertIn("Publish 发布前总预检", preflight_text)
            self.assertIn("不会触发真实发布", preflight_text)
            self.assertIn("wechat_article", preflight_text)
            self.assertIn("安全执行预演", preflight_text)
            self.assertIn("确认后执行", preflight_text)
            self.assertIn("execute_publish_request.py", preflight_text)
            self.assertIn("--confirm-execute", preflight_text)
            self.assertIn("safe_executor_command", payload["summary"]["channels"][0])
            self.assertEqual({plan["channel"] for plan in payload["plans"]}, {"wechat_article", "douyin_video", "bilibili_video"})

    def test_publish_xhs_video_uses_api_first_bridge_execution_request(self):
        with project_tempdir() as tmpdir:
            tmp = Path(tmpdir)
            video_manifest = tmp / "talking_head_video_manifest.json"
            final_video = tmp / "final.mp4"
            final_video.write_bytes(b"fake mp4")
            write_json(video_manifest, {"lane": "talking_head_video", "status": "completed"})
            write_json(
                tmp / "transwrite_manifest.json",
                {
                    "run_id": "run-hardening-publish-xhs-api-first",
                    "stage": "transwrite",
                    "status": "prepared_for_skill_execution",
                    "topics": [
                        {
                            "topic_id": "topic-demo",
                            "title": "小红书桥接测试",
                            "lanes": {
                                "talking_head_video": {
                                    "status": "completed",
                                    "manifest": str(video_manifest),
                                    "final_video": str(final_video),
                                },
                            },
                        }
                    ],
                },
            )
            write_json(
                tmp / "publish_decision.json",
                {
                    "run_id": "run-hardening-publish-xhs-api-first",
                    "gate": "Channel Gate",
                    "status": "approved",
                    "topics": [
                        {
                            "topic_id": "topic-demo",
                            "title": "小红书桥接测试",
                            "channels": ["xiaohongshu_video"],
                            "tags": ["AI", "财经"],
                        }
                    ],
                },
            )

            proc = subprocess.run(
                [
                    PYTHON,
                    str(ROOT / "scripts/build_stage5_publish.py"),
                    "--transwrite-manifest",
                    str(tmp / "transwrite_manifest.json"),
                    "--publish-decision",
                    str(tmp / "publish_decision.json"),
                    "--output-dir",
                    str(tmp / "publish_out"),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(proc.returncode, 0, msg=proc.stderr)
            payload = json.loads(proc.stdout)
            pack = payload["channel_packs"][0]
            self.assertEqual(pack["executor_skill"], "dasheng-xhs-publish-bridge")
            self.assertEqual(pack["execution_mode"], "api_first_with_browser_fallback")
            self.assertTrue(pack["execution_commands"]["confirm_execute_supported"])
            self.assertIsNotNone(pack["execution_commands"]["confirmed_executor_command"])
            self.assertTrue(Path(pack["execution_request"]).exists())
            self.assertTrue(Path(pack["verification_request"]).exists())

            execution_request = json.loads(Path(pack["execution_request"]).read_text(encoding="utf-8"))
            self.assertEqual(execution_request["platform"], "xiaohongshu")
            self.assertEqual(execution_request["route_priority"][0]["route"], "qianfan-local-api")
            self.assertEqual(execution_request["route_priority"][1]["route"], "social-auto-upload")
            self.assertEqual(execution_request["route_priority"][-1]["route"], "browser-profile")
            all_in_one = next(route for route in execution_request["route_priority"] if route["route"] == "all-in-one")
            self.assertIn("aione xhs creator post-note", "\n".join(all_in_one["command_templates"]))

    def test_record_publish_result_updates_channel_pack_and_verification_report(self):
        with project_tempdir() as tmpdir:
            tmp = Path(tmpdir)
            wechat_manifest = tmp / "wechat_article_manifest.json"
            wechat_html = tmp / "wechat.html"
            wechat_html.write_text("<html><body>公众号正文</body></html>", encoding="utf-8")
            write_json(wechat_manifest, {"lane": "wechat_article", "status": "completed"})
            write_json(
                tmp / "transwrite_manifest.json",
                {
                    "run_id": "run-hardening-publish-result",
                    "stage": "transwrite",
                    "status": "prepared_for_skill_execution",
                    "topics": [
                        {
                            "topic_id": "topic-demo",
                            "title": "发布结果回收测试",
                            "lanes": {
                                "wechat_article": {
                                    "status": "completed",
                                    "manifest": str(wechat_manifest),
                                    "final_html": str(wechat_html),
                                },
                            },
                        }
                    ],
                },
            )
            write_json(
                tmp / "publish_decision.json",
                {
                    "run_id": "run-hardening-publish-result",
                    "gate": "Channel Gate",
                    "status": "approved",
                    "topics": [{"topic_id": "topic-demo", "channels": ["wechat_article"]}],
                },
            )
            build_proc = subprocess.run(
                [
                    PYTHON,
                    str(ROOT / "scripts/build_stage5_publish.py"),
                    "--transwrite-manifest",
                    str(tmp / "transwrite_manifest.json"),
                    "--publish-decision",
                    str(tmp / "publish_decision.json"),
                    "--output-dir",
                    str(tmp / "publish_out"),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(build_proc.returncode, 0, msg=build_proc.stderr)
            publish_payload = json.loads(build_proc.stdout)
            self.assertEqual(publish_payload["publish_summary"]["status"], "pending_execution")
            self.assertEqual(publish_payload["publish_summary"]["total_channels"], 1)
            self.assertEqual(publish_payload["publish_summary"]["recorded_count"], 0)
            self.assertEqual(publish_payload["publish_summary"]["pending_count"], 1)
            self.assertEqual(publish_payload["publish_results"], [])
            channel_pack = publish_payload["channel_packs"][0]["pack_manifest"]
            initial_manifest = json.loads((tmp / "publish_out" / "publish_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(initial_manifest["publish_summary"], publish_payload["publish_summary"])
            initial_verification = json.loads((tmp / "publish_out" / "publish_verification_report.json").read_text(encoding="utf-8"))
            self.assertEqual(initial_verification["publish_summary"], publish_payload["publish_summary"])
            self.assertEqual(initial_verification["records"], [])
            self.assertEqual(initial_verification["draft_records"], [])
            result_proc = subprocess.run(
                [
                    PYTHON,
                    str(ROOT / "scripts/record_publish_result.py"),
                    "--channel-pack",
                    channel_pack,
                    "--success",
                    "true",
                    "--status",
                    "draft",
                    "--platform",
                    "wechat",
                    "--draft-id",
                    "draft_123",
                    "--verification-status",
                    "verified",
                    "--account",
                    "dasheng-test",
                    "--screenshot",
                    str(tmp / "wechat_draft.png"),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result_proc.returncode, 0, msg=result_proc.stderr)
            result_payload = json.loads(result_proc.stdout)
            self.assertEqual(result_payload["status"], "recorded")
            self.assertTrue(Path(result_payload["publish_result"]).exists())

            pack_payload = json.loads(Path(channel_pack).read_text(encoding="utf-8"))
            self.assertEqual(pack_payload["publish_status"], "draft")
            self.assertEqual(pack_payload["draft_id"], "draft_123")
            self.assertEqual(pack_payload["verification_status"], "verified")

            verification = json.loads((tmp / "publish_out" / "publish_verification_report.json").read_text(encoding="utf-8"))
            self.assertEqual(verification["status"], "all_drafted")
            self.assertEqual(verification["publish_summary"]["draft_count"], 1)
            self.assertEqual(verification["published_links"], [])
            self.assertEqual(verification["draft_records"][0]["draft_id"], "draft_123")

            execution = json.loads((tmp / "publish_out" / "channel_execution_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(execution["executions"][0]["status"], "draft")
            self.assertEqual(execution["executions"][0]["result"]["draft_id"], "draft_123")

            manifest = json.loads((tmp / "publish_out" / "publish_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["publish_results"][0]["draft_id"], "draft_123")
            self.assertEqual(manifest["status"], "all_drafted")
            self.assertEqual(manifest["publish_summary"]["pending_count"], 0)

            postmortem_proc = subprocess.run(
                [
                    PYTHON,
                    str(ROOT / "scripts/postmortem_writeback.py"),
                    "--publish-manifest",
                    str(tmp / "publish_out" / "publish_manifest.json"),
                    "--output-dir",
                    str(tmp / "postmortem_out"),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(postmortem_proc.returncode, 0, msg=postmortem_proc.stderr)
            postmortem = json.loads((tmp / "postmortem_out" / "postmortem_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(postmortem["topics"][0]["publish_results"][0]["draft_id"], "draft_123")
            self.assertTrue(postmortem["topics"][0]["drafted"])
            self.assertEqual(postmortem["writeback"]["topic_pattern_library"]["drafted_topics"], 1)
            report_text = (tmp / "postmortem_out" / "08_复盘报告.md").read_text(encoding="utf-8")
            self.assertIn("draft_123", report_text)

    def test_record_publish_result_reports_partial_when_other_channels_pending(self):
        with project_tempdir() as tmpdir:
            tmp = Path(tmpdir)
            wechat_manifest = tmp / "wechat_article_manifest.json"
            video_manifest = tmp / "talking_head_video_manifest.json"
            wechat_html = tmp / "wechat.html"
            video = tmp / "video.mp4"
            wechat_html.write_text("<html><body>公众号正文</body></html>", encoding="utf-8")
            video.write_bytes(b"fake mp4")
            write_json(wechat_manifest, {"lane": "wechat_article", "status": "completed"})
            write_json(video_manifest, {"lane": "talking_head_video", "status": "completed"})
            write_json(
                tmp / "transwrite_manifest.json",
                {
                    "run_id": "run-hardening-publish-partial",
                    "stage": "transwrite",
                    "status": "prepared_for_skill_execution",
                    "topics": [
                        {
                            "topic_id": "topic-demo",
                            "title": "发布结果部分回填测试",
                            "lanes": {
                                "wechat_article": {
                                    "status": "completed",
                                    "manifest": str(wechat_manifest),
                                    "final_html": str(wechat_html),
                                },
                                "talking_head_video": {
                                    "status": "completed",
                                    "manifest": str(video_manifest),
                                    "final_video": str(video),
                                },
                            },
                        }
                    ],
                },
            )
            write_json(
                tmp / "publish_decision.json",
                {
                    "run_id": "run-hardening-publish-partial",
                    "gate": "Channel Gate",
                    "status": "approved",
                    "topics": [{"topic_id": "topic-demo", "channels": ["wechat_article", "xiaohongshu_video"]}],
                },
            )
            build_proc = subprocess.run(
                [
                    PYTHON,
                    str(ROOT / "scripts/build_stage5_publish.py"),
                    "--transwrite-manifest",
                    str(tmp / "transwrite_manifest.json"),
                    "--publish-decision",
                    str(tmp / "publish_decision.json"),
                    "--output-dir",
                    str(tmp / "publish_out"),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(build_proc.returncode, 0, msg=build_proc.stderr)
            publish_payload = json.loads(build_proc.stdout)
            channel_pack = next(
                pack["pack_manifest"]
                for pack in publish_payload["channel_packs"]
                if pack["channel"] == "wechat_article"
            )

            result_proc = subprocess.run(
                [
                    PYTHON,
                    str(ROOT / "scripts/record_publish_result.py"),
                    "--channel-pack",
                    channel_pack,
                    "--success",
                    "true",
                    "--status",
                    "draft",
                    "--platform",
                    "wechat",
                    "--draft-id",
                    "draft_partial",
                    "--verification-status",
                    "verified",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result_proc.returncode, 0, msg=result_proc.stderr)

            manifest = json.loads((tmp / "publish_out" / "publish_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "partially_recorded")
            self.assertEqual(manifest["publish_summary"]["total_channels"], 2)
            self.assertEqual(manifest["publish_summary"]["recorded_count"], 1)
            self.assertEqual(manifest["publish_summary"]["pending_count"], 1)
            self.assertEqual(manifest["publish_summary"]["pending_channels"][0]["channel"], "xiaohongshu_video")

            verification = json.loads((tmp / "publish_out" / "publish_verification_report.json").read_text(encoding="utf-8"))
            self.assertEqual(verification["status"], "partially_recorded")
            self.assertEqual(verification["publish_summary"]["draft_count"], 1)
            self.assertEqual(verification["publish_summary"]["published_count"], 0)

    def test_publish_record_and_postmortem_end_to_end_mixed_topic(self):
        with project_tempdir() as tmpdir:
            tmp = Path(tmpdir)
            wechat_manifest = tmp / "wechat_article_manifest.json"
            video_manifest = tmp / "talking_head_video_manifest.json"
            wechat_html = tmp / "wechat.final.html"
            video = tmp / "talking_head.final.mp4"
            wechat_html.write_text("<html><body>混合发布整链测试</body></html>", encoding="utf-8")
            video.write_bytes(b"fake mp4")
            write_json(wechat_manifest, {"lane": "wechat_article", "status": "completed"})
            write_json(video_manifest, {"lane": "talking_head_video", "status": "completed"})
            write_json(
                tmp / "transwrite_manifest.json",
                {
                    "run_id": "run-hardening-publish-e2e-mixed",
                    "stage": "transwrite",
                    "status": "prepared_for_skill_execution",
                    "topics": [
                        {
                            "topic_id": "topic-demo",
                            "title": "发布整链混合状态测试",
                            "lanes": {
                                "wechat_article": {
                                    "status": "completed",
                                    "manifest": str(wechat_manifest),
                                    "final_html": str(wechat_html),
                                },
                                "talking_head_video": {
                                    "status": "completed",
                                    "manifest": str(video_manifest),
                                    "final_video": str(video),
                                },
                            },
                        }
                    ],
                },
            )
            write_json(
                tmp / "publish_decision.json",
                {
                    "run_id": "run-hardening-publish-e2e-mixed",
                    "gate": "Channel Gate",
                    "status": "approved",
                    "topics": [
                        {
                            "topic_id": "topic-demo",
                            "title": "发布整链混合状态测试",
                            "channels": ["wechat_article", "xiaohongshu_video"],
                            "tags": ["AI", "市场"],
                        }
                    ],
                },
            )

            build_proc = subprocess.run(
                [
                    PYTHON,
                    str(ROOT / "scripts/build_stage5_publish.py"),
                    "--transwrite-manifest",
                    str(tmp / "transwrite_manifest.json"),
                    "--publish-decision",
                    str(tmp / "publish_decision.json"),
                    "--output-dir",
                    str(tmp / "publish_out"),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(build_proc.returncode, 0, msg=build_proc.stderr)
            publish_payload = json.loads(build_proc.stdout)
            packs_by_channel = {pack["channel"]: pack["pack_manifest"] for pack in publish_payload["channel_packs"]}
            self.assertEqual(set(packs_by_channel), {"wechat_article", "xiaohongshu_video"})

            wechat_result = subprocess.run(
                [
                    PYTHON,
                    str(ROOT / "scripts/record_publish_result.py"),
                    "--channel-pack",
                    packs_by_channel["wechat_article"],
                    "--success",
                    "true",
                    "--status",
                    "draft",
                    "--platform",
                    "wechat",
                    "--draft-id",
                    "draft_e2e_001",
                    "--draft-url",
                    "https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit&appmsgid=draft_e2e_001",
                    "--verification-status",
                    "verified",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(wechat_result.returncode, 0, msg=wechat_result.stderr)

            xhs_result = subprocess.run(
                [
                    PYTHON,
                    str(ROOT / "scripts/record_publish_result.py"),
                    "--channel-pack",
                    packs_by_channel["xiaohongshu_video"],
                    "--success",
                    "true",
                    "--status",
                    "published",
                    "--platform",
                    "xiaohongshu",
                    "--platform-url",
                    "https://www.xiaohongshu.com/explore/e2e001",
                    "--platform-post-id",
                    "e2e001",
                    "--verification-status",
                    "verified",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(xhs_result.returncode, 0, msg=xhs_result.stderr)

            manifest = json.loads((tmp / "publish_out" / "publish_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "completed_with_mixed_status")
            self.assertEqual(manifest["publish_summary"]["total_channels"], 2)
            self.assertEqual(manifest["publish_summary"]["recorded_count"], 2)
            self.assertEqual(manifest["publish_summary"]["pending_count"], 0)
            self.assertEqual(manifest["publish_summary"]["draft_count"], 1)
            self.assertEqual(manifest["publish_summary"]["published_count"], 1)
            self.assertEqual(manifest["publish_summary"]["verified_count"], 2)

            verification = json.loads((tmp / "publish_out" / "publish_verification_report.json").read_text(encoding="utf-8"))
            self.assertEqual(verification["status"], "completed_with_mixed_status")
            self.assertEqual(len(verification["published_links"]), 1)
            self.assertEqual(verification["published_links"][0]["channel"], "xiaohongshu_video")
            self.assertEqual(verification["published_links"][0]["url"], "https://www.xiaohongshu.com/explore/e2e001")
            self.assertEqual(len(verification["draft_records"]), 1)
            self.assertEqual(verification["draft_records"][0]["channel"], "wechat_article")
            self.assertEqual(verification["draft_records"][0]["draft_id"], "draft_e2e_001")

            postmortem_proc = subprocess.run(
                [
                    PYTHON,
                    str(ROOT / "scripts/postmortem_writeback.py"),
                    "--publish-manifest",
                    str(tmp / "publish_out" / "publish_manifest.json"),
                    "--output-dir",
                    str(tmp / "postmortem_out"),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(postmortem_proc.returncode, 0, msg=postmortem_proc.stderr)
            postmortem = json.loads((tmp / "postmortem_out" / "postmortem_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(len(postmortem["topics"]), 1)
            self.assertEqual(postmortem["topics"][0]["topic_id"], "topic-demo")
            self.assertTrue(postmortem["topics"][0]["published"])
            self.assertTrue(postmortem["topics"][0]["drafted"])
            self.assertEqual(postmortem["topics"][0]["selected_channels"], ["wechat_article", "xiaohongshu_video"])
            self.assertEqual(postmortem["writeback"]["topic_pattern_library"]["published_topics"], 1)
            self.assertEqual(postmortem["writeback"]["topic_pattern_library"]["drafted_topics"], 1)

    def test_publish_channel_pack_can_select_second_browser_profile(self):
        with project_tempdir() as tmpdir:
            tmp = Path(tmpdir)
            video_manifest = tmp / "talking_head_video_manifest.json"
            video = tmp / "talking_head.final.mp4"
            video.write_bytes(b"fake mp4")
            write_json(video_manifest, {"lane": "talking_head_video", "status": "completed"})
            write_json(
                tmp / "transwrite_manifest.json",
                {
                    "run_id": "run-hardening-publish-profile-slot",
                    "stage": "transwrite",
                    "status": "completed",
                    "topics": [
                        {
                            "topic_id": "topic-demo",
                            "title": "多账号 Profile 测试",
                            "lanes": {
                                "talking_head_video": {
                                    "status": "completed",
                                    "manifest": str(video_manifest),
                                    "final_video": str(video),
                                }
                            },
                        }
                    ],
                },
            )
            write_json(
                tmp / "publish_decision.json",
                {
                    "run_id": "run-hardening-publish-profile-slot",
                    "gate": "Channel Gate",
                    "status": "approved",
                    "topics": [
                        {
                            "topic_id": "topic-demo",
                            "channels": ["xiaohongshu_video"],
                            "browser_profile_key": "xiaohongshu_video_2",
                        }
                    ],
                },
            )

            build_proc = subprocess.run(
                [
                    PYTHON,
                    str(ROOT / "scripts/build_stage5_publish.py"),
                    "--transwrite-manifest",
                    str(tmp / "transwrite_manifest.json"),
                    "--publish-decision",
                    str(tmp / "publish_decision.json"),
                    "--output-dir",
                    str(tmp / "publish_out"),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(build_proc.returncode, 0, msg=build_proc.stderr)
            publish_payload = json.loads(build_proc.stdout)
            pack_path = Path(publish_payload["channel_packs"][0]["pack_manifest"])
            channel_pack = json.loads(pack_path.read_text(encoding="utf-8"))
            self.assertEqual(channel_pack["browser_profile"]["profile_key"], "xiaohongshu_video_2")
            self.assertIn("NewmaPublishProfiles/xiaohongshu-2", channel_pack["browser_profile"]["profile_dir"])
            self.assertEqual(
                channel_pack["browser_profile"]["open_command"],
                "python3 scripts/open_publish_browser.py xiaohongshu_video_2",
            )

    def test_record_publish_result_failed_status_wins_over_partial_progress(self):
        with project_tempdir() as tmpdir:
            tmp = Path(tmpdir)
            pack_dir = tmp / "publish_out" / "channel_packs" / "topic-demo" / "wechat_article"
            pack_dir.mkdir(parents=True)
            channel_pack = pack_dir / "channel_pack.json"
            write_json(
                channel_pack,
                {
                    "topic_id": "topic-demo",
                    "title": "发布失败回填测试",
                    "channel": "wechat_article",
                    "platform": "wechat",
                    "status": "ready_for_execution",
                },
            )
            write_json(
                tmp / "publish_out" / "publish_manifest.json",
                {
                    "run_id": "run-hardening-publish-failed",
                    "stage": "publish",
                    "status": "pending_execution",
                    "channel_packs": [json.loads(channel_pack.read_text(encoding="utf-8"))],
                },
            )
            write_json(
                tmp / "publish_out" / "publish_verification_report.json",
                {"run_id": "run-hardening-publish-failed", "stage": "publish", "status": "pending_execution", "published_links": []},
            )

            result_proc = subprocess.run(
                [
                    PYTHON,
                    str(ROOT / "scripts/record_publish_result.py"),
                    "--channel-pack",
                    str(channel_pack),
                    "--success",
                    "false",
                    "--status",
                    "failed",
                    "--platform",
                    "wechat",
                    "--error",
                    "login expired",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result_proc.returncode, 0, msg=result_proc.stderr)

            manifest = json.loads((tmp / "publish_out" / "publish_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "failed")
            self.assertEqual(manifest["publish_summary"]["failed_count"], 1)
            verification = json.loads((tmp / "publish_out" / "publish_verification_report.json").read_text(encoding="utf-8"))
            self.assertEqual(verification["status"], "failed")

    def test_record_publish_result_requires_url_for_published_status(self):
        with project_tempdir() as tmpdir:
            tmp = Path(tmpdir)
            pack_dir = tmp / "publish_out" / "channel_packs" / "topic-demo" / "wechat_article"
            pack_dir.mkdir(parents=True)
            channel_pack = pack_dir / "channel_pack.json"
            write_json(
                channel_pack,
                {
                    "topic_id": "topic-demo",
                    "title": "发布无链接测试",
                    "channel": "wechat_article",
                    "platform": "wechat",
                    "status": "ready_for_execution",
                },
            )
            write_json(
                tmp / "publish_out" / "publish_manifest.json",
                {
                    "run_id": "run-hardening-publish-url-required",
                    "stage": "publish",
                    "status": "pending_execution",
                    "channel_packs": [json.loads(channel_pack.read_text(encoding="utf-8"))],
                },
            )
            write_json(
                tmp / "publish_out" / "publish_verification_report.json",
                {"run_id": "run-hardening-publish-url-required", "stage": "publish", "status": "pending_execution", "published_links": []},
            )

            result_proc = subprocess.run(
                [
                    PYTHON,
                    str(ROOT / "scripts/record_publish_result.py"),
                    "--channel-pack",
                    str(channel_pack),
                    "--success",
                    "true",
                    "--status",
                    "published",
                    "--platform",
                    "wechat",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result_proc.returncode, 0, msg=result_proc.stderr)

            verification = json.loads((tmp / "publish_out" / "publish_verification_report.json").read_text(encoding="utf-8"))
            self.assertEqual(verification["status"], "needs_manual_verification")
            self.assertEqual(verification["publish_summary"]["needs_manual_verification_count"], 1)
            self.assertEqual(verification["published_links"], [])
            self.assertEqual(verification["draft_records"], [])

    def test_record_publish_result_requires_draft_id_for_draft_status(self):
        with project_tempdir() as tmpdir:
            tmp = Path(tmpdir)
            pack_dir = tmp / "publish_out" / "channel_packs" / "topic-demo" / "wechat_article"
            pack_dir.mkdir(parents=True)
            channel_pack = pack_dir / "channel_pack.json"
            write_json(
                channel_pack,
                {
                    "topic_id": "topic-demo",
                    "title": "草稿无ID测试",
                    "channel": "wechat_article",
                    "platform": "wechat",
                    "status": "ready_for_execution",
                },
            )
            write_json(
                tmp / "publish_out" / "publish_manifest.json",
                {
                    "run_id": "run-hardening-publish-draft-id-required",
                    "stage": "publish",
                    "status": "pending_execution",
                    "channel_packs": [json.loads(channel_pack.read_text(encoding="utf-8"))],
                },
            )
            write_json(
                tmp / "publish_out" / "publish_verification_report.json",
                {"run_id": "run-hardening-publish-draft-id-required", "stage": "publish", "status": "pending_execution", "published_links": []},
            )

            result_proc = subprocess.run(
                [
                    PYTHON,
                    str(ROOT / "scripts/record_publish_result.py"),
                    "--channel-pack",
                    str(channel_pack),
                    "--success",
                    "true",
                    "--status",
                    "draft",
                    "--platform",
                    "wechat",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result_proc.returncode, 0, msg=result_proc.stderr)

            verification = json.loads((tmp / "publish_out" / "publish_verification_report.json").read_text(encoding="utf-8"))
            self.assertEqual(verification["status"], "needs_manual_verification")
            self.assertEqual(verification["publish_summary"]["needs_manual_verification_count"], 1)
            self.assertEqual(verification["published_links"], [])
            self.assertEqual(verification["draft_records"], [])

    def test_record_publish_result_requires_verified_status_for_published_links(self):
        with project_tempdir() as tmpdir:
            tmp = Path(tmpdir)
            pack_dir = tmp / "publish_out" / "channel_packs" / "topic-demo" / "wechat_article"
            pack_dir.mkdir(parents=True)
            channel_pack = pack_dir / "channel_pack.json"
            write_json(
                channel_pack,
                {
                    "topic_id": "topic-demo",
                    "title": "未验真链接测试",
                    "channel": "wechat_article",
                    "platform": "wechat",
                    "status": "ready_for_execution",
                },
            )
            write_json(
                tmp / "publish_out" / "publish_manifest.json",
                {
                    "run_id": "run-hardening-publish-verified-required",
                    "stage": "publish",
                    "status": "pending_execution",
                    "channel_packs": [json.loads(channel_pack.read_text(encoding="utf-8"))],
                },
            )
            write_json(
                tmp / "publish_out" / "publish_verification_report.json",
                {"run_id": "run-hardening-publish-verified-required", "stage": "publish", "status": "pending_execution", "published_links": []},
            )

            result_proc = subprocess.run(
                [
                    PYTHON,
                    str(ROOT / "scripts/record_publish_result.py"),
                    "--channel-pack",
                    str(channel_pack),
                    "--success",
                    "true",
                    "--status",
                    "published",
                    "--platform",
                    "wechat",
                    "--platform-url",
                    "https://mp.weixin.qq.com/s/not-yet-verified",
                    "--verification-status",
                    "needs_manual_verification",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result_proc.returncode, 0, msg=result_proc.stderr)

            verification = json.loads((tmp / "publish_out" / "publish_verification_report.json").read_text(encoding="utf-8"))
            self.assertEqual(verification["status"], "needs_manual_verification")
            self.assertEqual(verification["publish_summary"]["published_count"], 0)
            self.assertEqual(verification["published_links"], [])

    def test_record_publish_result_does_not_auto_verify_published_url(self):
        with project_tempdir() as tmpdir:
            tmp = Path(tmpdir)
            pack_dir = tmp / "publish_out" / "channel_packs" / "topic-demo" / "wechat_article"
            pack_dir.mkdir(parents=True)
            channel_pack = pack_dir / "channel_pack.json"
            write_json(
                channel_pack,
                {
                    "topic_id": "topic-demo",
                    "title": "发布链接默认未验真测试",
                    "channel": "wechat_article",
                    "platform": "wechat",
                    "status": "ready_for_execution",
                },
            )
            write_json(
                tmp / "publish_out" / "publish_manifest.json",
                {
                    "run_id": "run-hardening-publish-no-auto-verify-url",
                    "stage": "publish",
                    "status": "pending_execution",
                    "channel_packs": [json.loads(channel_pack.read_text(encoding="utf-8"))],
                },
            )
            write_json(
                tmp / "publish_out" / "publish_verification_report.json",
                {"run_id": "run-hardening-publish-no-auto-verify-url", "stage": "publish", "status": "pending_execution", "published_links": []},
            )

            result_proc = subprocess.run(
                [
                    PYTHON,
                    str(ROOT / "scripts/record_publish_result.py"),
                    "--channel-pack",
                    str(channel_pack),
                    "--success",
                    "true",
                    "--status",
                    "published",
                    "--platform",
                    "wechat",
                    "--platform-url",
                    "https://mp.weixin.qq.com/s/has-url-but-not-verified",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result_proc.returncode, 0, msg=result_proc.stderr)

            verification = json.loads((tmp / "publish_out" / "publish_verification_report.json").read_text(encoding="utf-8"))
            self.assertEqual(verification["status"], "needs_manual_verification")
            self.assertEqual(verification["publish_summary"]["published_count"], 0)
            self.assertEqual(verification["publish_summary"]["needs_manual_verification_count"], 1)
            self.assertEqual(verification["published_links"], [])

    def test_record_publish_result_does_not_auto_verify_draft_id(self):
        with project_tempdir() as tmpdir:
            tmp = Path(tmpdir)
            pack_dir = tmp / "publish_out" / "channel_packs" / "topic-demo" / "wechat_article"
            pack_dir.mkdir(parents=True)
            channel_pack = pack_dir / "channel_pack.json"
            write_json(
                channel_pack,
                {
                    "topic_id": "topic-demo",
                    "title": "草稿 ID 默认未验真测试",
                    "channel": "wechat_article",
                    "platform": "wechat",
                    "status": "ready_for_execution",
                },
            )
            write_json(
                tmp / "publish_out" / "publish_manifest.json",
                {
                    "run_id": "run-hardening-publish-no-auto-verify-draft",
                    "stage": "publish",
                    "status": "pending_execution",
                    "channel_packs": [json.loads(channel_pack.read_text(encoding="utf-8"))],
                },
            )
            write_json(
                tmp / "publish_out" / "publish_verification_report.json",
                {"run_id": "run-hardening-publish-no-auto-verify-draft", "stage": "publish", "status": "pending_execution", "published_links": []},
            )

            result_proc = subprocess.run(
                [
                    PYTHON,
                    str(ROOT / "scripts/record_publish_result.py"),
                    "--channel-pack",
                    str(channel_pack),
                    "--success",
                    "true",
                    "--status",
                    "draft",
                    "--platform",
                    "wechat",
                    "--draft-id",
                    "draft_not_explicitly_verified",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result_proc.returncode, 0, msg=result_proc.stderr)

            verification = json.loads((tmp / "publish_out" / "publish_verification_report.json").read_text(encoding="utf-8"))
            self.assertEqual(verification["status"], "needs_manual_verification")
            self.assertEqual(verification["publish_summary"]["draft_count"], 0)
            self.assertEqual(verification["publish_summary"]["needs_manual_verification_count"], 1)
            self.assertEqual(verification["draft_records"], [])

    def test_record_publish_result_keeps_draft_url_out_of_published_links(self):
        with project_tempdir() as tmpdir:
            tmp = Path(tmpdir)
            pack_dir = tmp / "publish_out" / "channel_packs" / "topic-demo" / "wechat_article"
            pack_dir.mkdir(parents=True)
            channel_pack = pack_dir / "channel_pack.json"
            write_json(
                channel_pack,
                {
                    "topic_id": "topic-demo",
                    "title": "草稿链接隔离测试",
                    "channel": "wechat_article",
                    "platform": "wechat",
                    "status": "ready_for_execution",
                },
            )
            write_json(
                tmp / "publish_out" / "publish_manifest.json",
                {
                    "run_id": "run-hardening-publish-draft-url",
                    "stage": "publish",
                    "status": "pending_execution",
                    "channel_packs": [json.loads(channel_pack.read_text(encoding="utf-8"))],
                },
            )
            write_json(
                tmp / "publish_out" / "publish_verification_report.json",
                {"run_id": "run-hardening-publish-draft-url", "stage": "publish", "status": "pending_execution", "published_links": []},
            )

            result_proc = subprocess.run(
                [
                    PYTHON,
                    str(ROOT / "scripts/record_publish_result.py"),
                    "--channel-pack",
                    str(channel_pack),
                    "--success",
                    "true",
                    "--status",
                    "draft",
                    "--platform",
                    "wechat",
                    "--draft-id",
                    "draft_url_123",
                    "--draft-url",
                    "https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit&action=edit&type=10&appmsgid=draft_url_123",
                    "--verification-status",
                    "verified",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result_proc.returncode, 0, msg=result_proc.stderr)

            verification = json.loads((tmp / "publish_out" / "publish_verification_report.json").read_text(encoding="utf-8"))
            self.assertEqual(verification["status"], "all_drafted")
            self.assertEqual(verification["published_links"], [])
            self.assertEqual(verification["draft_records"][0]["draft_id"], "draft_url_123")
            self.assertIn("appmsg_edit", verification["draft_records"][0]["draft_url"])

    def test_postmortem_does_not_count_published_without_platform_url(self):
        with project_tempdir() as tmpdir:
            tmp = Path(tmpdir)
            write_json(
                tmp / "publish_manifest.json",
                {
                    "run_id": "run-hardening-postmortem-published-url",
                    "stage": "publish",
                    "status": "needs_manual_verification",
                    "channel_packs": [
                        {
                            "topic_id": "topic-demo",
                            "title": "复盘发布口径测试",
                            "channel": "wechat_article",
                        }
                    ],
                    "publish_results": [
                        {
                            "topic_id": "topic-demo",
                            "channel": "wechat_article",
                            "status": "published",
                            "success": True,
                            "verification_status": "needs_manual_verification",
                        }
                    ],
                },
            )

            postmortem_proc = subprocess.run(
                [
                    PYTHON,
                    str(ROOT / "scripts/postmortem_writeback.py"),
                    "--publish-manifest",
                    str(tmp / "publish_manifest.json"),
                    "--output-dir",
                    str(tmp / "postmortem_out"),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(postmortem_proc.returncode, 0, msg=postmortem_proc.stderr)
            postmortem = json.loads((tmp / "postmortem_out" / "postmortem_manifest.json").read_text(encoding="utf-8"))
            self.assertFalse(postmortem["topics"][0]["published"])
            self.assertEqual(postmortem["writeback"]["topic_pattern_library"]["published_topics"], 0)

    def test_postmortem_does_not_count_unverified_published_url(self):
        with project_tempdir() as tmpdir:
            tmp = Path(tmpdir)
            write_json(
                tmp / "publish_manifest.json",
                {
                    "run_id": "run-hardening-postmortem-published-verified",
                    "stage": "publish",
                    "status": "needs_manual_verification",
                    "channel_packs": [
                        {
                            "topic_id": "topic-demo",
                            "title": "复盘验真口径测试",
                            "channel": "wechat_article",
                        }
                    ],
                    "publish_results": [
                        {
                            "topic_id": "topic-demo",
                            "channel": "wechat_article",
                            "status": "published",
                            "success": True,
                            "platform_url": "https://mp.weixin.qq.com/s/not-verified",
                            "verification_status": "needs_manual_verification",
                        }
                    ],
                },
            )

            postmortem_proc = subprocess.run(
                [
                    PYTHON,
                    str(ROOT / "scripts/postmortem_writeback.py"),
                    "--publish-manifest",
                    str(tmp / "publish_manifest.json"),
                    "--output-dir",
                    str(tmp / "postmortem_out"),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(postmortem_proc.returncode, 0, msg=postmortem_proc.stderr)
            postmortem = json.loads((tmp / "postmortem_out" / "postmortem_manifest.json").read_text(encoding="utf-8"))
            self.assertFalse(postmortem["topics"][0]["published"])
            self.assertEqual(postmortem["writeback"]["topic_pattern_library"]["published_topics"], 0)

    def test_postmortem_does_not_count_draft_without_draft_id(self):
        with project_tempdir() as tmpdir:
            tmp = Path(tmpdir)
            write_json(
                tmp / "publish_manifest.json",
                {
                    "run_id": "run-hardening-postmortem-draft-id",
                    "stage": "publish",
                    "status": "needs_manual_verification",
                    "channel_packs": [
                        {
                            "topic_id": "topic-demo",
                            "title": "复盘草稿口径测试",
                            "channel": "wechat_article",
                        }
                    ],
                    "publish_results": [
                        {
                            "topic_id": "topic-demo",
                            "channel": "wechat_article",
                            "status": "draft",
                            "success": True,
                            "verification_status": "needs_manual_verification",
                        }
                    ],
                },
            )

            postmortem_proc = subprocess.run(
                [
                    PYTHON,
                    str(ROOT / "scripts/postmortem_writeback.py"),
                    "--publish-manifest",
                    str(tmp / "publish_manifest.json"),
                    "--output-dir",
                    str(tmp / "postmortem_out"),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(postmortem_proc.returncode, 0, msg=postmortem_proc.stderr)
            postmortem = json.loads((tmp / "postmortem_out" / "postmortem_manifest.json").read_text(encoding="utf-8"))
            self.assertFalse(postmortem["topics"][0]["drafted"])
            self.assertEqual(postmortem["writeback"]["topic_pattern_library"]["drafted_topics"], 0)

    def test_postmortem_does_not_count_unverified_draft_id(self):
        with project_tempdir() as tmpdir:
            tmp = Path(tmpdir)
            write_json(
                tmp / "publish_manifest.json",
                {
                    "run_id": "run-hardening-postmortem-draft-verified",
                    "stage": "publish",
                    "status": "needs_manual_verification",
                    "channel_packs": [
                        {
                            "topic_id": "topic-demo",
                            "title": "复盘草稿验真口径测试",
                            "channel": "wechat_article",
                        }
                    ],
                    "publish_results": [
                        {
                            "topic_id": "topic-demo",
                            "channel": "wechat_article",
                            "status": "draft",
                            "success": True,
                            "draft_id": "draft_not_verified",
                            "verification_status": "needs_manual_verification",
                        }
                    ],
                },
            )

            postmortem_proc = subprocess.run(
                [
                    PYTHON,
                    str(ROOT / "scripts/postmortem_writeback.py"),
                    "--publish-manifest",
                    str(tmp / "publish_manifest.json"),
                    "--output-dir",
                    str(tmp / "postmortem_out"),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(postmortem_proc.returncode, 0, msg=postmortem_proc.stderr)
            postmortem = json.loads((tmp / "postmortem_out" / "postmortem_manifest.json").read_text(encoding="utf-8"))
            self.assertFalse(postmortem["topics"][0]["drafted"])
            self.assertEqual(postmortem["writeback"]["topic_pattern_library"]["drafted_topics"], 0)

    def test_postmortem_ignores_legacy_wechat_article_url_without_verified_result(self):
        with project_tempdir() as tmpdir:
            tmp = Path(tmpdir)
            write_json(
                tmp / "publish_manifest.json",
                {
                    "run_id": "run-hardening-postmortem-legacy-wechat-url",
                    "stage": "publish",
                    "status": "pending_execution",
                    "channel_packs": [
                        {
                            "topic_id": "topic-demo",
                            "title": "旧公众号字段隔离测试",
                            "channel": "wechat_article",
                            "wechat_article_url": "https://mp.weixin.qq.com/s/legacy-url",
                        }
                    ],
                    "publish_results": [],
                },
            )

            postmortem_proc = subprocess.run(
                [
                    PYTHON,
                    str(ROOT / "scripts/postmortem_writeback.py"),
                    "--publish-manifest",
                    str(tmp / "publish_manifest.json"),
                    "--output-dir",
                    str(tmp / "postmortem_out"),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(postmortem_proc.returncode, 0, msg=postmortem_proc.stderr)
            postmortem = json.loads((tmp / "postmortem_out" / "postmortem_manifest.json").read_text(encoding="utf-8"))
            self.assertFalse(postmortem["topics"][0]["published"])
            self.assertEqual(postmortem["performance_metrics"], [])

    def test_postmortem_groups_multiple_channel_packs_by_topic_id(self):
        with project_tempdir() as tmpdir:
            tmp = Path(tmpdir)
            write_json(
                tmp / "publish_manifest.json",
                {
                    "run_id": "run-hardening-postmortem-topic-group",
                    "stage": "publish",
                    "status": "completed_with_mixed_status",
                    "channel_packs": [
                        {
                            "topic_id": "topic-demo",
                            "title": "复盘聚合测试",
                            "channel": "wechat_article",
                            "title_candidates": ["标题A"],
                        },
                        {
                            "topic_id": "topic-demo",
                            "title": "复盘聚合测试",
                            "channel": "xiaohongshu_video",
                            "cover_candidates": ["cover-a.png"],
                        },
                    ],
                    "publish_results": [
                        {
                            "topic_id": "topic-demo",
                            "channel": "wechat_article",
                            "status": "draft",
                            "success": True,
                            "draft_id": "draft_abc",
                            "verification_status": "verified",
                        },
                        {
                            "topic_id": "topic-demo",
                            "channel": "xiaohongshu_video",
                            "status": "published",
                            "success": True,
                            "platform_url": "https://www.xiaohongshu.com/explore/abc",
                            "verification_status": "verified",
                        },
                    ],
                },
            )

            postmortem_proc = subprocess.run(
                [
                    PYTHON,
                    str(ROOT / "scripts/postmortem_writeback.py"),
                    "--publish-manifest",
                    str(tmp / "publish_manifest.json"),
                    "--output-dir",
                    str(tmp / "postmortem_out"),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(postmortem_proc.returncode, 0, msg=postmortem_proc.stderr)
            postmortem = json.loads((tmp / "postmortem_out" / "postmortem_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(len(postmortem["topics"]), 1)
            self.assertEqual(postmortem["topics"][0]["selected_channels"], ["wechat_article", "xiaohongshu_video"])
            self.assertTrue(postmortem["topics"][0]["published"])
            self.assertTrue(postmortem["topics"][0]["drafted"])
            self.assertEqual(len(postmortem["topics"][0]["publish_results"]), 2)
            self.assertEqual(postmortem["topics"][0]["selected_title_count"], 1)
            self.assertEqual(postmortem["topics"][0]["selected_cover_count"], 1)
            self.assertEqual(postmortem["writeback"]["topic_pattern_library"]["published_topics"], 1)
            self.assertEqual(postmortem["writeback"]["topic_pattern_library"]["drafted_topics"], 1)

    def test_postmortem_includes_publish_guard_summary(self):
        with project_tempdir() as tmpdir:
            tmp = Path(tmpdir)
            guard_json = tmp / "publish_guard_report.json"
            guard_md = tmp / "publish_guard_report.md"
            guard_json.write_text("{}", encoding="utf-8")
            guard_md.write_text("# guard\n", encoding="utf-8")
            write_json(
                tmp / "publish_manifest.json",
                {
                    "run_id": "run-hardening-postmortem-guard",
                    "stage": "publish",
                    "status": "all_published",
                    "publish_guard": {
                        "status": "passed",
                        "passed": True,
                        "checked_at": "2026-06-14T12:00:00+08:00",
                        "report_json": str(guard_json),
                        "report_markdown": str(guard_md),
                        "will_not_publish": True,
                    },
                    "channel_packs": [
                        {
                            "topic_id": "topic-demo",
                            "title": "复盘 Guard 测试",
                            "channel": "xiaohongshu_video",
                        }
                    ],
                    "publish_results": [
                        {
                            "topic_id": "topic-demo",
                            "channel": "xiaohongshu_video",
                            "status": "published",
                            "success": True,
                            "platform_url": "https://www.xiaohongshu.com/explore/guard-postmortem",
                            "verification_status": "verified",
                        }
                    ],
                },
            )

            postmortem_proc = subprocess.run(
                [
                    PYTHON,
                    str(ROOT / "scripts/postmortem_writeback.py"),
                    "--publish-manifest",
                    str(tmp / "publish_manifest.json"),
                    "--output-dir",
                    str(tmp / "postmortem_out"),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(postmortem_proc.returncode, 0, msg=postmortem_proc.stderr)
            postmortem = json.loads((tmp / "postmortem_out" / "postmortem_manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(postmortem["publish_guard"]["present"])
            self.assertTrue(postmortem["publish_guard"]["passed"])
            self.assertEqual(postmortem["publish_guard"]["status"], "passed")
            self.assertTrue(postmortem["writeback"]["channel_pattern_library"]["publish_guard_passed"])
            report_text = (tmp / "postmortem_out" / "08_复盘报告.md").read_text(encoding="utf-8")
            self.assertIn("Publish Guard", report_text)
            self.assertIn("passed", report_text)

    def test_postmortem_marks_missing_publish_guard_without_breaking_counts(self):
        with project_tempdir() as tmpdir:
            tmp = Path(tmpdir)
            write_json(
                tmp / "publish_manifest.json",
                {
                    "run_id": "run-hardening-postmortem-guard-missing",
                    "stage": "publish",
                    "status": "all_drafted",
                    "channel_packs": [
                        {
                            "topic_id": "topic-demo",
                            "title": "复盘缺 Guard 测试",
                            "channel": "wechat_article",
                        }
                    ],
                    "publish_results": [
                        {
                            "topic_id": "topic-demo",
                            "channel": "wechat_article",
                            "status": "draft",
                            "success": True,
                            "draft_id": "draft_guard_missing",
                            "verification_status": "verified",
                        }
                    ],
                },
            )

            postmortem_proc = subprocess.run(
                [
                    PYTHON,
                    str(ROOT / "scripts/postmortem_writeback.py"),
                    "--publish-manifest",
                    str(tmp / "publish_manifest.json"),
                    "--output-dir",
                    str(tmp / "postmortem_out"),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(postmortem_proc.returncode, 0, msg=postmortem_proc.stderr)
            postmortem = json.loads((tmp / "postmortem_out" / "postmortem_manifest.json").read_text(encoding="utf-8"))
            self.assertFalse(postmortem["publish_guard"]["present"])
            self.assertEqual(postmortem["publish_guard"]["status"], "missing")
            self.assertTrue(postmortem["topics"][0]["drafted"])
            self.assertEqual(postmortem["writeback"]["topic_pattern_library"]["drafted_topics"], 1)
            report_text = (tmp / "postmortem_out" / "08_复盘报告.md").read_text(encoding="utf-8")
            self.assertIn("未发现 `publish_manifest.publish_guard`", report_text)

    def test_postmortem_require_publish_guard_rejects_missing_guard(self):
        with project_tempdir() as tmpdir:
            tmp = Path(tmpdir)
            write_json(
                tmp / "publish_manifest.json",
                {
                    "run_id": "run-hardening-postmortem-require-guard-missing",
                    "stage": "publish",
                    "status": "all_drafted",
                    "channel_packs": [{"topic_id": "topic-demo", "title": "缺 Guard 强制门测试", "channel": "wechat_article"}],
                    "publish_results": [
                        {
                            "topic_id": "topic-demo",
                            "channel": "wechat_article",
                            "status": "draft",
                            "success": True,
                            "draft_id": "draft_guard_required_missing",
                            "verification_status": "verified",
                        }
                    ],
                },
            )

            postmortem_proc = subprocess.run(
                [
                    PYTHON,
                    str(ROOT / "scripts/postmortem_writeback.py"),
                    "--publish-manifest",
                    str(tmp / "publish_manifest.json"),
                    "--require-publish-guard",
                    "--output-dir",
                    str(tmp / "postmortem_out"),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(postmortem_proc.returncode, 0)
            self.assertIn("publish_manifest.publish_guard 缺失", postmortem_proc.stderr)
            self.assertFalse((tmp / "postmortem_out" / "postmortem_manifest.json").exists())

    def test_postmortem_require_publish_guard_rejects_failed_guard(self):
        with project_tempdir() as tmpdir:
            tmp = Path(tmpdir)
            write_json(
                tmp / "publish_manifest.json",
                {
                    "run_id": "run-hardening-postmortem-require-guard-failed",
                    "stage": "publish",
                    "status": "needs_manual_verification",
                    "publish_guard": {
                        "status": "failed",
                        "passed": False,
                        "checked_at": "2026-06-14T12:00:00+08:00",
                        "report_json": str(tmp / "publish_guard_report.json"),
                        "report_markdown": str(tmp / "publish_guard_report.md"),
                    },
                    "channel_packs": [{"topic_id": "topic-demo", "title": "Guard 失败强制门测试", "channel": "xiaohongshu_video"}],
                    "publish_results": [
                        {
                            "topic_id": "topic-demo",
                            "channel": "xiaohongshu_video",
                            "status": "published",
                            "success": True,
                            "platform_url": "https://www.xiaohongshu.com/explore/guard-failed",
                            "verification_status": "needs_manual_verification",
                        }
                    ],
                },
            )

            postmortem_proc = subprocess.run(
                [
                    PYTHON,
                    str(ROOT / "scripts/postmortem_writeback.py"),
                    "--publish-manifest",
                    str(tmp / "publish_manifest.json"),
                    "--require-publish-guard",
                    "--output-dir",
                    str(tmp / "postmortem_out"),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(postmortem_proc.returncode, 0)
            self.assertIn("当前状态为 `failed`", postmortem_proc.stderr)
            self.assertFalse((tmp / "postmortem_out" / "postmortem_manifest.json").exists())

    def test_postmortem_require_publish_guard_rejects_missing_guard_report_files(self):
        with project_tempdir() as tmpdir:
            tmp = Path(tmpdir)
            write_json(
                tmp / "publish_manifest.json",
                {
                    "run_id": "run-hardening-postmortem-require-guard-missing-files",
                    "stage": "publish",
                    "status": "all_published",
                    "publish_guard": {
                        "status": "passed",
                        "passed": True,
                        "checked_at": "2026-06-14T12:00:00+08:00",
                        "report_json": str(tmp / "missing_publish_guard_report.json"),
                        "report_markdown": str(tmp / "missing_publish_guard_report.md"),
                    },
                    "channel_packs": [{"topic_id": "topic-demo", "title": "Guard 报告缺失强制门测试", "channel": "xiaohongshu_video"}],
                    "publish_results": [
                        {
                            "topic_id": "topic-demo",
                            "channel": "xiaohongshu_video",
                            "status": "published",
                            "success": True,
                            "platform_url": "https://www.xiaohongshu.com/explore/guard-missing-report-files",
                            "verification_status": "verified",
                        }
                    ],
                },
            )

            postmortem_proc = subprocess.run(
                [
                    PYTHON,
                    str(ROOT / "scripts/postmortem_writeback.py"),
                    "--publish-manifest",
                    str(tmp / "publish_manifest.json"),
                    "--require-publish-guard",
                    "--output-dir",
                    str(tmp / "postmortem_out"),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(postmortem_proc.returncode, 0)
            self.assertIn("Publish Guard 报告文件存在", postmortem_proc.stderr)
            self.assertFalse((tmp / "postmortem_out" / "postmortem_manifest.json").exists())

    def test_mainline_postmortem_require_publish_guard_passes_when_guard_passed(self):
        with project_tempdir() as tmpdir:
            tmp = Path(tmpdir)
            publish_root = tmp / "publish_out"
            publish_root.mkdir(parents=True)
            (publish_root / "publish_guard_report.json").write_text("{}", encoding="utf-8")
            (publish_root / "publish_guard_report.md").write_text("# guard\n", encoding="utf-8")
            write_json(
                publish_root / "publish_manifest.json",
                {
                    "run_id": "run-hardening-mainline-postmortem-guard",
                    "stage": "publish",
                    "status": "all_published",
                    "publish_guard": {
                        "status": "passed",
                        "passed": True,
                        "checked_at": "2026-06-14T12:00:00+08:00",
                        "report_json": str(publish_root / "publish_guard_report.json"),
                        "report_markdown": str(publish_root / "publish_guard_report.md"),
                    },
                    "channel_packs": [{"topic_id": "topic-demo", "title": "主入口 Guard 强制门测试", "channel": "xiaohongshu_video"}],
                    "publish_results": [
                        {
                            "topic_id": "topic-demo",
                            "channel": "xiaohongshu_video",
                            "status": "published",
                            "success": True,
                            "platform_url": "https://www.xiaohongshu.com/explore/guard-mainline",
                            "verification_status": "verified",
                        }
                    ],
                },
            )

            postmortem_proc = subprocess.run(
                [
                    PYTHON,
                    str(ROOT / "scripts/run_mainline_stage.py"),
                    "postmortem",
                    "--publish-manifest",
                    str(publish_root / "publish_manifest.json"),
                    "--require-publish-guard",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(postmortem_proc.returncode, 0, msg=postmortem_proc.stderr)
            postmortem_path = Path(postmortem_proc.stdout.strip())
            self.assertTrue(postmortem_path.exists())
            postmortem = json.loads(postmortem_path.read_text(encoding="utf-8"))
            self.assertTrue(postmortem["publish_guard"]["passed"])

    def test_open_publish_browser_dry_run_uses_persistent_profile(self):
        proc = subprocess.run(
            [
                PYTHON,
                str(ROOT / "scripts/open_publish_browser.py"),
                "xiaohongshu_video",
                "--dry-run",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["platform"], "xiaohongshu")
        self.assertIn("NewmaPublishProfiles/xiaohongshu", payload["profile_dir"])
        self.assertIn("--user-data-dir=", payload["command"])
        self.assertIn("open -g", payload["command"])
        self.assertIn("--window-size=", payload["command"])
        self.assertIn("--window-position=", payload["command"])
        self.assertTrue(payload["window"]["never_maximize"])

    def test_publish_blocks_completed_lane_when_final_artifact_missing(self):
        with project_tempdir() as tmpdir:
            tmp = Path(tmpdir)
            video_manifest = tmp / "talking_head_video_manifest.json"
            write_json(video_manifest, {"lane": "talking_head_video", "status": "completed"})
            write_json(
                tmp / "transwrite_manifest.json",
                {
                    "run_id": "run-hardening-publish-missing-artifact",
                    "stage": "transwrite",
                    "status": "prepared_for_skill_execution",
                    "topics": [
                        {
                            "topic_id": "topic-demo",
                            "title": "缺产物发布测试",
                            "lanes": {
                                "talking_head_video": {
                                    "status": "completed",
                                    "manifest": str(video_manifest),
                                    "final_video": str(tmp / "missing.mp4"),
                                },
                            },
                        }
                    ],
                },
            )
            write_json(
                tmp / "publish_decision.json",
                {
                    "run_id": "run-hardening-publish-missing-artifact",
                    "gate": "Channel Gate",
                    "status": "approved",
                    "topics": [{"topic_id": "topic-demo", "channels": ["douyin_video"]}],
                },
            )

            proc = subprocess.run(
                [
                    PYTHON,
                    str(ROOT / "scripts/build_stage5_publish.py"),
                    "--transwrite-manifest",
                    str(tmp / "transwrite_manifest.json"),
                    "--publish-decision",
                    str(tmp / "publish_decision.json"),
                    "--output-dir",
                    str(tmp / "publish_out"),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["channel_packs"][0]["status"], "blocked_or_waiting")
            self.assertEqual(payload["channel_packs"][0]["blocking_reason"], "missing_required_artifacts:video")

    def test_publish_supports_flat_rewrite_manifest_topics(self):
        with project_tempdir() as tmpdir:
            tmp = Path(tmpdir)
            rewrite_root = tmp / "rewrite_root"
            rewrite_root.mkdir(parents=True, exist_ok=True)
            hot_file = rewrite_root / "06_改写_示例_wechat_hot.md"
            normal_file = rewrite_root / "06_改写_示例_xiaohongshu_normal.md"
            hot_file.write_text("## 标题\n\n这是公众号热烈版。", encoding="utf-8")
            normal_file.write_text("## 标题\n\n这是小红书普通版。", encoding="utf-8")

            rewrite_manifest = {
                "run_id": "run-hardening-006",
                "stage": "rewrite",
                "output_root": str(rewrite_root),
                "topics": [
                    {
                        "topic_id": "topic-flat-1",
                        "title": "扁平改写测试",
                        "variants": [
                            {"variant": "wechat_luxun_hot", "file": str(hot_file)},
                            {"variant": "xhs_video_lemon_normal", "file": str(normal_file)},
                        ],
                    }
                ],
            }

            with load_script_module("publish_video_flat_test", ROOT / "scripts/publish_video_supplement.py") as module:
                topics = module.extract_rewrite_topic_sources(rewrite_manifest, rewrite_root)

            self.assertEqual(len(topics), 1)
            self.assertEqual(topics[0].topic_id, "topic-flat-1")
            self.assertEqual(topics[0].topic_name, "扁平改写测试")
            self.assertEqual(topics[0].rewrite_source.resolve(), normal_file.resolve())

    def test_publish_builds_channel_manifests_with_pending_execution_status(self):
        with project_tempdir() as tmpdir:
            tmp = Path(tmpdir)
            video_topic_dir = tmp / "video_supplement" / "topic_demo"
            (video_topic_dir / "videos" / "motion_narrative").mkdir(parents=True, exist_ok=True)
            (video_topic_dir / "videos" / "interactive_charts").mkdir(parents=True, exist_ok=True)
            (video_topic_dir / "videos" / "motion_narrative" / "demo.mp4").write_text("video", encoding="utf-8")
            topic_video_manifest = video_topic_dir / "topic_video_manifest.json"
            topic_video_manifest.write_text("{}", encoding="utf-8")

            rewrite_file = tmp / "wechat_hot.md"
            rewrite_file.write_text("## 标题\n\n正文", encoding="utf-8")
            xhs_file = tmp / "xhs_hot.md"
            xhs_file.write_text("## 标题\n\n视频正文", encoding="utf-8")

            rewrite_manifest = {
                "run_id": "run-hardening-008",
                "stage": "rewrite",
                "topics": [
                    {
                        "topic_id": "topic-demo",
                        "title": "发布阶段测试",
                        "variants": [
                            {"variant": "wechat_luxun_hot", "file": str(rewrite_file)},
                            {"variant": "xhs_video_luxun_hot", "file": str(xhs_file)},
                        ],
                    }
                ],
            }
            publish_decision = {
                "run_id": "run-hardening-008",
                "gate": "Channel Gate",
                "status": "ready",
                "topics": [
                    {
                        "topic_id": "topic-demo",
                        "topic_name": "发布阶段测试",
                        "channels": ["wechat_article", "xiaohongshu_video", "bilibili_video"],
                        "title_candidates": ["题目A", "题目B"],
                        "cover_candidates": ["cover-a.png"],
                        "publish_time": "2026-04-13T22:00:00+08:00",
                    }
                ],
            }
            topic_manifests = [
                {
                    "topic_id": "topic-demo",
                    "topic": "发布阶段测试",
                    "topic_prefix": "topic_demo",
                    "topic_video_manifest": str(topic_video_manifest),
                    "exports": {
                        "interactive_charts": {"ok": False},
                        "motion_narrative": {"ok": True},
                    },
                }
            ]

            with load_script_module("publish_stage_outputs_test", ROOT / "scripts/publish_video_supplement.py") as module:
                outputs = module.build_publish_stage_outputs(
                    run_id="run-hardening-008",
                    rewrite_manifest_path=tmp / "rewrite_manifest.json",
                    publish_decision_path=tmp / "publish_decision.json",
                    rewrite_manifest=rewrite_manifest,
                    publish_decision=publish_decision,
                    topic_manifests=topic_manifests,
                    video_supplement_manifest_path=tmp / "publish_video_supplement_manifest.json",
                    video_supplement_report_path=tmp / "publish_video_supplement_report.md",
                )

            adaptation = outputs["adaptation_manifest"]
            execution = outputs["execution_manifest"]
            verification = outputs["verification_report"]
            publish_manifest = outputs["publish_manifest"]

            self.assertEqual(adaptation["status"], "ready_for_execution")
            self.assertEqual(len(adaptation["topics"][0]["channel_packs"]), 3)
            self.assertEqual(execution["status"], "ready_for_channel_execution")
            self.assertEqual(
                [item["status"] for item in execution["executions"]],
                ["pending_user_confirmation", "pending_execution", "manual_only"],
            )
            self.assertEqual(verification["status"], "pending_execution")
            self.assertEqual(publish_manifest["status"], "pending_channel_execution")
            self.assertIsNone(publish_manifest["next_stage"])
            self.assertEqual(publish_manifest["channel_packs"][0]["channels"], ["wechat_article", "xiaohongshu_video", "bilibili_video"])
            self.assertIn("publish_skill_stack", publish_manifest)
            self.assertIn("wechat", publish_manifest["publish_skill_stack"])

    def test_publish_supports_draft_manifest_as_formal_input(self):
        with project_tempdir() as tmpdir:
            tmp = Path(tmpdir)
            draft_file = tmp / "03_标准初稿_topic-demo.md"
            draft_file.write_text("## 标题\n\n正文", encoding="utf-8")
            draft_manifest_path = tmp / "draft_manifest.json"
            draft_manifest = {
                "run_id": "run-hardening-draft-publish",
                "stage": "draft",
                "drafts": [
                    {
                        "topic_id": "topic-demo",
                        "title": "Draft 直发测试",
                        "draft_file": str(draft_file),
                    }
                ],
            }

            with load_script_module("publish_draft_input_test", ROOT / "scripts/publish_video_supplement.py") as module:
                publish_manifest, rewrite_root = module.build_draft_publish_manifest(draft_manifest, draft_manifest_path)
                topics = module.extract_rewrite_topic_sources(publish_manifest, rewrite_root)
                decision = {
                    "run_id": "run-hardening-draft-publish",
                    "gate": "Channel Gate",
                    "status": "ready",
                    "topics": [
                        {
                            "topic_id": "topic-demo",
                            "topic_name": "Draft 直发测试",
                            "channels": ["wechat_article"],
                        }
                    ],
                }
                outputs = module.build_publish_stage_outputs(
                    run_id="run-hardening-draft-publish",
                    rewrite_manifest_path=draft_manifest_path,
                    publish_decision_path=tmp / "publish_decision.json",
                    rewrite_manifest=publish_manifest,
                    publish_decision=decision,
                    topic_manifests=[
                        module.build_minimal_topic_manifest(topics[0], tmp / "video_supplement")
                    ],
                    video_supplement_manifest_path=tmp / "publish_video_supplement_manifest.json",
                    video_supplement_report_path=tmp / "publish_video_supplement_report.md",
                )

            self.assertEqual(topics[0].rewrite_source.resolve(), draft_file.resolve())
            channel_pack = outputs["adaptation_manifest"]["topics"][0]["channel_packs"][0]
            self.assertEqual(channel_pack["variant"], "draft_publish")
            self.assertEqual(Path(channel_pack["variant_file"]).resolve(), draft_file.resolve())
            self.assertNotIn("material_manifest", outputs["publish_manifest"])

    def test_publish_can_load_existing_topic_video_manifests(self):
        with project_tempdir() as tmpdir:
            tmp = Path(tmpdir)
            output_root = tmp / "video_supplement"
            topic_dir = output_root / "topic_demo"
            topic_dir.mkdir(parents=True, exist_ok=True)
            write_json(
                topic_dir / "topic_video_manifest.json",
                {
                    "topic_id": "topic-demo",
                    "topic": "测试题",
                    "exports": {},
                },
            )

            with load_script_module("publish_video_reuse_test", ROOT / "scripts/publish_video_supplement.py") as module:
                manifests = module.load_existing_topic_manifests(output_root)

            self.assertEqual(len(manifests), 1)
            self.assertEqual(manifests[0]["topic_id"], "topic-demo")
            self.assertEqual(manifests[0]["topic_video_manifest"], str(topic_dir / "topic_video_manifest.json"))

    def test_build_minimal_topic_manifest_sets_topic_video_manifest_path(self):
        with project_tempdir() as tmpdir:
            tmp = Path(tmpdir)
            rewrite_file = tmp / "rewrite.md"
            rewrite_file.write_text("## 一\n\n这是一段测试内容 123%。", encoding="utf-8")
            output_root = tmp / "out"

            with load_script_module("publish_build_topic_manifest_test", ROOT / "scripts/publish_video_supplement.py") as module:
                result = module.build_minimal_topic_manifest(
                    module.RewriteTopicSource(
                        topic_id="topic-demo",
                        topic_name="测试题",
                        topic_prefix="topic_demo",
                        rewrite_source=rewrite_file,
                    ),
                    output_root,
                )

            self.assertTrue(result["topic_video_manifest"].endswith("topic_video_manifest.json"))
            self.assertTrue(Path(result["topic_video_manifest"]).exists())

    def test_publish_autofill_default_channel_matrix(self):
        with project_tempdir() as tmpdir:
            tmp = Path(tmpdir)
            rewrite_manifest = {
                "run_id": "run-hardening-009",
                "topics": [
                    {
                        "topic_id": "topic-demo",
                        "title": "测试发布默认矩阵",
                        "variants": [
                            {"variant": "wechat_luxun_hot", "file": str(tmp / "wechat.md")},
                            {"variant": "xhs_video_luxun_hot", "file": str(tmp / "xhs.md")},
                        ],
                    }
                ],
            }
            publish_decision = {
                "run_id": "run-hardening-009",
                "gate": "Channel Gate",
                "status": "ready",
                "topics": [{"topic_id": "topic-demo"}],
            }

            with load_script_module("publish_autofill_test", ROOT / "scripts/publish_video_supplement.py") as module:
                filled, changed = module.autofill_publish_decision(
                    publish_decision=publish_decision,
                    rewrite_manifest=rewrite_manifest,
                )

            self.assertTrue(changed)
            row = filled["topics"][0]
            self.assertEqual(
                row["channels"],
                ["wechat_article", "weibo_post", "x_post", "xiaohongshu_video", "douyin_video", "bilibili_video"],
            )
            self.assertEqual(row["title_candidates"], ["测试发布默认矩阵"])
            self.assertNotIn("cover_candidates", row)
            self.assertEqual(row["editor_status"], "auto_filled_publish_defaults")

    def test_publish_autofill_extends_legacy_auto_default_channels(self):
        rewrite_manifest = {
            "run_id": "run-hardening-010",
            "topics": [
                {
                    "topic_id": "topic-demo",
                    "title": "测试旧默认路由升级",
                    "variants": [
                        {"variant": "wechat_luxun_hot", "file": "wechat.md"},
                        {"variant": "xhs_video_luxun_hot", "file": "xhs.md"},
                    ],
                }
            ],
        }
        publish_decision = {
            "run_id": "run-hardening-010",
            "gate": "Channel Gate",
            "status": "ready",
            "topics": [
                {
                    "topic_id": "topic-demo",
                    "topic_name": "测试旧默认路由升级",
                    "channels": ["wechat_article", "weibo_post", "x_post"],
                    "editor_status": "auto_filled_default",
                }
            ],
        }

        with load_script_module("publish_autofill_extend_test", ROOT / "scripts/publish_video_supplement.py") as module:
            filled, changed = module.autofill_publish_decision(
                publish_decision=publish_decision,
                rewrite_manifest=rewrite_manifest,
            )

        self.assertTrue(changed)
        self.assertEqual(
            filled["topics"][0]["channels"],
            ["wechat_article", "weibo_post", "x_post", "xiaohongshu_video", "douyin_video", "bilibili_video"],
        )

    def test_publish_supports_optional_zhihu_channel_rule(self):
        with load_script_module("publish_zhihu_rule_test", ROOT / "scripts/publish_video_supplement.py") as module:
            self.assertEqual(module.normalize_channel_name("zhihu"), "zhihu_post")
            self.assertEqual(module.CHANNEL_EXECUTION_RULES["zhihu_post"]["executor_skill"], "zhihu-post")

    def test_publish_execution_manifest_contains_callable_executor_invocations(self):
        with load_script_module("publish_executor_invocation_test", ROOT / "scripts/publish_video_supplement.py") as module:
            execution_manifest = module.build_channel_execution_manifest(
                run_id="run-hardening-executors",
                adaptation_manifest={
                    "topics": [
                        {
                            "topic_id": "topic-demo",
                            "topic_name": "执行器调用测试",
                            "channel_packs": [
                                {
                                    "channel": "wechat_article",
                                    "variant": "wechat_luxun_hot",
                                    "variant_file": "/tmp/demo-wechat.md",
                                    "executor_skill": "baoyu-post-to-wechat",
                                    "automation_level": "semi_automated",
                                    "mode": "draft_or_browser_confirm",
                                    "requires_video": False,
                                    "assets_ready": True,
                                    "helper_skills": ["wechat-public-cli", "publish-guard"],
                                },
                                {
                                    "channel": "xiaohongshu_video",
                                    "variant": "xhs_video_luxun_hot",
                                    "variant_file": "/tmp/demo-xhs.md",
                                    "executor_skill": "xiaohongshu-auto",
                                    "automation_level": "automated",
                                    "mode": "auto_publish",
                                    "requires_video": True,
                                    "assets_ready": True,
                                    "available_videos": ["/tmp/demo.mp4"],
                                    "helper_skills": ["xiaohongshu-ops", "publish-guard"],
                                },
                                {
                                    "channel": "zhihu_post",
                                    "variant": "wechat_luxun_hot",
                                    "variant_file": "/tmp/demo-zhihu.md",
                                    "executor_skill": "zhihu-post",
                                    "automation_level": "semi_automated",
                                    "mode": "browser_confirm",
                                    "requires_video": False,
                                    "assets_ready": True,
                                    "helper_skills": ["publish-guard"],
                                },
                            ],
                        }
                    ]
                },
            )

        executions = {item["channel"]: item for item in execution_manifest["executions"]}
        self.assertEqual(
            executions["wechat_article"]["helper_invocations"][0]["command"],
            ["wechat-public-cli", "wechat:draft", "--file", "/tmp/demo-wechat.md"],
        )
        self.assertEqual(
            executions["xiaohongshu_video"]["executor_invocation"]["command"],
            ["openclaw", "skill", "xiaohongshu-auto", "publish", "--title", "执行器调用测试", "--content-file", "/tmp/demo-xhs.md", "--video", "/tmp/demo.mp4"],
        )
        self.assertEqual(executions["zhihu_post"]["executor_invocation"]["type"], "browser_procedure")

if __name__ == "__main__":
    unittest.main()
