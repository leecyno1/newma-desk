# 供应链瓶颈研究合同

`analysis.industry-chain` 是独立 `instock-industry-chain` Module 的确定性 Action。Newma-Desk 负责数据访问、Agent 编排和证据采集；InStock 只校验点时产业链拓扑、计算关键节点与瓶颈候选优先级、登记 Snapshot，并把结果交给页面或其他 Web 客户端。

## 权威文件

- 输入 JSON Schema：`integrations/newma-desk/schemas/industry-chain-research-packet.schema.json`
- 非真实数据示例：`integrations/newma-desk/examples/supply-chain-research.packet.json`
- HTTP：`POST /api/v1/industry-chain/research`
- Action：`analysis.industry-chain`
- 兼容 HTTP：`POST /api/v1/rotations/supply-chain-research`（仅旧 Adapter）

`integrations/newma-desk/schemas/supply-chain-research-packet.schema.json` 仅保留给 `schema_version=1.0` 的迁移兼容，不是新接入的合同来源。

示例文件只用于合同与联调验证，所有名称、证据和评分均不构成真实供应链研究。

## 研究包语义

规范研究包使用 `schema_version=2.0`，并明确 `theme`、`market`、`as_of` 和 `chain` 拓扑；引擎仍兼容 `schema_version=1.0`，但会标记为 legacy。`as_of` 是研究的点时截止日；任何 `evidence.observed_at` 晚于该日期都会被拒绝。

处理顺序固定为：

1. 校验证据 ID、来源引用、强度和日期。
2. 根据需求压力、卡点严重度、供应商集中度、扩产难度和替代难度排序稀缺层。
3. 在所属稀缺层得分基础上，根据业务暴露纯度、估值错位、催化时点、财务韧性和证据质量排序候选。
4. 扣除融资稀释、治理、地缘、流动性、炒作、会计质量、周期性和替代设计风险。
5. 输出证伪条件、证据覆盖、限制项和稳定 Snapshot。

评分字段全部使用 `0..5`。字段必须完整且不能出现未知键；证据引用必须指向当前研究包中的真实证据 ID。没有 strong 或 medium 证据的候选会被强制降为 `early_lead`、`confidence=low`。两个以上 strong 证据只有来自至少两个不同 `source_ref` 时才能形成 `confidence=high`；同源强证据会触发来源集中限制并把结果标记为 `data_state=partial`。

## 页面适配器

`/mods/industry-chain` 暴露只读页面适配器 `window.InStockIndustryChainResearch`：

```js
// 让页面通过已授权 Desk Action 执行；未嵌入 Desk 时只回退到同一附属运行时 API。
await window.InStockIndustryChainResearch.analyze(researchPacket);

// 宿主或同页组件已经取得 Action 成功结果时，直接渲染。
window.InStockIndustryChainResearch.acceptActionResult(actionResult);

// 清除当前显示，不删除服务端 Snapshot。
window.InStockIndustryChainResearch.clear();
```

同页组件也可派发 `instock:industry-chain-result` DOM 事件，`detail` 为完整 Action 响应或其中的 `data`。该接口属于 InStock 页面适配层，不扩展 Newma-Desk Bridge Protocol，也不要求 Desk 新增事件类型。

页面初始状态是“请输入主题开始研究”。完整链路固定为：定义主题 → 简单 Agent 采集公开事实与来源 → InStock 确定性校验 → 形成瓶颈层、候选与股票研究交接。Agent 不直接评分或选股；没有研究结果时不显示候选，也不会从 ETF 轮动行情生成供应链结论。页面最多展开前 20 家候选，完整数组仍保留在 Action 返回值；发布给 Desk Context 的摘要最多包含前 5 个稀缺层和前 10 家候选，避免把完整研究包复制进页面上下文。

## 输出边界

`priority_score` 是版本化研究优先级启发式，不是收益预测、目标价、择时分或买卖信号。`calibrated_backtest=false` 是强制输出。调用方应同时展示：

- `data_state` 与 `limitations`
- `confidence` 与 `evidence_summary`
- `penalty_score`
- `invalidation`
- `snapshot.snapshot_id`

若需要复现结论，调用方必须保留原始研究包或在宿主数据系统中保存对应证据引用；InStock 的进程内 Snapshot Registry 只保存紧凑元数据，不保存完整研究包。
