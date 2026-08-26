# InStock → Newma-Desk 功能迁移矩阵

目标不是复刻上游的 27 张数据库表格，而是把仍有研究价值的能力整理成 Desk 原生工作台。生产数据只通过 Desk Interface 读取；项目内只做确定性计算、解释和可视化。

| 上游功能 | Newma-Desk 去向 | Desk 数据 | 项目内计算 | 状态 |
| --- | --- | --- | --- | --- |
| 综合选股 | A 股候选 | `market.scan`、`market.quotes`、`market.ohlcv`、`research.equity-comparison`、`research.equity-snapshot` 回退 | 扫描身份与腾讯批量行情组合、技术预筛、批量财务重排、规则过滤、风险惩罚 | 已迁移 |
| 每日股票数据 | 市场概览 | `market.scan`、`market.overview`、`market.emotion` | 榜单归并、市场宽度、行业强弱、涨跌停与连板梯队 | 已迁移 |
| 每日 ETF 数据 | 行业与 ETF 轮动 | `market.ohlcv`、`market.overview` | 31 个一级行业 ETF 代理、量价轮动 | 已迁移 |
| 股票指标数据 | 技术与策略信号 | `market.ohlcv` | MACD、KDJ、RSI、BOLL、ATR、CCI、MFI、OBV 等 | 已迁移 |
| 指标买入 / 指标卖出 | 技术与策略信号 | `market.ohlcv` | 金叉、均线、超买超卖、趋势破位等规则 | 已迁移 |
| 股票 K 线形态 | 技术与策略信号 | `market.ohlcv` | 精选高解释度蜡烛形态识别 | 已迁移 |
| 放量上涨 | 技术与策略信号 | `market.scan`、`market.ohlcv` | 原规则 Desk 化 | 已迁移 |
| 均线多头 | 技术与策略信号 | `market.ohlcv` | 原规则 Desk 化 | 已迁移 |
| 停机坪 | 技术与策略信号 | `market.ohlcv` | 涨停后窄幅整理识别 | 已迁移 |
| 回踩年线 | 技术与策略信号 | `market.ohlcv` | MA250 突破与缩量回踩 | 已迁移，短窗口明确不可用 |
| 突破平台 | 技术与策略信号 | `market.ohlcv` | 平台突破与量能确认 | 已迁移 |
| 无大幅回撤 | 技术与策略信号 | `market.ohlcv` | 上涨质量与回撤约束 | 已迁移 |
| 海龟交易 | 技术与策略信号 | `market.ohlcv` | 60 日价格突破 | 已迁移 |
| 高而窄旗形 | 技术与策略信号 + 事件与资金 | `market.ohlcv` + `capital.dragon-tiger` | 价格前置条件成立后按需核验；仅机构专用席位净买为正确认，普通龙虎榜净买不替代 | 已迁移 |
| 放量跌停 | 技术与策略信号 | `market.scan`、`market.ohlcv` | 跌停与异常量能识别 | 已迁移 |
| 低 ATR 成长 | 技术与策略信号 | `market.ohlcv` | 低波动趋势识别 | 已迁移 |
| 基本面选股 | A 股候选 + 股票研究档案 | `market.scan`、`research.equity-comparison`、`research.equity-snapshot` | 候选批量估值/质量/成长筛选，单股档案完整证据拆解 | 已迁移，缺失项中性化 |
| 股票资金流向 | 个股事件与资金 | Desk Research HTTP Interface | 标准化、异常强度、证券归并 | 已迁移，按来源披露空值与失败 |
| 行业资金流向 | 市场概览 + 行业轮动 | `market.overview` | 市场概览展示行业净额；轮动按行业别名匹配，并写入项目 SQLite 日度账本形成最多 5 日持续性确认，不改变综合分 | 已迁移 |
| 概念资金流向 | 个股事件与资金 | Desk 概念资金 capability | 概念归并、持续性识别 | P1，等待正式 capability，禁止用概念归属或行业行情替代 |
| 涨停原因 | 个股事件与资金 | Desk 涨停原因 capability | 事件去重与主题归因 | P1，等待逐股正式 capability；`market.emotion` 不含涨停原因 |
| 股票龙虎榜 | 个股事件与资金 | Desk Research HTTP Interface | 机构席位、净买卖异常 | 已迁移 |
| 股票大宗交易 | 个股事件与资金 | Desk Research HTTP Interface | 折溢价、规模与连续性 | 已迁移 |
| 股票分红配送 | 个股事件与资金 + 股票研究档案 | Desk Research HTTP Interface | 股息与除权事件摘要 | 已迁移，经事件 Snapshot 进入股票档案 |
| 早盘抢筹 | 筹码与异动工作台 | Desk 集合竞价委托 capability | 开盘金额、抢筹幅度、委托金额、成交金额与占比 | P2，等待竞价委托字段；禁止用分钟 K 线伪装 |
| 尾盘抢筹 | 筹码与异动工作台 | Desk 尾盘委托 / 撮合 capability | 收盘金额、抢筹幅度、委托金额、成交金额与占比 | P2，等待尾盘委托字段；禁止用分钟 K 线伪装 |
| 我的关注 | 研究组合 | Desk Context / 宿主存储 | 研究理由、证伪条件、Snapshot 引用 | 研究模型已迁移，持久化归宿主 |

## 新前端信息架构

1. 市场概览：市场宽度、行业和股票榜单。
2. A 股候选：多条件扫描和可解释排序。
3. 技术与策略信号：指标、K 线形态和经典策略统一扫描。
4. CZSC 结构：分型、笔、中枢与官方信号。
5. 股票研究档案：基本面、估值、公告、研报、新闻与技术结构。
6. 个股事件与资金：资金流、龙虎榜、大宗交易、涨停原因和公司行动。
7. 行业与 ETF 轮动：31 个一级行业与可交易 ETF 代理。
8. 产业链研究：产业链节点、瓶颈与上市公司暴露。
9. 策略验证与研究组合：点时回测、样本外检验和研究清单。

旧 `stock_web.html`、`stock_indicators.html` 只保留上游诊断兼容，不进入 Newma-Desk Suite。
