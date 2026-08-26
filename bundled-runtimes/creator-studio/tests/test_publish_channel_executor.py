#!/usr/bin/env python3
"""
测试 Publish Channel Executor

测试策略：
1. Mock skill_invoker 返回值
2. 验证executor正确构建payload
3. 验证executor正确解析返回
4. 测试发布验证逻辑
5. 测试fallback机制
"""

import json
import sys
from pathlib import Path
from unittest.mock import Mock, patch
import pytest

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from publish_channel_executor import ChannelExecutor


@pytest.fixture
def mock_invoker():
    """创建mock invoker"""
    invoker = Mock()
    return invoker


def test_publish_to_wechat_draft_success(mock_invoker):
    """测试：微信发布到草稿箱成功"""
    mock_invoker.invoke.return_value = {
        "success": True,
        "url": "https://mp.weixin.qq.com/draft/123",
        "msg_id": "draft_123",
    }

    executor = ChannelExecutor(mock_invoker)
    result = executor.publish_to_wechat(
        content_file="/path/to/article.md",
        title="测试文章",
        cover_path="/path/to/cover.png",
        mode="draft",
    )

    # 验证调用参数
    mock_invoker.invoke.assert_called_once()
    call_args = mock_invoker.invoke.call_args
    assert call_args[0][0] == "wechat-mp-publisher"
    assert call_args[0][1]["title"] == "测试文章"
    assert call_args[0][1]["mode"] == "draft"

    # 验证返回值
    assert result["success"] is True
    assert result["platform"] == "wechat"
    assert result["status"] == "draft"
    assert result["msg_id"] == "draft_123"


def test_publish_to_wechat_publish_mode(mock_invoker):
    """测试：微信直接发布模式"""
    mock_invoker.invoke.return_value = {
        "success": True,
        "url": "https://mp.weixin.qq.com/s/abc123",
        "msg_id": "msg_123",
    }

    executor = ChannelExecutor(mock_invoker)
    result = executor.publish_to_wechat(
        content_file="/path/to/article.md",
        title="测试文章",
        mode="publish",
    )

    assert result["status"] == "published"


def test_publish_to_wechat_fallback(mock_invoker):
    """测试：微信发布fallback机制"""
    # 第一次调用失败，第二次成功
    mock_invoker.invoke.side_effect = [
        {"success": False, "error": "wechat-mp-publisher not found"},
        {"success": True, "url": "https://mp.weixin.qq.com/draft/456", "msg_id": "draft_456"},
    ]

    executor = ChannelExecutor(mock_invoker)
    result = executor.publish_to_wechat(
        content_file="/path/to/article.md",
        title="测试文章",
        mode="draft",
    )

    # 验证调用了两次（第一次失败，fallback到第二个skill）
    assert mock_invoker.invoke.call_count == 2
    assert result["success"] is True


def test_publish_to_wechat_all_failed(mock_invoker):
    """测试：微信发布所有方式都失败"""
    mock_invoker.invoke.side_effect = [
        {"success": False, "error": "wechat-mp-publisher failed"},
        {"success": False, "error": "baoyu-post-to-wechat failed"},
    ]

    executor = ChannelExecutor(mock_invoker)
    result = executor.publish_to_wechat(
        content_file="/path/to/article.md",
        title="测试文章",
    )

    assert result["success"] is False
    assert "error" in result


def test_publish_to_weibo_success(mock_invoker):
    """测试：微博发布成功"""
    mock_invoker.invoke.return_value = {
        "success": True,
        "url": "https://weibo.com/123456",
    }

    executor = ChannelExecutor(mock_invoker)
    result = executor.publish_to_weibo(
        content_file="/path/to/content.txt",
        images=["/path/to/img1.png", "/path/to/img2.png"],
    )

    # 验证调用参数
    call_args = mock_invoker.invoke.call_args
    assert call_args[0][0] == "baoyu-post-to-weibo"
    assert len(call_args[0][1]["images"]) == 2

    # 验证返回值
    assert result["success"] is True
    assert result["platform"] == "weibo"
    assert result["status"] == "published"
    assert result["url"] == "https://weibo.com/123456"


def test_publish_to_xhs_manual_required(mock_invoker):
    """测试：小红书发布（需要手动）"""
    executor = ChannelExecutor(mock_invoker)
    result = executor.publish_to_xhs(
        content_file="/path/to/content.md",
        images=["/path/to/img1.png"],
    )

    # 小红书不调用skill，直接返回manual_required
    mock_invoker.invoke.assert_not_called()

    assert result["success"] is True
    assert result["platform"] == "xhs"
    assert result["status"] == "manual_required"
    assert "package_path" in result


def test_run_publish_guard_all_success(mock_invoker):
    """测试：发布验证 - 全部成功"""
    executor = ChannelExecutor(mock_invoker)

    execution_results = [
        {"success": True, "platform": "wechat", "status": "draft", "url": ""},
        {"success": True, "platform": "weibo", "status": "published", "url": "https://weibo.com/123"},
        {"success": True, "platform": "xhs", "status": "manual_required", "package_path": "/path"},
    ]

    guard_result = executor.run_publish_guard(execution_results)

    assert guard_result["all_verified"] is True
    assert len(guard_result["results"]) == 3
    assert all(r["verified"] for r in guard_result["results"])


def test_run_publish_guard_partial_failure(mock_invoker):
    """测试：发布验证 - 部分失败"""
    executor = ChannelExecutor(mock_invoker)

    execution_results = [
        {"success": True, "platform": "wechat", "status": "draft", "url": ""},
        {"success": False, "platform": "weibo", "error": "API quota exceeded"},
    ]

    guard_result = executor.run_publish_guard(execution_results)

    assert guard_result["all_verified"] is False
    assert len(guard_result["results"]) == 2
    assert guard_result["results"][0]["verified"] is True
    assert guard_result["results"][1]["verified"] is False
    assert "error" in guard_result["results"][1]


def test_run_publish_guard_published_with_url(mock_invoker):
    """测试：发布验证 - 已发布且有URL"""
    executor = ChannelExecutor(mock_invoker)

    execution_results = [
        {"success": True, "platform": "weibo", "status": "published", "url": "https://weibo.com/123"},
    ]

    guard_result = executor.run_publish_guard(execution_results)

    assert guard_result["all_verified"] is True
    assert guard_result["results"][0]["verified"] is True
    assert guard_result["results"][0]["accessible"] is True
    assert guard_result["results"][0]["url"] == "https://weibo.com/123"


def test_exception_handling(mock_invoker):
    """测试：异常处理"""
    mock_invoker.invoke.side_effect = Exception("Network error")

    executor = ChannelExecutor(mock_invoker)
    result = executor.publish_to_wechat(
        content_file="/path/to/article.md",
        title="测试",
    )

    assert result["success"] is False
    assert "Network error" in result["error"]


def test_default_parameters(mock_invoker):
    """测试：默认参数"""
    mock_invoker.invoke.return_value = {"success": True}

    executor = ChannelExecutor(mock_invoker)

    # 测试微信默认mode=draft
    executor.publish_to_wechat("/path/to/article.md", "标题")
    call_args = mock_invoker.invoke.call_args
    assert call_args[0][1]["mode"] == "draft"

    # 测试微博默认images=[]
    executor.publish_to_weibo("/path/to/content.txt")
    call_args = mock_invoker.invoke.call_args
    assert call_args[0][1]["images"] == []


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
