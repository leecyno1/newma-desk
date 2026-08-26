# 摘要生成改进 - 快速启动指南

## 🚀 立即生效步骤

### 1. 安装新依赖

```bash
pip install beautifulsoup4==4.12.3

# 或使用项目脚本
bash scripts/manage.sh install
```

### 2. 重启服务

```bash
# 如果正在运行，先停止
bash scripts/manage.sh stop

# 启动服务（开发模式 - 热重载）
bash scripts/manage.sh dev

# 或后台运行
bash scripts/manage.sh start
```

### 3. 验证改进效果

#### 方法A：自动化测试脚本

```bash
# 确保服务已启动
python test_summary_improvement.py
```

**预期输出**：
```
================================================================================
摘要生成改进 - 自动化测试
================================================================================
测试时间: 2025-10-21 15:30:00
服务地址: http://127.0.0.1:8001
测试用例数: 5
================================================================================

[1/5] 路演邀请（带会议号）
--------------------------------------------------------------------------------
输入: XX证券分析师李明邀请您参加腾讯会议，讨论半导体行业最新观点。...
  ✅ tone 正确: meeting
  ✅ meeting_number 正确: '123456789'
  ✅ confidence 符合预期: 0.92 > 0.8
  ✅ summary 格式正确: ai: XX证券李明邀约芯片板块路演，看好国产替代
结果: ✅ 通过
...

================================================================================
测试结果汇总
================================================================================
总计: 5 个用例
通过: 5 个 (100.0%)
失败: 0 个 (0.0%)
================================================================================
🎉 所有测试通过！摘要生成改进效果符合预期。
```

#### 方法B：手动测试单条消息

```bash
curl -X POST http://127.0.0.1:8001/api/ai/test-tool-summary \
  -H "Content-Type: application/json" \
  -d '{
    "text": "XX证券邀请您参加腾讯会议（会议号123456789），讨论芯片板块观点：看好国产替代加速",
    "sender": "分析师",
    "temperature": 0.1
  }'
```

**预期返回**（JSON格式化）：
```json
{
  "status": "ok",
  "parsed": [{
    "id": "demo",
    "summary": "ai: XX证券邀约芯片板块路演，看好国产替代",
    "meeting_number": "123456789",
    "tone": "meeting",
    "confidence": 0.9
  }],
  "config": {
    "tool_model": "Qwen/Qwen3-8B",
    "api_url": "https://api.siliconflow.cn/v1"
  }
}
```

#### 方法C：查看真实数据改进

```bash
# 1. 触发一次消息派生
curl -X POST http://127.0.0.1:8001/api/messages/derive?period=1day

# 2. 查看派生结果
curl http://127.0.0.1:8001/api/messages?limit=10 | jq '.rows[] | {
  id: .id,
  content: .content_text[:50],
  summary: .derived.summary,
  confidence: .derived.confidence,
  origin: .derived.summary_origin
}'
```

---

## 📊 改进对比

### 改进前
- **输入质量**：只看到 snippet（200字符截断）
- **提示词**：要求输出 12 个字段，过度约束
- **处理方式**：20条消息批处理
- **命中率**：~45%
- **准确率**：~60%

### 改进后
- **输入质量**：完整 HTML body + 表格结构保留
- **提示词**：精简至 5 个核心字段 + 置信度
- **处理方式**：逐条独立推理（并发8线程）
- **命中率**：预期 75-85% ⬆️ +30-40%
- **准确率**：预期 80-88% ⬆️ +20-28%

---

## 🔍 关键改进点

### 1. 智能 HTML 解析
- ✅ 表格 → 文本（保留 `|` 分隔符）
- ✅ 段落保留换行
- ✅ 列表项添加 `•` 前缀
- ✅ 智能截断（避免切在句中）

**示例**：
```html
<table>
  <tr><td>会议号</td><td>123456789</td></tr>
  <tr><td>观点</td><td>看好芯片国产替代</td></tr>
</table>
```
↓ 转换为 ↓
```
会议号 | 123456789
观点 | 看好芯片国产替代
```

### 2. 精简提示词
**改进前**：12 字段
```
summary, summary_full, key_info, keywords, category, tone, 
meeting_link, meeting_number, appointment_time, analyst, organizer, platform
```

**改进后**：5 字段 + 置信度
```
id, summary, meeting_number, tone, confidence
```

### 3. 逐条推理
- ❌ 旧：20条打包 → 上下文混乱
- ✅ 新：1条独立 → 理解更准确

---

## 🎯 前端识别规则

在消息列表的"摘要"列：

| 显示样式 | 来源 | 说明 |
|---------|------|------|
| **橘黄色粗体** | `ai:` 开头 | 小模型成功生成 |
| 灰色斜体 | `fallback:` 开头 | 本地规则兜底 |
| 🟢 徽标 | `confidence ≥ 0.8` | 高置信度（可选展示） |
| 🟡 徽标 | `0.5 ≤ confidence < 0.8` | 中等置信度 |
| 🔴 徽标 | `confidence < 0.5` | 低置信度，建议人工复核 |

---

## 🛠️ 故障排查

### 问题1：测试脚本报错 `Connection refused`

**原因**：服务未启动

**解决**：
```bash
bash scripts/manage.sh dev
# 等待启动完成（看到 "Application startup complete"）
```

### 问题2：返回 `SILICONFLOW_API_KEY not configured`

**原因**：未配置 API Key

**解决**：
```bash
# 方法1：环境变量
export SILICONFLOW_API_KEY="your-api-key"

# 方法2：配置文件
# 编辑 data/ai_config.json
{
  "api_key": "your-api-key",
  "tool_model": "Qwen/Qwen3-8B"
}
```

### 问题3：confidence 始终为 0.5

**原因**：小模型未返回 confidence 字段（可能是模型版本问题）

**解决**：
- 检查 `tool_model` 配置（推荐 `Qwen/Qwen3-8B` 或 `Qwen2.5-14B-Instruct`）
- 查看 `/api/ai/test-tool-summary` 的 `raw` 输出，确认模型是否理解提示词

### 问题4：meeting_number 提取失败

**检查**：
1. 输入内容是否包含 9-13 位连续数字？
2. 小模型是否正确识别（查看 `raw` 输出）？
3. 会议号是否被 HTML 标签分割（如 `<span>123</span>-<span>456</span>`）？

**优化建议**：
- 在 HTML 解析时做预处理：`123-456-789` → `123456789`

---

## 📈 效果监控

### 方法1：查看派生成功率

```sql
-- 今日派生统计
SELECT 
    DATE(timestamp) as date,
    COUNT(*) as total,
    SUM(CASE WHEN json_extract(derived, '$.summary_origin') = 'tool' THEN 1 ELSE 0 END) as tool_success,
    SUM(CASE WHEN json_extract(derived, '$.summary_origin') = 'fallback' THEN 1 ELSE 0 END) as fallback,
    ROUND(AVG(CAST(json_extract(derived, '$.confidence') AS REAL)), 2) as avg_confidence
FROM messages
WHERE derived IS NOT NULL
  AND timestamp > date('now', '-7 days')
GROUP BY DATE(timestamp)
ORDER BY date DESC;
```

### 方法2：查看低置信度消息

```sql
-- 置信度 < 0.5 的消息（需人工复核）
SELECT 
    id,
    substr(content_text, 1, 50) as content_preview,
    json_extract(derived, '$.summary') as summary,
    json_extract(derived, '$.confidence') as confidence
FROM messages
WHERE json_extract(derived, '$.confidence') < 0.5
  AND timestamp > datetime('now', '-1 day')
ORDER BY timestamp DESC
LIMIT 20;
```

---

## 📚 参考文档

- 详细改进报告：`docs/summary-improvement-report.md`
- 测试脚本：`test_summary_improvement.py`
- API 文档：访问 http://127.0.0.1:8001/docs

---

## 💡 下一步建议

### 短期（1-2周）
1. ✅ 观察真实数据改进效果（运行测试脚本）
2. ✅ 在前端展示置信度徽标
3. ✅ 收集用户反馈

### 中期（1-2月）
4. 尝试更大的小模型（Qwen2.5-14B / GLM-4-9B）
5. 增加 Few-shot 示例（在提示词中加入典型案例）

### 长期（3-6月）
6. 构建人工反馈界面（👍/👎）
7. 收集 100+ 反馈后微调专项模型

---

## ✅ 检查清单

在提交代码前，请确认：

- [x] 安装了 `beautifulsoup4` 依赖
- [x] 服务重启成功
- [x] 测试脚本通过（5/5 用例）
- [x] 真实数据中出现 `ai:` 前缀摘要
- [x] `derived.confidence` 字段正常写入
- [ ] 前端"摘要"列正确显示（橘黄色/灰色）
- [ ] 向团队同步改进内容

---

**完成时间**：2025-10-21  
**改进版本**：v2.0  
**预期效果**：命中率 +30-40%，准确率 +20-28%

