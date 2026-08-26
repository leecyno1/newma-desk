# 行情数据边界与历史容量建议

## 运行时边界

CZSC 与行业/ETF 轮动只依赖 `MarketDataProvider`，默认实现通过 Newma-Desk 统一研究数据 API 读取数据。Skill、Token、抓取网站和数据库结构都不进入分析模块；以后替换数据源时只需要让 Desk 数据服务继续输出标准化 OHLCV 与行业快照。

标准 K 线最少字段：`date/open/high/low/close/volume`，推荐同时提供 `amount`、复权方式、交易日历、数据来源与更新时间。数据按日期升序、去重，并明确 A 股使用前复权还是不复权。

项目 Adapter 会把 Newma-Desk OHLCV 响应中的实际 `source`、`asOf`、`market`、`timeframe` 与 `adjust` 保留到 DataFrame 元数据，并继续写入 Analysis Snapshot 的 `provenance`。因此 `provider=newma-desk` 表示统一数据边界，`upstream_source=tencent` 等字段表示 Desk 当次实际采用的数据来源；两层来源不会混为一个名称。兼容旧 `/api/kline` 时无法确认复权和上游来源，相关字段保持 `unknown` 或空值，不做推断。

轮动页同时消费 Desk `market.overview`，把上涨、下跌、平盘数量与市场宽度作为全局环境证据，并将 `sectors` 中的行业净流入、流入和流出匹配到 31 个一级行业。Desk 目前只提供即时行业资金，没有历史序列；项目因此将每日 Desk 行业资金摘要写入独立 SQLite 日度账本，按 `as_of` 主键同日覆盖，累计最多 5 个观察日，至少 3 日才输出持续方向。重复刷新不会制造虚假持续性，完整轮动历史的容量也不会影响日度账本。行业资金只进入所选行业的确认标签和证据说明，不参与 ETF 横截面打分；历史 `asOf` 不复用当前资金或行业资金日度账本，避免未来数据泄漏。`/api/industry` 为空时，行业广度因子仍保持中性并将结果标记为 `partial`。

## 当前历史日期能力

Newma-Desk 当前 OHLCV Interface 只有 `symbol/market/timeframe/limit/adjust`，没有原生 `asOf/end/before`，并且 `limit` 上限为 800。项目侧 Adapter 因此采用兼容降级：历史请求统一拉取最近 800 根，再按 `date <= asOf` 截断并取所需窗口。

- 目标日期仍在最近 800 根覆盖范围内：可以重放，Snapshot 标记 `as_of_mode=client_filter`。
- 日期可达但所需前置 K 线不足：继续分析，但 Snapshot 标记 `coverage=partial`。
- 目标日期早于最近窗口最早日期：返回 HTTP 422 `historical_window_unavailable`，不伪造完整历史。
- 历史轮动不使用当前 `/api/industry` 或 `market.overview.sectors` 快照，行业因子按中性分处理，也不附加当前行业资金确认，避免前视偏差。

这是一条诚实但有限的回放 Interface，不等同于可翻页的完整历史库。未来需要 3～10 年稳定复盘时，应由 Web/Desk 数据 Interface 提供可定位的历史窗口，或由项目侧持久化已授权的标准化行情快照；本项目不会扩展 Desk 本体。

## Snapshot 与证据保留

分析成功后，项目把统一 Snapshot 元数据登记到有界进程内 Registry，并通过 `GET /api/v1/analysis-snapshots/{snapshot_id}` 查询。默认 TTL 为 24 小时、容量为 512 条，采用 LRU 淘汰；服务重启后失效。Registry 不保存完整 K 线、ECharts 配置或轮动候选明细，因此不是历史行情库，也不替代 Desk Artifact。

CZSC `evidence.input_quality` 会记录输入行剔除、重复日期、金额重建和疑似大时间间隔。大间隔只是基于周期阈值的日历筛查，未使用交易所交易日历，可能包含停牌或长假；接口会把这一限制原样返回，不将其误报为确定的数据缺失。

## 当前模块需要多少历史数据

| 场景 | 建议历史 | 说明 |
| --- | ---: | --- |
| 单股 CZSC 在线分析 | 120～800 根 | 当前接口上限 800 根；按需读取即可 |
| ETF 轮动在线分析 | 每只 165 根 | 31 个一级行业 ETF 代理 + 基准；一次读取同时支撑 40/60/120 日、3 组权重的 9 模型投票和 20 日历史回放 |
| 单股结构复盘 | 3～5 年日线 | 足以覆盖多轮趋势与中枢变化 |
| 全 A 批量扫描 | 5～10 年日线 | 需复权因子、交易日历、退市标的，避免幸存者偏差 |
| 长周期策略验证 | 10 年以上或完整上市期 | 需要点时成分、停牌/退市与财务披露日期 |

在线页面不需要预先保存全市场完整历史。只有批量扫描、组合回测和可重复研究才值得建立本地历史底座。

## 粗略容量

- 全 A 约 5400 只，10 年日线约 1300 万行：Parquet 约 0.5～1.5 GB；MySQL/PostgreSQL 含索引约 1.5～4 GB。
- 加每日估值、复权因子、交易状态和常用衍生字段：约 3～10 GB。
- 全市场 1 分钟线约 3.1 亿行/年：Parquet 约 15～30 GB/年；关系数据库含索引约 40～100 GB/年。

现阶段不建议采集全市场分钟历史；先把日线、复权因子和交易日历做完整，比扩大数据频率更重要。

## 推荐数据路由

| 数据需求 | 推荐来源 | 定位 |
| --- | --- | --- |
| A 股标准历史、复权、交易日历、财务三表、估值 | Tushare，经 Newma-Desk 数据服务封装 | 长期历史底座 |
| A 股实时盘口、龙虎榜、涨停池、题材、研报、公告、融资融券、ETF 期权 | `a-stock-data` | A 股特色与实时补充 |
| 港美股行情、财务、美股期权、SEC Filing/XBRL | `global-stock-data` | 全球市场补充 |

三类来源组合后可以满足当前 CZSC、轮动和大部分原项目模块，但不能把 Skill 本身当成生产 API。生产运行应由 Newma-Desk 数据服务统一处理鉴权、频率限制、缓存、复权、字段映射、许可与失败降级；本项目只消费稳定合同。
