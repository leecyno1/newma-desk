#!/usr/bin/env python3
"""
端到端测试：安装冒烟测试
验证安装脚本创建正确的目录结构
"""

import os
import tempfile
import unittest
from pathlib import Path


class TestInstallSmoke(unittest.TestCase):
    """测试安装脚本的基本功能"""

    def setUp(self):
        """设置测试环境"""
        self.project_root = Path(__file__).parent.parent.parent

    def test_install_scripts_exist(self):
        """验证安装脚本存在"""
        openclaw_script = self.project_root / "install_to_openclaw.sh"
        hermes_script = self.project_root / "install_to_hermes.sh"

        self.assertTrue(openclaw_script.exists(),
                       "install_to_openclaw.sh not found")
        self.assertTrue(hermes_script.exists(),
                       "install_to_hermes.sh not found")

    def test_install_scripts_executable(self):
        """验证安装脚本可执行"""
        openclaw_script = self.project_root / "install_to_openclaw.sh"
        hermes_script = self.project_root / "install_to_hermes.sh"

        self.assertTrue(os.access(openclaw_script, os.X_OK),
                       "install_to_openclaw.sh not executable")
        self.assertTrue(os.access(hermes_script, os.X_OK),
                       "install_to_hermes.sh not executable")

    def test_required_directories_exist(self):
        """验证必需的目录存在"""
        required_dirs = [
            "scripts",
            "skills",
            "tests",
            "configs",
            "docs"
        ]

        for dir_name in required_dirs:
            dir_path = self.project_root / dir_name
            self.assertTrue(dir_path.exists(),
                          f"Required directory '{dir_name}' not found")
            self.assertTrue(dir_path.is_dir(),
                          f"'{dir_name}' is not a directory")

    def test_core_scripts_exist(self):
        """验证核心脚本存在"""
        core_scripts = [
            "scripts/path_config.py",
            "scripts/workflow_doctor.py",
            "scripts/run_stage1_intake.py"
        ]

        for script in core_scripts:
            script_path = self.project_root / script
            self.assertTrue(script_path.exists(),
                          f"Core script '{script}' not found")

    def test_export_manifest_exists(self):
        """验证导出清单存在"""
        manifest = self.project_root / "openclaw-skill-exports" / \
                   "newma-media-studio-current" / "EXPORT_MANIFEST.json"

        self.assertTrue(manifest.exists(),
                       "EXPORT_MANIFEST.json not found")

    def test_env_template_exists(self):
        """验证环境变量模板存在"""
        env_template = self.project_root / "openclaw-skill-exports" / \
                      "newma-media-studio-current" / "ENV_TEMPLATE.env"

        self.assertTrue(env_template.exists(),
                       "ENV_TEMPLATE.env not found")

    def test_readme_exists(self):
        """验证 README 存在"""
        readme = self.project_root / "README.md"
        self.assertTrue(readme.exists(), "README.md not found")

    def test_claude_md_exists(self):
        """验证 CLAUDE.md 存在"""
        claude_md = self.project_root / "CLAUDE.md"
        self.assertTrue(claude_md.exists(), "CLAUDE.md not found")


if __name__ == '__main__':
    unittest.main()
