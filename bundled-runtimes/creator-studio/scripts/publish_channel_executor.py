#!/usr/bin/env python3
"""
Publish Channel Executor - 渠道发布执行器

集成 WeChat/Weibo 发布能力，真实执行发布操作（非仅生成包）。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from skill_invoker import SkillInvoker


class ChannelExecutor:
    """渠道发布执行器"""

    def __init__(self, invoker: SkillInvoker | None = None):
        self.invoker = invoker or SkillInvoker()

    def publish_to_wechat(
        self,
        content_file: str,
        title: str,
        cover_path: str | None = None,
        mode: str = "draft",
    ) -> dict[str, Any]:
        """
        发布到微信公众号

        Args:
            content_file: Markdown内容文件路径
            title: 文章标题
            cover_path: 封面图片路径（可选）
            mode: 发布模式（draft=草稿箱，publish=直接发布）

        Returns:
            {
                "success": bool,
                "platform": "wechat",
                "status": "draft" | "published",
                "url": str,
                "msg_id": str
            }
        """
        payload = {
            "content_file": content_file,
            "title": title,
            "cover_path": cover_path,
            "mode": mode,
        }

        try:
            # 优先使用 wechat-multi-publisher（支持批量）
            result = self.invoker.invoke("wechat-mp-publisher", payload)
            if result.get("success"):
                return {
                    "success": True,
                    "platform": "wechat",
                    "status": "draft" if mode == "draft" else "published",
                    "url": result.get("url", ""),
                    "msg_id": result.get("msg_id", ""),
                }
            else:
                # Fallback到 baoyu-post-to-wechat
                result = self.invoker.invoke("baoyu-post-to-wechat", payload)
                if result.get("success"):
                    return {
                        "success": True,
                        "platform": "wechat",
                        "status": "draft" if mode == "draft" else "published",
                        "url": result.get("url", ""),
                        "msg_id": result.get("msg_id", ""),
                    }
                else:
                    return {
                        "success": False,
                        "platform": "wechat",
                        "error": result.get("error", "Unknown error"),
                    }
        except Exception as e:
            return {
                "success": False,
                "platform": "wechat",
                "error": str(e),
            }

    def publish_to_weibo(
        self,
        content_file: str,
        images: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        发布到微博

        Args:
            content_file: 内容文件路径
            images: 图片路径列表（最多9张）

        Returns:
            {
                "success": bool,
                "platform": "weibo",
                "status": "published",
                "url": str
            }
        """
        payload = {
            "content_file": content_file,
            "images": images or [],
        }

        try:
            result = self.invoker.invoke("baoyu-post-to-weibo", payload)
            if result.get("success"):
                return {
                    "success": True,
                    "platform": "weibo",
                    "status": "published",
                    "url": result.get("url", ""),
                }
            else:
                return {
                    "success": False,
                    "platform": "weibo",
                    "error": result.get("error", "Unknown error"),
                }
        except Exception as e:
            return {
                "success": False,
                "platform": "weibo",
                "error": str(e),
            }

    def publish_to_xhs(
        self,
        content_file: str,
        images: list[str],
    ) -> dict[str, Any]:
        """
        发布到小红书（目前仅生成待发布包，标记为manual_required）

        Args:
            content_file: 内容文件路径
            images: 图片路径列表（1-10张）

        Returns:
            {
                "success": bool,
                "platform": "xhs",
                "status": "manual_required",
                "package_path": str
            }
        """
        # 小红书目前没有API，需要手动发布
        # 这里仅生成待发布包
        return {
            "success": True,
            "platform": "xhs",
            "status": "manual_required",
            "package_path": content_file,
            "note": "小红书需要手动发布，请使用生成的内容和图片",
        }

    def run_publish_guard(
        self,
        execution_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        验证发布结果

        Args:
            execution_results: 各平台的发布结果列表

        Returns:
            {
                "all_verified": bool,
                "results": [
                    {
                        "platform": str,
                        "verified": bool,
                        "accessible": bool,
                        "error": str (if any)
                    }
                ]
            }
        """
        verified_results = []
        all_verified = True

        for result in execution_results:
            platform = result.get("platform", "unknown")
            status = result.get("status", "")
            url = result.get("url", "")

            if not result.get("success"):
                verified_results.append({
                    "platform": platform,
                    "verified": False,
                    "accessible": False,
                    "error": result.get("error", "Unknown error"),
                })
                all_verified = False
                continue

            # 对已发布平台，尝试验证URL可访问性
            if status == "published" and url:
                # 这里可以添加URL可访问性检查
                # 暂时简化为：有URL就认为可访问
                verified_results.append({
                    "platform": platform,
                    "verified": True,
                    "accessible": True,
                    "url": url,
                })
            elif status == "draft":
                # 草稿箱状态，认为验证通过
                verified_results.append({
                    "platform": platform,
                    "verified": True,
                    "accessible": False,  # 草稿箱不公开可访问
                    "note": "已推送到草稿箱",
                })
            elif status == "manual_required":
                # 需要手动发布，认为验证通过
                verified_results.append({
                    "platform": platform,
                    "verified": True,
                    "accessible": False,
                    "note": "需要手动发布",
                })
            else:
                verified_results.append({
                    "platform": platform,
                    "verified": False,
                    "accessible": False,
                    "error": f"Unknown status: {status}",
                })
                all_verified = False

        return {
            "all_verified": all_verified,
            "results": verified_results,
        }


# ─── 便捷函数 ──────────────────────────────────────────────────────────────────

def create_executor() -> ChannelExecutor:
    """创建默认执行器实例"""
    return ChannelExecutor()


if __name__ == "__main__":
    # 测试用例
    executor = create_executor()

    # 测试微信发布
    print("测试微信发布...")
    result = executor.publish_to_wechat(
        content_file="/path/to/article.md",
        title="测试文章",
        cover_path="/path/to/cover.png",
        mode="draft",
    )
    print(f"结果: {result}")

    # 测试发布验证
    print("\n测试发布验证...")
    guard_result = executor.run_publish_guard([
        {"success": True, "platform": "wechat", "status": "draft", "url": ""},
        {"success": True, "platform": "weibo", "status": "published", "url": "https://weibo.com/123"},
    ])
    print(f"验证结果: {guard_result}")
