# Macro Monitor Standard

更新：2026-10-06
合同：`newma-desk.macro-monitor.v1`

## 目的

宏观观察是 Research 领域的上游事实基座，统一表达增长、价格、流动性、未来经济事件、证据来源、新鲜度和覆盖缺口。它不启动新的 Agent、数据库或常驻服务，也不直接生成资产配置或买卖建议。`decisionReview` 是可追溯的研究采纳意见：状态假设、支撑指标、反证、待补缺口和下次复议事件，不能当交易信号。

宏观观察与 Circle / 周期叠加的边界如下：

- 宏观观察负责可核验的指标、发布日历、前值、预期、实际值和数据修订风险；
- 周期叠加负责通过发布门槛后的概率观察窗；
- 周期叠加概率不得反写宏观指标，也不得被解释为确定性的经济拐点或精确日期。

## 首版覆盖

核心指标：

- 中国官方制造业 PMI、GDP 同比、CPI 同比、PPI 同比、M2 同比；
- 中国规模以上工业增加值、出口同比、1 年期 LPR；
- 美国 CPI 同比、失业率。

经济日历：

- 优先 Tushare Pro `eco_cal`，按 100 条分页查询，最长未来 30 天；
- 主源不可用时尝试已配置的 FMP，再降级到百度股市通；
- 百度备用源最多查询今天及未来 14 天，不提前隐藏低重要性事件；
- `calendarCoverage` 区分已查询、未覆盖和暂无收录日期，不声称来源收录了全球全部事件；
- 降级、范围收窄和来源失败进入 `sources` 与 `gaps`。

事件归并与评级：

- 只在同一来源、日期、时间、地区、币种下做保守归并，归一化空白、全半角括号及明确利率/增速的百分号标注。缺少时间时只合并完全相同的标题。
- 不删除标题中的月份、单位、同比/环比、核心/总体、初值/终值；相似但口径不明的事件不合并。
- `recordCount` 是来源记录数，`records` 保留合并前的标准化记录。主行选用完整的一条记录，不跨记录拼接实际值、预期和前值。
- 数值或来源评级冲突进入 `conflictFields`；页面对应数值显示待核验，停止显示公布偏差，原值仍可展开检查。
- 来源评级优先。缺失时，仅对有限的主要经济体政策、通胀、增长、就业、景气和活动指标给出可解释的 Desk 规则建议；其他事件保持 `unknown`，不默认判为低重要性。
- `importanceBasis.kind` 区分 `source / rule / unknown`。规则建议包含 `ruleId / version / reason`，不是来源或官方评级；来源评级冲突保持未评级。

地区与时间口径：

- `regionCode / regionGroup` 区分内地、香港、澳门、台湾及其他经济统计地区；欧洲筛选包含英国、瑞士、挪威等，不依赖标题子串筛选。
- `regionBasis` 记录地区判定依据。标题和来源地区冲突时不单方面改写，进入“地区待核验”；缺少明确地区时不按币种猜测。国际组织的跨国报告不按美元币种归入美国。
- `timeBasis` 区分来源显式偏移、时区未注明、仅日期。只有明确偏移才提供可定位的 `timestamp`；页面保留来源时刻，不按浏览器时区重解释。
- [Tushare eco_cal 文档](https://tushare.pro/document/2?doc_id=233) 目前仅标注“日期”“时间”，未说明时区，因此不默认北京时间、UTC 或经济体当地时间。获取时间也不能当作官方发布时间。
- 缺失、待定或无法解析的时刻不补成午夜；来源明确给出的 `00:00` 则保留。不同偏移或不同地区争议记录不能误合并，原始日期、时刻和地区字段保留在 `source` 中。

中国宏观指标优先读取 Tushare Pro 结构化宏观序列和经济日历，缺失或失效时自动降级到 AkShare 的金十、东方财富等公开聚合数据。生产环境配置 `TUSHARE_TOKEN` 后启用主链路。聚合源不是官方原始发布机构，因此合同固定输出 `official-primary-source-verification` 缺口，Agent 和用户应在形成重要判断前回到国家统计局、人民银行、FRED、央行或对应统计机构复核。

美国 CPI 优先使用 [FRED `CPIAUCNS`](https://fred.stlouisfed.org/series/CPIAUCNS) 转发的 BLS CPI-U 全项目未经季调月度指数（原始系列 `CUUR0000SA0`），以当月指数除以上年同月指数减 1 计算同比，四舍五入至 0.1 个百分点。FRED 不是独立调查；原始机构、两个系列号与计算说明均进入页面和 Agent 上下文。FRED 无有效期内观测时才使用 Tushare/公开聚合降级值，同期优先采用 BLS/FRED 口径。公开 CSV 的观测日期是统计月份，不是正式发布日期；未取得正式发布日期时输出 `releaseDate=null`、`dateBasis=period`，页面显示“发布日期未核实”。若聚合源仅提供来源更新日期，则以 `dateBasis=source-update` 标识，不能称为正式发布日。`revisionStatus=not-tracked` 表明历史修订版本未取得；当前未接入 ALFRED vintage，不声称可以还原某天当时可见的数据。

美国失业率使用 Tushare、BLS `LNS14000000`、[FRED `UNRATE`](https://fred.stlouisfed.org/series/UNRATE) 和公开聚合源逐级补充；有新鲜 Tushare 值时仍与已缓存的 FRED 数据比较，同期优先 BLS/FRED，不为此重复请求限额内的 BLS 直连。FRED 是 BLS 同口径 U-3 季调月度序列的转发，不是独立调查；`source` 保留原始机构、原始系列号、当前系列号和降级原因，页面与 Agent 共用这些字段。BLS/FRED 月度观测使用 `period` 和 `dateBasis=period`，未取得正式发布日期时 `releaseDate=null`，不把月初或网页更新时间当作发布日期。历史修订版本未跟踪。空值不补零；所有来源均失效或陈旧时保留缺口与陈旧标记，不将历史记录当作最新数据。

## 状态表达

全球旁证的 `Crucix.asOf` 仅是采集时间，不证明各项观测最新。GSCPI 保留 `YYYY-MM` 月份，以月末和 50 天更新窗口判断新鲜度，不伪造发布日期。能源 `observations` 将数值、现货/期货/库存类型、单位、来源系列、统计期或原始报价时间作为整体传递；Yahoo 期货不得标为 EIA 现货，库存保留“千桶”口径。日频、周频、期货报价分别使用 7、14、3 天保守更新窗口，不宣称实时；缺少时间的旧快照保持未知，来源异常保留值但标陈旧。页面与 Agent 共用这些记录，不再用扫描时间刷新旧值的新鲜度。

能源备用通路位于 Crucix 采集层，不在 Desk 快照归一化时联网。2026-09-10 核对 Tushare 公开目录，未发现同口径的美国能源现货与商业原油库存总量接口；`eco_cal` 事件变化量不能替代库存存量。EIA API 未配置或某项没有有效观测时，仅该项转向公开来源：WTI / Brent / Henry Hub 使用 FRED 的 `DCOILWTICO` / `DCOILBRENTEU` / `DHHNGSP`（原始机构仍为 EIA）；库存使用 [EIA WPSR 表 4](https://ir.eia.gov/wpsr/table4.csv) 的 `Commercial (Excluding SPR)` 行，百万桶乘 1000 转千桶，仅取当前周和前一周。空值跳过，不能补零；不同数据期不计算油价差，非相邻周不计算周库存变化。保留原始机构、原始系列、当前系列、出处和备用原因供页面与 Agent 共用。请求随现有 15 分钟扫描执行，FRED 仅查询最近 60 天；旧数据依旧按原数据期标记陈旧。

宏观状态只做证据归纳：

- `growth`：结合 PMI 是否位于 50 上下、GDP 同比相对前值变化；
- `inflation`：比较 CPI、PPI 与前值的变化；
- `liquidity`：比较 M2 与 LPR 的边际变化；
- `signal` 仅允许 `positive / neutral / negative / mixed / unknown`。

状态不是资产涨跌预测。每个维度必须附带 `evidenceIds`。历史字段名 `regime.confidence.score` 实为核心指标的有效期覆盖率，不是判断概率；页面必须明确标作覆盖率。陈旧数据不得被静默视为当前状态。

状态判定只使用中国 PMI/GDP、CPI/PPI、M2/LPR 三组证据；美国 CPI 与失业率是跨市场旁证，不能填补中国维度的缺口，也不进入中国状态的 `overall.evidenceIds`。增长需要 PMI 及可与前值比较的 GDP，价格需要 CPI/PPI 均有可比变化，流动性需要 M2/LPR 均有可比变化。单项有效观测可以展示，但该维度保持 `unknown`；任一维度不完整时总体标记“关键证据不足，暂不判定”，采纳意见暂缓。全页时效覆盖率即使较高，也不能替代这道证据完整性门槛。这里仅借鉴交叉验证原则，不引入未经回测的跨资产权重或转型概率。

流动性 `assessment` 只使用有效期内 M1/M2 同比和 SHIBOR 的各自前一观测变化。货币数量、资金价格任一维度缺失时标记 `complete=false`，不作总体方向判断。月频社融、融资额有强季节性，两融余额与 M2-M1 差仅作旁证。不得把不同频率序列的斜率乘以五天、产生负存量或给未经回测的预测置信度；旧 `liquidity.forecast` 已撤销。全市场两融余额只有沪深同日均有数据才合计。

经济日历默认展示前 12 条，可逐批展开；筛选后总数和来源记录数始终保留。Agent 上下文中的 `upcomingEvents` 只含当前页面展开的事件，`visibleEventCount` 和 `eventsTruncated` 明示范围。未评级不等于低重要性，时区未注明不补作北京时间。

设计取舍：借鉴 [OpenBB](https://github.com/openbq-org/OpenBB) 的提供者元数据与来源路由、[FRED/ALFRED 实时版本接口](https://fred.stlouisfed.org/docs/api/fred/series_observations.html) 的数据期／可见版本分离、[纽约联储 Nowcast](https://github.com/FRBNY-RG/New-York-Nowcast) 的混频和新闻分解思想。当前未积累完整 vintage 与样本外回测，因此不引入 `statsmodels` 动态因子预测；纽约联储仓库未声明许可证，只借鉴方法、不复制代码。现有 AKShare 作为聚合输入，不把采集时间当发布日期。

## 核心字段

每个指标至少包含：

- `id / name / region / category / unit`
- `period / releaseDate / nextReleaseDate`
- `value / forecast / previous / change / direction`
- `source / evidenceId / asOf / freshness / confidence`
- 轻量 `history`，用于趋势可视化，不重复保存完整上游数据。

每个经济事件至少包含：

- `date / time / region / currency / title`
- `timeBasis / regionCode / regionGroup / regionBasis`
- `importance / status`
- `actual / forecast / previous`
- `actualText / forecastText / previousText` 保留原始单位文本
- `importanceBasis / recordCount / records / conflictFields`
- `source / evidenceId / asOf`

## 接入规则

1. 新 Mod 通过统一能力 `research.macro-monitor` 读取，不直接绑定 AkShare、FMP 或百度。
2. 无 API Key 时正常使用公开降级源，不要求用户为页面单独配置模型或 Agent。
3. 所有来源都必须提供状态、更新时间、数量和失败原因；空数据与不可用必须区分。
4. Agent Context 至少包含宏观状态、指标、未来事件、来源状态和缺口；日历还需携带覆盖范围、筛选后事件数、来源记录数、规则建议数、冲突数、地区待核验数、时区未注明数及前 40 条事件。截断必须明示，归并记录、地区与时间口径、评级依据不得丢失。
5. 页面可以解释传导路径和情景，但不得输出确定性市场预测、仓位或买卖时机。

## 最小接口

Crucix 来源健康统一由采集结果生成：`ok`、`partial`、`stale`、`error`、`unknown` 互斥，正常、部分、陈旧、不可用和待核验之和等于来源总数。返回错误对象、缺少凭据、报价全部无效不能计作正常；超时来源保留在明细中。公开事件接口成功返回零事件与请求失败分开处理。静态接入说明不代表已经采集实时数据。旧快照缺失的来源明细计为待核验，不沿用虚高成功数。宏观、新闻、全球情报与 Agent 共享同一状态；仅部分成功且失败数为零时也必须显示降级。来源采集状态不是每条观测的新鲜度，单项缺失不能把其他仍有效的能源记录一律标陈旧。来源提示使用固定说明，不把含凭据的原始请求错误转发到页面。

```http
GET /api/research/macro-monitor?days=7
```

`days` 范围为 1–30。返回 `newma-desk.macro-monitor.v1` Feed。
