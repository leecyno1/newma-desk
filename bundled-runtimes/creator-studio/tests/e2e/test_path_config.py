#!/usr/bin/env python3
"""
端到端测试：路径配置系统
验证 NEWMA 环境变量覆盖和旧变量兼容功能
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))


class TestPathConfig(unittest.TestCase):
    """测试路径配置系统的环境变量覆盖功能"""

    def setUp(self):
        """保存原始环境变量"""
        self.original_env = os.environ.get('NEWMA_PROJECT_ROOT')

    def tearDown(self):
        """恢复原始环境变量"""
        env_vars = [
            'NEWMA_PROJECT_ROOT',
            'NEWMA_DESKTOP_ROOT',
            'NEWMA_OUTPUT_ROOT',
            'DASHENG_PROJECT_ROOT',
            'DASHENG_DESKTOP_ROOT',
            'DASHENG_OUTPUT_ROOT',
        ]
        for var in env_vars:
            if var in os.environ:
                del os.environ[var]

    def test_env_override_basic(self):
        """测试基本的环境变量覆盖"""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ['NEWMA_PROJECT_ROOT'] = tmpdir

            # Import after setting env var
            import path_config
            from importlib import reload
            reload(path_config)

            # Verify project root is set correctly
            project_root = path_config.get_project_root()
            self.assertEqual(str(project_root), tmpdir)

    def test_resolve_path_with_override(self):
        """NEWMA 变量优先于旧兼容变量"""
        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as legacy_dir:
            os.environ['NEWMA_PROJECT_ROOT'] = tmpdir
            os.environ['DASHENG_PROJECT_ROOT'] = legacy_dir

            import path_config
            from importlib import reload
            reload(path_config)

            # Test get_project_root
            project_root = path_config.get_project_root()
            self.assertEqual(str(project_root), tmpdir)

    def test_output_paths_configurable(self):
        """测试输出路径可配置"""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ['NEWMA_DESKTOP_ROOT'] = tmpdir

            import path_config
            from importlib import reload
            reload(path_config)

            # Check desktop root path
            desktop_root = path_config.get_desktop_root()
            self.assertEqual(str(desktop_root), tmpdir)

    def test_legacy_env_remains_compatible(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ['DASHENG_PROJECT_ROOT'] = tmpdir

            import path_config
            from importlib import reload
            reload(path_config)

            self.assertEqual(str(path_config.get_project_root()), tmpdir)

    def test_core_resolver_maps_legacy_output_env_to_newma_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ['DASHENG_OUTPUT_ROOT'] = tmpdir

            from core.path_resolver import PathResolver

            resolver = PathResolver()
            self.assertEqual(resolver.resolve('work_dirs.outputs'), Path(tmpdir))


if __name__ == '__main__':
    unittest.main()
