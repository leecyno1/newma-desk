# 个股事件与资金合同

## 定位

`instock-event-flow` 是 evidence-first 的事件与资金工作台。它既可按 A 股代码读取 Desk 已托管数据，也保留 Desk Agent 点时事件包输入；项目负责确定性去重、时效、来源覆盖、异常强度、方向和证券归并。

## 接口

Action：`analysis.event-flow`

HTTP：`POST /api/v1/event-flows`

输入支持两种互斥模式：

- 股票代码：`{"symbol":"300502","asOf":"2026-08-11"}`，`asOf` 可选。
- 事件包：`instock-event-flow-packet-v1`。

股票代码模式读取 Desk Research HTTP Interface 的主力资金、融资融券、龙虎榜、大宗交易、股东户数、分红送转和限售解禁，并通过 Desk Data Service capability 读取公告、研报与新闻。项目不直连旧 MySQL，也不恢复原抓取器。

每条事件包含：`id`、`type`、`symbol`、`occurred_at`、`title`、`direction`、`magnitude_score`、`evidence_strength`、`source_ref`，可带标量 `details`。支持公告、新闻、研报、主力资金、融资融券、龙虎榜、大宗交易、股东变化、分红、解禁、涨停原因、北向和机构资金类型。

## 处理规则

- 相同 `source_ref` 只保留异常强度最高的一条。
- 30 日内标记 `fresh`，超过 30 日保留审计但标记 `stale`。
- 异常强度 = magnitude 65% + 证据强度 25% + 时效 10%。代码查询模式的 magnitude 使用资金绝对值历史分位、公开成交额或公开比例形成研究优先级；事件包模式继续使用宿主提供值。
- 按证券汇总正向、负向事件数量与强度差。
- 输出 `coverage`、字段单位和 `failures`；空数据与接口失败分别披露。

公告、研报和新闻默认保持中性，不从标题自动推断涨跌。资金和筹码方向只描述已观察证据，不会把异常强度解释为收益预测或交易信号。
