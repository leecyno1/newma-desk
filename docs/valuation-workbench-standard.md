# Newma-Desk 预测与估值标准

Mod：`valuation-workbench`
合同：`newma-desk.valuation-workbench.v1`
存储：`valuation-workbench/models`
兼容级别：Level 3

## 1. 职责与边界

预测与估值 Mod 将财报研究、同业比较和投资逻辑中的可验证输入，整理为轻量驱动式 DCF。它负责：

- 固化历史收入基期和关键经营驱动；
- 管理悲观、基准、乐观三种预测情景；
- 计算 NOPAT、D&A、CapEx、营运资本变化与 UFCF；
- 使用 WACC 和永续增长法计算企业价值；
- 完成企业价值、净债务、股权价值和稀释每股价值桥接；
- 生成以当前假设为中心的 5×5 WACC × 终值增长敏感性矩阵；
- 保留 Evidence Ledger 来源、截至日期、审计结果和数据缺口。

本 Mod 不是完整三表模型、正式估值意见、评级系统或交易建议。完整三表、Excel 交付和复杂分部估值应由 Desk Agent 在用户明确要求后作为独立交付生成。

## 2. 数据分层

运行时必须明确区分：

1. 历史事实：财报、附注、行情或 Evidence Ledger 中已披露的数据；
2. 研究假设：增长、利润率、税率、资本强度、WACC 和终值增长；
3. 模型计算：收入、EBIT、NOPAT、UFCF、现值、终值与每股价值；
4. 数据缺口：无法从统一接口读取或仍需人工核验的字段。

缺失输入必须显示为缺失或审计失败，不得使用模型记忆或无来源估算静默补齐。

## 3. 最小模型结构

### 历史基期

- 报告期；
- 收入；
- EBIT 率；
- D&A / 收入；
- CapEx / 收入；
- ΔNWC / Δ收入；
- 对应 Evidence ID。

### 资本结构

- 当前股价；
- 稀释股数；
- 总债务；
- 现金及等价物；
- 无风险利率；
- Beta；
- 权益风险溢价；
- 税前债务成本与税率。

### 三情景驱动

每个情景必须按预测年度横向展示：

- 收入增长；
- EBIT 率；
- 税率；
- D&A / 收入；
- CapEx / 收入；
- ΔNWC / Δ收入；
- 情景 WACC；
- 终值增长；
- 情景依据。

## 4. 计算规则

```text
Revenue(t) = Revenue(t-1) × (1 + Growth(t))
EBIT(t) = Revenue(t) × EBIT Margin(t)
NOPAT(t) = EBIT(t) - max(EBIT(t) × Tax Rate(t), 0)
UFCF(t) = NOPAT(t) + D&A(t) - CapEx(t) - ΔNWC(t)
Discount Factor(t) = 1 / (1 + WACC)^(t - 0.5)
Terminal Value = Final UFCF × (1 + g) / (WACC - g)
Equity Value = Enterprise Value - (Debt - Cash)
Implied Price = Equity Value / Diluted Shares
```

约束：

- `terminalGrowthPct < waccPct`；
- 使用年中折现；
- 终值增长敏感性和 WACC 敏感性均使用 5 个对称取值；
- 中心格必须等于当前情景模型输出；
- 净现金使用负净债务表示并增加股权价值；
- 稀释股数、债务、现金或基期收入缺失时，不得输出伪精确每股价值。

## 5. 审计规则

页面至少显示：

- 历史收入基期是否存在；
- 历史输入是否关联来源；
- 终值增长是否低于 WACC；
- EV 到股权价值桥接是否完整；
- 终值现值占企业价值比例；
- 悲观、基准、乐观的末期 UFCF 层级是否合理。

终值现值占企业价值超过 75% 时显示警示，但不自动禁止保存，因为高增长公司和较短显式预测期可能出现该结果。

## 6. Desk Agent 上下文

Agent 可读取：

- 当前公司、情景、币种、单位和截至日期；
- 历史输入和资本结构输入；
- 三情景逐年驱动；
- FCF 预测与价值桥接；
- 5×5 敏感性矩阵；
- 审计检查、来源和数据缺口。

Agent 默认问题组：

- 假设与口径；
- 估值与敏感性；
- 审计与更新。

Agent 可以补充更长周期财务、财报附注、管理层指引、同业数据和宏观利率，但不得把模型输出直接转换为买卖或仓位建议。

## 7. 部署与依赖

- 不新增数据库；
- 不新增模型设置；
- 不新增 Agent 服务；
- 不新增端口；
- 复用 Research 领域 API、Desk Storage、Desk Agent 与 `security.selected` 事件；
- Excel 或完整三表模型仅作为可选 Agent 交付，不进入默认运行时依赖。
