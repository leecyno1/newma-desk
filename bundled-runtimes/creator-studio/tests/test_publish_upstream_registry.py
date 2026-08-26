import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock


PROJECT_ROOT = Path(__file__).parent.parent
PYTHON = sys.executable


def test_publish_upstream_registry_contains_bridge_dependencies():
    registry_path = PROJECT_ROOT / "configs" / "publish" / "upstream_repos.json"
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    repos = {row["name"]: row for row in payload["repositories"]}

    assert repos["agent-skills-launch-pack"]["repo"] == "https://github.com/chenjin-cmd/agent-skills-launch-pack_.git"
    assert "dasheng-publish-operations-bridge" in repos["agent-skills-launch-pack"]["used_by_skills"]
    assert repos["all-in-one"]["repo"] == "https://github.com/cv-cat/All-IN-ONE.git"
    assert "dasheng-xhs-publish-bridge" in repos["all-in-one"]["used_by_skills"]
    assert repos["xhs-skills"]["repo"] == "https://github.com/cv-cat/XhsSkills.git"
    assert repos["spider-xhs"]["repo"] == "https://github.com/cv-cat/Spider_XHS.git"
    assert repos["xiaohongshu-mcp"]["repo"] == "https://github.com/xpzouying/xiaohongshu-mcp.git"
    assert "rednote-mcp" not in repos
    assert "x-cli" not in repos
    assert repos["xhs-downloader"]["repo"] == "https://github.com/JoeanAmier/XHS-Downloader.git"
    assert repos["social-auto-upload"]["repo"] == "https://github.com/dreammis/social-auto-upload.git"
    assert "social-auto-upload-bridge" in repos["social-auto-upload"]["used_by_skills"]
    assert repos["qianfan-sync"]["repo"] == "https://github.com/DevilJie/social-auto-upload-web-ui.git"
    assert repos["postbot"]["repo"] == "https://github.com/gitcoffee-os/postbot.git"
    assert repos["opencli"]["repo"] == "https://github.com/jackwener/OpenCLI.git"
    assert repos["biliup-rs"]["repo"] == "https://github.com/biliup/biliup-rs.git"
    assert "bilibili-upload-bridge" in repos["biliup-rs"]["used_by_skills"]
    assert repos["biliup-rs"]["lifecycle"] == "archived"

    for row in repos.values():
        assert row["version_locked"] is False

    reserve_registry = json.loads(
        (PROJECT_ROOT / "configs" / "external" / "reserved_projects.json").read_text(encoding="utf-8")
    )
    rejected = {row["name"] for row in reserve_registry["rejected"]}
    assert {"rednote-mcp", "x-cli"} <= rejected


def test_publish_account_registry_contains_slots_without_secrets():
    registry_path = PROJECT_ROOT / "configs" / "publish" / "account_registry.json"
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    serialized = json.dumps(payload, ensure_ascii=False).lower()

    assert set(payload["channels"]["xiaohongshu_video"]["slots"]) == {"slot-1", "slot-2"}
    assert set(payload["channels"]["douyin_video"]["slots"]) == {"slot-1", "slot-2"}
    assert set(payload["logical_accounts"]) == {"publisher-a", "publisher-b"}
    assert "app_secret" not in serialized
    assert "cookie_value" not in serialized
    assert payload["policy"]["store_cookies"] is False
    assert payload["channels"]["xiaohongshu_video"]["slots"]["slot-1"]["account_metadata"]["matrix_role"] == "primary"
    assert payload["channels"]["xiaohongshu_video"]["slots"]["slot-2"]["account_metadata"]["matrix_role"] == "secondary"
    assert payload["channels"]["douyin_video"]["slots"]["slot-1"]["network_policy"]["mode"] == "local"


def test_expand_publish_matrix_creates_independent_tasks_for_all_account_slots(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake mp4")
    matrix_path = tmp_path / "publish_matrix.json"
    write_json(
        matrix_path,
        {
            "schema_version": "1.0",
            "run_id": "run-matrix-test",
            "status": "approved",
            "defaults": {"publish_metadata": {"title": "矩阵发布测试", "tags": ["财经"]}},
            "items": [
                {
                    "topic_id": "topic-demo",
                    "variant_id": "main-video",
                    "artifact_overrides": {"video": "video.mp4"},
                    "targets": [
                        {"channel": "xiaohongshu_video", "account_slots": "all"},
                        {"channel": "douyin_video", "account_slots": ["slot-1"]},
                    ],
                }
            ],
        },
    )

    proc = subprocess.run(
        [PYTHON, str(PROJECT_ROOT / "scripts" / "expand_publish_matrix.py"), "--matrix", str(matrix_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["status"] == "approved"
    assert payload["summary"]["task_count"] == 3
    assert len({task["task_id"] for task in payload["tasks"]}) == 3
    xhs_tasks = [task for task in payload["tasks"] if task["channel"] == "xiaohongshu_video"]
    assert {task["account_slot"] for task in xhs_tasks} == {"slot-1", "slot-2"}
    assert {task["browser_profile_key"] for task in xhs_tasks} == {"xiaohongshu_video", "xiaohongshu_video_2"}
    assert all(task["artifact_overrides"]["video"] == str(video.resolve()) for task in payload["tasks"])


def test_expand_publish_matrix_blocks_unknown_account_slot(tmp_path):
    matrix_path = tmp_path / "publish_matrix.json"
    write_json(
        matrix_path,
        {
            "schema_version": "1.0",
            "run_id": "run-matrix-invalid-slot",
            "status": "approved",
            "items": [
                {
                    "topic_id": "topic-demo",
                    "targets": [
                        {"channel": "douyin_video", "account_slots": ["slot-9"]}
                    ],
                }
            ],
        },
    )

    proc = subprocess.run(
        [PYTHON, str(PROJECT_ROOT / "scripts" / "expand_publish_matrix.py"), "--matrix", str(matrix_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["status"] == "blocked"
    assert any("unknown_account_slot:douyin_video:slot-9" in error for error in payload["errors"])


def test_expand_publish_matrix_freezes_account_presets_with_deterministic_precedence(tmp_path):
    registry_path = tmp_path / "account_registry.json"
    write_json(
        registry_path,
        {
            "channels": {
                "xiaohongshu_video": {
                    "publish_presets": {
                        "tags": ["channel-tag"],
                        "platform_notes": {"channel_option": "channel"},
                    },
                    "slots": {
                        "slot-1": {
                            "label": "测试主账号",
                            "default": True,
                            "browser_profile": "xiaohongshu_video",
                            "auth_modes": ["social_auto_upload"],
                            "account_metadata": {
                                "group": "finance",
                                "matrix_role": "primary",
                                "owner_alias": "owner-a",
                                "operator_alias": "operator-a",
                            },
                            "publish_presets": {
                                "tags": ["account-tag"],
                                "platform_notes": {"account_option": "account"},
                            },
                            "network_policy": {"mode": "local", "proxy_profile": None},
                        }
                    },
                }
            }
        },
    )
    matrix_path = tmp_path / "publish_matrix.json"
    write_json(
        matrix_path,
        {
            "schema_version": "1.0",
            "run_id": "run-preset-inheritance",
            "status": "approved",
            "defaults": {
                "publish_metadata": {"title": "global-title", "visibility": "default"},
                "channels": {
                    "xiaohongshu_video": {
                        "publish_metadata": {
                            "visibility": "friends",
                            "platform_notes": {"matrix_channel_option": "matrix-channel"},
                        }
                    }
                },
            },
            "items": [
                {
                    "topic_id": "topic-demo",
                    "variant_id": "variant-a",
                    "publish_metadata": {
                        "summary": "variant-summary",
                        "platform_notes": {"variant_option": "variant"},
                    },
                    "targets": [
                        {
                            "channel": "xiaohongshu_video",
                            "account_slots": ["slot-1"],
                            "publish_metadata": {"title": "target-title"},
                            "platform_notes": {"target_option": "target"},
                        }
                    ],
                }
            ],
        },
    )

    proc = subprocess.run(
        [PYTHON, str(PROJECT_ROOT / "scripts" / "expand_publish_matrix.py"), "--matrix", str(matrix_path)],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "DASHENG_PUBLISH_ACCOUNT_REGISTRY": str(registry_path)},
    )

    assert proc.returncode == 0, proc.stderr
    task = json.loads(proc.stdout)["tasks"][0]
    assert task["publish_metadata"]["title"] == "target-title"
    assert task["publish_metadata"]["summary"] == "variant-summary"
    assert task["publish_metadata"]["visibility"] == "friends"
    assert task["publish_metadata"]["tags"] == ["account-tag"]
    assert task["publish_metadata"]["platform_notes"] == {
        "matrix_channel_option": "matrix-channel",
        "variant_option": "variant",
        "channel_option": "channel",
        "account_option": "account",
        "target_option": "target",
    }
    assert task["account_context"]["group"] == "finance"
    assert task["account_context"]["matrix_role"] == "primary"
    assert task["metadata_inheritance"]["final_snapshot_frozen"] is True


def test_publish_failure_classification_and_backoff_policy_are_conservative():
    scripts_dir = str(PROJECT_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    module = __import__("record_publish_result")

    assert module.classify_failure(
        {}, status="failed", success=False, error="HTTP 429 too many requests"
    ) == "rate_limit"
    rate_policy = module.retry_policy("rate_limit", attempt_number=2, override_seconds=None)
    assert rate_policy["retryable"] is True
    assert rate_policy["requires_user_action"] is False
    assert rate_policy["retry_after_seconds"] == 1800

    risk_policy = module.retry_policy("platform_risk", attempt_number=1, override_seconds=None)
    assert risk_policy["retryable"] is False
    assert risk_policy["requires_user_action"] is True
    assert risk_policy["required_action"] == "resolve_platform_risk_or_captcha"


def test_expand_publish_matrix_blocks_and_strips_sensitive_account_presets(tmp_path):
    registry_path = tmp_path / "account_registry.json"
    write_json(
        registry_path,
        {
            "channels": {
                "douyin_video": {
                    "slots": {
                        "slot-1": {
                            "default": True,
                            "publish_presets": {
                                "title": "safe-title",
                                "api_key": "must-not-leak",
                                "platform_notes": {"access_token": "also-must-not-leak"},
                            },
                        }
                    }
                }
            }
        },
    )
    matrix_path = tmp_path / "publish_matrix.json"
    write_json(
        matrix_path,
        {
            "schema_version": "1.0",
            "run_id": "run-sensitive-preset",
            "status": "approved",
            "items": [
                {
                    "topic_id": "topic-demo",
                    "targets": [{"channel": "douyin_video", "account_slots": ["slot-1"]}],
                }
            ],
        },
    )

    proc = subprocess.run(
        [PYTHON, str(PROJECT_ROOT / "scripts" / "expand_publish_matrix.py"), "--matrix", str(matrix_path)],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "DASHENG_PUBLISH_ACCOUNT_REGISTRY": str(registry_path)},
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    serialized = json.dumps(payload, ensure_ascii=False)
    assert payload["status"] == "blocked"
    assert payload["tasks"][0]["publish_metadata"]["title"] == "safe-title"
    assert "must-not-leak" not in serialized
    assert any(error.startswith("sensitive_publish_metadata:") for error in payload["errors"])


def test_stage5_matrix_tasks_keep_account_results_and_retries_independent(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake mp4")
    transwrite_manifest = tmp_path / "transwrite_manifest.json"
    publish_decision = tmp_path / "publish_decision.json"
    publish_root = tmp_path / "publish_out"
    write_json(
        transwrite_manifest,
        {
            "run_id": "run-matrix-stage5",
            "stage": "transwrite",
            "status": "completed",
            "topics": [
                {
                    "topic_id": "topic-demo",
                    "title": "矩阵发布测试",
                    "lanes": {
                        "talking_head_video": {
                            "status": "completed",
                            "final_video": str(video),
                        }
                    },
                }
            ],
        },
    )
    tasks = []
    for slot in ("slot-1", "slot-2"):
        tasks.append(
            {
                "task_id": f"topic-demo-main-video-xiaohongshu-video-{slot}",
                "batch_id": "batch-matrix-stage5",
                "topic_id": "topic-demo",
                "variant_id": "main-video",
                "channel": "xiaohongshu_video",
                "channels": ["xiaohongshu_video"],
                "account_slot": slot,
                "artifact_overrides": {"video": str(video)},
                "publish_metadata": {
                    "title": f"矩阵发布测试 {slot}",
                    "summary": "同平台多账号独立执行测试。",
                    "tags": ["财经"],
                },
            }
        )
    write_json(
        publish_decision,
        {
            "run_id": "run-matrix-stage5",
            "batch_id": "batch-matrix-stage5",
            "gate": "Channel Gate",
            "status": "approved",
            "topics": [{"topic_id": "topic-demo", "channels": ["xiaohongshu_video"]}],
            "tasks": tasks,
        },
    )

    build_proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts" / "build_stage5_publish.py"),
            "--transwrite-manifest",
            str(transwrite_manifest),
            "--publish-decision",
            str(publish_decision),
            "--output-dir",
            str(publish_root),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert build_proc.returncode == 0, build_proc.stderr
    built = json.loads(build_proc.stdout)
    assert len(built["channel_packs"]) == 2
    assert {pack["account_slot"] for pack in built["channel_packs"]} == {"slot-1", "slot-2"}
    assert len({pack["pack_manifest"] for pack in built["channel_packs"]}) == 2
    for pack in built["channel_packs"]:
        assert Path(pack["pack_manifest"]).parent.name == pack["task_id"]
        validation = json.loads(Path(pack["platform_form_validation_report"]).read_text(encoding="utf-8"))
        assert validation["task_id"] == pack["task_id"]
        assert validation["account_slot"] == pack["account_slot"]
        execution_request = json.loads(Path(pack["execution_request"]).read_text(encoding="utf-8"))
        assert execution_request["task_id"] == pack["task_id"]
        assert execution_request["variant_id"] == "main-video"
        assert execution_request["confirmation_scope"] == "task_or_campaign_authorization"
        interaction_policy = execution_request["authorized_interaction_policy"]
        assert interaction_policy["final_publish_click"] == "continue_without_reconfirming"
        assert interaction_policy["ordinary_platform_prompts"] == "auto_resolve_from_approved_publish_metadata"
        assert interaction_policy["synced_one_time_password"] == "fill_once_when_platform_account_and_time_match"
        assert interaction_policy["one_time_password_retention"] == "memory_only_never_log_or_persist"
        assert "graphical_captcha" in interaction_policy["hard_stop_challenges"]
        assert execution_request["fallback_policy"]["on_synced_one_time_password"].endswith("without_logging")
        assert execution_request["fallback_policy"]["on_graphical_or_slider_captcha"] == "stop_and_report_without_looping"

    payload_proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts" / "build_publish_payload.py"),
            "--channel-pack",
            built["channel_packs"][0]["pack_manifest"],
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert payload_proc.returncode == 0, payload_proc.stderr
    payload_report = json.loads(payload_proc.stdout)
    executor_payload = json.loads(Path(payload_report["publish_payload"]).read_text(encoding="utf-8"))
    assert executor_payload["task_id"] == built["channel_packs"][0]["task_id"]
    assert executor_payload["account_slot"] == built["channel_packs"][0]["account_slot"]

    packs_by_slot = {pack["account_slot"]: Path(pack["pack_manifest"]) for pack in built["channel_packs"]}

    def record(slot: str, *args: str) -> dict:
        proc = subprocess.run(
            [
                PYTHON,
                str(PROJECT_ROOT / "scripts" / "record_publish_result.py"),
                "--channel-pack",
                str(packs_by_slot[slot]),
                *args,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr
        return json.loads(proc.stdout)

    failed = record("slot-1", "--success", "false", "--error", "connection reset by peer")
    assert failed["attempt_number"] == 1
    assert failed["failure_category"] == "network"
    assert failed["retryable"] is True
    assert failed["requires_user_action"] is False
    assert failed["publish_retry_status"] == "scheduled_backoff"
    failed_retry = json.loads(Path(failed["publish_retry_request"]).read_text(encoding="utf-8"))
    assert failed_retry["automatic_execution"] is False
    assert failed_retry["requires_user_confirmation"] is True
    second = record(
        "slot-2",
        "--success",
        "true",
        "--status",
        "published",
        "--platform-url",
        "https://www.xiaohongshu.com/explore/slot-2",
        "--verification-status",
        "verified",
    )
    assert second["attempt_number"] == 1
    retried = record(
        "slot-1",
        "--success",
        "true",
        "--status",
        "published",
        "--platform-url",
        "https://www.xiaohongshu.com/explore/slot-1",
        "--verification-status",
        "verified",
    )
    assert retried["attempt_number"] == 2
    assert retried["publish_retry_status"] == "not_required_latest_attempt_succeeded"

    manifest = json.loads((publish_root / "publish_manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["publish_results"]) == 2
    assert {row["account_slot"] for row in manifest["publish_results"]} == {"slot-1", "slot-2"}
    assert manifest["publish_summary"]["status"] == "all_published"
    first_history = json.loads(Path(retried["publish_result_history"]).read_text(encoding="utf-8"))
    assert [attempt["status"] for attempt in first_history["attempts"]] == ["failed", "published"]
    assert first_history["attempts"][0]["failure_category"] == "network"
    assert first_history["attempts"][1]["retry_of_attempt_id"] == first_history["attempts"][0]["attempt_id"]

    guard_proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts" / "publish_guard.py"),
            "--publish-manifest",
            str(publish_root / "publish_manifest.json"),
            "--fail-on-error",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert guard_proc.returncode == 0, guard_proc.stderr
    guard = json.loads(guard_proc.stdout)
    assert guard["passed"] is True
    assert {row["account_slot"] for row in guard["channel_checks"]} == {"slot-1", "slot-2"}


def test_publish_account_center_initializes_external_session_link(tmp_path):
    upstream = tmp_path / "social-auto-upload"
    upstream.mkdir()
    (upstream / "cookies").mkdir()
    session_root = tmp_path / "sessions"
    proc = subprocess.run(
        [PYTHON, str(PROJECT_ROOT / "scripts" / "publish_accounts.py"), "--init", "--channel", "douyin_video"],
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "SOCIAL_AUTO_UPLOAD_ROOT": str(upstream),
            "DASHENG_PUBLISH_SESSION_ROOT": str(session_root),
        },
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["initialization"]["status"] == "secure_session_link_ready"
    assert (upstream / "cookies").is_symlink()
    assert (upstream / "cookies").resolve() == (session_root / "social-auto-upload" / "cookies").resolve()


def test_publish_account_center_delegates_auth_check_without_exposing_cookies(tmp_path):
    upstream = tmp_path / "social-auto-upload"
    upstream.mkdir()
    fake_sau = write_fake_sau(tmp_path)
    proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts" / "publish_accounts.py"),
            "--channel",
            "douyin_video",
            "--slot",
            "slot-1",
            "--check-auth",
        ],
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "SOCIAL_AUTO_UPLOAD_ROOT": str(upstream),
            "SOCIAL_AUTO_UPLOAD_CLI": str(fake_sau),
            "DASHENG_PUBLISH_SESSION_ROOT": str(tmp_path / "sessions"),
        },
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    auth = next(
        item for item in payload["accounts"][0]["auth"]
        if item["mode"] == "social_auto_upload"
    )
    assert auth["status"] == "valid"
    assert auth["cookie_contents_exposed"] is False
    assert payload["safety"]["does_not_publish"] is True
    assert payload["summary"]["cli_valid_count"] == 1


def test_stage5_registers_wechat_channels_video_with_guarded_social_route():
    scripts_dir = str(PROJECT_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    module = __import__("build_stage5_publish")

    assert module.CHANNEL_RULES["wechat_channels_video"]["source_lane"] == "talking_head_video"
    assert module.platform_for_channel("wechat_channels_video") == "wechat_channels"
    routes = module.generic_execution_routes(
        {"channel": "wechat_channels_video", "browser_profile": {"open_command": "open channels"}}
    )
    assert routes[0]["route"] == "qianfan-local-api"
    assert routes[1]["route"] == "social-auto-upload"
    assert routes[0]["type"] == "qianfan_local_api"
    assert routes[1]["type"] == "external_uploader_fallback"


def test_stage5_account_slot_selects_registered_browser_profile():
    scripts_dir = str(PROJECT_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    module = __import__("build_stage5_publish")

    assert module.browser_profile_key_for_account("xiaohongshu_video", "slot-2") == "xiaohongshu_video_2"
    assert module.browser_profile_key_for_account("douyin_video", "slot-2") == "douyin_video_2"
    assert module.account_slot_for_channel({"account_slot": "2号槽位"}, "douyin_video") == "slot-2"


def test_stage5_channel_pack_is_blocked_when_platform_form_validation_fails(tmp_path):
    scripts_dir = str(PROJECT_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    module = __import__("build_stage5_publish")
    video = tmp_path / "final.mp4"
    video.write_bytes(b"fake mp4")
    pack = {
        "topic_id": "topic-demo",
        "title": "B站表单校验测试",
        "channel": "bilibili_video",
        "source_lane": "talking_head_video",
        "lane_status": "completed",
        "lane_manifest": str(tmp_path / "video_manifest.json"),
        "status": "ready_for_execution",
        "blocking_reason": None,
        "missing_artifacts": [],
        "executor_skill": "manual_upload",
        "execution_mode": "manual_only",
        "artifact_hint": {"video": str(video)},
        "publish_metadata": {
            "title": "B站表单校验测试",
            "summary": "缺少分区时必须阻断。",
            "platform_notes": {},
        },
        "account_slot": "slot-1",
        "account_operations": None,
    }

    result = module.write_channel_pack_files(tmp_path, pack)

    assert result["status"] == "blocked_or_waiting"
    assert result["blocking_reason"] == "platform_form_validation_failed:missing_bilibili_tid"
    validation = json.loads(Path(result["platform_form_validation_report"]).read_text(encoding="utf-8"))
    assert validation["status"] == "blocked"


def test_check_publish_upstreams_lists_selected_repo_without_remote():
    proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts" / "check_publish_upstreams.py"),
            "--name",
            "social-auto-upload",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["check_remote"] is False
    assert payload["repositories"][0]["name"] == "social-auto-upload"
    assert payload["repositories"][0]["repo"] == "https://github.com/dreammis/social-auto-upload.git"


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sample_xhs_execution_request(tmp: Path) -> Path:
    video = tmp / "video.mp4"
    video.write_bytes(b"fake mp4")
    request = {
        "schema_version": "1.0",
        "topic_id": "topic-demo",
        "title": "小红书执行准备测试",
        "channel": "xiaohongshu_video",
        "platform": "xiaohongshu",
        "status": "ready_for_user_confirmation",
        "executor_skill": "dasheng-xhs-publish-bridge",
        "execution_mode": "api_first_with_browser_fallback",
        "inputs": {
            "artifacts": {"video": str(video)},
            "publish_metadata": {"title": "小红书执行准备测试", "tags": ["AI"]},
            "browser_profile": {"open_command": "python3 scripts/open_publish_browser.py xiaohongshu_video"},
        },
        "route_priority": [
            {"route": "all-in-one", "type": "api_first_cli"},
            {"route": "xhs-skills-spider-xhs", "type": "api_first_skill"},
            {"route": "xiaohongshu-mcp", "type": "mcp_fallback"},
            {"route": "rednote-mcp", "type": "mcp_fallback"},
            {
                "route": "browser-profile",
                "type": "browser_confirm_fallback",
                "open_command": "python3 scripts/open_publish_browser.py xiaohongshu_video",
            },
        ],
    }
    request_path = tmp / "execution_request.json"
    write_json(request_path, request)
    return request_path


def test_prepare_xhs_publish_execution_falls_back_to_browser_profile(tmp_path):
    request_path = sample_xhs_execution_request(tmp_path)
    env = {
        **os.environ,
        "ALL_IN_ONE_ROOT": str(tmp_path / "missing-all-in-one"),
        "XHS_SKILLS_ROOT": str(tmp_path / "missing-xhs-skills"),
        "SPIDER_XHS_ROOT": str(tmp_path / "missing-spider-xhs"),
        "XIAOHONGSHU_MCP_ROOT": str(tmp_path / "missing-xiaohongshu-mcp"),
        "REDNOTE_MCP_ROOT": str(tmp_path / "missing-rednote-mcp"),
        "PATH": "/usr/bin:/bin",
    }
    proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts" / "prepare_xhs_publish_execution.py"),
            "--execution-request",
            str(request_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["status"] == "ready_for_user_confirmation"
    assert payload["selected_route"] == "browser-profile"
    assert payload["will_not_publish"] is True
    assert payload["requires_user_confirmation"] is True
    assert payload["route_checks"][0]["reason"] == "missing_all_in_one"
    assert payload["route_checks"][1]["reason"] == "missing_xhs_skills_or_spider_xhs"


def test_prepare_xhs_publish_execution_prefers_all_in_one_when_root_exists(tmp_path):
    request_path = sample_xhs_execution_request(tmp_path)
    all_in_one_root = tmp_path / "All-IN-ONE"
    all_in_one_root.mkdir()
    env = {
        **os.environ,
        "ALL_IN_ONE_ROOT": str(all_in_one_root),
        "PATH": "/usr/bin:/bin",
    }
    output_path = tmp_path / "xhs_execution_plan.json"
    proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts" / "prepare_xhs_publish_execution.py"),
            "--execution-request",
            str(request_path),
            "--output",
            str(output_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["selected_route"] == "all-in-one"
    assert payload["route_checks"][0]["reason"] == "upstream_root_found"
    assert any("aione xhs creator post-note" in command for command in payload["prepared_commands"])
    assert payload["confirmed_executor_command"] is None
    assert payload["confirm_execute_supported"] is False
    assert output_path.exists()


def sample_execution_request(tmp: Path, *, channel: str, platform: str, routes: list[dict]) -> Path:
    request = {
        "schema_version": "1.0",
        "topic_id": "topic-demo",
        "title": f"{channel} 执行准备测试",
        "channel": channel,
        "platform": platform,
        "status": "ready_for_user_confirmation",
        "executor_skill": routes[0]["route"],
        "execution_mode": routes[0].get("type"),
        "requires_user_confirmation": True,
        "channel_pack": str(tmp / "channel_pack.json"),
        "inputs": {
            "artifacts": {},
            "publish_metadata": {"title": f"{channel} 执行准备测试"},
            "browser_profile": {"open_command": f"python3 scripts/open_publish_browser.py {channel}"},
        },
        "route_priority": routes,
    }
    request_path = tmp / f"{channel}_execution_request.json"
    write_json(request_path, request)
    return request_path


def test_prepare_publish_execution_selects_local_wechat_skill(tmp_path):
    request_path = sample_execution_request(
        tmp_path,
        channel="wechat_article",
        platform="wechat",
        routes=[
            {"route": "baoyu-post-to-wechat", "type": "skill_draft_push"},
            {"route": "browser-profile", "type": "browser_confirm_fallback", "open_command": "python3 scripts/open_publish_browser.py wechat_article"},
        ],
    )
    proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts" / "prepare_publish_execution.py"),
            "--execution-request",
            str(request_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["platform"] == "wechat"
    assert payload["selected_route"] == "baoyu-post-to-wechat"
    assert payload["will_not_publish"] is True
    assert any("build_publish_payload.py" in command for command in payload["prepared_commands"])
    assert "execute_publish_request.py" in payload["safe_executor_command"]
    assert "--confirm-execute" not in payload["safe_executor_command"]
    assert "--confirm-execute" in payload["confirmed_executor_command"]


def test_prepare_publish_execution_douyin_falls_back_to_browser_when_skill_missing(tmp_path):
    request_path = sample_execution_request(
        tmp_path,
        channel="douyin_video",
        platform="douyin",
        routes=[
            {"route": "douyin-upload-skill", "type": "skill_or_api_upload"},
            {"route": "browser-profile", "type": "browser_confirm_fallback", "open_command": "python3 scripts/open_publish_browser.py douyin_video"},
        ],
    )
    proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts" / "prepare_publish_execution.py"),
            "--execution-request",
            str(request_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["platform"] == "douyin"
    assert payload["selected_route"] == "browser-profile"
    assert payload["requires_user_confirmation"] is True


def test_prepare_publish_execution_bilibili_falls_back_to_manual_package(tmp_path):
    channel_pack = tmp_path / "channel_pack.json"
    write_json(channel_pack, {"channel": "bilibili_video"})
    request_path = sample_execution_request(
        tmp_path,
        channel="bilibili_video",
        platform="bilibili",
        routes=[
            {"route": "biliup-rs", "type": "external_cli"},
            {"route": "manual-package", "type": "manual_package"},
        ],
    )
    proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts" / "prepare_publish_execution.py"),
            "--execution-request",
            str(request_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "BILIUP_RS_ROOT": str(tmp_path / "missing-biliup"), "PATH": "/usr/bin:/bin"},
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["platform"] == "bilibili"
    assert payload["selected_route"] == "manual-package"
    assert payload["prepared_commands"] == ["open channel_pack directory and upload manually"]
    assert payload["confirmed_executor_command"] is None
    assert payload["confirm_execute_supported"] is False


def sample_video_channel_pack(tmp: Path, *, channel: str = "bilibili_video") -> Path:
    video = tmp / "final.mp4"
    subtitle = tmp / "final.srt"
    cover = tmp / "cover.jpg"
    video.write_bytes(b"fake mp4")
    subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\n测试\n", encoding="utf-8")
    cover.write_bytes(b"fake jpg")
    platform_notes = {"tid": 188} if channel == "bilibili_video" else {}
    pack = {
        "topic_id": "topic-demo",
        "title": "视频上传包测试",
        "channel": channel,
        "status": "ready_for_execution",
        "artifact_hint": {"video": str(video), "video_srt": str(subtitle)},
        "publish_metadata": {
            "title": "视频上传包测试",
            "summary": "用于验证外部上传器配置生成。",
            "tags": ["AI", "财经"],
            "cover": str(cover),
            "platform_notes": platform_notes,
        },
    }
    pack_path = tmp / "channel_pack.json"
    write_json(pack_path, pack)
    return pack_path


def test_platform_form_validator_blocks_bilibili_without_tid(tmp_path):
    pack_path = sample_video_channel_pack(tmp_path, channel="bilibili_video")
    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    pack["publish_metadata"]["platform_notes"] = {}
    write_json(pack_path, pack)

    proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts" / "validate_publish_form.py"),
            "--channel-pack",
            str(pack_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["status"] == "blocked"
    assert "missing_bilibili_tid" in {item["code"] for item in payload["blocking_errors"]}
    assert payload["safety"]["does_not_publish"] is True


def test_platform_form_validator_warns_without_blocking_long_xhs_title(tmp_path):
    pack_path = sample_video_channel_pack(tmp_path, channel="xiaohongshu_video")
    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    pack["publish_metadata"]["title"] = "这是一个用于验证平台长度告警但不应该阻断发布任务的很长标题"
    write_json(pack_path, pack)

    proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts" / "validate_publish_form.py"),
            "--channel-pack",
            str(pack_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["status"] == "passed"
    assert "title_may_exceed_platform_limit" in {item["code"] for item in payload["warnings"]}


def write_fake_sau(tmp: Path, *, auth_ok: bool = True, upload_ok: bool = True) -> Path:
    cli = tmp / "fake-sau"
    cli.write_text(
        "#!/bin/sh\n"
        "if [ \"$2\" = \"check\" ]; then\n"
        f"  echo {'valid' if auth_ok else 'invalid'}\n"
        f"  exit {0 if auth_ok else 1}\n"
        "fi\n"
        f"echo {'upload submitted' if upload_ok else 'upload failed'}\n"
        f"exit {0 if upload_ok else 2}\n",
        encoding="utf-8",
    )
    cli.chmod(0o755)
    return cli


def test_build_video_upload_package_creates_bilibili_and_social_payloads(tmp_path):
    pack_path = sample_video_channel_pack(tmp_path, channel="bilibili_video")
    proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts" / "build_video_upload_package.py"),
            "--channel-pack",
            str(pack_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["status"] == "ready"
    assert Path(payload["outputs"]["platform_form_validation"]).exists()
    social_path = Path(payload["outputs"]["social_auto_upload_request"])
    bili_path = Path(payload["outputs"]["bilibili_submission"])
    assert social_path.exists()
    assert bili_path.exists()

    social = json.loads(social_path.read_text(encoding="utf-8"))
    bili = json.loads(bili_path.read_text(encoding="utf-8"))
    assert social["platform"] == "bilibili"
    assert social["upload"]["auto_publish"] is False
    assert bili["submission"]["title"] == "视频上传包测试"
    assert bili["submission"]["video"].endswith("final.mp4")


def test_build_video_upload_package_supports_wechat_channels_and_account_slot(tmp_path):
    pack_path = sample_video_channel_pack(tmp_path, channel="wechat_channels_video")
    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    pack["publish_metadata"]["scheduled_at"] = "2026-07-21T18:30:00+08:00"
    pack["publish_metadata"]["platform_notes"] = {
        "account_slot": "2号槽位",
        "short_title": "熔断与芯片",
        "draft": True,
    }
    write_json(pack_path, pack)

    proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts" / "build_video_upload_package.py"),
            "--channel-pack",
            str(pack_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    request = json.loads(Path(report["outputs"]["social_auto_upload_request"]).read_text(encoding="utf-8"))
    assert request["platform"] == "wechat_channels"
    assert request["upload"]["account_name"] == "slot-2"
    assert request["upload"]["scheduled_at"] == "2026-07-21 18:30"
    assert request["upload"]["platform_options"]["draft"] is True


def test_execute_social_auto_upload_dry_run_builds_guarded_tencent_command(tmp_path):
    pack_path = sample_video_channel_pack(tmp_path, channel="wechat_channels_video")
    social_root = tmp_path / "social-auto-upload"
    social_root.mkdir()
    fake_sau = write_fake_sau(tmp_path)
    proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts" / "execute_social_auto_upload.py"),
            "--channel-pack",
            str(pack_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "SOCIAL_AUTO_UPLOAD_ROOT": str(social_root),
            "SOCIAL_AUTO_UPLOAD_CLI": str(fake_sau),
        },
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["status"] == "ready_for_user_confirmation"
    assert payload["will_not_publish"] is True
    assert " tencent upload-video " in payload["upload_command"]
    assert "--account slot-1" in payload["upload_command"]
    assert "--headed" in payload["upload_command"]


def test_execute_social_auto_upload_confirm_runs_auth_and_leaves_verification_pending(tmp_path):
    pack_path = sample_video_channel_pack(tmp_path, channel="douyin_video")
    social_root = tmp_path / "social-auto-upload"
    social_root.mkdir()
    fake_sau = write_fake_sau(tmp_path)
    proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts" / "execute_social_auto_upload.py"),
            "--channel-pack",
            str(pack_path),
            "--confirm-execute",
        ],
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "SOCIAL_AUTO_UPLOAD_ROOT": str(social_root),
            "SOCIAL_AUTO_UPLOAD_CLI": str(fake_sau),
        },
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["success"] is True
    assert payload["status"] == "pending_verification"
    assert payload["verification_status"] == "needs_manual_verification"
    assert payload["platform_response"]["auth_check"]["stdout"] == "valid"
    assert payload["platform_response"]["upload"]["stdout"] == "upload submitted"


def test_build_publish_payload_creates_wechat_executor_payload(tmp_path):
    html = tmp_path / "wechat.html"
    html.write_text("<html><body>正文</body></html>", encoding="utf-8")
    pack_path = tmp_path / "channel_pack.json"
    write_json(
        pack_path,
        {
            "topic_id": "topic-demo",
            "title": "公众号 payload 测试",
            "channel": "wechat_article",
            "executor_skill": "baoyu-post-to-wechat",
            "artifact_hint": {"wechat_html": str(html)},
            "publish_metadata": {"title": "公众号 payload 测试", "summary": "摘要"},
        },
    )
    proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts" / "build_publish_payload.py"),
            "--channel-pack",
            str(pack_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    payload_path = Path(report["publish_payload"])
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    assert report["status"] == "ready_for_executor"
    assert payload["will_not_publish"] is True
    assert payload["payload"]["skill"] == "baoyu-post-to-wechat"
    assert payload["payload"]["content_html"] == str(html.resolve())
    assert payload["payload"]["result_writeback"]["command"] == "python3 scripts/record_publish_result.py"
    assert payload["platform_form_validation"]["status"] == "passed"
    assert Path(report["platform_form_validation"]).exists()


def test_build_publish_payload_creates_video_executor_payload(tmp_path):
    pack_path = sample_video_channel_pack(tmp_path, channel="douyin_video")
    proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts" / "build_publish_payload.py"),
            "--channel-pack",
            str(pack_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    payload = json.loads(Path(report["publish_payload"]).read_text(encoding="utf-8"))
    assert payload["status"] == "ready_for_executor"
    assert payload["payload"]["channel"] == "douyin_video"
    assert payload["payload"]["video"].endswith("final.mp4")
    assert payload["payload"]["auto_publish"] is False


def test_prepare_publish_execution_social_auto_upload_commands_include_converter(tmp_path):
    pack_path = sample_video_channel_pack(tmp_path, channel="douyin_video")
    social_root = tmp_path / "social-auto-upload"
    social_root.mkdir()
    fake_sau = write_fake_sau(tmp_path)
    request_path = sample_execution_request(
        tmp_path,
        channel="douyin_video",
        platform="douyin",
        routes=[
            {"route": "social-auto-upload", "type": "external_uploader_fallback"},
            {"route": "manual-package", "type": "manual_package"},
        ],
    )
    request = json.loads(request_path.read_text(encoding="utf-8"))
    request["channel_pack"] = str(pack_path)
    write_json(request_path, request)
    proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts" / "prepare_publish_execution.py"),
            "--execution-request",
            str(request_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "SOCIAL_AUTO_UPLOAD_ROOT": str(social_root),
            "SOCIAL_AUTO_UPLOAD_CLI": str(fake_sau),
            "PATH": "/usr/bin:/bin",
        },
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["selected_route"] == "social-auto-upload"
    assert any("build_video_upload_package.py" in command for command in payload["prepared_commands"])
    assert any("execute_social_auto_upload.py" in command for command in payload["prepared_commands"])
    assert payload["confirmed_executor_command"].endswith("--confirm-execute")
    assert payload["confirm_execute_supported"] is True


def test_publish_doctor_checks_selected_channels_without_publishing(tmp_path):
    output_json = tmp_path / "publish_doctor.json"
    output_md = tmp_path / "publish_doctor.md"
    proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts" / "publish_doctor.py"),
            "--channel",
            "wechat_article,douyin_video",
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
        ],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "SOCIAL_AUTO_UPLOAD_ROOT": str(tmp_path / "missing-social-auto-upload"), "PATH": "/usr/bin:/bin"},
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["mode"] == "publish_doctor"
    assert payload["will_not_publish"] is True
    assert payload["safety"]["does_not_read_cookies"] is True
    assert payload["safety"]["does_not_open_browser"] is True
    assert {channel["channel"] for channel in payload["channels"]} == {"wechat_article", "douyin_video"}
    assert output_json.exists()
    assert output_md.exists()
    assert "不触发真实发布" in output_md.read_text(encoding="utf-8")


def test_publish_doctor_supports_wechat_channels_as_first_class_channel(tmp_path):
    social_root = tmp_path / "social-auto-upload"
    social_root.mkdir()
    fake_sau = write_fake_sau(tmp_path)
    proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts" / "publish_doctor.py"),
            "--channel",
            "wechat_channels_video",
        ],
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "SOCIAL_AUTO_UPLOAD_ROOT": str(social_root),
            "SOCIAL_AUTO_UPLOAD_CLI": str(fake_sau),
            "PATH": "/usr/bin:/bin",
        },
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    channel = payload["channels"][0]
    assert channel["channel"] == "wechat_channels_video"
    assert channel["platform"] == "wechat_channels"
    assert channel["selected_route"] == "social-auto-upload"
    assert channel["confirm_execute_supported"] is True
    assert "wechat_channels_video" in channel["available_browser_profiles"]


def test_publish_doctor_deep_auth_blocks_invalid_default_cli_account(tmp_path):
    social_root = tmp_path / "social-auto-upload"
    social_root.mkdir()
    fake_sau = write_fake_sau(tmp_path, auth_ok=False)
    proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts" / "publish_doctor.py"),
            "--channel",
            "douyin_video",
            "--check-auth",
        ],
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "SOCIAL_AUTO_UPLOAD_ROOT": str(social_root),
            "SOCIAL_AUTO_UPLOAD_CLI": str(fake_sau),
            "DASHENG_PUBLISH_SESSION_ROOT": str(tmp_path / "sessions"),
            "PATH": "/usr/bin:/bin",
        },
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    channel = payload["channels"][0]
    assert channel["status"] == "blocked_auth_required"
    assert channel["selected_account_slot"] == "slot-1"
    assert channel["selected_account_auth_status"] == "invalid"
    assert channel["confirm_execute_supported"] is False
    assert payload["summary"]["blocked_count"] == 1


def test_publish_doctor_xhs_reports_api_first_missing_dependencies(tmp_path):
    proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts" / "publish_doctor.py"),
            "--channel",
            "xiaohongshu_video",
        ],
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "ALL_IN_ONE_ROOT": str(tmp_path / "missing-all-in-one"),
            "XHS_SKILLS_ROOT": str(tmp_path / "missing-xhs-skills"),
            "SPIDER_XHS_ROOT": str(tmp_path / "missing-spider-xhs"),
                "XIAOHONGSHU_MCP_ROOT": str(tmp_path / "missing-xiaohongshu-mcp"),
                "REDNOTE_MCP_ROOT": str(tmp_path / "missing-rednote-mcp"),
                "SOCIAL_AUTO_UPLOAD_ROOT": str(tmp_path / "missing-social-auto-upload"),
                "PATH": "/usr/bin:/bin",
            },
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    route_reasons = {check["route"]: check["reason"] for check in payload["channels"][0]["route_checks"]}
    assert route_reasons["all-in-one"] == "missing_all_in_one"
    assert route_reasons["xhs-skills-spider-xhs"] == "missing_xhs_skills_or_spider_xhs"
    assert route_reasons["xiaohongshu-mcp"] == "missing_xiaohongshu_mcp_root"
    assert route_reasons["rednote-mcp"] == "missing_rednote_mcp_root"
    assert payload["channels"][0]["selected_route"] == "browser-profile"


def test_publish_doctor_lists_multiple_browser_profiles_for_platform(tmp_path):
    proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts" / "publish_doctor.py"),
            "--channel",
            "xiaohongshu_video",
        ],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PATH": "/usr/bin:/bin"},
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    channel = payload["channels"][0]
    assert "xiaohongshu_video" in channel["available_browser_profiles"]
    assert "xiaohongshu_video_2" in channel["available_browser_profiles"]
    assert channel["browser_profile"]["profile_key"] == "xiaohongshu_video"


def test_mainline_doctor_publish_routes_to_publish_doctor(tmp_path):
    output_md = tmp_path / "publish_doctor.md"
    proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts" / "run_mainline_stage.py"),
            "doctor",
            "--publish",
            "--channel",
            "bilibili_video",
            "--output-md",
            str(output_md),
        ],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "BILIUP_RS_ROOT": str(tmp_path / "missing-biliup-rs"), "PATH": "/usr/bin:/bin"},
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["mode"] == "publish_doctor"
    assert payload["channels"][0]["channel"] == "bilibili_video"
    assert payload["channels"][0]["will_not_publish"] is True
    assert output_md.exists()


def test_publish_contract_docs_include_guard_and_strict_postmortem_terms():
    stage_contract = (PROJECT_ROOT / "skills" / "dasheng-media-sop" / "references" / "stage-contract.md").read_text(encoding="utf-8")
    api_reference = (PROJECT_ROOT / "docs" / "API_REFERENCE.md").read_text(encoding="utf-8")

    for required in [
        "publish_guard_report.json",
        "publish_manifest.publish_guard",
        "draft_url",
        "platform_url",
        "--require-publish-guard",
    ]:
        assert required in stage_contract
        assert required in api_reference

    assert "--verification-status verified" in api_reference


def sample_publish_manifest_for_guard(tmp: Path, *, verified: bool = True) -> Path:
    publish_root = tmp / "publish_out"
    publish_root.mkdir(parents=True, exist_ok=True)
    wechat_result_file = publish_root / "channel_packs" / "topic-demo" / "wechat_article" / "publish_result.json"
    xhs_result_file = publish_root / "channel_packs" / "topic-demo" / "xiaohongshu_video" / "publish_result.json"
    wechat_pack = {
        "topic_id": "topic-demo",
        "title": "批次验收测试",
        "channel": "wechat_article",
        "platform": "wechat",
        "status": "ready_for_execution",
    }
    xhs_pack = {
        "topic_id": "topic-demo",
        "title": "批次验收测试",
        "channel": "xiaohongshu_video",
        "platform": "xiaohongshu",
        "status": "ready_for_execution",
    }
    results = [
        {
            "topic_id": "topic-demo",
            "title": "批次验收测试",
            "channel": "wechat_article",
            "platform": "wechat",
            "success": True,
            "status": "draft",
            "draft_id": "draft_guard_001",
            "draft_url": "https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit&appmsgid=draft_guard_001",
            "verification_status": "verified",
            "result_file": str(wechat_result_file),
        },
        {
            "topic_id": "topic-demo",
            "title": "批次验收测试",
            "channel": "xiaohongshu_video",
            "platform": "xiaohongshu",
            "success": True,
            "status": "published",
            "platform_url": "https://www.xiaohongshu.com/explore/guard001",
            "verification_status": "verified" if verified else "needs_manual_verification",
            "result_file": str(xhs_result_file),
        },
    ]
    manifest = {
        "run_id": "run-publish-guard",
        "stage": "publish",
        "status": "completed_with_mixed_status" if verified else "needs_manual_verification",
        "channel_packs": [wechat_pack, xhs_pack],
        "publish_results": results,
        "publish_summary": {
            "status": "completed_with_mixed_status" if verified else "needs_manual_verification",
            "total_channels": 2,
            "recorded_count": 2,
            "pending_count": 0,
            "failed_count": 0,
            "draft_count": 1,
            "published_count": 1 if verified else 0,
            "verified_count": 2 if verified else 1,
            "needs_manual_verification_count": 0 if verified else 1,
            "pending_channels": [],
        },
    }
    verification_report = {
        "run_id": "run-publish-guard",
        "stage": "publish",
        "status": manifest["status"],
        "records": results,
        "publish_summary": manifest["publish_summary"],
        "published_links": [
            {
                "topic_id": "topic-demo",
                "channel": "xiaohongshu_video",
                "platform": "xiaohongshu",
                "url": "https://www.xiaohongshu.com/explore/guard001",
                "status": "published",
            }
        ]
        if verified
        else [],
        "draft_records": [
            {
                "topic_id": "topic-demo",
                "channel": "wechat_article",
                "platform": "wechat",
                "draft_id": "draft_guard_001",
                "draft_url": "https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit&appmsgid=draft_guard_001",
                "status": "draft",
            }
        ],
    }
    wechat_result_file.parent.mkdir(parents=True, exist_ok=True)
    xhs_result_file.parent.mkdir(parents=True, exist_ok=True)
    write_json(
        wechat_result_file,
        {
            "topic_id": "topic-demo",
            "title": "批次验收测试",
            "channel": "wechat_article",
            "platform": "wechat",
            "status": "draft",
            "success": True,
            "draft_id": "draft_guard_001",
            "draft_url": "https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit&appmsgid=draft_guard_001",
            "verification_status": "verified",
        },
    )
    write_json(
        xhs_result_file,
        {
            "topic_id": "topic-demo",
            "title": "批次验收测试",
            "channel": "xiaohongshu_video",
            "platform": "xiaohongshu",
            "status": "published",
            "success": True,
            "platform_url": "https://www.xiaohongshu.com/explore/guard001",
            "verification_status": "verified" if verified else "needs_manual_verification",
        },
    )
    write_json(publish_root / "publish_manifest.json", manifest)
    write_json(publish_root / "publish_verification_report.json", verification_report)
    return publish_root / "publish_manifest.json"


def test_publish_guard_passes_verified_mixed_batch(tmp_path):
    manifest_path = sample_publish_manifest_for_guard(tmp_path)
    output_md = tmp_path / "publish_guard.md"
    proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts" / "publish_guard.py"),
            "--publish-manifest",
            str(manifest_path),
            "--output-md",
            str(output_md),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["mode"] == "publish_guard"
    assert payload["will_not_publish"] is True
    assert payload["passed"] is True
    assert payload["status"] == "passed"
    assert payload["summary"]["published_count"] == 1
    assert payload["summary"]["draft_count"] == 1
    assert Path(payload["guard_report_json"]).exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["publish_guard"]["status"] == "passed"
    assert manifest["publish_guard"]["passed"] is True
    assert Path(manifest["publish_guard"]["report_json"]).exists()
    assert output_md.exists()


def test_publish_guard_fails_unverified_published_link(tmp_path):
    manifest_path = sample_publish_manifest_for_guard(tmp_path, verified=False)
    proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts" / "publish_guard.py"),
            "--publish-manifest",
            str(manifest_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["passed"] is False
    assert payload["status"] == "failed"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["publish_guard"]["status"] == "failed"
    xhs_check = next(item for item in payload["channel_checks"] if item["channel"] == "xiaohongshu_video")
    assert "published_not_verified" in xhs_check["issues"]
    assert payload["expected_published_links"] == []


def test_publish_guard_fail_on_error_exits_non_zero(tmp_path):
    manifest_path = sample_publish_manifest_for_guard(tmp_path, verified=False)
    proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts" / "publish_guard.py"),
            "--publish-manifest",
            str(manifest_path),
            "--fail-on-error",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 1
    payload = json.loads(proc.stdout)
    assert payload["passed"] is False
    assert payload["status"] == "failed"


def test_publish_guard_reports_pending_when_result_missing(tmp_path):
    publish_root = tmp_path / "publish_out"
    publish_root.mkdir(parents=True, exist_ok=True)
    manifest = {
        "run_id": "run-publish-guard-pending",
        "stage": "publish",
        "status": "pending_execution",
        "channel_packs": [
            {
                "topic_id": "topic-demo",
                "title": "待回填测试",
                "channel": "wechat_article",
                "platform": "wechat",
                "status": "ready_for_execution",
            }
        ],
        "publish_results": [],
        "publish_summary": {
            "status": "pending_execution",
            "total_channels": 1,
            "recorded_count": 0,
            "pending_count": 1,
            "failed_count": 0,
            "draft_count": 0,
            "published_count": 0,
            "verified_count": 0,
            "needs_manual_verification_count": 0,
            "pending_channels": [{"topic_id": "topic-demo", "channel": "wechat_article"}],
        },
    }
    write_json(publish_root / "publish_manifest.json", manifest)
    write_json(
        publish_root / "publish_verification_report.json",
        {
            "run_id": "run-publish-guard-pending",
            "stage": "publish",
            "status": "pending_execution",
            "records": [],
            "published_links": [],
            "draft_records": [],
            "publish_summary": manifest["publish_summary"],
        },
    )

    proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts" / "publish_guard.py"),
            "--publish-manifest",
            str(publish_root / "publish_manifest.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["status"] == "pending_execution"
    assert payload["passed"] is False
    assert payload["summary"]["pending_guard_count"] == 1
    assert payload["summary"]["blocking_issue_count"] == 0
    assert payload["summary"]["guard_issue_count"] == 1


def test_publish_guard_fails_when_verification_report_missing(tmp_path):
    manifest_path = sample_publish_manifest_for_guard(tmp_path)
    verification_path = manifest_path.parent / "publish_verification_report.json"
    verification_path.unlink()

    proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts" / "publish_guard.py"),
            "--publish-manifest",
            str(manifest_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["passed"] is False
    assert payload["status"] == "failed"
    assert payload["publish_verification_report_exists"] is False
    assert "missing_publish_verification_report" in payload["summary"]["consistency_issues"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["publish_guard"]["status"] == "failed"


def test_publish_guard_fails_when_result_file_missing(tmp_path):
    manifest_path = sample_publish_manifest_for_guard(tmp_path)
    verification_path = manifest_path.parent / "publish_verification_report.json"
    verification = json.loads(verification_path.read_text(encoding="utf-8"))
    result_file = Path(verification["records"][0]["result_file"])
    result_file.unlink()

    proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts" / "publish_guard.py"),
            "--publish-manifest",
            str(manifest_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["passed"] is False
    assert payload["status"] == "failed"
    assert any("missing_result_file" in issue for issue in payload["channel_checks"][0]["issues"])


def test_publish_guard_fails_when_result_file_content_mismatch(tmp_path):
    manifest_path = sample_publish_manifest_for_guard(tmp_path)
    verification_path = manifest_path.parent / "publish_verification_report.json"
    verification = json.loads(verification_path.read_text(encoding="utf-8"))
    result_file = Path(verification["records"][1]["result_file"])
    result_payload = json.loads(result_file.read_text(encoding="utf-8"))
    result_payload["platform_url"] = "https://www.xiaohongshu.com/explore/tampered"
    write_json(result_file, result_payload)

    proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts" / "publish_guard.py"),
            "--publish-manifest",
            str(manifest_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["passed"] is False
    assert payload["status"] == "failed"
    xhs_check = next(item for item in payload["channel_checks"] if item["channel"] == "xiaohongshu_video")
    assert "result_file_content_mismatch" in xhs_check["issues"]


def test_publish_guard_fails_summary_mismatch(tmp_path):
    manifest_path = sample_publish_manifest_for_guard(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["publish_summary"]["published_count"] = 99
    write_json(manifest_path, manifest)

    proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts" / "publish_guard.py"),
            "--publish-manifest",
            str(manifest_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["passed"] is False
    assert payload["status"] == "failed"
    assert "publish_summary_mismatch" in payload["summary"]["consistency_issues"]


def test_publish_guard_fails_when_manifest_and_verification_records_diverge(tmp_path):
    manifest_path = sample_publish_manifest_for_guard(tmp_path)
    verification_path = manifest_path.parent / "publish_verification_report.json"
    verification = json.loads(verification_path.read_text(encoding="utf-8"))
    verification["records"][1]["platform_url"] = "https://www.xiaohongshu.com/explore/different"
    write_json(verification_path, verification)

    proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts" / "publish_guard.py"),
            "--publish-manifest",
            str(manifest_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["passed"] is False
    assert payload["status"] == "failed"
    assert "manifest_verification_records_mismatch" in payload["summary"]["consistency_issues"]


def test_publish_guard_fails_when_verification_summary_mismatch(tmp_path):
    manifest_path = sample_publish_manifest_for_guard(tmp_path)
    verification_path = manifest_path.parent / "publish_verification_report.json"
    verification = json.loads(verification_path.read_text(encoding="utf-8"))
    verification["publish_summary"]["published_count"] = 99
    write_json(verification_path, verification)

    proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts" / "publish_guard.py"),
            "--publish-manifest",
            str(manifest_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["passed"] is False
    assert payload["status"] == "failed"
    assert "verification_publish_summary_mismatch" in payload["summary"]["consistency_issues"]
    assert "manifest_verification_summary_mismatch" in payload["summary"]["consistency_issues"]


def test_mainline_doctor_publish_manifest_routes_to_publish_guard(tmp_path):
    manifest_path = sample_publish_manifest_for_guard(tmp_path)
    output_json = tmp_path / "publish_guard.json"
    proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts" / "run_mainline_stage.py"),
            "doctor",
            "--publish-manifest",
            str(manifest_path),
            "--output-json",
            str(output_json),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["mode"] == "publish_guard"
    assert payload["passed"] is True
    assert output_json.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["publish_guard"]["report_json"] == str(output_json.resolve())


def test_mainline_doctor_publish_manifest_fail_on_error_routes_to_publish_guard(tmp_path):
    manifest_path = sample_publish_manifest_for_guard(tmp_path, verified=False)
    proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts" / "run_mainline_stage.py"),
            "doctor",
            "--publish-manifest",
            str(manifest_path),
            "--fail-on-error",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 1
    payload = json.loads(proc.stdout)
    assert payload["mode"] == "publish_guard"
    assert payload["passed"] is False


def test_publish_guard_then_strict_postmortem_end_to_end(tmp_path):
    manifest_path = sample_publish_manifest_for_guard(tmp_path)
    guard_proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts" / "publish_guard.py"),
            "--publish-manifest",
            str(manifest_path),
            "--fail-on-error",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert guard_proc.returncode == 0, guard_proc.stderr
    guard_payload = json.loads(guard_proc.stdout)
    assert guard_payload["passed"] is True
    assert Path(guard_payload["guard_report_json"]).exists()
    assert Path(guard_payload["guard_report_markdown"]).exists()

    postmortem_dir = tmp_path / "postmortem_out"
    postmortem_proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts" / "postmortem_writeback.py"),
            "--publish-manifest",
            str(manifest_path),
            "--require-publish-guard",
            "--output-dir",
            str(postmortem_dir),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert postmortem_proc.returncode == 0, postmortem_proc.stderr
    postmortem = json.loads((postmortem_dir / "postmortem_manifest.json").read_text(encoding="utf-8"))
    assert postmortem["publish_guard"]["passed"] is True
    assert postmortem["publish_guard"]["report_json"] == guard_payload["guard_report_json"]
    assert postmortem["writeback"]["topic_pattern_library"]["published_topics"] == 1
    assert postmortem["writeback"]["topic_pattern_library"]["drafted_topics"] == 1


def sample_wechat_channel_pack_with_execution_request(tmp: Path) -> Path:
    html = tmp / "wechat.html"
    html.write_text("<html><body>正文</body></html>", encoding="utf-8")
    pack_dir = tmp / "publish_out" / "channel_packs" / "topic-demo" / "wechat_article"
    pack_dir.mkdir(parents=True)
    pack_path = pack_dir / "channel_pack.json"
    request_path = pack_dir / "execution_request.json"
    verification_path = pack_dir / "verification_request.json"
    write_json(
        pack_path,
        {
            "topic_id": "topic-demo",
            "title": "执行入口测试",
            "channel": "wechat_article",
            "status": "ready_for_execution",
            "executor_skill": "baoyu-post-to-wechat",
            "execution_mode": "draft_push_or_browser_confirm",
            "artifact_hint": {"wechat_html": str(html)},
            "publish_metadata": {"title": "执行入口测试", "summary": "摘要"},
            "pack_manifest": str(pack_path),
            "execution_request": str(request_path),
            "verification_request": str(verification_path),
        },
    )
    write_json(
        request_path,
        {
            "schema_version": "1.0",
            "topic_id": "topic-demo",
            "title": "执行入口测试",
            "channel": "wechat_article",
            "platform": "wechat",
            "status": "ready_for_user_confirmation",
            "executor_skill": "baoyu-post-to-wechat",
            "execution_mode": "draft_push_or_browser_confirm",
            "requires_user_confirmation": True,
            "channel_pack": str(pack_path),
            "inputs": {"artifacts": {"wechat_html": str(html)}, "publish_metadata": {"title": "执行入口测试"}},
            "route_priority": [
                {"route": "baoyu-post-to-wechat", "type": "skill_draft_push"},
                {"route": "browser-profile", "type": "browser_confirm_fallback", "open_command": "python3 scripts/open_publish_browser.py wechat_article"},
            ],
        },
    )
    write_json(tmp / "publish_out" / "publish_manifest.json", {"run_id": "run-execute-test", "stage": "publish", "channel_packs": [json.loads(pack_path.read_text(encoding="utf-8"))]})
    write_json(tmp / "publish_out" / "channel_execution_manifest.json", {"run_id": "run-execute-test", "stage": "publish", "executions": [{"topic_id": "topic-demo", "channel": "wechat_article", "status": "pending_user_confirmation"}]})
    write_json(tmp / "publish_out" / "publish_verification_report.json", {"run_id": "run-execute-test", "stage": "publish", "status": "pending_execution", "published_links": []})
    return request_path


def sample_social_channel_pack_with_execution_request(tmp: Path, *, channel: str = "douyin_video") -> Path:
    source_pack = sample_video_channel_pack(tmp, channel=channel)
    pack = json.loads(source_pack.read_text(encoding="utf-8"))
    pack_dir = tmp / "publish_out" / "channel_packs" / "topic-demo" / channel
    pack_dir.mkdir(parents=True)
    pack_path = pack_dir / "channel_pack.json"
    request_path = pack_dir / "execution_request.json"
    pack.update(
        {
            "pack_manifest": str(pack_path),
            "execution_request": str(request_path),
            "platform": "wechat_channels" if channel == "wechat_channels_video" else "douyin",
        }
    )
    write_json(pack_path, pack)
    write_json(
        request_path,
        {
            "schema_version": "1.0",
            "topic_id": "topic-demo",
            "title": "外部执行入口测试",
            "channel": channel,
            "platform": pack["platform"],
            "status": "ready_for_user_confirmation",
            "requires_user_confirmation": True,
            "channel_pack": str(pack_path),
            "inputs": {"artifacts": pack["artifact_hint"], "publish_metadata": pack["publish_metadata"]},
            "route_priority": [{"route": "social-auto-upload", "type": "external_uploader_fallback"}],
        },
    )
    publish_root = tmp / "publish_out"
    write_json(
        publish_root / "publish_manifest.json",
        {"run_id": "run-social-execute-test", "stage": "publish", "channel_packs": [pack]},
    )
    write_json(
        publish_root / "channel_execution_manifest.json",
        {
            "run_id": "run-social-execute-test",
            "stage": "publish",
            "executions": [{"topic_id": "topic-demo", "channel": channel, "status": "pending_user_confirmation"}],
        },
    )
    write_json(
        publish_root / "publish_verification_report.json",
        {"run_id": "run-social-execute-test", "stage": "publish", "status": "pending_execution", "published_links": []},
    )
    return request_path


def test_execute_publish_request_defaults_to_dry_run(tmp_path):
    request_path = sample_wechat_channel_pack_with_execution_request(tmp_path)
    proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts" / "execute_publish_request.py"),
            "--execution-request",
            str(request_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["mode"] == "dry_run"
    assert payload["will_not_publish"] is True
    assert payload["selected_route"] == "baoyu-post-to-wechat"
    assert Path(payload["publish_payload"]).exists()
    assert not (request_path.parent / "publish_result.json").exists()


def test_execute_publish_request_blocks_platform_form_errors_before_skill_invocation(tmp_path):
    request_path = sample_wechat_channel_pack_with_execution_request(tmp_path)
    pack_path = request_path.parent / "channel_pack.json"
    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    pack["title"] = ""
    pack["publish_metadata"]["title"] = ""
    write_json(pack_path, pack)
    scripts_dir = str(PROJECT_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    module = __import__("execute_publish_request")
    invoker = Mock()

    result = module.execute_request(request_path, confirm_execute=True, invoker=invoker)

    assert result["status"] == "blocked_platform_form_validation"
    assert result["will_not_publish"] is True
    assert "missing_title" in result["errors"]
    invoker.invoke.assert_not_called()
    assert not (request_path.parent / "publish_result.json").exists()


def test_execute_publish_request_confirm_invokes_skill_and_records_result(tmp_path):
    request_path = sample_wechat_channel_pack_with_execution_request(tmp_path)
    scripts_dir = str(PROJECT_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    module = __import__("execute_publish_request")
    invoker = Mock()
    invoker.invoke.return_value = {
        "success": True,
        "platform": "wechat",
        "status": "draft",
        "url": "https://mp.weixin.qq.com/draft/abc",
        "msg_id": "draft_abc",
        "verification_status": "verified",
    }
    result = module.execute_request(request_path, confirm_execute=True, invoker=invoker)

    assert result["status"] == "executed_and_recorded"
    invoker.invoke.assert_called_once()
    assert invoker.invoke.call_args[0][0] == "baoyu-post-to-wechat"
    assert (request_path.parent / "publish_result.json").exists()
    verification = json.loads((tmp_path / "publish_out" / "publish_verification_report.json").read_text(encoding="utf-8"))
    assert verification["published_links"] == []
    assert verification["draft_records"][0]["draft_id"] == "draft_abc"


def test_execute_publish_request_confirm_does_not_auto_verify_skill_result(tmp_path):
    request_path = sample_wechat_channel_pack_with_execution_request(tmp_path)
    scripts_dir = str(PROJECT_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    module = __import__("execute_publish_request")
    invoker = Mock()
    invoker.invoke.return_value = {
        "success": True,
        "platform": "wechat",
        "status": "draft",
        "url": "https://mp.weixin.qq.com/draft/not-verified",
        "msg_id": "draft_not_verified_by_skill",
    }

    result = module.execute_request(request_path, confirm_execute=True, invoker=invoker)

    assert result["status"] == "executed_and_recorded"
    verification = json.loads((tmp_path / "publish_out" / "publish_verification_report.json").read_text(encoding="utf-8"))
    assert verification["status"] == "needs_manual_verification"
    assert verification["draft_records"] == []
    assert verification["publish_summary"]["draft_count"] == 0
    assert verification["publish_summary"]["needs_manual_verification_count"] == 1


def test_execute_publish_request_blocks_external_cli_even_with_confirm(tmp_path, monkeypatch):
    pack_path = sample_video_channel_pack(tmp_path, channel="xiaohongshu_video")
    all_in_one_root = tmp_path / "All-IN-ONE"
    all_in_one_root.mkdir()
    monkeypatch.setenv("ALL_IN_ONE_ROOT", str(all_in_one_root))
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    request_path = sample_execution_request(
        tmp_path,
        channel="xiaohongshu_video",
        platform="xiaohongshu",
        routes=[
            {"route": "all-in-one", "type": "api_first_cli"},
            {"route": "browser-profile", "type": "browser_confirm_fallback", "open_command": "python3 scripts/open_publish_browser.py xiaohongshu_video"},
        ],
    )
    request = json.loads(request_path.read_text(encoding="utf-8"))
    request["channel_pack"] = str(pack_path)
    write_json(request_path, request)
    scripts_dir = str(PROJECT_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    module = __import__("execute_publish_request")
    invoker = Mock()

    result = module.execute_request(request_path, confirm_execute=True, invoker=invoker)

    assert result["status"] == "blocked_manual_or_external_route"
    assert result["selected_route"] == "all-in-one"
    assert result["selected_route_type"] == "api_first_cli"
    assert result["will_not_publish"] is True
    invoker.invoke.assert_not_called()
    assert not (request_path.parent / "publish_result.json").exists()


def test_execute_publish_request_previews_social_auto_upload_without_publishing(tmp_path, monkeypatch):
    request_path = sample_social_channel_pack_with_execution_request(tmp_path)
    social_root = tmp_path / "social-auto-upload"
    social_root.mkdir()
    fake_sau = write_fake_sau(tmp_path)
    monkeypatch.setenv("SOCIAL_AUTO_UPLOAD_ROOT", str(social_root))
    monkeypatch.setenv("SOCIAL_AUTO_UPLOAD_CLI", str(fake_sau))
    scripts_dir = str(PROJECT_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    module = __import__("execute_publish_request")

    result = module.execute_request(request_path, confirm_execute=False)

    assert result["mode"] == "dry_run"
    assert result["selected_route"] == "social-auto-upload"
    assert result["external_preview"]["status"] == "ready_for_user_confirmation"
    assert result["external_preview"]["will_not_publish"] is True
    assert not (request_path.parent / "publish_result.json").exists()


def test_execute_publish_request_runs_social_auto_upload_only_after_confirm(tmp_path, monkeypatch):
    request_path = sample_social_channel_pack_with_execution_request(tmp_path)
    social_root = tmp_path / "social-auto-upload"
    social_root.mkdir()
    fake_sau = write_fake_sau(tmp_path)
    monkeypatch.setenv("SOCIAL_AUTO_UPLOAD_ROOT", str(social_root))
    monkeypatch.setenv("SOCIAL_AUTO_UPLOAD_CLI", str(fake_sau))
    scripts_dir = str(PROJECT_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    module = __import__("execute_publish_request")

    result = module.execute_request(request_path, confirm_execute=True)

    assert result["status"] == "executed_and_recorded"
    assert result["selected_route"] == "social-auto-upload"
    assert result["external_result"]["status"] == "pending_verification"
    publish_result = json.loads((request_path.parent / "publish_result.json").read_text(encoding="utf-8"))
    assert publish_result["status"] == "pending_verification"
    assert publish_result["verification_status"] == "needs_manual_verification"
