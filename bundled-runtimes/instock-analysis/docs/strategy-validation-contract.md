# 策略验证合同

## 定位

`instock-strategy-validation` 是选股、CZSC 与轮动共用的点时验证 Module。它集中执行语义和偏差检查，不替代信号来源，也不生成交易指令。

## 输入

Action：`analysis.strategy-validation`

HTTP：`POST /api/v1/strategy-validations`

输入包版本为 `instock-strategy-validation-packet-v1`，主要字段：

- `strategy.id`、`strategy.name`、`strategy.source_module`。
- `source_module` 仅支持 `stock-candidates`、`czsc`、`rotation`。
- `as_of`：验证截止日。
- `benchmark`：6 位比较基准代码。
- `holding_period_sessions`：1～60 个交易日。
- `cost_bps_per_side`：单边 0～100 bps。
- `signals`：2～200 条严格按日期递增的历史决策；每条包含决策日和 1～20 个等权标的。

## 固定执行语义

- 决策时点：`decision_date` 收盘。
- 执行时点：下一交易日开盘。
- 平仓：开仓后固定交易日数的开盘。
- 组合：同一决策内标的等权。
- 成本：每次完整计入买入和卖出双边成本。
- 切分：按时间顺序前 65% 为训练区间，后 35% 为样本外区间。

策略验证与轮动稳健性实验共用 `instock/core/validation/` 内部实现，包括有效开盘价、下一交易日执行窗口、双边成本、复合收益、年化波动、Sharpe、最大回撤、信息比率和基准超额，避免两套口径漂移。

## 输出

- `train`、`out_of_sample`：收益、年化、年化波动、Sharpe、最大回撤、胜率、信息比率、基准与超额。
- `coverage`：输入信号、成功执行、失败和证据门槛。
- `trades`：决策日、执行日、标的和净收益。
- `failures`、`limitations`、`verdict`。
- `snapshot`：稳定 Analysis Snapshot。

行情只通过 Desk `market.ohlcv` 获取，最多使用最近 800 根。输入信号必须来自当时保存的研究记录；本模块不会用今天的候选池、CZSC 结构或轮动排名重建过去决策。
