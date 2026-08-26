#!/usr/bin/env python3
"""
Path Configuration Module
统一管理所有硬编码路径，支持环境变量覆盖

COMPATIBILITY WRAPPER: get_project_root 已委托给 core.path_resolver，
以消除项目根目录检测逻辑的重复。本模块保留其他历史辅助函数以兼容现有脚本。
新代码建议直接使用 core.path_resolver。
"""

import os
import sys
from pathlib import Path

# 将项目根目录加入路径以导入 core.path_resolver（当从 scripts/ 运行时）
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.path_resolver import PathResolver


def _env_path(primary: str, legacy: str, default: Path) -> Path:
    """优先读取 Newma 变量，并兼容旧变量。"""
    return Path(os.getenv(primary) or os.getenv(legacy) or str(default)).expanduser()


def get_project_root() -> Path:
    """
    获取项目根目录

    基于 core.path_resolver.PathResolver，但优先尊重 NEWMA_PROJECT_ROOT 环境变量，
    并在环境变量变化时重新解析，避免单例缓存导致测试失败。
    优先级：
    1. 环境变量 NEWMA_PROJECT_ROOT
    2. 旧环境变量兼容值
    3. 自动检测（查找 CLAUDE.md）
    """
    env_root = os.environ.get("NEWMA_PROJECT_ROOT") or os.environ.get("DASHENG_PROJECT_ROOT")
    if env_root:
        return Path(env_root).expanduser()
    return PathResolver().get_project_root()


def get_desktop_root() -> Path:
    """获取桌面交付根目录（任务文件夹的父目录）"""
    default = Path.home() / "Desktop" / "自媒体创作"
    value = (
        os.getenv("NEWMA_DESKTOP_ROOT")
        or os.getenv("NEWMA_OUTPUT_ROOT")
        or os.getenv("DASHENG_DESKTOP_ROOT")
        or os.getenv("DASHENG_OUTPUT_ROOT")
        or str(default)
    )
    return Path(value).expanduser()


# 六阶段在任务文件夹内的子目录名。
# 桌面结构按任务组织：<desktop>/<run_id>/<环节目录>/，而非旧的按环节分顶层目录。
STAGE_DIR_NAMES: dict[str, str] = {
    "intake": "01_采集",
    "brief": "02_选题",
    "draft": "03_初稿",
    "transwrite": "04_转写",
    "publish": "05_发布",
    "postmortem": "06_复盘",
}


def get_run_root(run_id: str) -> Path:
    """获取任务文件夹根目录：<desktop>/<run_id>"""
    if not run_id:
        raise ValueError("run_id 不能为空")
    return get_desktop_root() / run_id


def get_stage_dir(stage: str, run_id: str) -> Path:
    """获取任务文件夹内的六阶段目录：<desktop>/<run_id>/<01_采集 等>"""
    if stage not in STAGE_DIR_NAMES:
        raise ValueError(f"未知六阶段：{stage}（全局目录请使用 get_output_root）")
    return get_run_root(run_id) / STAGE_DIR_NAMES[stage]


def get_feishu_config_path() -> Path:
    """获取飞书API配置文件路径"""
    default = Path.home() / "clawd" / "configs" / "feishu_api.conf"
    return _env_path("NEWMA_FEISHU_CONFIG", "DASHENG_FEISHU_CONFIG", default)


def get_feishu_bot_config_path() -> Path:
    """获取飞书Bot配置文件路径"""
    root = get_project_root()
    default = root / "configs" / "feishu" / "liweis_bot_config.json"
    return _env_path("NEWMA_FEISHU_BOT_CONFIG", "DASHENG_FEISHU_BOT_CONFIG", default)


def get_feishu_stage_contract_path() -> Path:
    """获取飞书阶段审核合约路径"""
    root = get_project_root()
    default = root / "configs" / "feishu" / "stage_review_contract.json"
    return _env_path("NEWMA_FEISHU_STAGE_CONTRACT", "DASHENG_FEISHU_STAGE_CONTRACT", default)


def get_output_root(stage: str) -> Path:
    """获取非任务级全局输出目录（范式学习/视频训练/热点捕捉/改写等）

    六阶段（intake/brief/draft/transwrite/publish/postmortem）已按任务组织，
    请改用 get_stage_dir(stage, run_id) 或 canonical_workflow.canonical_stage_dir。
    默认输出到 ~/Desktop/自媒体创作/，可通过 NEWMA_OUTPUT_ROOT 环境变量覆盖。
    """
    if stage in STAGE_DIR_NAMES:
        raise ValueError(
            f"六阶段 {stage} 已按任务组织，请使用 get_stage_dir(stage, run_id)"
        )
    output_base = _env_path(
        "NEWMA_OUTPUT_ROOT",
        "DASHENG_OUTPUT_ROOT",
        Path.home() / "Desktop" / "自媒体创作",
    )
    stage_dirs = {
        "paradigm": "00_范式学习",
        "video_training": "00_范式学习/视频训练",
        "rewrite": "00_改写",
        "hotspot": "00_热点捕捉",
    }
    stage_dir = stage_dirs.get(stage, stage)
    return output_base / stage_dir


def get_templates_dir() -> Path:
    """获取模板目录"""
    root = get_project_root()
    return root / "skills" / "dasheng-media-rewrite-v2" / "templates"


def get_skills_dir() -> Path:
    """获取skills目录"""
    root = get_project_root()
    return root / "skills"


def get_scripts_dir() -> Path:
    """获取scripts目录"""
    root = get_project_root()
    return root / "scripts"


def get_engine_dir() -> Path:
    """获取引擎目录"""
    root = get_project_root()
    return root / "引擎"


def get_dna_config_path() -> Path:
    """获取DNA配置文件路径"""
    root = get_project_root()
    return root / "dna" / "dna_config.yaml"


# 环境变量说明
ENV_VARS_HELP = """
Path Configuration Environment Variables:

Core Paths:
  NEWMA_PROJECT_ROOT            - 项目根目录 (default: auto-detect via CLAUDE.md)
  NEWMA_DESKTOP_ROOT            - 桌面交付目录 (default: ~/Desktop/自媒体创作)
  NEWMA_OUTPUT_ROOT             - 产物输出根目录 (default: ~/Desktop/自媒体创作)

Feishu Configuration:
  NEWMA_FEISHU_CONFIG           - 飞书API配置 (default: ~/clawd/configs/feishu_api.conf)
  NEWMA_FEISHU_BOT_CONFIG       - 飞书Bot配置 (default: {PROJECT_ROOT}/configs/feishu/liweis_bot_config.json)
  NEWMA_FEISHU_STAGE_CONTRACT   - 飞书阶段合约 (default: {PROJECT_ROOT}/configs/feishu/stage_review_contract.json)

Usage:
  export NEWMA_PROJECT_ROOT=/path/to/project
  python3 scripts/workflow_doctor.py

Legacy environment names remain runtime aliases during migration.
Note: get_project_root now delegates to core.path_resolver. Prefer core.path_resolver for new code.
"""


if __name__ == "__main__":
    print("Current Path Configuration:")
    print(f"  Project Root: {get_project_root()}")
    print(f"  Desktop Root: {get_desktop_root()}")
    print(f"  Run Root (creator-demo): {get_run_root('creator-demo')}")
    print(f"  Stage Dir (intake): {get_stage_dir('intake', 'creator-demo')}")
    print(f"  Stage Dir (publish): {get_stage_dir('publish', 'creator-demo')}")
    print(f"  Feishu Config: {get_feishu_config_path()}")
    print(f"  Feishu Bot Config: {get_feishu_bot_config_path()}")
    print(f"  Feishu Stage Contract: {get_feishu_stage_contract_path()}")
    print(f"  Templates Dir: {get_templates_dir()}")
    print(f"  Skills Dir: {get_skills_dir()}")
    print(f"  DNA Config: {get_dna_config_path()}")
    print()
    print(ENV_VARS_HELP)
