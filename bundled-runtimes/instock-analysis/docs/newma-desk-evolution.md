# InStock Analysis 下一步进化与 Newma-Desk 适配方案

## 目标状态

InStock Analysis 不是 Desk 内的一段源码，也不是另一套 Agent 平台，而是由 Newma-Desk 托管生命周期的附属分析运行时与 Mod Suite：

- `instock-market-workbench` 负责市场宽度、行业强弱和常用行情榜单。
- `instock-market-map` 负责申万行业与个股涨跌云图，以及 Top100 / 多榜 Top500 覆盖切换。
- `instock-technical-signals` 负责技术指标、K 线形态与原 InStock 经典策略扫描。
- `instock-czsc` 负责单标的 CZSC 结构分析。
- `instock-rotation` 负责行业与 ETF 轮动、候选排序和历史切换轨迹。
- `instock-industry-chain` 负责产业链拓扑、供应链瓶颈和证据排序。
- `instock-stock-candidates` 负责 A 股最新活跃池的可解释候选排序。
- `instock-stock-research` 负责组合技术结构、基本面与披露证据的单股研究档案。
- `instock-strategy-validation` 负责选股、CZSC 与轮动信号的统一点时验证。
- `instock-event-flow` 负责事件与资金证据的去重、时效和证券级异常归并。
- `instock-research-book` 负责研究理由、证伪条件、Snapshot 引用与风险暴露汇总。
- `instock-suite` 只负责项目身份、页面发现、导航默认值和共同运行环境。
- Newma-Desk 负责身份、权限、数据路由、Action Gateway、Mod Copilot、跨 Mod Context 与 `instock-analysis` 进程生命周期。
- `MarketDataProvider` 是分析内核唯一行情 Seam，具体数据来源通过 Adapter 更换。

这套边界让分析 Module 保持足够深：CZSC 对象、行情清洗、轮动评分、降级和证据摘要都隐藏在稳定 API 后面；Desk 适配只位于 `integrations/newma-desk/`、Bridge 和 `NewmaDeskMarketDataProvider`，变更具有较高 locality。

## 已落地的第一阶段

1. 标准 Suite Descriptor：一次声明 11 个独立页面，支持 Git / 本地 Store 与 HTTP well-known 自动发现。
2. Level 2 Connected Mod：11 个页面声明 13 个确定性 Data Action，权限均为 `analysis.read`。
3. 宿主 Action 通道：嵌入态使用 `vibedesk:action-request/result`，不把 Session、Provider URL 或密钥交给业务页面。
4. 附属运行时诊断回退：Action 暂不可用时，页面可调用同一 `instock-analysis` 进程的 `/api/v1`；这不是独立部署模式。
5. Newma 数据 Adapter：正式使用 `NEWMA_DESK_DATA_*`，旧 `NEWMA_DOCK_*` / `VIBEDESK_*` 仅作兼容。
6. 结构化 Agent Context：页面持续发布当前标的、筛选条件、数据时间、摘要、Action 和任务状态。
7. 历史日期锚点：CZSC 与轮动均接受可选 `asOf=YYYY-MM-DD`，页面、Action 与 `/api/v1` 合同保持一致。
8. Analysis Snapshot：每次结果携带分析版本、参数、数据窗口、来源、freshness、覆盖率、输入摘要与结果摘要的稳定摘要 ID。
9. 无前视降级：历史轮动不会复用当前行业广度；Desk 不支持原生历史锚点时，只在最近 800 根窗口内做项目侧过滤并明确标记限制。
10. Snapshot 生命周期：结果自动进入有界进程内 Registry，可按 `snapshot_id` 查询；只保存元数据，重启后失效。
11. 运行实例可观测性：健康响应提供实例 ID、启动时间、运行时长，以及 Snapshot、批量扫描、轮动缓存的聚合容量与占用；实例变化明确代表所有内存态资源进入新世代。
12. API 运行指标：固定低基数路由模板统计请求量、错误率、状态类别和有界延迟分位数，不采集证券代码、资源 ID、查询参数、请求体或错误文本，也不把业务降级纳入进程 readiness。
13. CZSC Evidence：一次 CZSC Implementation 同时输出结构稳定性、最近结构变化与输入质量证据，不重复计算。
14. 跨 Module 联动：轮动发出 Desk 既有 `security.selected`，CZSC 接收并切换标的；标准路径走 `postMessage`，`BroadcastChannel` 只保留给维护诊断。
15. CZSC 批量结构雷达：复用同一单标的 Analysis Module，单批最多 20 个代码、每任务最多 4 并发，以有界进程内 Task Resource 提供创建、轮询和取消。
16. 批量 Action 仍属于 `instock-czsc`：标准路径用 `analysis.czsc.scan` 创建任务，同源 POST 只作为附属运行时诊断回退；不新增第三个 Module，也不要求 Desk 增加任务系统。
17. 轮动稳健性实验仍属于 `instock-rotation`：`analysis.rotation.experiment` 手动触发 9 组参数的训练/样本外检验，不新增 Module。
18. 产业链研究拆为独立 `instock-industry-chain` Module：`analysis.industry-chain` 只消费 Newma-Desk Agent/Data 提供的点时拓扑与证据包，项目侧不联网、不新增数据 Adapter；旧轮动 Action 仅保留兼容 Adapter。
19. 实验采用收盘信号、下一交易日开盘执行、每次再平衡收取完整双边成本，并给出 10/25/50 bps 压力结果。
20. 实验 Context 只发布 verdict、覆盖年限、样本外指标和限制摘要，不把权益曲线、逐期交易或参数全表复制给 Desk Agent。
21. 股票研究档案拆为独立 `instock-stock-research` Module：组合 Desk 基本面、公告、研报、新闻与项目 CZSC 结构，可引用产业链 Snapshot，但不输出投资评级或交易建议。
22. 策略验证拆为独立 `instock-strategy-validation` Module：接收三个研究 Module 的点时信号包，集中下一交易日开盘、成本、时间切分、回撤和覆盖限制。
23. 个股事件与资金拆为独立 `instock-event-flow` Module：接收宿主结构化事件包，集中来源去重、时效、异常强度、方向与证券映射，不恢复旧抓取表。
24. 研究组合拆为独立 `instock-research-book` Module：校验理由、证伪条件和 Snapshot 引用，汇总暴露与风险；不持久化、不恢复 attention 表、不包含交易。
25. 市场概览拆为独立 `instock-market-workbench` Module：把上游每日行情、行业强弱和常用排行重组为 Desk 原生页面，只消费 `market.overview` 与 `market.scan`。
26. 技术指标、K 线形态与经典策略合并为独立 `instock-technical-signals` Module：统一证据拆解，并在数据不足或需要龙虎榜时公开标记限制。

## 下一阶段优先级

### P0：数据完整性与证据质量（项目侧，基础版已完成）

- 消费并检测 Newma-Desk 已有行业广度 Capability；缺失时维持诚实的 `partial`，不修改 Desk 本体。
- 继续在项目侧验证交易日历、复权方式、停牌状态、来源时间和 freshness。
- 已把 Desk OHLCV 返回的实际来源、来源时间、市场、周期与复权方式透传到 Analysis Snapshot `provenance`；兼容旧接口时保持未知值，不伪造来源。
- Analysis Snapshot 已保存“当期输入快照摘要”，但不复制完整历史行情；进程内 Registry 默认 TTL 24 小时、上限 512 条，并提供资源查询 Interface。
- CZSC 已返回版本化结构稳定性、最近一次结构变化和输入质量字段；稳定性为明确标识的项目启发式，输入间隔检测不伪装为交易所日历校验。

### P1：可复盘研究工作台（已完成基础版）

- 已增加日期锚点，让 CZSC 与轮动在 Desk 最近 800 根覆盖范围内按历史 `asOf` 重放。
- 已形成统一 Analysis Snapshot：输入窗口、数据来源、版本、参数、覆盖率、结果摘要和风险提示。
- 当前先以可查询的轻量 Registry 提供快照索引；若未来 Desk 已有 Artifact Interface 需要消费，再增加新的 Adapter，不在 Mod 内复制公共行情数据库。
- 已建立 CZSC 与轮动联动：轮动选中 ETF 后通过标准 `security.selected` 事件切换 CZSC，硬链接仅保留为独立导航回退。

当前 Desk OHLCV Interface 只支持最近窗口的 `limit`，不支持 `end`、`before` 或 `asOf`。本项目不会为此改造 Desk：Adapter 请求最多 800 根，按 `date <= asOf` 过滤；覆盖不到目标日期时返回 `historical_window_unavailable`，覆盖不足时 Snapshot 标记 `coverage=partial`。

### P2：批量扫描与策略实验（基础版已完成）

- 单标的 CZSC 编排已提取为共用 Analysis Module；批量任务输出紧凑候选、Evidence 摘要和 `snapshot_id`，不保存完整 K 线或图表。
- Task Registry 已限制活动任务数、记录数、保留时间和单任务并发；取消可阻止后续调度，但不能强制中断已经发出的上游 HTTP 请求，活动槽在全部在途请求结算后才释放。
- 页面已提供代码输入、周期、K 线数、并发数、截止日、进度、失败计数和候选回看；点击候选可直接切换单标的 CZSC。
- 候选分 `instock-czsc-candidate-score-v1` 明确属于 InStock 启发式，不冒充官方 CZSC 交易信号。
- 已对轮动 40/60/120 日窗口和 balanced/momentum/defensive 权重做 65% 训练、35% 样本外实验；训练段选参数，样本外段只检验。
- 轮动评分已固定为七因子合同；估值与基本面只有在行业级点时覆盖达到 75% 时才启用，否则从有效权重中剔除。实验同时报告逐因子 Rank IC、Top3 命中和去除因子后的边际变化，不使用样本外结果反向调权。
- 在线轮动新增 9 模型等票确认：40/60/120 日与三组权重各投一票，至少 5/9 同向只标记“参数一致”，不改变用户所选窗口的综合分排名，也不直接称为预测强信号。
- 当前 800 根真实 Desk 历史中，10 日主周期的单模型样本外 Top3 跑赢基准为 55.8%；按两个不重叠采样相位拆分后为 46.2%～65.4%，统计区间仍很宽。带持仓缓冲的状态化严格多数集成为 59.1%（22 次），但与在线当日静态投票不是同一口径；在线同口径回测仅 50.0%（26 次）。因此状态化结果只保留为影子策略候选，页面静态投票仅显示参数一致性。
- 已固定收盘信号、下一交易日开盘执行；历史行业广度统一中性化，避免把当日行业快照回填到历史。
- 已加入每次再平衡完整双边成本、10/25/50 bps 压力、基准与 ETF 等权对照、参数平台和最小证据门槛。
- 申万行业指数优先用于价格信号；不可用时允许已声明的同类行业 ETF 代理。31 行业稳健性实验至少要求 24 个 ETF 参与横截面，有效价格信号覆盖低于 90% 时只输出“证据不足”。
- 当前结果保留在项目响应与 Analysis Snapshot 摘要中，不要求 Desk 新增 Strategy Ledger 或 Artifact 功能。

### P3：Agent 协同

- 保留 Desk Mod Copilot 作为唯一通用问答入口。
- Agent 只读取结构化 Context、Analysis Snapshot 和 Evidence，不抓截图、不遍历任意 DOM。
- 未来若加入“解释当前结构”或“生成复盘”，声明为 Desk Agent Action；模型、会话和记忆仍由 Desk 选择。
- 不引入项目自有模型 Provider、密钥设置、长期记忆或第二套右侧抽屉。

## 明确不做

- 不修改或扩展 Newma-Desk 本体来迁就本项目。
- 不把 CZSC、TA-Lib、InStock 爬虫和 MySQL 强塞进 Desk 核心运行时。
- 不让浏览器直接持有行情、模型或 Agent 密钥。
- 不把 `a-stock-data`、`global-stock-data` 等 Skill 当作生产 API；它们只能成为 Desk 数据服务背后的采集或研究 Adapter。
- 不提供 Dockerfile、Compose、容器镜像或独立镜像发布流程。
- 不把 `9988` 作为面向用户的独立产品入口；由 Desk External Mod Runtime 发现、启动、复用和健康检查。

## 发布与认证门槛

每次发布至少完成：

1. Python 全量测试和 `compileall`。
2. Bridge JavaScript 语法检查。
3. JSON 解析、Newma Suite Compiler、Manifest 兼容检查和 DataServiceDescriptor 校验。
4. 直接启动 Tornado，检查 health、capabilities、well-known 和 11 个 `/mods/*` 页面。
5. 在真实 Desk iframe 中检查 `hello → init → ack`、Action request/result、主题、语言、时区和 Context。
6. 320px 无文档级横向溢出，图表在主题变化后保留数据并重绘。
7. 批量扫描验证创建、轮询、完成、失败隔离、取消和候选回看，Context 只发布任务摘要，不复制完整候选结果。
8. 轮动实验验证无前视、训练/样本外隔离、成本单调性、真实 Desk 800 根覆盖、手动触发和 Context 摘要边界。

Manifest 的 Level 2 只是声明。只有上述运行检查生成认证证据后，才可对外标记为 certified Level 2。

项目提供 `.venv/bin/python scripts/newma_release_check.py --live` 收敛上述门槛：离线部分验证测试、编译、Bridge、JSON、diff 与无 Docker 交付边界；在线部分复用既有 Desk 栈完成原生 Suite 编译、DataServiceDescriptor 与 JSON Schema 校验、主题检查、核心栈状态、Level 2 认证，并由宿主 `DataServiceClient` 真实调用 13 个主要 capability 校验输入和输出合同。InStock 自身 readiness、Action、认证和页面探针失败会阻断发布；其他与本 Suite 无依赖关系的可选或外部 Mod 降级进入报告 warning，不会被误判为 InStock 发布失败。结果可通过 `--report` 生成机器可读 JSON 证据。
