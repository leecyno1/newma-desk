#!/usr/bin/env python3
"""
Pre-launch 基线回归测试套件

用于验证 P0 修复和 UI 改进的基线功能。
这些测试应该在任何修改前运行，确保基线功能正常。
"""

import subprocess
import sys
import os
from pathlib import Path
from unittest import TestCase, main as unittest_main

# 项目根目录
ROOT = Path(__file__).parent.parent.resolve()


class TestPrelaunchBaseline(TestCase):
    """Pre-launch 基线回归测试"""

    def test_workflow_doctor_runs_without_crash(self):
        """workflow_doctor --help 应正常退出，不报 AttributeError"""
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "workflow_doctor.py"), "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        # 0 = 成功，1 = 帮助信息正常退出
        self.assertIn(
            result.returncode,
            [0, 1],
            f"workflow_doctor --help 失败: {result.stderr}",
        )

    def test_install_scripts_are_executable(self):
        """安装脚本应该是可执行的"""
        for script_name in ["install_to_openclaw.sh", "install_to_hermes.sh"]:
            script_path = ROOT / script_name
            self.assertTrue(
                script_path.exists(),
                f"脚本不存在: {script_path}",
            )
            content = script_path.read_text(errors="ignore")
            self.assertTrue(
                content.startswith("#!/"),
                f"脚本缺少 shebang: {script_name}",
            )

    def test_provider_registry_returns_dict(self):
        """provider_registry 应返回 dict 而非 None（API key 缺失时）"""
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import sys; sys.path.insert(0, 'scripts'); "
                    "from provider_registry import resolve_chat_provider; "
                    "r = resolve_chat_provider("
                    "base_url_keys=['X'], "
                    "api_key_keys=['X'], "
                    "model_keys=['X'], "
                    "timeout_keys=['X']"
                    "); "
                    "print(type(r).__name__, "
                    "'_unavailable' if r.get('_unavailable') else 'available', "
                    "'_warning' if r.get('_warning') else 'no_warning')"
                ),
            ],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            timeout=10,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"provider_registry 测试失败: {result.stderr}",
        )
        output = result.stdout.strip()
        self.assertTrue(
            output.startswith("dict"),
            f"期望返回 dict，实际: {output}",
        )
        # API key 缺失时应该有 _unavailable 或 _warning
        self.assertIn(
            "_unavailable",
            output,
            f"API key 缺失时应标记为 unavailable: {output}",
        )

    def test_rewrite_has_timeout_in_source(self):
        """rewrite_execute_stage5.py 的 call_claude 应包含 timeout 参数"""
        content = (ROOT / "scripts" / "rewrite_execute_stage5.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "timeout=",
            content,
            "rewrite_execute_stage5.py 应包含 timeout= 参数",
        )

    def test_orchestrator_has_skip_retry(self):
        """orchestrator.py 应包含 skip_on_failure 和 max_retries 参数"""
        content = (ROOT / "core" / "orchestrator.py").read_text(encoding="utf-8")
        self.assertIn(
            "skip_on_failure",
            content,
            "orchestrator.py 应包含 skip_on_failure 参数",
        )
        self.assertIn(
            "max_retries",
            content,
            "orchestrator.py 应包含 max_retries 参数",
        )
        self.assertIn(
            "retry_count",
            content,
            "StageResult 应包含 retry_count 字段",
        )
        self.assertIn(
            "skipped",
            content,
            "StageResult 应包含 skipped 字段",
        )

    def test_workflow_doctor_has_error_handling(self):
        """workflow_doctor.py 的 provider_summary 应包含异常处理"""
        content = (ROOT / "scripts" / "workflow_doctor.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "except Exception",
            content,
            "workflow_doctor.py 应包含异常处理",
        )
        # 应该检查 _unavailable 而不是 None
        self.assertIn(
            "_unavailable",
            content,
            "workflow_doctor.py 应检查 _unavailable 字段",
        )

    def test_all_skills_have_frontmatter(self):
        """所有包含 index.js 或 config.json 的 skill 目录应包含 SKILL.md"""
        missing_frontmatter = []
        for skill_dir in (ROOT / "skills").iterdir():
            if not skill_dir.is_dir() or skill_dir.name.startswith("."):
                continue
            # 只检查有 skill 标记的目录（index.js 或 config.json）
            has_marker = (skill_dir / "index.js").exists() or (skill_dir / "config.json").exists()
            if not has_marker:
                # 跳过不是 skill 的子模块目录（如 dasheng-media-rewrite-v2 等）
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                missing_frontmatter.append(f"{skill_dir.name}/SKILL.md (missing)")
                continue
            content = skill_md.read_text(encoding="utf-8")
            if not content.startswith("---"):
                missing_frontmatter.append(f"{skill_dir.name}/SKILL.md (no frontmatter)")
        self.assertEqual(
            missing_frontmatter,
            [],
            f"以下 SKILL.md 缺少 YAML frontmatter: {missing_frontmatter}",
        )

    def test_stage_interfaces_no_hardcoded_paths(self):
        """docs/STAGE_INTERFACES.md 不应包含硬编码绝对路径"""
        stage_interfaces = ROOT / "docs" / "STAGE_INTERFACES.md"
        if not stage_interfaces.exists():
            self.skipTest("docs/STAGE_INTERFACES.md 不存在，跳过")
        content = stage_interfaces.read_text(encoding="utf-8")
        hardcoded = [
            line.strip()
            for line in content.splitlines()
            if any(prefix in line for prefix in ("/Users/", "/Volumes/"))
            and not line.strip().startswith("#")
        ]
        self.assertEqual(
            hardcoded,
            [],
            f"docs/STAGE_INTERFACES.md 包含硬编码路径: {hardcoded[:3]}",
        )


if __name__ == "__main__":
    unittest_main(verbosity=2)
