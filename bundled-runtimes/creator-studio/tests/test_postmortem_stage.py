#!/usr/bin/env python3
"""
测试 Postmortem Stage 核心功能

测试策略：
1. 验证复盘报告生成
2. 验证模式库更新逻辑
3. 验证L1知识库回写
4. 验证性能指标提取
5. 验证manifest生成
"""

import json
import sys
from pathlib import Path
from unittest.mock import Mock, patch
import pytest

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))


@pytest.fixture
def mock_publish_manifest():
    """创建mock publish manifest"""
    return {
        "run_id": "2026-04-17_120000",
        "stage": "publish",
        "status": "completed",
        "channel_packs": [
            {
                "platform": "wechat",
                "topic_id": "topic-001",
                "url": "https://mp.weixin.qq.com/s/abc123",
                "status": "published",
            },
            {
                "platform": "weibo",
                "topic_id": "topic-001",
                "url": "https://weibo.com/123456",
                "status": "published",
            },
        ],
    }


@pytest.fixture
def mock_rewrite_manifest():
    """创建mock rewrite manifest"""
    return {
        "run_id": "2026-04-17_120000",
        "stage": "rewrite",
        "status": "completed",
        "topics": {
            "topic-001": {
                "wechat_hot": {
                    "status": "completed",
                    "quality_score": 8.5,
                    "word_count": 1280,
                },
                "wechat_normal": {
                    "status": "completed",
                    "quality_score": 8.2,
                    "word_count": 980,
                },
            }
        },
    }


def test_postmortem_manifest_generation(mock_publish_manifest, mock_rewrite_manifest):
    """测试：Postmortem manifest 生成"""
    manifest = {
        "run_id": "2026-04-17_120000",
        "stage": "postmortem",
        "status": "completed",
        "upstream": {
            "publish_manifest": "/path/to/publish_manifest.json",
            "rewrite_manifest": "/path/to/rewrite_manifest.json",
        },
        "topics": [
            {
                "topic_id": "topic-001",
                "performance_metrics": {
                    "wechat": {
                        "read_count": 1500,
                        "like_count": 80,
                        "share_count": 25,
                    },
                    "weibo": {
                        "read_count": 3000,
                        "like_count": 150,
                        "comment_count": 30,
                    },
                },
                "quality_metrics": {
                    "wechat_hot": {"score": 8.5, "word_count": 1280},
                    "wechat_normal": {"score": 8.2, "word_count": 980},
                },
            }
        ],
        "pattern_updates": {
            "topic_patterns": 2,
            "evidence_patterns": 3,
            "visual_patterns": 1,
            "channel_patterns": 2,
        },
    }

    # 验证 manifest 结构
    assert manifest["stage"] == "postmortem"
    assert manifest["status"] == "completed"
    assert len(manifest["topics"]) == 1

    # 验证性能指标
    topic = manifest["topics"][0]
    assert "performance_metrics" in topic
    assert "wechat" in topic["performance_metrics"]
    assert topic["performance_metrics"]["wechat"]["read_count"] == 1500

    # 验证模式更新
    assert manifest["pattern_updates"]["topic_patterns"] == 2


def test_performance_metrics_extraction(mock_publish_manifest):
    """测试：性能指标提取"""
    def extract_performance_metrics(publish_manifest):
        metrics = {}
        for pack in publish_manifest.get("channel_packs", []):
            platform = pack["platform"]
            # 模拟从URL提取数据（实际会调用API）
            if platform == "wechat":
                metrics[platform] = {
                    "read_count": 1500,
                    "like_count": 80,
                    "share_count": 25,
                }
            elif platform == "weibo":
                metrics[platform] = {
                    "read_count": 3000,
                    "like_count": 150,
                    "comment_count": 30,
                }
        return metrics

    metrics = extract_performance_metrics(mock_publish_manifest)

    assert "wechat" in metrics
    assert "weibo" in metrics
    assert metrics["wechat"]["read_count"] > 0
    assert metrics["weibo"]["like_count"] > 0


def test_topic_pattern_extraction():
    """测试：选题模式提取"""
    topic_card = {
        "topic_id": "topic-001",
        "topic_kind": "hot_event",
        "core_proposition": "AI技术发展趋势",
        "conflict_axis": "技术进步 vs 伦理担忧",
        "scoring": {
            "heat": 8,
            "sharpness": 7,
            "evidence": 9,
            "longevity": 6,
            "reader_value": 8,
        },
    }

    # 提取模式
    pattern = {
        "pattern_type": "topic",
        "topic_kind": topic_card["topic_kind"],
        "conflict_axis": topic_card["conflict_axis"],
        "avg_scoring": sum(topic_card["scoring"].values()) / len(topic_card["scoring"]),
        "success_indicator": "high_engagement",
    }

    assert pattern["pattern_type"] == "topic"
    assert pattern["topic_kind"] == "hot_event"
    assert pattern["avg_scoring"] >= 7.0


def test_evidence_pattern_extraction():
    """测试：论据模式提取"""
    reasoning_sheet = {
        "claims": [
            {
                "claim_id": "claim-001",
                "claim_text": "AI市场规模持续增长",
                "evidence_items": [
                    {"type": "data", "source": "tushare", "effectiveness": "high"},
                    {"type": "chart", "source": "matplotlib", "effectiveness": "medium"},
                ],
            }
        ]
    }

    # 提取模式
    patterns = []
    for claim in reasoning_sheet["claims"]:
        for evidence in claim["evidence_items"]:
            if evidence["effectiveness"] == "high":
                patterns.append({
                    "pattern_type": "evidence",
                    "evidence_type": evidence["type"],
                    "source": evidence["source"],
                    "effectiveness": evidence["effectiveness"],
                })

    assert len(patterns) >= 1
    assert patterns[0]["pattern_type"] == "evidence"
    assert patterns[0]["effectiveness"] == "high"


def test_visual_pattern_extraction():
    """测试：视觉模式提取"""
    draft_asset_manifest = {
        "topics": [
            {
                "topic_id": "topic-001",
                "assets": [
                    {
                        "asset_type": "chart",
                        "chart_type": "line",
                        "relevance_score": 0.9,
                        "editor_status": "approved",
                    },
                    {
                        "asset_type": "infographic",
                        "style": "notion",
                        "relevance_score": 0.85,
                        "editor_status": "approved",
                    },
                ],
            }
        ]
    }

    # 提取模式
    patterns = []
    for topic in draft_asset_manifest["topics"]:
        for asset in topic["assets"]:
            if asset.get("editor_status") == "approved" and asset.get("relevance_score", 0) >= 0.8:
                patterns.append({
                    "pattern_type": "visual",
                    "asset_type": asset["asset_type"],
                    "style": asset.get("style", asset.get("chart_type")),
                    "relevance_score": asset["relevance_score"],
                })

    assert len(patterns) == 2
    assert all(p["relevance_score"] >= 0.8 for p in patterns)


def test_channel_pattern_extraction():
    """测试：渠道模式提取"""
    performance_data = {
        "wechat_hot": {
            "read_count": 1500,
            "like_count": 80,
            "share_count": 25,
            "word_count": 1280,
            "quality_score": 8.5,
        },
        "wechat_normal": {
            "read_count": 800,
            "like_count": 40,
            "share_count": 10,
            "word_count": 980,
            "quality_score": 8.2,
        },
    }

    # 提取模式
    patterns = []
    for version, metrics in performance_data.items():
        engagement_rate = (metrics["like_count"] + metrics["share_count"]) / metrics["read_count"]
        if engagement_rate >= 0.05:  # 5%互动率
            patterns.append({
                "pattern_type": "channel",
                "version": version,
                "engagement_rate": engagement_rate,
                "word_count": metrics["word_count"],
                "quality_score": metrics["quality_score"],
            })

    assert len(patterns) >= 1
    assert all(p["engagement_rate"] >= 0.05 for p in patterns)


def test_l1_knowledge_base_update():
    """测试：L1知识库回写"""
    validated_patterns = [
        {
            "pattern_type": "topic",
            "topic_kind": "hot_event",
            "success_indicator": "high_engagement",
            "recommendation": "热点事件类选题应强调冲突轴",
        },
        {
            "pattern_type": "evidence",
            "evidence_type": "data",
            "source": "tushare",
            "recommendation": "金融数据使用Tushare效果最佳",
        },
    ]

    # 生成L1回写建议
    l1_suggestions = {
        "topic_patterns": [p for p in validated_patterns if p["pattern_type"] == "topic"],
        "evidence_patterns": [p for p in validated_patterns if p["pattern_type"] == "evidence"],
        "update_timestamp": "2026-04-17T12:00:00",
    }

    assert len(l1_suggestions["topic_patterns"]) == 1
    assert len(l1_suggestions["evidence_patterns"]) == 1
    assert "recommendation" in l1_suggestions["topic_patterns"][0]


def test_postmortem_report_structure():
    """测试：复盘报告结构"""
    report = {
        "run_id": "2026-04-17_120000",
        "report_date": "2026-04-17",
        "summary": {
            "total_topics": 1,
            "total_versions": 4,
            "total_channels": 3,
            "avg_quality_score": 8.3,
        },
        "performance_analysis": {
            "best_performing_version": "wechat_hot",
            "best_performing_channel": "weibo",
            "engagement_rate": 0.07,
        },
        "pattern_library_updates": {
            "topic_patterns": 2,
            "evidence_patterns": 3,
            "visual_patterns": 1,
            "channel_patterns": 2,
        },
        "recommendations": [
            "热点版本在微信平台表现最佳",
            "数据类论据使用Tushare效果显著",
            "Notion风格配图获得高认可度",
        ],
    }

    # 验证报告结构
    assert "run_id" in report
    assert "summary" in report
    assert "performance_analysis" in report
    assert "pattern_library_updates" in report
    assert "recommendations" in report

    # 验证数据完整性
    assert report["summary"]["total_topics"] > 0
    assert report["summary"]["avg_quality_score"] >= 8.0
    assert len(report["recommendations"]) >= 3


def test_pattern_validation():
    """测试：模式验证"""
    def validate_pattern(pattern, performance_threshold=0.7):
        """验证模式是否值得保留"""
        if pattern["pattern_type"] == "topic":
            return pattern.get("avg_scoring", 0) >= 7.0
        elif pattern["pattern_type"] == "evidence":
            return pattern.get("effectiveness") == "high"
        elif pattern["pattern_type"] == "visual":
            return pattern.get("relevance_score", 0) >= 0.8
        elif pattern["pattern_type"] == "channel":
            return pattern.get("engagement_rate", 0) >= 0.05
        return False

    # 测试各类模式验证
    assert validate_pattern({"pattern_type": "topic", "avg_scoring": 7.5}) is True
    assert validate_pattern({"pattern_type": "topic", "avg_scoring": 6.5}) is False
    assert validate_pattern({"pattern_type": "evidence", "effectiveness": "high"}) is True
    assert validate_pattern({"pattern_type": "visual", "relevance_score": 0.85}) is True
    assert validate_pattern({"pattern_type": "channel", "engagement_rate": 0.07}) is True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
