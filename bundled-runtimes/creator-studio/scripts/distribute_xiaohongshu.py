#!/usr/bin/env python3
"""
小红书自动发布脚本
从 rewrite_manifest.json 读取内容和元数据，调用 xiaohongshu-auto skill 发布
"""

import json
import os
import sys
import time
import random
import subprocess
from pathlib import Path
from datetime import datetime

from path_config import get_output_root

def load_rewrite_manifest(run_id: str, workspace: str) -> dict:
    """加载 rewrite manifest"""
    manifest_path = Path(workspace) / "06_改写" / run_id / "rewrite_manifest.json"

    if not manifest_path.exists():
        raise FileNotFoundError(f"Rewrite manifest not found: {manifest_path}")

    with open(manifest_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_video_manifest(run_id: str, workspace: str) -> dict:
    """加载 video manifest（可选）"""
    manifest_path = Path(workspace) / run_id / "05_发布" / "publish_video_supplement_manifest.json"

    if not manifest_path.exists():
        print(f"⚠️  Video manifest not found: {manifest_path}")
        return None

    with open(manifest_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def find_video_for_topic(topic_id: str, video_manifest: dict) -> str:
    """查找选题对应的视频文件"""
    if not video_manifest:
        return None

    # 查找 motion_narrative 视频
    for topic_data in video_manifest.get('topics', []):
        if topic_data.get('topic_id') == topic_id:
            videos = topic_data.get('videos', {}).get('motion_narrative', [])
            if videos:
                return videos[0].get('path')

    return None

def publish_to_xiaohongshu(
    title: str,
    content: str,
    cover_text: str,
    hashtags: list,
    video_path: str = None,
    image_paths: list = None
) -> dict:
    """
    调用 xiaohongshu-auto skill 发布内容

    Args:
        title: 标题（≤20字）
        content: 正文内容
        cover_text: 封面文案（前300字）
        hashtags: 话题标签列表（5-8个）
        video_path: 视频文件路径（可选）
        image_paths: 图片文件路径列表（可选）

    Returns:
        发布结果字典
    """

    # 构建发布命令
    # 注意：这里需要根据 xiaohongshu-auto 的实际 API 调整

    # 方案 1: 如果 xiaohongshu-auto 支持命令行
    cmd = [
        "openclaw", "skill", "xiaohongshu-auto", "publish",
        "--title", title,
        "--content", content,
        "--cover-text", cover_text,
    ]

    # 添加话题标签
    for tag in hashtags:
        cmd.extend(["--hashtag", tag])

    # 添加视频或图片
    if video_path:
        cmd.extend(["--video", video_path])
    elif image_paths:
        for img in image_paths:
            cmd.extend(["--image", img])

    print(f"📤 执行发布命令: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5分钟超时
        )

        if result.returncode == 0:
            return {
                "success": True,
                "stdout": result.stdout,
                "stderr": result.stderr
            }
        else:
            return {
                "success": False,
                "error": result.stderr,
                "stdout": result.stdout
            }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "发布超时（5分钟）"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

def main():
    """主函数"""

    if len(sys.argv) < 2:
        print("Usage: python3 distribute_xiaohongshu.py <run_id> [--dry-run]")
        sys.exit(1)

    run_id = sys.argv[1]
    dry_run = "--dry-run" in sys.argv

    workspace = os.getenv("DASHENG_WORKSPACE", str(get_output_root("publish").parent))

    print(f"🚀 开始小红书分发流程")
    print(f"   Run ID: {run_id}")
    print(f"   Workspace: {workspace}")
    print(f"   Dry Run: {dry_run}")
    print()

    # 1. 加载 manifests
    print("📖 加载 manifests...")
    rewrite_manifest = load_rewrite_manifest(run_id, workspace)
    video_manifest = load_video_manifest(run_id, workspace)

    # 2. 提取小红书变体
    topics = rewrite_manifest.get('topics', [])
    xhs_posts = []

    for topic in topics:
        topic_id = topic.get('topic_id')
        topic_title = topic.get('topic_title')

        # 查找 xhs_video_luxun_hot 变体
        variants = topic.get('variants', [])
        xhs_variant = None

        for variant in variants:
            if variant.get('variant_id') == 'xhs_video_luxun_hot':
                xhs_variant = variant
                break

        if not xhs_variant:
            print(f"⚠️  选题 {topic_id} 没有 xhs_video_luxun_hot 变体，跳过")
            continue

        # 读取内容文件
        content_path = Path(workspace) / xhs_variant.get('file_path')
        if not content_path.exists():
            print(f"⚠️  内容文件不存在: {content_path}，跳过")
            continue

        with open(content_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 提取元数据
        metadata = xhs_variant.get('platform_metadata', {})
        title = metadata.get('title', topic_title[:20])  # 确保 ≤20字
        hashtags = metadata.get('hashtags', [])
        cover_text = metadata.get('cover_text', content[:300])

        # 查找视频
        video_path = find_video_for_topic(topic_id, video_manifest)

        xhs_posts.append({
            'topic_id': topic_id,
            'topic_title': topic_title,
            'title': title,
            'content': content,
            'cover_text': cover_text,
            'hashtags': hashtags,
            'video_path': video_path
        })

    if not xhs_posts:
        print("❌ 没有找到可发布的小红书内容")
        sys.exit(1)

    # 3. 展示发布计划
    print()
    print("=" * 60)
    print("              小红书发布计划")
    print("=" * 60)
    for i, post in enumerate(xhs_posts, 1):
        print(f"{i}. {post['topic_title']}")
        print(f"   标题: {post['title']}")
        print(f"   话题: {', '.join(post['hashtags'][:3])}...")
        print(f"   视频: {'✓' if post['video_path'] else '✗'}")
        print()
    print("=" * 60)
    print()

    if dry_run:
        print("🔍 Dry run 模式，不执行实际发布")
        sys.exit(0)

    # 4. 确认发布
    confirm = input("确认发布到小红书？(yes/no): ")
    if confirm.lower() != 'yes':
        print("❌ 用户取消发布")
        sys.exit(0)

    # 5. 依次发布
    results = []

    for i, post in enumerate(xhs_posts, 1):
        print()
        print(f"📤 发布 {i}/{len(xhs_posts)}: {post['topic_title']}")

        result = publish_to_xiaohongshu(
            title=post['title'],
            content=post['content'],
            cover_text=post['cover_text'],
            hashtags=post['hashtags'],
            video_path=post['video_path']
        )

        result['topic_id'] = post['topic_id']
        result['topic_title'] = post['topic_title']
        result['timestamp'] = datetime.now().isoformat()

        results.append(result)

        if result['success']:
            print(f"✅ 发布成功")
        else:
            print(f"❌ 发布失败: {result.get('error')}")

        # 如果还有下一篇，随机等待 5-30 分钟
        if i < len(xhs_posts):
            wait_seconds = random.randint(300, 1800)  # 5-30分钟
            wait_minutes = wait_seconds / 60
            print(f"⏳ 等待 {wait_minutes:.1f} 分钟后发布下一篇...")
            time.sleep(wait_seconds)

    # 6. 保存结果
    output_dir = Path(workspace) / "08_渠道分发" / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / "xiaohongshu_distribute_result.json"

    output_data = {
        "run_id": run_id,
        "platform": "xiaohongshu",
        "generated_at": datetime.now().isoformat(),
        "total": len(results),
        "success": sum(1 for r in results if r['success']),
        "failed": sum(1 for r in results if not r['success']),
        "results": results
    }

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print()
    print("=" * 60)
    print(f"✅ 小红书分发完成")
    print(f"   成功: {output_data['success']}/{output_data['total']}")
    print(f"   失败: {output_data['failed']}/{output_data['total']}")
    print(f"   结果: {output_file}")
    print("=" * 60)

if __name__ == "__main__":
    main()
