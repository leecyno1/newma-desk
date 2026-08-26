# A/H 股候选合同

`analysis.stock-candidates` 是独立 `instock-stock-candidates` Module 的确定性 Action。它支持 A 股、港股及联合候选池，用于缩小后续研究范围，不是收益预测、仓位建议或交易指令。

## 接口

- 页面：`GET /mods/stock-candidates`
- Action：`analysis.stock-candidates`
- HTTP：`GET /api/v1/stock-candidates/snapshots`
- 基础参数：`universeSize=30|50|100|200`、`outputSize=10|20|30`、`bars=120|240`
- 筛选画像：`profile=balanced|trend|value|defensive`
- 可选市场规则：`industries`、`minAmount`、`minMarketCap`、`maxMarketCap`、`minTurnover`、`maxTurnover`、`minVolumeRatio`、`maxVolumeRatio`。
- 可选技术规则：`minMomentum20`、`maxVolatility`、`requiredSignals`，多值使用逗号分隔。
- 可选基本面规则：`maxPE`、`maxPB`、`minROE`、`minRevenueGrowth`、`minNetProfitGrowth`、`maxValuationPercentile`。
- 可选事件引用：`eventFlowSnapshotId`。只附加证券级事件证据，不改变因子分数和排名。
- 缓存控制：普通请求复用 5 分钟结果缓存；财务横向比较也在项目 Adapter 内有界复用 5 分钟。显式 `refresh=1` 同时绕过两层缓存，强制重新读取 Desk 数据并生成新的历史版本。

## 数据边界

1. 使用 Desk 现有 `market.scan` 取得宽扫描池；当延迟扫描源盘前只有证券身份时，再用 Desk 现有 `market.quotes` 批量补腾讯价格、成交额与估值，并在项目 Adapter 内按目标字段重排。Desk 的 `market.security-master` 当前只返回证券总数与交易所统计，不返回分页证券明细，因此仍不能把扫描池宣称为全市场。
2. 使用 Desk 现有 `market.ohlcv`，读取候选的前复权日线。
3. 对财务预选池按每批最多 4 只调用 Desk 现有 `research.equity-comparison`；横向比较缺失或失败的单股再回退 `research.equity-snapshot`，读取财务质量、成长、估值、核心指标、数据质量和证据缺口。
4. 项目不直连 Tushare、东方财富或其他数据源；实际 Provider 由 Desk 决定并在结果中公开。
5. 当前扫描不支持历史截止日，因此不提供历史股票池回放，避免把今天可见的股票池用于过去日期。
6. 日线按上市历史分层：80 根及以上使用完整模型；10～79 根使用可用短窗口，并将趋势、动量、稳定性和经典策略的横截面分数按 `50 + confidence × (percentile - 50)` 向 50 分收缩，其中 `confidence=min(1, history_bars/80)`；少于 10 根只进入新股观察，不参与正式技术排名。三种情况都不视为 Desk 行情失败。
7. 盘前实时成交额尚未形成时，候选池以宽扫描池中的市值顺序作为临时入口，流动性因子使用 Desk 最近完整日 K 的成交额代理；开盘后自动切回实时成交额。

## 因子模型

`instock-stock-candidate-score-v3` 使用两阶段排序：

1. Desk 宽池先执行行业、成交额、市值、换手率、量比和扫描 PE/PB 等市场硬筛，再按已启用条件选择日线深算池。深算成功后执行动量、波动率和经典信号等技术硬筛。
2. 技术通过池使用趋势、动量、流动性、稳定性、扫描估值和经典策略完成技术预评分。输出 10 只时最多取预评分前 20 名做批量财务比较；输出 20/30 只时保留前 30 名。批次大小不超过 4，只对批量缺失项调用单股快照。
3. 在财务预选池内加入 Desk 财务质量、成长和估值评分，重新计算最终排名。

默认 `balanced` 权重：

- 趋势 20%：收盘相对 MA20、MA20 相对 MA60、MA20 斜率。
- 动量 15%：20 日与 60 日收益。
- 流动性 10%：成交额、换手率与量比。
- 稳定性 10%：年化波动率与最大回撤。
- 估值 10%：Desk `scorecard.valuation`。
- 财务质量 15%：Desk `scorecard.quality`。
- 成长 10%：Desk `scorecard.growth`。
- 原 InStock 精选策略 10%：均线多头、放量上涨、平台突破、低波动成长。

短历史股票使用实际可见窗口：快慢均线、短长动量、波动和回撤窗口都不会超过已有日线。接口同时返回 `history_bars`、`history_mode`、`technical_confidence`、`data_start`、`data_end`、`history_source` 和 `history_has_more`。若实际窗口不足 20 日，页面会显示真实动量窗口，不会把 6 日或其他短窗口误标为“20 日动量”。

其他画像依次按“趋势、动量、流动性、稳定性、估值、质量、成长、经典策略”配置：

- `trend`：25%、20%、10%、5%、5%、10%、15%、10%。
- `value`：10%、5%、10%、15%、25%、20%、10%、5%。
- `defensive`：10%、5%、10%、20%、15%、25%、10%、5%。

市场与技术硬筛选先执行，剩余股票再做预评分；ROE、营收/净利增速与估值分位等规则在 Desk 财务快照返回后执行。没有开启基本面硬条件时，Desk 财务接口失败或单个评分缺失不会淘汰股票，对应估值、质量、成长因子按 50 分中性处理；一旦用户显式开启某项基本面硬条件，该指标缺失视为不通过，不会被中性分掩盖。

单日涨幅接近涨停、换手率超过 20%、量比超过 3、高估值和高波动会触发公开惩罚。所有候选返回 `factor_scores`、`factor_contributions`、`classic_signals`、`risks` 和 `penalty_score`。

每个候选还返回 `preselection_rank`、`preselection_score` 和 `fundamentals`。`fundamentals` 包含质量/成长/估值评分、营收与净利增长、ROE、毛利率、净利率、现金转化、PE/PB、Desk 数据质量、覆盖率和证据缺口；实际字段取决于 Desk 当时可用数据。

## 输出边界

- `data_state=partial` 表示真实 K 线请求失败、财务快照失败或财务因子缺失；短上市历史不会把整批结果标成不完整。
- `screening_coverage` 分开公开宽池、市场规则通过数、深算数、技术规则通过数、财务评估数、全部规则通过数、规则排除数，以及未进入动态财务预选池的数量；`excluded_by_rules` 只记录真正未通过规则的股票，不把两阶段预筛之外的股票误算成规则淘汰。
- `coverage.short_history_count` 公开 10～79 根日线且已使用置信度收缩模型的股票数。
- `new_listing_watchlist` 公开少于 10 根日线、暂不参加正式技术排名的股票；兼容字段 `history_exclusions` 返回同一列表，`coverage.new_listing_watch_count` 和 `coverage.history_excluded_count` 公开数量。
- 候选的 `amount_source` 公开流动性使用 `scan_realtime` 还是 `latest_daily_bar_proxy`，代理口径会写入 `limitations`。
- `coverage` 公开市场/技术/基本面各阶段排除数、财务覆盖、批次数、单股回退数，以及批量/单股各自的失败数、超时数、超时预算和并发上限。批量比较最多同时 3 批、单批允许 60 秒；单股回退最多同时 3 只、单股沿用 20 秒 Desk 超时。
- 财务预选池按输出数量动态收敛，结果通过 `two_stage_preselection_top_20` 或 `two_stage_preselection_top_30` 明示；其余股票不进入最终输出。
- `calibrated_backtest=false` 表示模型尚未完成统一样本外校准。
- `evidence_quality` 集中公开证券池、日线、财务、流动性、点时复盘和样本外校准六项状态；不计算掩盖关键缺口的综合可信度分。证券池分页和历史点时数据尚未具备时，定位固定为 `research_candidate_only`。
- `candidate_lifecycle`（`schema_version=2.0`）只比较市场、覆盖方式、池规模、输出数量、历史窗口、筛选画像和筛选条件完全一致的持久化候选历史；按 `as_of` 去重后记录首次出现、累计出现、连续观察以及上一期排名/分数变化。它只描述实际保存过的同口径候选观察，不是未来收益回测；历史记录缺失或旧快照没有同口径标记时，页面不会把轨迹当作可靠证据。
- Snapshot 记录 `market.scan + market.quotes + market.ohlcv + research.equity-comparison + research.equity-snapshot fallback` 来源、候选覆盖、模型版本和结果摘要，不保存完整 K 线。
- 页面点击候选会发送 `security.selected`，供 Desk、CZSC 或其他研究 Module 继续使用。
