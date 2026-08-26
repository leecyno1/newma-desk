# Domain Context

## A 股候选 Module

A 股候选 Module 从 Newma-Desk `market.scan` 提供的最新成交活跃池出发，通过 `market.ohlcv` 获取前复权日线，按趋势、动量、流动性、稳定性、估值与原 InStock 精选策略进行横截面排序。

其 Interface 输出候选排名、因子得分与贡献、经典策略确认、过热惩罚、风险、覆盖情况和 Analysis Snapshot。当前只支持最新截面，不把当前股票池用于历史回放；分数用于缩小研究范围，不是收益预测或交易指令。

## 产业链研究 Module

产业链研究 Module 是独立的 Newma-Desk 附属研究 Module。它消费 Desk Agent/Data 形成的点时证据包，描述上游、中游、下游与基础设施节点及其关系，识别其中的供应链瓶颈层，再核验上市公司的真实暴露与证伪条件。

其 Interface 只接受结构化证据，不自行抓取网页、公告、行情或调用模型。输出是产业链结构、关键节点、瓶颈层、候选研究优先级、证据覆盖、限制和 Analysis Snapshot，不是收益预测或交易指令。

## 行业与 ETF 轮动 Module

行业与 ETF 轮动 Module 只负责申万一级行业与可交易 ETF 的量价排序、确认层和稳健性实验。它不推断产业链关系，也不承载产业链研究状态。
