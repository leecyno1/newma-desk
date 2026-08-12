# Macro Monitor Standard

日期：2026-08-03
合同：`newma-desk.macro-monitor.v1`

## 目的

宏观观察是 Research 领域的上游事实基座，统一表达增长、价格、流动性、未来经济事件、证据来源、新鲜度和覆盖缺口。它不启动新的 Agent、数据库或常驻服务，也不直接生成资产配置或买卖建议。

宏观观察与 Circle / 七周期研究的边界如下：

- 宏观观察负责可核验的指标、发布日历、前值、预期、实际值和数据修订风险；
- 七周期负责通过发布门槛后的概率观察窗；
- 七周期概率不得反写宏观指标，也不得被解释为确定性的经济拐点或精确日期。

## 首版覆盖

核心指标：

- 中国官方制造业 PMI、GDP 同比、CPI 同比、PPI 同比、M2 同比；
- 中国 1 年期 LPR；
- 美国 CPI 同比。

经济日历：

- 配置 `FMP_API_KEY` 时使用 FMP Economic Calendar，单次覆盖最长 30 天；
- 未配置或 FMP 不可用时，自动降级到百度股市通经济日历；
- 公开降级源最多抓取未来 14 天，并只展示中高重要性事件；
- 降级、范围收窄和来源失败必须进入 `sources` 与 `gaps`。

首版宏观指标通过 AkShare 读取金十、东方财富等公开聚合数据。聚合源不是官方原始发布机构，因此合同固定输出 `official-primary-source-verification` 缺口，Agent 和用户应在形成重要判断前回到国家统计局、人民银行、FRED、央行或对应统计机构复核。

## 状态表达

宏观状态只做证据归纳：

- `growth`：结合 PMI 是否位于 50 上下、GDP 同比相对前值变化；
- `inflation`：比较 CPI、PPI 与前值的变化；
- `liquidity`：比较 M2 与 LPR 的边际变化；
- `signal` 仅允许 `positive / neutral / negative / mixed / unknown`。

状态不是资产涨跌预测。每个维度必须附带 `evidenceIds`，整体置信度由处于合理更新窗口的指标比例决定。陈旧数据不得被静默视为当前状态。

## 核心字段

每个指标至少包含：

- `id / name / region / category / unit`
- `period / releaseDate / nextReleaseDate`
- `value / forecast / previous / change / direction`
- `source / evidenceId / asOf / freshness / confidence`
- 轻量 `history`，用于趋势可视化，不重复保存完整上游数据。

每个经济事件至少包含：

- `date / time / region / currency / title`
- `importance / status`
- `actual / forecast / previous`
- `source / evidenceId / asOf`

## 接入规则

1. 新 Mod 通过统一能力 `research.macro-monitor` 读取，不直接绑定 AkShare、FMP 或百度。
2. 无 API Key 时正常使用公开降级源，不要求用户为页面单独配置模型或 Agent。
3. 所有来源都必须提供状态、更新时间、数量和失败原因；空数据与不可用必须区分。
4. Agent Context 至少包含宏观状态、指标、未来事件、来源状态和缺口。
5. 页面可以解释传导路径和情景，但不得输出确定性市场预测、仓位或买卖时机。

## 最小接口

```http
GET /api/research/macro-monitor?days=7
```

`days` 范围为 1–30。返回 `newma-desk.macro-monitor.v1` Feed。
