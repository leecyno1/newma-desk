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
- `capital_model`（可选）：`{mode: "fixed_sleeves", slots: 1..20}`；不传时只做逐笔诊断，不把重叠信号当作无限本金组合。

## 固定执行语义

- 决策时点：`decision_date` 收盘。
- 执行时点：下一交易日开盘。
- 平仓：开仓后固定交易日数的开盘。
- 组合：同一决策内标的等权。
- 成本：逐笔诊断扣简单双边成本；固定分仓的买入费用含在预算内、卖出费用按退出金额计提。
- 切分：按完整原始信号顺序前 65% 为训练区间，后 35% 为样本外；跨界训练持有期剔除，不向训练泄漏样本外收益。
- 日期：独立 SSE 交易日历，不用行情缺日缩短持有期，也不外推跨境底层市场日历。
- 量价：计划买卖日必须有正开盘价和正日成交量。全天有量只作事后证据，不代表开盘成交容量。
- 限价（引擎 1.6.0）：股票 `daily + stk_limit`，ETF `fund_daily + etf_limit`，仅同标的同日期原始开盘与限价配对；不拿复权行情和统一 10% 阈值替代。买入在涨停、卖出在跌停时不确认成交，不输出该笔收益；缺配对则仅保留明确标注的理论诊断，不给出 `diagnostic_ready`。
- 固定分仓：份额独立滚动、不借款、不转移资金、先退出后入场、满仓跳过。触限或执行缺口传播现金与持仓未知；不根据事后证据重新选股、分配本金。训练与样本外是独立账本。

策略验证与轮动稳健性实验复用 `instock/core/validation/` 的基础计算。历史限价核验本轮仅接入策略验证，不声称轮动实验已同步完成。

## 输出

- `train`、`out_of_sample`：收益、年化、年化波动、Sharpe、最大回撤、胜率、信息比率、基准与超额。
- `coverage`：输入信号、成功执行、失败和证据门槛。
- `trades`：决策日、执行日、标的和净收益。
- `trades[].price_limit_checks`：每个标的买/卖方向的 `checked/adverse/unverified` 状态、原始开盘、上下限及原因。
- `validation_audit.execution_evidence.price_limits`：全部计划买卖项的配对、触限、未核验数，以及数据源、接收时间、失败原因；含跨界和满仓跳过记录，不等于实际分仓成交次数。
- `capital_backtest`（显式开启时）：训练与样本外分仓账本、每日开盘交易前后及收盘采样净值。缺估值不补零、不跨缺口确认完整回撤；期末金额已知仍可展示端点收益。
- `failures`、`limitations`、`verdict`。
- `snapshot`：稳定 Analysis Snapshot。

收益行情通过 Desk `market.ohlcv` 获取，最多使用最近 800 根；独立日历和原始限价分别通过 Desk `/api/capital-flow/trading-calendar` 与 `/api/capital-flow/execution-prices` 获取。限价源失败时不把旧缓存追认为本次成功配对。`fund_daily` 是供应商原始日线（复权因子另有接口），不宣称其文档直接写明“未复权”。

旧历史不覆写、不自动追认当前规则；页面与 Agent 一致提示重跑。输入信号必须来自当时保存的研究记录；本模块不会用今天的候选池、CZSC 结构或轮动排名重建过去决策。基准为理论毛收益。未实现停复牌状态、整手、开盘容量、排队、部分成交、税费和独立分红现金流；通过核验不代表策略有效或可以实盘。
