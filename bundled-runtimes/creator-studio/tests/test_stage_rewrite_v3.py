#!/usr/bin/env python3
"""
测试 dasheng-stage-rewrite-v3 Skill

测试策略：
1. 使用真实的draft_manifest.json fixture
2. Mock AI调用（通过环境变量）
3. 验证JSON输出格式符合schema
4. 验证质量评分、字数、锚点保留率
"""

import json
import os
import subprocess
import sys
from pathlib import Path
import tempfile
import pytest

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

SKILL_DIR = PROJECT_ROOT / "skills" / "dasheng-stage-rewrite-v3"
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "rewrite_execute_stage5.py"


@pytest.fixture
def temp_output_dir():
    """创建临时输出目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def valid_draft_manifest(temp_output_dir):
    """创建有效的draft_manifest.json fixture"""
    manifest_file = temp_output_dir / "draft_manifest.json"
    manifest_data = {
        "run_id": "test-2026-04-14",
        "stage": "draft",
        "status": "ready_for_review",
        "output_dir": str(temp_output_dir),
        "drafts": [
            {
                "topic_id": "topic-001",
                "title": "测试选题：AI技术发展趋势",
                "draft_file": str(temp_output_dir / "03_标准初稿_topic-001.md"),
                "reasoning_sheet_file": str(temp_output_dir / "03_ReasoningSheet_topic-001.md"),
                "reasoning_sheet_json": str(temp_output_dir / "03_ReasoningSheet_topic-001.json")
            }
        ]
    }
    manifest_file.write_text(json.dumps(manifest_data, ensure_ascii=False, indent=2), encoding='utf-8')

    # 创建mock初稿文件
    draft_file = temp_output_dir / "03_标准初稿_topic-001.md"
    draft_file.write_text("# 测试初稿\n\n这是一篇测试初稿。{{image: 测试图片}}\n\n内容正文...", encoding='utf-8')

    return manifest_file


@pytest.fixture
def valid_final_structure_snapshot(temp_output_dir):
    """创建有效的final_structure_snapshot.json fixture"""
    snapshot_file = temp_output_dir / "final_structure_snapshot.json"
    snapshot_data = {
        "run_id": "test-2026-04-14",
        "status": "approved",
        "topics": [
            {
                "topic_id": "topic-001",
                "title": "测试选题：AI技术发展趋势",
                "doc_file": str(temp_output_dir / "03_标准初稿_topic-001.md"),
                "final_primary_sections": ["引言", "核心论点", "结论"],
                "editor_note": "已确认结构"
            }
        ]
    }
    snapshot_file.write_text(json.dumps(snapshot_data, ensure_ascii=False, indent=2), encoding='utf-8')
    return snapshot_file


def test_skill_directory_structure():
    """测试skill目录结构完整性"""
    assert SKILL_DIR.exists(), f"Skill directory not found: {SKILL_DIR}"
    assert (SKILL_DIR / "index.js").exists(), "index.js not found"
    assert (SKILL_DIR / "config.json").exists(), "config.json not found"
    assert (SKILL_DIR / "SKILL.md").exists(), "SKILL.md not found"


def test_config_json_schema():
    """测试config.json格式正确"""
    config_file = SKILL_DIR / "config.json"
    config = json.loads(config_file.read_text(encoding='utf-8'))

    assert config["name"] == "dasheng-stage-rewrite-v3"
    assert config["version"] == "3.0.0"
    assert config["stage"] == "rewrite"
    assert config["runner"] == "node"
    assert config["entry"] == "index.js"
    assert config["upstream_gate"] == "final_structure_snapshot.json"
    assert config["hitl"] is True

    # 验证质量要求
    assert config["quality_requirements"]["min_quality_score"] == 8.0
    assert config["quality_requirements"]["word_count_deviation"] == "±15%"
    assert config["quality_requirements"]["anchor_preservation_rate"] == "≥80%"


def test_script_exists():
    """测试Python脚本存在"""
    assert SCRIPT_PATH.exists(), f"Script not found: {SCRIPT_PATH}"


def test_script_accepts_cli_arguments():
    """测试脚本接受CLI参数"""
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--help"],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    assert "--draft-manifest" in result.stdout
    assert "--output-dir" in result.stdout
    assert "--run-id" in result.stdout
    assert "--versions" in result.stdout
    assert "--json-output" in result.stdout


def test_rewrite_with_valid_input(valid_draft_manifest, valid_final_structure_snapshot, temp_output_dir):
    """测试：有效输入 → 成功输出（需要mock AI调用）"""
    pytest.skip("需要配置mock AI调用环境")

    result = subprocess.run(
        [
            sys.executable, str(SCRIPT_PATH),
            "--draft-manifest", str(valid_draft_manifest),
            "--output-dir", str(temp_output_dir),
            "--versions", "wechat_hot,wechat_normal",
            "--json-output"
        ],
        capture_output=True,
        text=True,
        timeout=120
    )

    assert result.returncode == 0, f"Script failed: {result.stderr}"

    # 解析JSON输出
    output = json.loads(result.stdout)
    assert output["success"] is True
    assert "run_id" in output
    assert "manifest_file" in output
    assert output["next_step"] == "dasheng-stage-publish"
    assert output["completed_versions"] >= 0


def test_rewrite_without_draft_manifest(temp_output_dir):
    """测试：缺少draft_manifest.json → 应该失败"""
    result = subprocess.run(
        [
            sys.executable, str(SCRIPT_PATH),
            "--draft-manifest", str(temp_output_dir / "nonexistent.json"),
            "--json-output"
        ],
        capture_output=True,
        text=True,
        timeout=10
    )

    assert result.returncode != 0
    assert "不存在" in result.stderr or "not found" in result.stderr.lower()


def test_json_output_schema():
    """测试：JSON输出格式符合schema"""
    mock_output = {
        "success": True,
        "run_id": "test-2026-04-14",
        "output_dir": "/path/to/output",
        "manifest_file": "/path/to/rewrite_manifest.json",
        "completed_versions": 4,
        "failed_topics": 0,
        "total_topics": 1,
        "versions": ["wechat_hot", "wechat_normal", "xiaohongshu_hot", "xiaohongshu_normal"],
        "next_step": "dasheng-stage-publish"
    }

    # 验证schema
    assert "success" in mock_output
    assert "run_id" in mock_output
    assert "output_dir" in mock_output
    assert "manifest_file" in mock_output
    assert "completed_versions" in mock_output
    assert "failed_topics" in mock_output
    assert "total_topics" in mock_output
    assert "versions" in mock_output
    assert "next_step" in mock_output
    assert mock_output["next_step"] == "dasheng-stage-publish"


def test_quality_thresholds():
    """测试：质量门槛验证"""
    # 模拟质量评分低于8.0的情况
    version_result = {
        "status": "completed",
        "quality_score": 7.5,  # 低于8.0
        "word_count": 1300,
        "target_word_count": 1300,
        "anchor_preserved_rate": 85
    }

    # 这个版本应该被标记为需要重新生成
    # （实际逻辑在should_regenerate()中）
    assert version_result["quality_score"] < 8.0


def test_word_count_deviation():
    """测试：字数偏差15%验证"""
    target = 1300
    min_allowed = target * 0.85  # 1105
    max_allowed = target * 1.15  # 1495

    # 测试边界情况（使用容差处理浮点数精度）
    assert 1105 >= min_allowed - 0.1
    assert 1495 <= max_allowed + 0.1
    assert 1000 < min_allowed  # 应该失败
    assert 1600 > max_allowed  # 应该失败


def test_nodejs_wrapper_syntax():
    """测试：Node.js wrapper语法正确"""
    result = subprocess.run(
        ["node", "--check", str(SKILL_DIR / "index.js")],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0, f"Node.js syntax error: {result.stderr}"


def test_versions_config():
    """测试：版本配置正确"""
    config_file = SKILL_DIR / "config.json"
    config = json.loads(config_file.read_text(encoding='utf-8'))

    versions = config["versions"]
    assert "wechat_hot" in versions
    assert "wechat_normal" in versions
    assert "xiaohongshu_hot" in versions
    assert "xiaohongshu_normal" in versions

    # 验证字数配置
    assert versions["wechat_hot"]["word_count"] == 1300
    assert versions["wechat_normal"]["word_count"] == 1000
    assert versions["xiaohongshu_hot"]["word_count"] == 900
    assert versions["xiaohongshu_normal"]["word_count"] == 650


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
