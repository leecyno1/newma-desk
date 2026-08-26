#!/usr/bin/env python3
"""
测试摘要生成改进效果

使用方法：
    python test_summary_improvement.py
"""

import requests
import json
from datetime import datetime

BASE_URL = "http://127.0.0.1:8001"

# 测试用例（模拟真实场景）
TEST_CASES = [
    {
        "name": "路演邀请（带会议号）",
        "text": """XX证券分析师李明邀请您参加腾讯会议，讨论半导体行业最新观点。

会议主题：国产芯片替代加速，设备与材料环节投资机会
会议时间：2025-10-22 14:00
会议号：123-456-789
会议链接：https://meeting.tencent.com/dm/xxx

核心观点：
1. 看好国产替代加速，政策支持力度加大
2. 建议关注设备龙头（北方华创、中微公司）和材料标的（沪硅产业）
3. 短期关注科创板芯片股反弹机会

请提前加入会议室。""",
        "expected_tone": "meeting",
        "expected_meeting_number": "123456789",
        "expected_confidence": "> 0.8",
    },
    {
        "name": "观点分享（看多）",
        "text": """最新研判：新能源车产业链底部反转信号明确

核心逻辑：
- 9月销量超预期，同比+35%，环比+12%
- 动力电池库存去化进入尾声，Q4有望重回增长
- 欧洲碳排新规落地，海外需求提速

投资建议：
- 整车：看好比亚迪、理想汽车
- 电池：宁德时代、亿纬锂能
- 上游：六氟磷酸锂价格筑底，关注天赐材料

风险提示：海外需求不及预期""",
        "expected_tone": "bullish",
        "expected_meeting_number": "",
        "expected_confidence": "> 0.7",
    },
    {
        "name": "观点分享（看空）",
        "text": """警惕地产板块短期调整风险

近期地产股大涨，但基本面支撑不足：
1. 政策放松力度低于预期，一线城市限购仅边际松动
2. 9月销售数据仍在低位，库存高企
3. 开发商现金流压力未明显缓解

建议：
- 短期逢高减仓，等待更明确的政策信号
- 关注央企开发商（安全边际较高）
- 规避高杠杆民企""",
        "expected_tone": "bearish",
        "expected_meeting_number": "",
        "expected_confidence": "> 0.7",
    },
    {
        "name": "信息有限（短消息）",
        "text": "今天下午有空吗？",
        "expected_tone": "neutral",
        "expected_meeting_number": "",
        "expected_confidence": "< 0.5",
    },
    {
        "name": "HTML 表格邮件（会议邀请）",
        "text": """<html>
<body>
<table border="1">
  <tr>
    <td>会议主题</td>
    <td>医药板块投资策略</td>
  </tr>
  <tr>
    <td>路演时间</td>
    <td>2025-10-23 10:00</td>
  </tr>
  <tr>
    <td>会议平台</td>
    <td>进门财经</td>
  </tr>
  <tr>
    <td>会议号</td>
    <td>987654321</td>
  </tr>
  <tr>
    <td>分析师</td>
    <td>张三 - XX券商医药首席</td>
  </tr>
</table>
<p>核心观点：创新药出海加速，CXO 板块估值修复</p>
</body>
</html>""",
        "expected_tone": "meeting",
        "expected_meeting_number": "987654321",
        "expected_confidence": "> 0.8",
    },
]


def test_tool_summary(text: str, sender: str = "测试联系人"):
    """调用测试端点"""
    try:
        resp = requests.post(
            f"{BASE_URL}/api/ai/test-tool-summary",
            json={"text": text, "sender": sender, "temperature": 0.1},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"status": "error", "error": str(e)}


def evaluate_result(result: dict, expected: dict) -> dict:
    """评估结果是否符合预期"""
    evaluation = {"pass": True, "details": []}
    
    if result.get("status") != "ok":
        evaluation["pass"] = False
        evaluation["details"].append(f"❌ 请求失败: {result.get('error')}")
        return evaluation
    
    parsed = result.get("parsed")
    if not parsed or not isinstance(parsed, list) or len(parsed) == 0:
        evaluation["pass"] = False
        evaluation["details"].append("❌ 解析失败或返回为空")
        return evaluation
    
    item = parsed[0]
    
    # 检查 tone
    actual_tone = item.get("tone", "")
    expected_tone = expected.get("expected_tone", "")
    if actual_tone == expected_tone:
        evaluation["details"].append(f"✅ tone 正确: {actual_tone}")
    else:
        evaluation["pass"] = False
        evaluation["details"].append(f"❌ tone 错误: 期望 {expected_tone}, 实际 {actual_tone}")
    
    # 检查 meeting_number
    actual_number = item.get("meeting_number", "")
    expected_number = expected.get("expected_meeting_number", "")
    if actual_number == expected_number:
        evaluation["details"].append(f"✅ meeting_number 正确: '{actual_number}'")
    else:
        evaluation["pass"] = False
        evaluation["details"].append(
            f"❌ meeting_number 错误: 期望 '{expected_number}', 实际 '{actual_number}'"
        )
    
    # 检查 confidence
    actual_conf = item.get("confidence", 0.0)
    expected_conf_str = expected.get("expected_confidence", "")
    if "> 0.8" in expected_conf_str:
        if actual_conf > 0.8:
            evaluation["details"].append(f"✅ confidence 符合预期: {actual_conf:.2f} > 0.8")
        else:
            evaluation["pass"] = False
            evaluation["details"].append(
                f"⚠️ confidence 偏低: {actual_conf:.2f} (期望 > 0.8)"
            )
    elif "> 0.7" in expected_conf_str:
        if actual_conf > 0.7:
            evaluation["details"].append(f"✅ confidence 符合预期: {actual_conf:.2f} > 0.7")
        else:
            evaluation["details"].append(
                f"⚠️ confidence 偏低: {actual_conf:.2f} (期望 > 0.7，可接受)"
            )
    elif "< 0.5" in expected_conf_str:
        if actual_conf < 0.5:
            evaluation["details"].append(
                f"✅ confidence 符合预期: {actual_conf:.2f} < 0.5 (信息有限场景)"
            )
        else:
            evaluation["details"].append(
                f"⚠️ confidence 意外偏高: {actual_conf:.2f} (期望 < 0.5，但可接受)"
            )
    
    # 检查 summary
    summary = item.get("summary", "")
    if summary.startswith("ai: "):
        evaluation["details"].append(f"✅ summary 格式正确: {summary}")
    else:
        evaluation["pass"] = False
        evaluation["details"].append(f"❌ summary 缺少前缀: {summary}")
    
    return evaluation


def main():
    print("=" * 80)
    print("摘要生成改进 - 自动化测试")
    print("=" * 80)
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"服务地址: {BASE_URL}")
    print(f"测试用例数: {len(TEST_CASES)}")
    print("=" * 80)
    print()
    
    passed = 0
    failed = 0
    
    for i, case in enumerate(TEST_CASES, 1):
        print(f"[{i}/{len(TEST_CASES)}] {case['name']}")
        print("-" * 80)
        
        # 显示输入片段
        text_preview = case["text"][:100].replace("\n", " ")
        if len(case["text"]) > 100:
            text_preview += "..."
        print(f"输入: {text_preview}")
        
        # 调用测试
        result = test_tool_summary(case["text"])
        
        # 评估结果
        evaluation = evaluate_result(result, case)
        
        # 显示结果
        for detail in evaluation["details"]:
            print(f"  {detail}")
        
        if evaluation["pass"]:
            print(f"结果: ✅ 通过")
            passed += 1
        else:
            print(f"结果: ❌ 失败")
            failed += 1
        
        # 显示原始返回（便于调试）
        if result.get("parsed"):
            item = result["parsed"][0]
            print(f"\n  原始返回:")
            print(f"    summary: {item.get('summary')}")
            print(f"    meeting_number: {item.get('meeting_number')}")
            print(f"    tone: {item.get('tone')}")
            print(f"    confidence: {item.get('confidence')}")
        
        print()
    
    # 统计
    print("=" * 80)
    print("测试结果汇总")
    print("=" * 80)
    print(f"总计: {len(TEST_CASES)} 个用例")
    print(f"通过: {passed} 个 ({passed/len(TEST_CASES)*100:.1f}%)")
    print(f"失败: {failed} 个 ({failed/len(TEST_CASES)*100:.1f}%)")
    print("=" * 80)
    
    if failed == 0:
        print("🎉 所有测试通过！摘要生成改进效果符合预期。")
    else:
        print("⚠️ 部分测试失败，请检查小模型配置或提示词。")
    
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    exit(main())

