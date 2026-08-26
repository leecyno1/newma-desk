import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


# 支持环境变量覆盖测试根目录
_ROOT_ENV = os.environ.get("DASHENG_ROOT")
if _ROOT_ENV:
    ROOT = Path(_ROOT_ENV)
else:
    # 使用脚本所在目录作为默认值
    ROOT = Path(__file__).parent.parent.resolve()


class InstallScriptsTests(unittest.TestCase):
    def test_primary_install_script_has_existing_verification_entrypoint(self):
        install_script = ROOT / "scripts" / "install.sh"
        content = install_script.read_text(encoding="utf-8")

        self.assertNotIn("$BASE_DIR", content)
        self.assertTrue((ROOT / "scripts" / "verify_installation.py").exists())

    def test_openclaw_install_script_creates_workspace_and_entry_skill(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp_test") as tmpdir:
            tmp = Path(tmpdir)
            skills_dir = tmp / "openclaw-skills"
            workspace_dir = tmp / "openclaw-workspace"

            proc = subprocess.run(
                ["bash", str(ROOT / "install_to_openclaw.sh"), "--skip-confirm", str(skills_dir), str(workspace_dir)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stderr)
            self.assertTrue((skills_dir / "dasheng-media-sop").exists())
            self.assertTrue((workspace_dir / "scripts" / "run_mainline_stage.py").exists())
            self.assertTrue((workspace_dir / "ENV_TEMPLATE.env").exists())

    def test_hermes_install_script_creates_workspace_and_entry_skill(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp_test") as tmpdir:
            tmp = Path(tmpdir)
            skills_dir = tmp / "hermes-skills"
            workspace_dir = tmp / "hermes-workspace"

            proc = subprocess.run(
                ["bash", str(ROOT / "install_to_hermes.sh"), "--skip-confirm", str(skills_dir), str(workspace_dir)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stderr)
            self.assertTrue((skills_dir / "dasheng-media-sop").exists())
            self.assertTrue((workspace_dir / "scripts" / "run_mainline_stage.py").exists())
            self.assertTrue((workspace_dir / "ENV_TEMPLATE.env").exists())


if __name__ == "__main__":
    unittest.main()
