"""
路径解析器 - 统一管理项目路径配置

支持：
- 自动检测项目根目录
- 环境变量覆盖
- 相对路径自动转换为绝对路径
"""

import os
import re
import yaml
from pathlib import Path
from typing import Dict, Any, Optional


class PathResolver:
    """路径解析器"""

    def __init__(self, config_file: Optional[str] = None):
        self.project_root = self._detect_project_root()
        self.config = self._load_config(config_file)

    def _detect_project_root(self) -> Path:
        """从当前文件向上查找包含 CLAUDE.md 的目录"""
        env_root = os.environ.get("NEWMA_PROJECT_ROOT") or os.environ.get("DASHENG_PROJECT_ROOT")
        if env_root:
            return Path(env_root).expanduser()
        current = Path(__file__).resolve()
        for parent in [current] + list(current.parents):
            if (parent / 'CLAUDE.md').exists():
                return parent
        raise RuntimeError("Cannot detect project root: CLAUDE.md not found")

    def _load_config(self, config_file: Optional[str] = None) -> Dict[str, Any]:
        """加载配置文件"""
        if config_file is None:
            # 优先加载 paths.local.yaml，fallback到 paths.default.yaml
            local_config = self.project_root / 'configs' / 'paths.local.yaml'
            default_config = self.project_root / 'configs' / 'paths.default.yaml'
            config_file = str(local_config if local_config.exists() else default_config)

        with open(config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        # 展开环境变量
        return self._expand_env_vars(config)

    def _expand_env_vars(self, obj: Any) -> Any:
        """递归展开环境变量，支持 ${VAR:-default} 语法"""
        if isinstance(obj, str):
            # 支持 ${VAR:-default} 语法
            pattern = r'\$\{([^:}]+)(?::-(.*?))?\}'

            def replacer(match):
                var_name, default = match.groups()
                value = os.environ.get(var_name)
                if value is None and var_name.startswith("NEWMA_"):
                    legacy_name = "DASHENG_" + var_name[len("NEWMA_"):]
                    value = os.environ.get(legacy_name)
                return value if value is not None else (default or '')

            return re.sub(pattern, replacer, obj)
        elif isinstance(obj, dict):
            return {k: self._expand_env_vars(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._expand_env_vars(item) for item in obj]
        return obj

    def resolve(self, path_key: str) -> Path:
        """
        解析路径键为绝对路径

        Args:
            path_key: 点号分隔的路径键，如 'work_dirs.materials'

        Returns:
            Path: 解析后的绝对路径

        Raises:
            KeyError: 路径键不存在
            ValueError: 路径键不是字符串类型
        """
        # 支持点号路径：work_dirs.materials
        keys = path_key.split('.')
        value = self.config

        try:
            for key in keys:
                value = value[key]
        except (KeyError, TypeError) as e:
            raise KeyError(f"Path key '{path_key}' not found in config") from e

        if isinstance(value, str):
            path = Path(value).expanduser()
            if not path.is_absolute():
                path = self.project_root / path
            return path

        raise ValueError(f"Path key '{path_key}' does not resolve to string, got {type(value)}")

    def get_project_root(self) -> Path:
        """获取项目根目录"""
        return self.project_root


# 全局单例
_resolver: Optional[PathResolver] = None


def get_path_resolver() -> PathResolver:
    """获取全局路径解析器单例"""
    global _resolver
    if _resolver is None:
        _resolver = PathResolver()
    return _resolver


def resolve_path(key: str) -> Path:
    """
    便捷函数：解析路径键为绝对路径

    Args:
        key: 点号分隔的路径键，如 'work_dirs.materials'

    Returns:
        Path: 解析后的绝对路径
    """
    return get_path_resolver().resolve(key)


def get_project_root() -> Path:
    """便捷函数：获取项目根目录"""
    return get_path_resolver().get_project_root()


if __name__ == '__main__':
    # 测试代码
    import sys

    try:
        resolver = PathResolver()
        print(f"项目根目录: {resolver.get_project_root()}")
        print(f"素材目录: {resolver.resolve('work_dirs.materials')}")
        print(f"产物目录: {resolver.resolve('work_dirs.outputs')}")
        print(f"Feishu配置: {resolver.resolve('external.feishu_config')}")
        print("\n✅ 路径解析器测试通过")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 路径解析器测试失败: {e}")
        sys.exit(1)
