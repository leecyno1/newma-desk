# 外部金融项目隔离试用与审计

审计日期：2026-07-27
状态：Quarantined Pilot，默认关闭
范围：`daily_stock_analysis`、`QuantDinger`
明确排除：Qlib

## 结论

两个上游项目都不应整仓注册为 Newma-Desk 默认 Mod。Newma-Desk 只在 Quarantined Pilot 中验证可复用的实现，再通过 Desk 自有的统一数据、事件、导航、设置和右侧 Agent Interface 暴露能力。

- `daily_stock_analysis` 适合补充研究任务编排、报告历史、多数据源降级和数据质量诊断，试用模式固定为 `analysis-only`。
- `QuantDinger` 适合补充回测、Strategy Ledger、指标目录和实验归因，试用模式固定为 `paper-only`。
- 上游自带 Agent、模型调用、通知、账户体系和真实交易链路都不进入 Desk。
- 两个试用均由 [`config/external-finance-mod-pilots.json`](../../config/external-finance-mod-pilots.json) 统一约束，未通过全部验收门槛前不进入 `mods/store.json`。

## 现有个股研究的增强方式

FinanceToolkit 与 EdgarTools 不作为新的独立 Mod 引入。它们的理念已经落入现有个股研究 Module：

- A 股、港股、美股使用相同的估值、增长、盈利与资本效率、现金流、资产负债、披露证据六个维度。
- Market Research Adapter 只负责按市场采集和归一事实，不改变共同研究框架。
- Evidence Ledger 保存来源、原字段、截止日期、单位、币种、置信度和缺口。
- EDGAR 是美股可选披露 Adapter；未配置 SEC User-Agent 时不影响 A/H/US 共同页面。
- Desk Agent 必须引用 Evidence Ledger，不得用模型常识填补数据缺口。

## daily_stock_analysis

### 审计基线

- 上游：<https://github.com/ZhuLinsen/daily_stock_analysis>
- Revision：`905c339d80ad2daa6fd2bab3bb10267b23c7ac1c`
- Tag：`v3.28.0`
- License：MIT
- 上游默认 Web 端口：`8000`，与现有运行环境冲突；试用保留端口为 `8921`。

### 可吸收实现

- 分析上下文包和任务阶段表达。
- 报告历史、复制与任务进度。
- 数据来源按优先级降级与 last-good 缓存思路。
- 定时分析计划和失败重试流程。
- 数据质量、来源状态和诊断信息。

### 必须剔除

- 买卖点、看多看空、评分和操作建议。
- 项目自带 Agent、LLM 路由和凭据读取。
- Futu、Longbridge 等券商或真实账户导入。
- 重复的组合账户、通知、回测和设置页面。
- 直接访问外部数据源；试用只允许经过 Desk 统一数据 Interface。

### 风险结论

Python 源码编译检查通过，未发现提交的常见密钥文件。依赖文件大量使用范围版本，并包含 Git revision 依赖；`pip-audit --no-deps` 因 `python-dotenv>=1.0.0` 等未锁定依赖拒绝给出确定结论。因此当前依赖审计状态是 `blocked-unpinned-requirements`，不是“无漏洞”。进入可运行试用前必须生成带哈希的锁文件并重新审计。

## QuantDinger

### 审计基线

- 上游：<https://github.com/OpenByteInc/QuantDinger>
- Revision：`23b1aad65c87ef9c5e5424830e99794075a0e632`
- Tag：`v5.0.8`
- License：Apache-2.0
- 上游默认端口：后端 `5000`、前端 `8888`、移动端 `8889`；试用保留端口为 `8922`。

### 可吸收实现

- 回测引擎及结果读取。
- Strategy Ledger 和实验版本记录。
- 指标目录、指标组合和可复现实验参数。
- 收益、风险、费用和性能归因。

### 必须剔除

- `live_trading`、`quick_trade` 与真实订单链路。
- Alpaca、IBKR、币安、OKX、Bitget、Gate 等券商或交易所 Adapter。
- 券商凭据、交易所 Secret 和真实账户状态。
- `/api/agent/v1`、MCP Server 与项目自带 Agent。
- 支付、社区、多用户账户和部署运维页面。
- 任意用户策略代码执行；试用只允许已审核的策略模板和参数。

### 风险结论

Python 源码编译检查通过，未发现提交的常见密钥文件。`requirements.lock` 的直接锁定依赖扫描未发现已知漏洞；完整传递依赖解析超过限定时间仍未收敛，因此最终依赖门槛仍未通过。上游仓库明确包含真实交易实现，且 `quick_trade.py` 在多重开关满足时能够进入真实下单分支。即使上游提供 live guard，Desk 仍把相关实现视为不可达代码：试用进程不得获得凭据，Desk 能力策略不得暴露订单 Action，网络也不得直连券商或交易所。

## 机器可验证的隔离策略

运行：

```bash
npm run pilots:check
```

检查内容包括：

- `defaultEnabled` 必须为 `false`。
- 仅允许 `analysis-only` 或 `paper-only`。
- 固定完整 Git revision。
- 只绑定 `127.0.0.1`，且不占用 Desk 和现有 Mods 端口。
- 环境变量白名单不得包含 Key、Token、Secret、Password、Broker 或 Credential。
- 所有试用都必须拒绝真实交易、订单、内置 Agent、模型调用、通知和凭据读取。
- `paper-only` 必须额外拒绝 live enable、broker connect、MCP 和任意策略代码执行。
- 试用只通过 Desk 统一数据 Interface 读取市场数据，数据写入限定在独立目录。

## Desk Pilot Extraction Interface

Desk API 已提供统一状态与提取入口：

- `GET /api/finance-pilots`：返回默认关闭、审计状态、工作区与允许能力，不读取或返回任何 Secret。
- `POST /api/finance-pilots/daily-stock-analysis/adapt`：只接收研究上下文、数据质量、报告历史和任务进度，输出 `newma-desk.daily-stock-analysis-context.v1`。
- `POST /api/finance-pilots/quantdinger/adapt`：只接收纸面回测结果，输出 `newma-desk.strategy-ledger.v1`。

两个入口都经过同一个运行时闸门。即使手动设置启用环境变量，只要固定版本依赖审计不是 `no-known-vulnerabilities`，调用仍返回 `409 finance_pilot_activation_blocked`。QuantDinger Adapter 还会主动拒绝 live 模式、订单、券商、凭据与任意策略代码字段。

## 验收门槛

| 门槛 | daily_stock_analysis | QuantDinger |
| --- | --- | --- |
| 固定版本依赖审计 | 未通过，需生成锁文件 | 直接锁定依赖未发现漏洞；完整传递解析超时，最终门槛未通过 |
| 常见密钥静态检查 | 通过 | 通过 |
| 独立端口 | `8921` | `8922` |
| 数据出口 | Desk-only | Desk-only |
| Agent | 仅 Desk 右侧 Agent | 仅 Desk 右侧 Agent |
| 交易能力 | 全部禁止 | 仅回测/纸面实验，真实交易禁止 |
| 凭据 | 禁止券商与模型凭据 | 禁止券商、交易所与模型凭据 |
| 默认商店注册 | 禁止 | 禁止 |

## 当前 Go / No-Go

| Pilot | 当前决策 | 原因 | 允许继续的工作 |
| --- | --- | --- | --- |
| daily_stock_analysis | **No-Go** | 依赖未锁定，无法给出可靠漏洞结论 | 继续完善 Desk 自有研究上下文 Adapter 与离线 fixture；不得启动上游运行时 |
| QuantDinger | **No-Go** | 直接锁定依赖未发现漏洞，但完整传递依赖审计超时 | 继续完善纸面 Strategy Ledger、回测归因与测试 fixture；不得接券商、真实订单或上游 Agent |

`npm run pilots:check` 会直接输出两项的 `decision=no-go`。只有重新固定版本、完成传递依赖审计并通过其余门槛后，决策才可改为 Go；即使 Go，也只发布经过提取的 Desk Mod，不运行上游整仓。

只有依赖审计、能力合同、无端口冲突、凭据隔离、响应式嵌入和 Desk Agent Context 全部通过后，才能提交单独的 Go/No-Go 决策。通过也只代表可以发布经过提取的 Newma-Desk Mod，不代表允许运行上游整仓。
