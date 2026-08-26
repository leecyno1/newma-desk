# 股票研究档案合同

## 定位

`instock-stock-research` 是单标的研究档案 Module。它把 Newma-Desk 提供的基本面、估值、公告、研报、新闻证据与项目内 CZSC 技术结构组合成可审计底稿，用于继续研究，不输出评级、目标价或买卖建议。

## 数据边界

- `research.equity-snapshot`：公司身份、估值、成长、盈利质量、财务证据账本。
- `market.ohlcv`：前复权 K 线，供 CZSC 结构分析使用。
- `market.announcements`：近期公告。
- `market.reports`：近期研报索引。
- `market.news`：近期相关新闻。
- 可选产业链 Snapshot：只引用项目 Snapshot Registry 中已存在的 `instock-industry-chain-research` 结果。
- 可选事件资金 Snapshot：按当前股票过滤 `instock-event-flow` 的去重事件、强度与时效证据。

项目不直连 Tushare、网站或旧 InStock 数据库。公告、研报或新闻暂时不可用时，档案返回 `partial` 并公开失败项，不伪造内容。

## 接口

Action：`analysis.stock-research`

HTTP：`GET /api/v1/stock-research/dossiers`

参数：

- `symbol`：必填，6 位 A 股代码，可带 `.SH`、`.SZ`、`.BJ`。
- `period`：`daily`、`weekly`、`monthly`，默认 `daily`。
- `bars`：`120`、`240`、`480`、`800`，默认 `240`。
- `asOf`：可选历史截止日。
- `industryChainSnapshotId`：可选产业链 Snapshot ID。
- `eventFlowSnapshotId`：可选事件与资金 Snapshot ID。

## 输出

- `identity`：证券身份。
- `technical`：CZSC 引擎、摘要、结构与证据。
- `fundamentals`：指标、scorecard、质量和 Evidence Ledger。
- `disclosures`：公告、研报、新闻及覆盖数量。
- `industry_chain`：可选产业链 Snapshot 摘要。
- `event_flow`：可选证券级事件与资金证据，不作为收益预测。
- `assessment`：优势、张力、证据缺口与中性结论。
- `failures`、`limitations`、`data_state`：数据降级说明。
- `snapshot`：分析版本、输入、来源、覆盖与结果摘要。

## 历史点时规则

选择 `asOf` 后，档案不允许把当前证据伪装成历史证据：

- K 线按 `date <= asOf` 过滤。
- 公告、研报和新闻按自身日期过滤；Desk 当前只提供最新窗口，所以结果会标记客户端点时过滤限制。
- 如果 Desk 的股票基本面 Snapshot 生成时间晚于 `asOf`，档案排除当前估值、当前预期和当前综合 scorecard，只保留 `evidenceLedger` 中截止日前有明确日期锚点的财务指标。
- 事件 Snapshot 可晚于研究截止日，但只保留截止日前事件，并按研究截止日重算时效与强度；早于研究截止日的事件 Snapshot 不允许补齐之后区间。
- 产业链 Snapshot 晚于研究截止日时拒绝引用，避免把事后产业链证据回填到历史档案。
- 触发上述降级时 `data_state=partial`，页面显示“点时完整性”说明。

## 综合判断规则

`assessment` 是证据归纳，不是预测评分：

- 基本面 scorecard 的 `strong` 进入优势，`weak` 进入张力。
- CZSC `bullish` 进入优势，`bearish` 进入张力；震荡且趋势强度不足时进入证据缺口。
- 已引用事件 Snapshot 时，各取强度最高的正向和负向事件进入优势与张力；事件不改变基本面或技术分数。
- 已引用产业链 Snapshot 时，高或中置信的已核验暴露进入优势，证伪条件进入张力；低置信暴露进入缺口。
- `evidence_balance` 只统计各类证据数量，便于页面快速判断覆盖，不形成加权总分或买卖建议。
- `invalidation_conditions` 将当前研究成立所依赖的基本面、技术、事件与产业链证据转为明确证伪条件，供研究组合持续复核，不代表自动交易规则。

## 页面联动

页面路径为 `/mods/stock-research`。页面接收 Desk `security.selected` 切换标的，也可发出同一事件联动 CZSC 等其他 Module。页面只把紧凑研究摘要放入 Desk Context，不复制完整公告、新闻或行情数据。

### URL 交接参数

跨 Module 打开股票研究页时使用以下参数：

| 参数 | 用途 | 是否参与计算 |
| --- | --- | --- |
| `symbol` | A 股代码；兼容 `code` 别名 | 是 |
| `period` | `daily`、`weekly`、`monthly` | 是 |
| `bars` | `120`、`240`、`480`、`800` | 是 |
| `asOf` | 历史截止日；兼容 `as_of` 别名 | 是 |
| `sourceModule` | 交接来源 Module | 否，仅页面展示 |
| `sourceSnapshotId` | 来源页面本次分析的 Snapshot | 否，仅用于追溯 |
| `eventFlowSnapshotId` | `instock-event-flow` 事件证据 | 是，解析成功后进入档案 |
| `industryChainSnapshotId` | `instock-industry-chain-research` 产业链证据 | 是，解析成功后进入档案 |

普通来源快照和证据快照必须分开：`sourceSnapshotId` 不会转发给 `analysis.stock-research`，不能改变评分或结论；只有两个明确的证据 Snapshot 参数可以进入计算。

事件证据示例：

```text
/mods/stock-research?symbol=300502&period=daily&bars=240&asOf=2026-08-12&sourceModule=instock-event-flow&sourceSnapshotId=instock-event-flow%3A...&eventFlowSnapshotId=instock-event-flow%3A...
```

### Snapshot 解析边界

- Snapshot 必须存在于当前附属运行时的进程内 Registry，且分析类型必须匹配。
- 事件 Snapshot 会按当前股票代码过滤；产业链 Snapshot 只提取当前股票已核验的证券暴露。
- Snapshot 不存在、类型不匹配或没有当前证券证据时，不会静默替代为其他数据；结果通过 `limitations` 和 `partial` 状态披露。
- Registry 默认最多 512 条、保存 24 小时，服务重启后失效，不是 Desk 的持久化研究库。
- 页面明确显示“已进入本次计算”或“未解析，未进入本次计算”，便于人工验收。

### `security.selected` 边界

- 只接收中国市场股票；ETF、指数、基金和非中国市场事件不会触发股票研究。
- 切换到新股票时，若事件没有显式携带证据 Snapshot，页面会清空旧事件和产业链引用，避免跨股票串用证据。
- 当前 Desk iframe 不提供子页面切换宿主 Mod 的能力，所以跨 Module 链接以新页打开；不扩展 Desk Bridge Protocol。
