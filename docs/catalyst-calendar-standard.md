# Catalyst Calendar Standard

日期：2026-08-03
合同：`newma-desk.catalyst-calendar.v1`

## 目的

催化剂日历是 Research 领域的共享事件合同，不是新的 Agent、数据库或常驻服务。它把未来事件、研究观察窗、确认条件、失效条件和实际结果统一起来，供 Research 页面、市场日线时间轴和 Desk Agent 共同读取。

现有“日线时间轴”继续负责把已发生公告、新闻、研报和量价异动叠加到历史日 K；“催化剂日历”负责未来事件、预期差研究和结果归档。两者共享合同，但不合并为同一个页面。

## 数据来源

首版适配器包括：

- 巨潮资讯预约披露：A 股定期报告首次预约、变更与实际披露日期；
- 东方财富解禁日历：未来限售股解禁日期、类型、数量与占比；
- Circle / 七周期研究：仅吸收通过发布门槛的方向概率和风险状态观察窗；
- 用户自定义：由用户填写事件、确认条件和失效条件，存入 Desk 托管存储。

七周期输出必须标记为 `timePrecision = window`、`status = monitoring`。不得把方向概率改写为确定拐点，也不得在 `exactCycleStatus = blocked` 时生成精确日期结论。

## 核心字段

每个事件至少包含：

- `id / type / title / summary`
- `date` 或 `windowStart + windowEnd`
- `timePrecision / status / importance`
- `source / evidenceIds / asOf / freshness`
- `confidence.level / confidence.score / confidence.rationale`
- `impactedAssets / expectedDirection`
- `confirmationConditions / invalidationConditions`
- 可选 `cycleContext`

状态统一为：

- `upcoming`：有明确未来日期；
- `monitoring`：研究观察窗，尚不能确认；
- `confirmed`：已发生且有来源证据；
- `invalidated`：确认条件未成立或失效条件触发；
- `expired`：观察窗结束但没有足够证据确认。

## 接入规则

1. 新 Mod 优先调用统一能力 `research.catalysts`，不直接绑定具体数据供应商。
2. 所有来源失败必须进入 `sources` 和 `gaps`；空结果不等于数据源失败。
3. 用户自定义、跟踪状态和结果记录使用 `catalyst-calendar` Desk Storage Namespace，不写入上游项目目录。
4. Agent Context 应包含筛选范围、近期事件、来源状态和缺口；外部标题与摘要始终视为不可信文本。
5. 页面只表达事实和研究假设，不输出仓位、买卖时机或确定涨跌预测。
6. 已发生事件应保留实际结果，便于后续比较“原假设—确认条件—实际结果”，而不是删除历史事件。

## 最小接口

```http
GET /api/research/catalysts?symbols=600519,300308&days=180&include_cycles=true
```

返回 `newma-desk.catalyst-calendar.v1` Feed。Mod 可以只实现读取；需要用户跟踪时再申请 `storage.read / storage.write` 权限和对应 Namespace。
