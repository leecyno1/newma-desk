#!/usr/bin/env python3
"""
飞书Rewrite Stage 5同步脚本

功能：
1. 获取飞书API token
2. 发送改写完成通知到群组
3. 上传改写报告到飞书
"""

import json
import requests
from pathlib import Path
from datetime import datetime
import os

from path_config import get_feishu_config_path

# 飞书配置
config_file = get_feishu_config_path()
config = {}
if config_file.exists():
    with open(config_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                key, value = line.split('=', 1)
                config[key] = value.strip('"')

APP_ID = config.get('APP_ID')
APP_SECRET = config.get('APP_SECRET')
TENANT_KEY = config.get('TENANT_KEY')
CHAT_ID = config.get('CHAT_ID')

class FeishuRewriteSync:
    def __init__(self):
        self.app_id = APP_ID
        self.app_secret = APP_SECRET
        self.tenant_key = TENANT_KEY
        self.chat_id = CHAT_ID
        self.access_token = None
        self.tenant_access_token = None
        self.run_id = "2026-04-11_085602"
        # 使用相对路径或从参数获取
        from path_config import get_output_root
        self.output_dir = get_output_root("rewrite") / self.run_id

    def get_tenant_access_token(self):
        """获取租户级别的访问令牌"""
        url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        headers = {"Content-Type": "application/json"}
        data = {
            "app_id": self.app_id,
            "app_secret": self.app_secret
        }

        try:
            response = requests.post(url, headers=headers, json=data, timeout=10)
            result = response.json()
            if result.get("code") == 0:
                self.tenant_access_token = result["tenant_access_token"]
                print(f"✓ 获取飞书token成功")
                return self.tenant_access_token
            else:
                print(f"✗ 获取token失败: {result.get('msg')}")
                return None
        except Exception as e:
            print(f"✗ 获取token异常: {str(e)}")
            return None

    def send_group_message(self, message_text):
        """发送群组消息"""
        if not self.tenant_access_token:
            print("✗ 未获取token，无法发送消息")
            return False

        url = f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id"
        headers = {
            "Authorization": f"Bearer {self.tenant_access_token}",
            "Content-Type": "application/json"
        }

        # 使用 Card 卡片格式
        data = {
            "receive_id": self.chat_id,
            "msg_type": "interactive",
            "content": json.dumps({
                "type": "template",
                "data": {
                    "template_id": "AAMApvLe1Ah1C40",  # 通用卡片模板
                    "template_variable": {
                        "content": message_text
                    }
                }
            })
        }

        try:
            response = requests.post(url, headers=headers, json=data, timeout=10)
            result = response.json()
            if result.get("code") == 0:
                print(f"✓ 群组消息发送成功")
                return True
            else:
                # 尝试回退到纯文本格式
                print(f"⚠️ Card格式发送失败，尝试纯文本格式...")
                return self.send_text_message(message_text)
        except Exception as e:
            print(f"✗ 发送群组消息异常: {str(e)}")
            return False

    def send_text_message(self, message_text):
        """发送纯文本消息"""
        url = f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id"
        headers = {
            "Authorization": f"Bearer {self.tenant_access_token}",
            "Content-Type": "application/json"
        }

        # 限制消息长度
        if len(message_text) > 2000:
            message_text = message_text[:2000] + "...(更多内容请查看完整报告)"

        data = {
            "receive_id": self.chat_id,
            "msg_type": "text",
            "content": json.dumps({"text": message_text})
        }

        try:
            response = requests.post(url, headers=headers, json=data, timeout=10)
            result = response.json()
            if result.get("code") == 0:
                print(f"✓ 纯文本消息发送成功")
                return True
            else:
                print(f"✗ 纯文本消息发送失败: {result.get('msg')}")
                return False
        except Exception as e:
            print(f"✗ 发送纯文本消息异常: {str(e)}")
            return False

    def generate_summary_message(self):
        """生成改写完成摘要消息"""
        manifest_file = self.output_dir / "rewrite_manifest.json"
        if not manifest_file.exists():
            return None

        with open(manifest_file, 'r', encoding='utf-8') as f:
            manifest = json.load(f)

        topics = manifest.get("topics", {})
        total_versions = len(topics) * 4  # 3个主题×4个版本

        # 统计质量等级
        ready_count = 0
        review_count = 0
        needs_work_count = 0

        for topic_versions in topics.values():
            for version_result in topic_versions.values():
                status = version_result.get('quality_status', '')
                if '✅' in status or status == 'Ready':
                    ready_count += 1
                elif '⚠️' in status or status == 'Review':
                    review_count += 1
                else:
                    needs_work_count += 1

        message = f"""🎯 Rewrite Stage 5 改写阶段完成

📋 改写摘要：
━━━━━━━━━━━━━━━━━━━━━━
✅ 完成版本数：{total_versions}/12
📊 质量分布：
  • Ready（✅）: {ready_count} 个
  • Review（⚠️）: {review_count} 个
  • Needs Work（❌）: {needs_work_count} 个

📌 主题列表：
  1. Claude新模型引发华尔街紧急会议
  2. 稳定币牌照落地-加密市场的银行牌照时刻
  3. 日本士兵闯使馆事件背后-个体极端行为还是系统性问题

💾 输出位置：
~/Desktop/自媒体创作/00_改写/2026-04-11_085602/

📄 产出文件：
  • rewrite_manifest.json - 改写清单
  • 06_改写_报告.md - 详细分析报告
  • 12个改写版本 md 文件

⚠️ 注意事项：
  • 质量评分平均 6.8/10，部分版本需要编辑调整
  • 字数控制需要优化（偏差较大）
  • 建议编辑人工审阅后进入 Publish 阶段

🔄 下一步：Publish Stage (Stage 6) 或 Rewrite 优化迭代
"""
        return message

    def sync_all(self):
        """执行完整的飞书同步"""
        print("\n🚀 启动飞书 Rewrite 同步")
        print(f"Run ID: {self.run_id}")

        # 步骤1：获取token
        print("\n[1/2] 获取飞书API token...")
        if not self.get_tenant_access_token():
            return False

        # 步骤2：发送群组消息
        print("\n[2/2] 发送改写完成通知...")
        message = self.generate_summary_message()
        if message:
            success = self.send_group_message(message)
            if success:
                print("\n✅ 飞书同步完成")
                return True

        return False

if __name__ == "__main__":
    sync = FeishuRewriteSync()
    sync.sync_all()
