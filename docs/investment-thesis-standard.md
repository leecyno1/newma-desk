# Newma-Desk 结构化投资逻辑标准

投资逻辑 Mod 使用 `newma-desk.investment-thesis.v1` 合同，把一次性的个股观点变成可以持续核验、被证伪和跨 Mod 引用的研究档案。

## 目标

- 核心论点必须可证伪，不能使用任何事实都无法推翻的表达。
- 每个逻辑维护 3–5 个支柱与 3–5 个证伪风险。
- 确认性和反方证据使用相同的来源、截至日期、新鲜度和可信度标准。
- 催化剂、证据、信息缺口和复盘记录可以被 Desk Agent 读取。
- 状态变化由证据驱动，不保存加仓、减仓、止损、退出或买卖时机指令。

## 数据合同

共享 Schema 位于 `packages/contracts/src/thesis.ts`。根对象包含：

```text
InvestmentThesisPortfolio
├── schemaVersion: newma-desk.investment-thesis.v1
├── updatedAt
└── theses[]
    ├── security: market / symbol / name / exchange
    ├── title / statement
    ├── status: draft / active / watch / invalidated / archived
    ├── conviction: high / medium / low
    ├── pillars[3..5]
    │   └── expectation / currentStatus / trend / evidenceIds
    ├── invalidationRisks[3..5]
    │   └── invalidationCondition / status / evidenceIds
    ├── linkedCatalysts[]
    ├── evidence[]
    │   └── source / asOf / freshness / confidence / impact
    ├── updates[]
    ├── valuation? / nextReviewAt / gaps[]
    └── createdAt / updatedAt
```

`impact` 只允许 `strengthened / weakened / neutral / invalidated`，用于描述证据如何改变研究命题，不代表交易动作。

## 存储

Mod 使用 Desk-managed Storage：

- namespace：`thesis-tracker`
- document key：`portfolio`
- scope：`user-workspace`
- schema version：`1`
- local fallback：`newma-desk.thesis-tracker.v1`

独立调试或 Desk Storage 不可用时保留浏览器本地降级。嵌入 Desk 后以远端文档为准，并通过 revision 做乐观并发控制。Mod 不新增数据库、服务或端口。

## 跨 Mod 关系

- 个股研究：提供证券身份、财务、公告、研报和新闻证据。
- 产业链研究：补充上下游传导、竞争替代和行业证伪条件。
- 宏观观察：补充增长、价格、流动性与行业传导背景。
- 催化剂日历：通过稳定事件 ID 关联未来验证节点。
- 我的研报 / 研究记录：保留长文本材料和研究过程；投资逻辑只沉淀结构化结论。

第一版通过稳定 ID 建立松耦合关系，不复制其他 Mod 的数据库，也不允许跨 namespace 越权读取。未来可以由 Desk 数据路由提供只读聚合视图。

## Agent Context

页面向 Desk 发布：

- 当前 `market / symbol / name`
- 核心论点、状态和确信度
- 支柱计分卡与证伪风险
- 催化剂、证据、更新日志和信息缺口
- 下次复盘时间与未保存状态

统一 Agent 可以继续调用 Desk 的轻量研究能力，补充更长周期行情、财务、公告、新闻和同业对比。新增信息必须保留来源与截至时间，并说明它增强、削弱还是不改变哪个支柱。

## 接入要求

其他项目如要复用本标准，应：

1. 使用共享合同或提供无损映射。
2. 保留稳定的 thesis、pillar、risk、catalyst 和 evidence ID。
3. 声明 `storage.read` 与 `storage.write`，由 Desk 分配 namespace。
4. 将证券身份放入 Agent Context 的 `selection.symbol / market / name`。
5. 显式列出 freshness、confidence 和 gaps，不用模型常识静默补齐缺失信息。
6. 不在 Mod 内重复实现 Agent、模型选择或独立聊天记录。
