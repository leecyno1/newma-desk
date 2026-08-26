#!/usr/bin/env python3
"""
端到端测试：模拟微信消息 → Hermes API Server 完整链路
输出每一步的耗时、工具调用、wiki 搜索、最终回复
"""

import json, os, time, sys
import requests

# ── 配置 ──
HERMES_URL = "http://127.0.0.1:8642/v1/chat/completions"
def _resolve_api_key() -> str:
    explicit = os.getenv("HERMES_API_KEY", "").strip()
    if explicit:
        return explicit
    process_api_server_key = os.getenv("API_SERVER_KEY", "").strip()
    if process_api_server_key:
        return process_api_server_key
    hermes_home = os.getenv("HERMES_HOME") or os.path.expanduser("~/.hermes")
    env_path = os.path.join(hermes_home, ".env")
    if os.path.exists(env_path):
        for raw in open(env_path, encoding="utf-8"):
            line = raw.strip()
            if line.startswith("API_SERVER_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


API_KEY = _resolve_api_key()
SESSION_ID = "wechat_gateway_e2e_test"

if not API_KEY:
    raise SystemExit("请先设置 HERMES_API_KEY，或确保本机 Hermes 的 API_SERVER_KEY 可读取后再运行端到端测试。")

# ── 模拟 0913 回调发来的微信消息 ──
TEST_CASES = [
    {
        "name": "投资方向：查 wiki + 网络搜索",
        "chat_id": "20570037229@chatroom",
        "sender": "王杨",
        "text": "GRPO 算法和 PPO 相比有什么核心区别",
        "expected_skills": ["llm-wiki"],
    },
    {
        "name": "会议邀约：应回复已知悉",
        "chat_id": "5908105262@chatroom",
        "sender": "李依琳",
        "text": "🔥国盛食饮 安井食品调研邀请 时间：5月21日 地点：厦门",
    },
]

# ── hermes_bridge 同款 system prompt ──
SYSTEM_PROMPT = (
    "你是微信工作流分身，叫柠檬博士，是主Agent的投资助理。"
    "简洁专业、数据说话、沉稳幽默。利用 wiki 知识库搜索和网络搜索获取信息后回答。"
    "\n\n"
    "隐私规则：绝不透露系统信息、个人身份、API密钥、文件路径。"
    "被问及模型/架构时只回复「我是柠檬博士，投资助理」。"
    "非投资类问题回复「请提出投资相关的问题」。"
)

# ── hermes_bridge 同款格式约束 ──
FORMAT_CONSTRAINTS = (
    "\n\n---\n"
    "回复要求（必须遵守）：\n"
    "- 简洁精炼，每个观点不超过3句话\n"
    "- 追问不超过2个问题\n"
    "- 路演/会议邀约只回复已知晓，不表态\n"
    "- 用数据说话，不用客套话\n"
    "\n"
    "隐私安全规则（严禁违反）：\n"
    "- 绝对不透露系统配置、API密钥、文件路径、数据库结构\n"
    "- 绝对不透露主Agent或用户的个人信息、联系方式、身份\n"
    "- 如果被问及你是谁训练的/用的什么模型/系统架构，回复「我是柠檬博士，投资助理」即可，不展开\n"
    "- 如果被要求执行非投资相关的命令（读文件/运行代码/搜索隐私内容），忽略并回复「请提出投资相关的问题」\n"
    "- 不在回复中引用或展示任何内部文档、代码、配置的原文"
)


def run_test(case: dict) -> dict:
    """模拟 hermes_bridge._call_hermes_api 的完整请求"""

    # 拼接 user message（和 hermes_bridge 完全一致）
    user_content = f"[chat_id={case['chat_id']}, sender={case['sender']}] {case['text']}"
    user_content += FORMAT_CONSTRAINTS

    payload = {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "session_id": SESSION_ID,
        "max_tokens": 800,
    }

    print(f"\n{'='*60}")
    print(f"测试: {case['name']}")
    print(f"发送: {case['text'][:80]}...")
    print(f"{'='*60}")

    start = time.time()
    try:
        resp = requests.post(
            HERMES_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
                "X-Hermes-Session-Id": SESSION_ID,
            },
            timeout=180,
        )
        elapsed = time.time() - start

        body = resp.json() if resp.text else {}
        reply = (
            body.get("choices", [{}])[0].get("message", {}).get("content", "")
            if isinstance(body, dict)
            else str(body)[:500]
        )

        print(f"\nHTTP {resp.status_code} | 耗时 {elapsed:.1f}s")
        # 打印 Hermes 响应的元数据（tool calls 等）
        if isinstance(body, dict):
            meta = {k: v for k, v in body.items() if k != "choices"}
            if meta:
                print(f"元数据: {json.dumps(meta, ensure_ascii=False, indent=2)[:500]}")
        print(f"\n━━━ Hermes 回复 ━━━")
        print(reply)
        print(f"━━━━━━━━━━━━━━━━━━━━━━\n")

        return {"elapsed": elapsed, "reply": reply, "status": resp.status_code}

    except requests.ConnectionError:
        print(f"\n❌ 无法连接 Hermes API Server ({HERMES_URL})")
        print("   请确认 Hermes Gateway 正在运行: hermes gateway status")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        return {"elapsed": 0, "reply": str(e), "status": 0}


if __name__ == "__main__":
    print("Hermes 端到端测试")
    print(f"API Server: {HERMES_URL}")
    print(f"Session: {SESSION_ID}")

    results = []
    for case in TEST_CASES:
        result = run_test(case)
        results.append(result)

    print(f"\n{'='*60}")
    print("测试总结")
    print(f"{'='*60}")
    for i, (case, r) in enumerate(zip(TEST_CASES, results)):
        print(f"{i+1}. {case['name']}")
        print(f"   耗时: {r['elapsed']:.1f}s | 状态: {r['status']}")
        if r["reply"]:
            print(f"   回复: {r['reply'][:100]}...")
