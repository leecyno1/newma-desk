import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path


# 支持环境变量覆盖测试根目录
_ROOT_ENV = os.environ.get("DASHENG_ROOT")
if _ROOT_ENV:
    ROOT = Path(_ROOT_ENV)
else:
    # 使用脚本所在目录作为默认值
    ROOT = Path(__file__).parent.parent.resolve()
PYTHON = sys.executable


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class WorkflowDoctorTests(unittest.TestCase):
    def test_stage_contract_snapshot_excludes_optional_paradigm_asset(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        try:
            from canonical_workflow import stage_contract_snapshot
        finally:
            sys.path.pop(0)

        snapshot = stage_contract_snapshot("non-existent-run")
        self.assertEqual(
            list(snapshot["stages"].keys()),
            ["intake", "brief", "draft", "transwrite", "publish", "postmortem"],
        )
        self.assertNotIn("paradigm", snapshot["stages"])

    def test_doctor_contract_excludes_optional_paradigm_asset_from_formal_stages(self):
        proc = subprocess.run(
            [PYTHON, str(ROOT / "scripts/workflow_doctor.py"), "--run-id", "non-existent-run"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        payload = json.loads(proc.stdout)
        stages = payload["canonical_contract"]["stages"]
        self.assertNotIn("paradigm", stages)
        self.assertIn("paradigm", payload["optional_assets"])

    def test_doctor_discovers_nested_optional_paradigm_manifests(self):
        run_id = "run-doctor-paradigm-asset"
        asset_dir = ROOT / "产物/00_范式学习" / run_id / "结构变化解读"
        try:
            write_json(
                asset_dir / "paradigm_manifest.json",
                {
                    "run_id": run_id,
                    "stage": "paradigm",
                    "status": "pending_editor_calibration",
                    "profile_name": "结构变化解读",
                    "analysis_mode": "heuristic_fallback",
                },
            )

            proc = subprocess.run(
                [PYTHON, str(ROOT / "scripts/workflow_doctor.py"), "--run-id", run_id],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stderr)
            payload = json.loads(proc.stdout)
            paradigm = payload["optional_assets"]["paradigm"]
            self.assertTrue(paradigm["manifest_exists"])
            self.assertEqual(paradigm["manifest_count"], 1)
            self.assertEqual(paradigm["manifest_status"], "pending_editor_calibration")
            self.assertEqual(paradigm["manifests"][0]["profile_name"], "结构变化解读")
        finally:
            if asset_dir.parent.exists():
                shutil.rmtree(asset_dir.parent)

    def test_doctor_reports_missing_transwrite_manifest_after_draft_gate(self):
        run_id = "run-doctor-missing-transwrite"
        intake_dir = ROOT / "产物" / run_id / "01_采集"
        brief_dir = ROOT / "产物" / run_id / "02_选题"
        draft_dir = ROOT / "产物" / run_id / "03_初稿"
        cleanup_targets = [intake_dir, brief_dir, draft_dir]
        try:
            write_json(intake_dir / "intake_manifest.json", {"run_id": run_id, "stage": "intake"})
            write_json(brief_dir / "brief_manifest.json", {"run_id": run_id, "stage": "brief"})
            write_json(
                brief_dir / "selected_topics.json",
                {"run_id": run_id, "status": "approved", "selected_topics": [{"topic_id": "t1"}]},
            )
            write_json(draft_dir / "draft_manifest.json", {"run_id": run_id, "stage": "draft"})
            write_json(
                draft_dir / "final_structure_snapshot.json",
                {"run_id": run_id, "status": "approved", "topics": [{"topic_id": "t1"}]},
            )

            proc = subprocess.run(
                [PYTHON, str(ROOT / "scripts/workflow_doctor.py"), "--run-id", run_id],
                capture_output=True,
                text=True,
                check=False,
                env={**os.environ, "DASHENG_OUTPUT_ROOT": str(ROOT / "产物")},
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertTrue(any("transwrite" in issue for issue in payload["issues"]))
            self.assertFalse(any("material" in issue or "rewrite" in issue for issue in payload["issues"]))
        finally:
            for target in cleanup_targets:
                if target.exists():
                    shutil.rmtree(target)

    def test_doctor_can_inspect_nonexistent_run(self):
        proc = subprocess.run(
            [PYTHON, str(ROOT / "scripts/workflow_doctor.py"), "--run-id", "non-existent-run"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["run_id"], "non-existent-run")
        self.assertIn("canonical_contract", payload)

    def test_doctor_latest_reports_when_no_runs_exist(self):
        proc = subprocess.run(
            [PYTHON, str(ROOT / "scripts/workflow_doctor.py"), "--latest"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            self.skipTest("当前工作区已有可发现 run，无法验证空 --latest 提示")
        self.assertIn("未找到任何可用 run", proc.stderr or proc.stdout)


if __name__ == "__main__":
    unittest.main()
