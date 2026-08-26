import json
import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
PYTHON = sys.executable


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_publish_fixture(tmp_path: Path, *, channel: str, account_stage: str) -> tuple[Path, Path, Path]:
    if channel == "wechat_article":
        artifact = tmp_path / "wechat.final.html"
        artifact.write_text("<html><body>publish operations test</body></html>", encoding="utf-8")
        lane_name = "wechat_article"
        lane = {"status": "completed", "final_html": str(artifact)}
    else:
        artifact = tmp_path / "video.mp4"
        artifact.write_bytes(b"fake mp4")
        lane_name = "talking_head_video"
        lane = {"status": "completed", "final_video": str(artifact)}

    transwrite_manifest = tmp_path / "transwrite_manifest.json"
    publish_decision = tmp_path / "publish_decision.json"
    output_dir = tmp_path / "publish_out"
    write_json(
        transwrite_manifest,
        {
            "run_id": "run-publish-operations",
            "stage": "transwrite",
            "status": "completed",
            "topics": [
                {
                    "topic_id": "topic-demo",
                    "title": "Operations bridge test",
                    "lanes": {lane_name: lane},
                }
            ],
        },
    )
    write_json(
        publish_decision,
        {
            "run_id": "run-publish-operations",
            "gate": "Channel Gate",
            "status": "approved",
            "topics": [
                {
                    "topic_id": "topic-demo",
                    "title": "Operations bridge test",
                    "channels": [channel],
                    "account_stage": account_stage,
                    "account_goal": "knowledge account",
                    "account_slot": "slot_1",
                    "matrix_role": "primary",
                    "target_audience": "finance readers",
                    "weekly_capacity": 3,
                }
            ],
        },
    )
    return transwrite_manifest, publish_decision, output_dir


def run_builder(transwrite_manifest: Path, publish_decision: Path, output_dir: Path) -> dict:
    proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts" / "build_stage5_publish.py"),
            "--transwrite-manifest",
            str(transwrite_manifest),
            "--publish-decision",
            str(publish_decision),
            "--output-dir",
            str(output_dir),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_cold_start_operations_review_blocks_guarded_execution_until_valid_advice(tmp_path):
    transwrite_manifest, publish_decision, output_dir = build_publish_fixture(
        tmp_path,
        channel="wechat_article",
        account_stage="cold_start",
    )
    payload = run_builder(transwrite_manifest, publish_decision, output_dir)
    pack = payload["channel_packs"][0]
    operations = pack["account_operations"]

    assert operations["required"] is True
    assert operations["status"] == "required_before_execution"
    assert operations["upstream_skill"] == "wechat-account-launch-expert"
    assert Path(operations["request"]).exists()
    request = json.loads(Path(operations["request"]).read_text(encoding="utf-8"))
    assert request["required_before_execution"] is True
    assert request["constraints"]["does_not_publish"] is True
    execution_request = json.loads(Path(pack["execution_request"]).read_text(encoding="utf-8"))
    assert execution_request["status"] == "waiting_for_operations_review"
    assert pack["execution_commands"]["confirmed_executor_command"] is None

    write_json(
        Path(operations["advice_json"]),
        {
            "schema_version": "dasheng.publish.operations_advice.v1",
            "status": "completed",
            "topic_id": "topic-demo",
            "channel": "wechat_article",
            "platform": "wechat",
            "account_stage": "cold_start",
            "upstream_skill": "wechat-account-launch-expert",
            "recommendations": {"title_or_hook": ["keep the promise concrete"]},
        },
    )
    rebuilt = run_builder(transwrite_manifest, publish_decision, output_dir)
    rebuilt_pack = rebuilt["channel_packs"][0]
    rebuilt_operations = rebuilt_pack["account_operations"]
    rebuilt_execution_request = json.loads(Path(rebuilt_pack["execution_request"]).read_text(encoding="utf-8"))

    assert rebuilt_operations["review_completed"] is True
    assert rebuilt_operations["status"] == "completed"
    assert rebuilt_execution_request["status"] == "ready_for_user_confirmation"
    assert "--confirm-execute" in rebuilt_pack["execution_commands"]["confirmed_executor_command"]


def test_active_account_gets_non_blocking_xiaohongshu_operations_advisory(tmp_path):
    transwrite_manifest, publish_decision, output_dir = build_publish_fixture(
        tmp_path,
        channel="xiaohongshu_video",
        account_stage="active",
    )
    payload = run_builder(transwrite_manifest, publish_decision, output_dir)
    pack = payload["channel_packs"][0]
    operations = pack["account_operations"]
    execution_request = json.loads(Path(pack["execution_request"]).read_text(encoding="utf-8"))

    assert operations["required"] is False
    assert operations["status"] == "advisory_pending"
    assert operations["upstream_skill"] == "xiaohongshu-account-launch-expert"
    assert execution_request["status"] == "ready_for_user_confirmation"


def test_unspecified_account_stage_preserves_existing_wechat_execution_behavior(tmp_path):
    transwrite_manifest, publish_decision, output_dir = build_publish_fixture(
        tmp_path,
        channel="wechat_article",
        account_stage="unspecified",
    )
    payload = run_builder(transwrite_manifest, publish_decision, output_dir)
    pack = payload["channel_packs"][0]
    verification_request = json.loads(Path(pack["verification_request"]).read_text(encoding="utf-8"))

    assert pack["account_operations"]["required"] is False
    assert pack["execution_commands"]["confirm_execute_supported"] is True
    assert "--confirm-execute" in pack["execution_commands"]["confirmed_executor_command"]
    assert "opens" in verification_request["requested_performance_metrics"]


def test_publish_doctor_reports_external_operations_skill_readiness(tmp_path):
    upstream_root = tmp_path / "agent-skills-launch-pack"
    skill_file = upstream_root / "skills" / "wechat-account-launch-expert" / "SKILL.md"
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text("---\nname: wechat-account-launch-expert\ndescription: test\n---\n", encoding="utf-8")
    proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts" / "publish_doctor.py"),
            "--channel",
            "wechat_article",
        ],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "AGENT_SKILLS_LAUNCH_PACK_ROOT": str(upstream_root)},
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    operations = payload["channels"][0]["account_operations"]
    assert operations["available"] is True
    assert operations["upstream_skill"] == "wechat-account-launch-expert"
    assert payload["summary"]["operations_ready_count"] == 1
