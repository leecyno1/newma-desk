# Newma-Desk 财报研究标准

日期：2026-08-04
合同：`newma-desk.earnings-research.v1`

## 目标

财报研究 Mod 把财报前与财报后的工作放进同一份结构化底稿：

```text
最新报告期与来源核验
        ↓
内部预期 / 一致预期 / 公司特定指标
        ↓
实际结果与 Beat / Miss
        ↓
差异驱动、利润率、经营指标与指引变化
        ↓
预测修订与投资逻辑影响
        ↓
下一期验证条件和数据缺口
```

页面只记录事实、预期、研究假设和逻辑影响，不保存评级、目标价、买卖动作或财报后的价格反应预测。

## 数据合同

共享 Schema 位于 `packages/contracts/src/earnings.ts`。根对象包含：

- 证券身份、市场、币种；
- `preview / reported` 模式；
- 报告期、期末日、披露日和披露时段；
- 最新报告期核验状态和主要来源；
- 财务指标与公司特定经营指标；
- 实际、内部预期、一致预期及金额、百分比或基点差异；
- 当前与上次管理层指引；
- 高于、符合、低于预期三种条件情景；
- 旧预测、新预测和修订原因；
- 对 Thesis 支柱的 `strengthened / weakened / neutral / invalidated` 影响；
- 来源材料、截至日期和数据缺口。

## 来源与截至日期

1. 使用数据前先验证最新报告期，不把模型记忆当成财报事实。
2. 公司财报、交易所或监管披露和管理层材料优先于新闻摘要。
3. 一致预期必须标注来源和快照日期；缺少时保持空值，不静默估算。
4. 财报差异需要检查会计口径、基数、一次性项目、季节性、并购和汇率等影响。
5. 当前指引必须与上次指引使用相同口径比较；口径变化本身也要记录。

## 数据与存储复用

首版不新增数据库、后端服务或端口。页面复用：

- `equityResearch`：跨市场证券身份、证据账本、来源诊断和缺口；
- `financials`：A 股最新财务摘要；
- `announcements / reports / news`：公告、研报与新闻证据入口；
- Desk Agent：延伸读取更长周期财务、经营数据和外部证据；
- Desk-managed Storage：保存用户录入的预期、指引、修订和逻辑影响。

存储配置：

- namespace：`earnings-workbench`
- document key：`workbooks`
- scope：`user-workspace`
- schema version：`1`
- local fallback：`newma-desk.earnings-workbench.v1`

## Agent Context

页面向统一 Desk Agent 发布当前证券、报告期、模式、来源核验、预期差、经营指标、指引、条件情景、预测修订、Thesis 影响和数据缺口。

Agent 可以继续查询页面之外的数据，但新增内容必须：

- 给出来源和截至日期；
- 区分财报事实、管理层表述、市场一致预期和研究假设；
- 说明它如何改变经营假设、预测或 Thesis 支柱；
- 不直接转换为买卖、仓位或价格反应建议。

长篇 DOCX 财报前瞻或财报复盘报告属于可选 Agent 任务，不进入 Mod 运行时代码。

## 接入要求

其他项目接入本标准时应：

1. 使用共享合同或提供无损映射；
2. 保留稳定的 workbook、metric、source、revision 和 thesis-impact ID；
3. 声明 `storage.read / storage.write`，由 Desk 分配 namespace；
4. 将证券与报告期放进 Agent Context；
5. 显式展示未核验、来源失败和缺失一致预期；
6. 不在 Mod 内重复实现 Agent、模型设置、聊天记录或独立数据库。
