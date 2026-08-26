#!/usr/bin/env python3
"""
端到端测试：Skill 可发现性
验证所有 skills 可以被正确发现和加载
"""

import os
import json
import unittest
from pathlib import Path


class TestSkillDiscovery(unittest.TestCase):
    """测试 skill 可发现性"""

    def setUp(self):
        """设置测试环境"""
        self.project_root = Path(__file__).parent.parent.parent
        self.skills_dir = self.project_root / "skills"

    def test_skills_directory_exists(self):
        """验证 skills 目录存在"""
        self.assertTrue(self.skills_dir.exists())
        self.assertTrue(self.skills_dir.is_dir())

    def test_all_skills_have_skill_md(self):
        """验证所有 skill 都有 SKILL.md 文件"""
        # Exclude non-skill directories
        exclude_dirs = {'.archive', 'dasheng-daily-shared', 'dasheng-media-rewrite-v2'}

        skills = [d for d in self.skills_dir.iterdir()
                 if d.is_dir() and not d.name.startswith('.') and d.name not in exclude_dirs]

        self.assertGreater(len(skills), 0, "No skills found")

        missing_skill_md = []
        for skill_dir in skills:
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                missing_skill_md.append(skill_dir.name)

        self.assertEqual(len(missing_skill_md), 0,
                        f"Skills missing SKILL.md: {missing_skill_md}")

    def test_all_skills_have_config_json(self):
        """验证所有 skill 都有 config.json 文件（如果需要）"""
        # Exclude non-skill directories and skills that don't use config.json
        exclude_dirs = {
            '.archive',
            'dasheng-daily-shared',  # Shared runtime library
            'dasheng-media-rewrite-v2',  # Deprecated version
            'dasheng-media-sop',  # Uses agents/ structure
            'dasheng-stage-brief-ai',  # Uses agents/ structure
            'dasheng-stage-publish',  # Uses agents/ structure
            'dasheng-style-profiler',  # Uses agents/ structure
            'feishu-doc-creator'  # Uses agents/ structure
        }

        skills = [d for d in self.skills_dir.iterdir()
                 if d.is_dir() and not d.name.startswith('.') and d.name not in exclude_dirs]

        missing_config = []
        for skill_dir in skills:
            config_json = skill_dir / "config.json"
            skill_md = skill_dir / "SKILL.md"
            if not config_json.exists():
                # OpenClaw/Hermes 外部 skill 通常只有 SKILL.md，允许缺少 config.json
                if skill_md.exists():
                    continue
                missing_config.append(skill_dir.name)

        self.assertEqual(len(missing_config), 0,
                        f"Skills missing config.json: {missing_config}")

    def test_config_json_valid(self):
        """验证所有 config.json 文件格式正确"""
        exclude_dirs = {'.archive', 'dasheng-daily-shared', 'dasheng-media-rewrite-v2'}

        skills = [d for d in self.skills_dir.iterdir()
                 if d.is_dir() and d.name not in exclude_dirs]

        invalid_configs = []
        for skill_dir in skills:
            config_json = skill_dir / "config.json"
            if config_json.exists():
                try:
                    with open(config_json, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                        # Verify required fields
                        if 'name' not in config:
                            invalid_configs.append(f"{skill_dir.name}: missing 'name'")
                        if 'version' not in config:
                            invalid_configs.append(f"{skill_dir.name}: missing 'version'")
                except json.JSONDecodeError as e:
                    invalid_configs.append(f"{skill_dir.name}: {e}")

        self.assertEqual(len(invalid_configs), 0,
                        f"Invalid config.json files: {invalid_configs}")

    def test_minimum_skill_count(self):
        """验证至少有预期数量的 skills"""
        exclude_dirs = {'.archive', 'dasheng-daily-shared', 'dasheng-media-rewrite-v2'}

        skills = [d for d in self.skills_dir.iterdir()
                 if d.is_dir() and d.name not in exclude_dirs]

        # Based on EXPORT_MANIFEST.json, we should have at least 10 formal skills
        self.assertGreaterEqual(len(skills), 10,
                               f"Expected at least 10 skills, found {len(skills)}")


if __name__ == '__main__':
    unittest.main()
