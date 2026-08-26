import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path


# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from path_config import get_project_root

ROOT = get_project_root()
NODE = shutil.which("node") or "node"


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class FeishuPostmortemSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.run_id = "test-feishu-postmortem-2026-04-05"
        self.runtime_run_dir = ROOT / "skills/dasheng-daily-shared/runtime-data/runs" / self.run_id
        self.postmortem_dir = ROOT / "产物" / self.run_id / "06_复盘"

    def tearDown(self) -> None:
        shutil.rmtree(self.runtime_run_dir, ignore_errors=True)
        shutil.rmtree(self.postmortem_dir, ignore_errors=True)

    def test_feishu_plan_contains_postmortem_docs_and_message(self):
        write_json(
            self.runtime_run_dir / "run_manifest.json",
            {
                "run_id": self.run_id,
                "run_date": "2026-04-05",
                "status": "running",
                "current_step": "postmortem",
                "artifacts": [],
            },
        )
        write_json(
            self.postmortem_dir / "postmortem_manifest.json",
            {
                "run_id": self.run_id,
                "stage": "postmortem",
                "status": "completed",
                "topics": [{"topic_id": "topic6", "topic_name": "测试题"}],
            },
        )
        write_text(
            self.postmortem_dir / "08_复盘报告.md",
            "# 08 复盘报告\n\n## 测试题\n- 已发布：`true`\n- 渠道：`['wechat']`\n",
        )
        write_text(
            self.postmortem_dir / "08_L1回写建议.md",
            "# 08 L1 回写建议\n\n- 题材回写：`{'wechat': 1}`\n",
        )

        proc = subprocess.run(
            [NODE, str(ROOT / "skills/dasheng-daily-shared/runtime/feishu-plan.js"), self.run_id],
            capture_output=True,
            text=True,
            env={**os.environ, "DASHENG_OUTPUT_ROOT": str(ROOT / "产物")},
            check=False,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        payload = json.loads(proc.stdout)

        postmortem_docs = [item for item in payload["docs"] if item["stage"] == "postmortem"]
        self.assertEqual(len(postmortem_docs), 2)
        self.assertTrue(any(item["title"] == "07_复盘报告" for item in postmortem_docs))
        self.assertTrue(any(item["title"] == "07_L1回写建议" for item in postmortem_docs))

        postmortem_message = next(item for item in payload["messages"] if item["stage"] == "postmortem")
        self.assertIn("分析复盘审核提醒", postmortem_message["body_template"])
        self.assertIn("修正结论口径", postmortem_message["body_template"])

    def test_runner_build_sync_bridge_contract_still_works_for_feishu_live(self):
        write_json(
            self.runtime_run_dir / "run_manifest.json",
            {"run_id": self.run_id, "run_date": "2026-04-05", "artifacts": []},
        )
        write_text(self.postmortem_dir / "08_复盘报告.md", "# 08 复盘报告\n")
        write_text(self.postmortem_dir / "08_L1回写建议.md", "# 08 L1 回写建议\n")

        inline = (
            "const runner = require('./skills/dasheng-daily-shared/runtime/runner.js');"
            f"const payload = runner.buildSyncBridgeContract('{self.run_id}');"
            "console.log(JSON.stringify({ docs: payload.docs.length, messages: payload.messages.length, actions: payload.actions.length }));"
        )
        proc = subprocess.run(
            [NODE, "-e", inline],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            env={**os.environ, "DASHENG_OUTPUT_ROOT": str(ROOT / "产物")},
            check=False,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertGreater(payload["docs"], 0)
        self.assertGreater(payload["messages"], 0)
        self.assertGreater(payload["actions"], 0)


if __name__ == "__main__":
    unittest.main()
