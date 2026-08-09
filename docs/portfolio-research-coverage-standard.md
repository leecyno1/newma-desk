# Newma-Desk Portfolio Research Coverage 1.0

## 1. 目标

Portfolio Research Coverage 连接“结构化研究档案”和“组合持仓”，用于回答：

- 当前持仓是否存在有效投资逻辑或研究备忘录；
- 是否存在财报、同业或估值等支持分析；
- 哪些逻辑已到复核日期、待更新或已证伪；
- 从组合页面应回到哪一个来源 Mod 继续研究。

它是研究可追溯性检查，不是持仓评分、投资评级、仓位建议或交易信号。

## 2. 派生合同

合同版本为 `newma-desk.portfolio-research-coverage.v1`，共享 TypeScript Schema 位于
`packages/contracts/src/portfolioResearch.ts`。

每个证券只保留：

- 市场、证券代码、名称和关联账户 ID；
- `complete / partial / missing` 覆盖状态；
- 有效引用数量；
- 已覆盖的核心与支持档案类型；
- 缺失组和需关注原因；
- 最近更新时间；
- Research Archive Index 中的最小引用。

禁止复制投资逻辑正文、研究结论、财务表、估值矩阵、新闻、行情和上传文件。

## 3. 覆盖规则

核心档案：

- `thesis`；
- `research-memo`。

支持档案：

- `earnings`；
- `peer-comparison`；
- `valuation`。

状态规则：

- `complete`：至少一份有效核心档案，且至少一份有效支持档案；
- `partial`：存在关联研究引用，但未同时满足核心与支持覆盖；
- `missing`：没有任何关联研究引用。

需关注原因只描述研究维护状态：

- `review-overdue`：有效投资逻辑的复核日期已到；
- `stale-core-research`：研究备忘录已标记待更新；
- `invalidated-thesis`：存在已证伪投资逻辑。

已归档、草稿、待更新和已证伪档案可以保留为可追溯引用，但不计入有效覆盖。

## 4. Desk Interface

```http
GET /api/portfolio-center/research-coverage
X-User-Id: <user>
X-Workspace-Id: <workspace>
```

Desk 读取成本口径组合持仓和同一用户、同一工作区的 Research Archive Index，在请求时即时编译覆盖结果。接口：

- 不读取实时行情；
- 不新增数据库表或后台任务；
- 不把派生结果再次持久化；
- 不跨用户或工作区匹配；
- 同一证券出现在多个账户时只生成一条覆盖结果，并保留账户 ID 列表。

旧 Vibe Research 持仓只允许用户在“组合设置”中明确执行迁移。读取组合或创建新工作区不得隐式导入本机旧账，否则会破坏工作区隔离。

## 5. Mod 与 Agent

组合总览显示覆盖摘要、证券级覆盖状态、缺失项、需关注原因和来源回跳。选择证券后，Desk Agent Context 可以读取该证券的覆盖摘要与引用列表。

Agent 可以据此：

- 查找缺失研究环节；
- 回到来源 Mod 补充或复核档案；
- 汇总哪些持仓需要更新研究材料。

Agent 不得把覆盖完整度解释为预期收益、确信度、仓位质量或买卖判断。

## 6. 验收

1. 组合持仓与研究档案按标准化市场和证券代码匹配；
2. 多账户同证券合并且保留账户引用；
3. 用户与工作区相互隔离；
4. 研究索引不可用时，组合账本和行情继续工作；
5. 响应不包含研究正文或底层数据；
6. 来源引用可以回到对应 Mod；
7. 当前证券覆盖摘要进入 Level 3 Agent Context。
