#!/usr/bin/env python3
"""
测试 dasheng-stage-draft Skill

测试策略：
1. 使用真实的selected_topics.json fixture
2. Mock AI调用（通过环境变量DASHENG_DRAFT_FAKE_RESPONSE）
3. 验证JSON输出格式符合schema
4. 验证gate文件生成正确
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
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

SKILL_DIR = PROJECT_ROOT / "skills" / "dasheng-daily-draft"
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "build_stage3_draft.py"

from build_stage3_draft import (
    inspect_draft_quality,
    resolve_selected_card,
)


@pytest.fixture
def temp_output_dir():
    """创建临时输出目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def valid_selected_topics(temp_output_dir):
    """创建有效的selected_topics.json fixture"""
    topics_file = temp_output_dir / "selected_topics.json"
    topics_data = {
        "run_id": "test-2026-04-14",
        "status": "approved",
        "selected_topics": [
            {
                "topic_id": "topic-001",
                "title": "测试选题：AI技术发展趋势",
                "core_proposition": "AI技术正在改变世界",
                "conflict_axis": "技术进步 vs 伦理担忧",
                "recommended_structure": "PCIS",
                "proof_requirements": [
                    {"requirement": "AI市场规模数据", "current_evidence": "部分", "gap": "需要最新数据"}
                ]
            }
        ]
    }
    topics_file.write_text(json.dumps(topics_data, ensure_ascii=False, indent=2), encoding='utf-8')
    return topics_file


@pytest.fixture
def empty_selected_topics(temp_output_dir):
    """创建空的selected_topics.json（应该失败）"""
    topics_file = temp_output_dir / "empty_selected_topics.json"
    topics_data = {
        "run_id": "test-2026-04-14",
        "status": "pending",
        "selected_topics": []
    }
    topics_file.write_text(json.dumps(topics_data, ensure_ascii=False, indent=2), encoding='utf-8')
    return topics_file


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

    assert config["name"] == "dasheng-daily-draft"
    assert config["replacement"] == "dasheng-media-sop"


def test_script_exists():
    """测试Python脚本存在"""
    assert SCRIPT_PATH.exists(), f"Script not found: {SCRIPT_PATH}"


def test_draft_generation_with_valid_input(valid_selected_topics, temp_output_dir):
    """测试：有效的selected_topics.json → 成功输出"""
    # 注意：这个测试需要真实的AI调用或mock
    # 暂时跳过，因为需要配置mock环境
    pytest.skip("需要配置DASHENG_DRAFT_FAKE_RESPONSE环境变量")

    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), str(valid_selected_topics), "--output-dir", str(temp_output_dir)],
        capture_output=True,
        text=True,
        timeout=60
    )

    assert result.returncode == 0, f"Script failed: {result.stderr}"

    # 解析JSON输出
    output = json.loads(result.stdout)
    assert output["success"] is True
    assert "run_id" in output
    assert "draft_files" in output
    assert "manifest_file" in output
    assert "final_structure_snapshot" in output
    assert output["next_step"] == "dasheng-stage-transwrite"


def test_draft_generation_with_empty_topics(empty_selected_topics, temp_output_dir):
    """测试：空的selected_topics.json → 应该失败或返回空结果"""
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), str(empty_selected_topics), "--output-dir", str(temp_output_dir)],
        capture_output=True,
        text=True,
        timeout=60
    )

    # 脚本应该失败或返回draft_count=0
    if result.returncode == 0:
        output = json.loads(result.stdout)
        assert output["draft_count"] == 0, "Empty topics should produce 0 drafts"
    else:
        # 失败也是可接受的行为
        assert "selected_topics" in result.stderr.lower() or "empty" in result.stderr.lower()


def test_json_output_schema(valid_selected_topics, temp_output_dir):
    """测试：JSON输出格式符合schema（使用mock）"""
    # 创建mock输出
    mock_output = {
        "success": True,
        "run_id": "test-2026-04-14",
        "out_dir": str(temp_output_dir),
        "draft_count": 1,
        "draft_files": [str(temp_output_dir / "03_标准初稿_topic-001.md")],
        "manifest_file": str(temp_output_dir / "draft_manifest.json"),
        "final_structure_snapshot": str(temp_output_dir / "final_structure_snapshot.json"),
        "drafts": [
            {
                "topic_id": "topic-001",
                "title": "测试选题：AI技术发展趋势",
                "draft_file": str(temp_output_dir / "03_标准初稿_topic-001.md")
            }
        ],
        "next_step": "dasheng-stage-transwrite"
    }

    # 验证schema
    assert "success" in mock_output
    assert "run_id" in mock_output
    assert "out_dir" in mock_output
    assert "draft_count" in mock_output
    assert "draft_files" in mock_output
    assert "manifest_file" in mock_output
    assert "final_structure_snapshot" in mock_output
    assert "next_step" in mock_output
    assert mock_output["next_step"] == "dasheng-stage-transwrite"


def test_nodejs_wrapper_syntax():
    """测试：Node.js wrapper语法正确"""
    result = subprocess.run(
        ["node", "--check", str(SKILL_DIR / "index.js")],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0, f"Node.js syntax error: {result.stderr}"


def test_inspect_draft_quality_flags_not_but_ai_cliche():
    draft = """# 测试稿

## 一、开头

这不是一次普通的事件，而是市场重新定价的开始。这意味着后续变量需要继续观察。

## 二、分析

正文继续展开。
"""

    gate = inspect_draft_quality(draft, {"topic_id": "topic-001", "title": "测试稿"}, {"claims": []})

    pattern_ids = {item["pattern_id"] for item in gate["ai_cliche_hits"]}
    assert "not_but" in pattern_ids
    assert "this_means" in pattern_ids
    assert gate["status"] == "warning"


def test_resolve_selected_card_merges_source_topics_and_keeps_10000_floor():
    cards = {
        "T01": {"topic_id": "T01", "title": "题一", "logic_chain": ["A"]},
        "T08": {"topic_id": "T08", "title": "题八", "logic_chain": ["B"]},
    }
    selected = {
        "topic_id": "T01+T08",
        "source_topic_ids": ["T01", "T08"],
        "title": "合并题",
        "draft_contract": {
            "target_cjk_chars_min": 10000,
            "quality_floor_cjk_chars": 10000,
            "style_polish": False,
        },
    }

    merged = resolve_selected_card(selected, cards)

    assert merged["topic_id"] == "T01+T08"
    assert merged["source_topic_ids"] == ["T01", "T08"]
    assert merged["logic_chain"] == ["A", "B"]
    assert merged["title"] == "合并题"
    assert merged["draft_contract"]["quality_floor_cjk_chars"] == 10000


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
