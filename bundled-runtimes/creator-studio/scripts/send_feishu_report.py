#!/usr/bin/env python3
"""
飞书文档创建脚本 - 正确处理 block 类型
基于 clawdbot 的经验：
1. 过滤不支持的 block 类型（Table 31, TableCell 32）
2. 按 first_level_block_ids 排序
3. 使用 markdown convert API
"""
import os
import sys
import json
import requests
from pathlib import Path

# 飞书配置
APP_ID = os.getenv("FEISHU_APP_ID", "cli_a94d22306138dbc2")
APP_SECRET = os.getenv("FEISHU_APP_SECRET", "Zqi9eW7aaPt6ozcndlXHPeW4LDiA86hO")
CHAT_ID = os.getenv("DASHENG_FEISHU_CHAT_ID", "oc_975d43c5704bf8c755bb9e32bf7c3922")

# 不支持通过 API 创建的 block 类型
UNSUPPORTED_CREATE_TYPES = {31, 32}  # Table, TableCell

BLOCK_TYPE_NAMES = {
    31: "Table",
    32: "TableCell",
}

def get_tenant_access_token():
    """获取 tenant_access_token"""
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    headers = {"Content-Type": "application/json"}
    data = {"app_id": APP_ID, "app_secret": APP_SECRET}

    response = requests.post(url, headers=headers, json=data)
    result = response.json()

    if result.get("code") != 0:
        raise Exception(f"获取 token 失败: {result}")

    return result["tenant_access_token"]

def create_document(token, title):
    """创建飞书文档"""
    url = "https://open.feishu.cn/open-apis/docx/v1/documents"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    data = {
        "folder_token": "",
        "title": title
    }

    response = requests.post(url, headers=headers, json=data)
    result = response.json()

    if result.get("code") != 0:
        raise Exception(f"创建文档失败: {result}")

    return result["data"]["document"]["document_id"]

def convert_markdown(token, markdown):
    """将 markdown 转换为 blocks"""
    url = "https://open.feishu.cn/open-apis/docx/v1/documents/blocks/convert"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    data = {
        "content_type": "markdown",
        "content": markdown
    }

    response = requests.post(url, headers=headers, json=data)

    # 调试：打印响应
    print(f"Response status: {response.status_code}")
    print(f"Response text: {response.text[:500]}")

    try:
        result = response.json()
    except Exception as e:
        raise Exception(f"解析响应失败: {e}, 响应内容: {response.text[:500]}")

    if result.get("code") != 0:
        raise Exception(f"转换 markdown 失败: {result}")

    return {
        "blocks": result["data"].get("blocks", []),
        "first_level_block_ids": result["data"].get("first_level_block_ids", [])
    }

def clean_blocks_for_insert(blocks):
    """清理 blocks，移除不支持的类型"""
    skipped = []
    cleaned = []

    for block in blocks:
        block_type = block.get("block_type")
        if block_type in UNSUPPORTED_CREATE_TYPES:
            type_name = BLOCK_TYPE_NAMES.get(block_type, f"type_{block_type}")
            skipped.append(type_name)
            continue
        cleaned.append(block)

    return cleaned, skipped

def sort_blocks_by_first_level(blocks, first_level_ids):
    """按 first_level_block_ids 排序 blocks"""
    if not first_level_ids:
        return blocks

    # 创建 block_id 到 block 的映射
    block_map = {b.get("block_id"): b for b in blocks}

    # 按 first_level_ids 顺序排序
    sorted_blocks = []
    for block_id in first_level_ids:
        if block_id in block_map:
            sorted_blocks.append(block_map[block_id])

    # 添加剩余的 blocks
    sorted_ids = set(first_level_ids)
    remaining = [b for b in blocks if b.get("block_id") not in sorted_ids]
    sorted_blocks.extend(remaining)

    return sorted_blocks

def insert_blocks(token, doc_id, blocks):
    """插入 blocks 到文档"""
    url = f"https://open.feishu.cn/open-apis/docx/v1/documents/{doc_id}/blocks/{doc_id}/children"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    data = {
        "children": blocks
    }

    response = requests.post(url, headers=headers, json=data)
    result = response.json()

    if result.get("code") != 0:
        raise Exception(f"插入 blocks 失败: {result}")

    return result["data"].get("children", [])

def write_doc(token, doc_id, markdown):
    """
    写入 markdown 内容到文档
    正确处理流程：
    1. convert markdown to blocks
    2. clean blocks (remove unsupported types)
    3. sort blocks by first_level_block_ids
    4. insert blocks
    """
    # 1. 转换 markdown
    print("转换 markdown...")
    converted = convert_markdown(token, markdown)
    blocks = converted["blocks"]
    first_level_ids = converted["first_level_block_ids"]

    if not blocks:
        print("⚠️  没有内容可写入")
        return

    # 2. 清理 blocks
    print("清理 blocks...")
    cleaned_blocks, skipped = clean_blocks_for_insert(blocks)

    if skipped:
        print(f"⚠️  跳过不支持的 block 类型: {', '.join(skipped)}")
        print("   （表格不能通过 API 创建，请手动添加）")

    if not cleaned_blocks:
        print("⚠️  清理后没有可插入的 blocks")
        return

    # 3. 排序 blocks
    print("排序 blocks...")
    sorted_blocks = sort_blocks_by_first_level(cleaned_blocks, first_level_ids)

    # 4. 插入 blocks
    print(f"插入 {len(sorted_blocks)} 个 blocks...")
    inserted = insert_blocks(token, doc_id, sorted_blocks)

    print(f"✅ 成功插入 {len(inserted)} 个 blocks")

def send_to_chat(token, chat_id, doc_id, title, stage_emoji="📄"):
    """发送文档到飞书群"""
    url = "https://open.feishu.cn/open-apis/im/v1/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    doc_url = f"https://bytedance.larkoffice.com/docx/{doc_id}"

    data = {
        "receive_id": chat_id,
        "msg_type": "text",
        "content": json.dumps({
            "text": f"{stage_emoji} {title}\n\n文档链接：{doc_url}\n\n请查看并审核"
        })
    }

    params = {"receive_id_type": "chat_id"}
    response = requests.post(url, headers=headers, params=params, json=data)
    result = response.json()

    if result.get("code") != 0:
        raise Exception(f"发送消息失败: {result}")

    return result

def send_stage_report(stage_name, report_content, run_id, stage_emoji="📄"):
    """
    发送阶段报告到飞书群

    Args:
        stage_name: 阶段名称（如 "intake", "brief", "draft", "publish"）
        report_content: 报告内容（markdown 格式）
        run_id: 运行批次 ID
        stage_emoji: 阶段表情符号
    """
    # 获取 token
    print("获取 tenant_access_token...")
    token = get_tenant_access_token()

    # 创建文档
    title = f"{stage_name.upper()} 阶段报告 - {run_id}"
    print(f"创建文档: {title}")
    doc_id = create_document(token, title)
    print(f"文档 ID: {doc_id}")

    # 写入内容
    print("写入内容...")
    write_doc(token, doc_id, report_content)

    # 发送到群
    print("发送到飞书群...")
    send_to_chat(token, CHAT_ID, doc_id, title, stage_emoji)

    doc_url = f"https://bytedance.larkoffice.com/docx/{doc_id}"
    print(f"\n✅ 完成！文档链接: {doc_url}")

def main():
    """命令行入口"""
    if len(sys.argv) < 4:
        print("用法: python3 send_feishu_report.py <stage_name> <report_file> <run_id> [emoji]")
        print("示例: python3 send_feishu_report.py publish /path/to/report.md 2026-04-07_141203 🚀")
        sys.exit(1)

    stage_name = sys.argv[1]
    report_file = sys.argv[2]
    run_id = sys.argv[3]
    stage_emoji = sys.argv[4] if len(sys.argv) > 4 else "📄"

    # 读取报告内容
    with open(report_file, 'r', encoding='utf-8') as f:
        report_content = f.read()

    # 发送报告
    send_stage_report(stage_name, report_content, run_id, stage_emoji)

if __name__ == "__main__":
    main()
