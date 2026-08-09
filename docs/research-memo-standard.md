# Newma-Desk 研究备忘录标准

Mod：`research-memo`
合同：`newma-desk.research-memo.v1`
存储：`research-memo/memos`
兼容级别：Level 3

## 1. 定位

研究备忘录是投研流程的收敛层，不是新的数据孤岛。它把投资逻辑、财报、同业、估值、催化剂、产业链、宏观和资讯档案汇总成可讨论、可证伪、可版本化的研究结论，再交给 Desk Agent 或 Orchestra。

研究候选应先在 `idea-funnel` 完成双向假设、来源审计和研究任务，再进入深度研究与备忘录收敛；原始扫描结果不得直接升级为备忘录结论。

基本原则：

- 先写研究结论，不从公司简介开始；
- 通过 `sourceModId + artifactId` 引用底层档案，不复制其全部数据；
- 区分已报告事实、管理层指引、市场预期和研究推断；
- 重要判断保留来源、截至日期、状态与数据缺口；
- 三种情景必须有可观察触发条件，概率合计为 100%；
- 必须主动记录反方证据、逻辑断点和后续跟踪指标；
- 保存研究偏向与确信度，但不保存买卖评级、仓位或个性化建议。

## 2. 引用关系

每个关联档案至少包含：

```text
kind + sourceModId + artifactId + title + asOf + status
```

标准来源 Mod：

| 研究内容 | 来源 Mod | 典型档案 |
| --- | --- | --- |
| 核心论点与证伪 | `thesis-tracker` | Investment Thesis |
| 财报前后预期差 | `earnings-workbench` | Earnings Workbook |
| 竞争与可比口径 | `peer-comparison` | Peer Case |
| 预测与估值 | `valuation-workbench` | Valuation Model |
| 事件与观察窗 | `catalyst-calendar` | Catalyst Event |
| 产业链位置 | `industry-map` | Industry Artifact |
| 宏观状态 | `macro-monitor` | Macro Snapshot |

引用状态为 `linked / stale / missing`。来源档案变化时，备忘录不会静默覆盖原结论；用户或 Agent 必须创建新版本并说明判断变化。

## 3. 最小结构

一份可发布备忘录至少包含：

1. 证券与研究边界：市场、代码、报告币种、截至日期、预测期、财年、覆盖范围和披露限制；
2. 执行结论：研究偏向、确信度、结论、核心论点、关键争议、差异认知、市场可能遗漏和逻辑断点；
3. 三至七项关键驱动：重要性、当前判断、监控指标、确认条件和证伪条件；
4. 悲观、基准、乐观情景：概率、经营路径、估值档案引用和触发条件；
5. 催化剂与风险：未来 3–6 个月事件、确认/失效条件、领先预警和断点；
6. 监控面板：最新状态、趋势、阈值、频率和下次复核日；
7. 来源与缺口：证据类型、截至日期、核验状态和未完成项；
8. 版本记录：版本号、创建时间、变更摘要和变化章节。

## 4. 事实分层

`claimType` 必须使用以下值之一：

- `reported`：财报、公告或官方数据中的已报告事实；
- `guidance`：管理层指引或正式公司评论；
- `consensus`：市场一致预期或第三方估算；
- `inference`：研究员或 Agent 的推断。

无法核验的数据使用 `stale / unavailable` 或写入 `gaps`，不得用模型记忆静默补齐。

## 5. Agent Context

右侧 Desk Agent 可以读取当前备忘录的：

- 研究边界和执行结论；
- 关联档案 ID 与状态；
- 驱动、三情景、催化剂、风险和监控项；
- 来源、缺口、版本历史和未保存状态。

默认问题组：

- 结论与证据：收敛结论、审计引用与来源；
- 反方与情景：挑战核心论点、校验三情景；
- 补充与版本：读取页面之外的数据、形成下一版更新清单。

Agent 可以按需补充更长周期财务、公告、电话会、同业、产业链、宏观和新闻，但新增信息必须说明来源、截至日期及其对当前判断的影响。

## 6. 存储与部署

- Desk-managed Storage 命名空间：`research-memo`；
- 文档键：`memos`；
- 本地缓存：`newma-desk.research-memo.v1`；
- 支持 `security.selected` 事件；
- 不新增数据库、服务、端口、模型设置或独立 Agent；
- 底层研究档案继续由各自 Mod 维护；
- 页面通过懒加载进入 Research 运行时，单页构建产物保持低于 256 KiB。
