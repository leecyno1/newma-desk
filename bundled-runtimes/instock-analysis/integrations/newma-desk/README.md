# Newma-Desk 标准模组交付物

本目录是 InStock Analysis 对牛马 / Newma-Desk 的规范来源。项目只作为 `instock-suite` 附属模组交付；Desk 通过 External Mod Runtime 托管进程，并通过 Suite、Bridge、Action 和 Data Service Interface 接入。项目仍保有隔离的 Python 依赖，但不再形成独立部署、数据平台、模型或 Agent 系统。

## 交付边界

- `instock-suite/suite.json`：`instock-suite` 项目描述，一次声明市场概览、大盘云图、行业与 ETF 轮动、A/H 股候选、选股中心、股票研究档案、缠论结构分析、个股事件与资金、产业链研究、策略验证和研究组合 11 个独立 Mod。
- `store.json`：最小 Git / 本地商店入口，用于发布前让 Newma-Desk 原生 Suite Compiler 校验展开结果。Git 来源只有在改动合并并发布到声明的远程引用后才能获取；当前开发态使用本地文件或 HTTP Suite Discovery。
- `data-service.json`：13 个主要分析 capability 的确定性能力合同，覆盖市场概览、大盘云图、选股中心、A/H 股候选、股票研究、策略验证、个股事件资金、研究组合、CZSC 单股/批量、轮动快照/实验与产业链研究；第 14 个旧供应链 capability 仅保留兼容 Adapter。
- `schemas/industry-chain-research-packet.schema.json`：产业链研究包的完整嵌套字段、评分与数量约束；`examples/` 中的示例只用于联调，不代表真实研究。
- `GET /.well-known/newma-desk-suite.json`：HTTP Suite Discovery 标准入口。
- `GET /.well-known/newma-dock-suite.json`、`GET /.well-known/vibedesk-suite.json`：兼容期回退入口。
- `/mods/market-workbench`、`/mods/market-map`、`/mods/technical-signals`、`/mods/stock-candidates`、`/mods/stock-research`、`/mods/strategy-validation`、`/mods/event-flow`、`/mods/research-book`、`/mods/czsc`、`/mods/rotation`、`/mods/industry-chain`：可独立访问、也可嵌入的稳定页面。

11 个页面声明为 Level 2 Connected Mod。页面通过 `vibedesk:action-request/result` 调用宿主批准的 Action；宿主暂未授予 Action 时，同源 `/api/v1` 只作为同一附属运行时的诊断回退，不构成独立运行产品。

市场概览消费 Desk `market.overview` 与 `market.scan`，重新组织上游每日行情、行业强弱和常用榜单。选股中心消费 Desk 多维 `market.scan` 与 A/H `market.ohlcv`，按行情、估值、技术方向、K 线形态和经典策略执行硬筛选；两者都不连接旧 MySQL 页面。

当前 Desk 商店已登记的 `instock-czsc` 与 `instock-rotation` 可直接执行官方 Level 2 认证。`instock-industry-chain` 与 `instock-stock-candidates` 完成项目侧 Suite 编译、真实接口、Bridge 与嵌入预认证后，待宿主导入本 Suite 再执行同级认证；本项目不修改 Desk 本体或默认商店。

A 股候选 Module 只调用 Desk 现有 `market.scan`、`market.quotes`、`market.ohlcv`、`research.equity-comparison` 与 `research.equity-snapshot`，不增加 Desk 数据接口。扫描源盘前只有证券身份时，项目 Adapter 用 Desk 腾讯批量行情补价格和估值；实时成交额尚未形成则临时保留市值入口顺序，并用最近完整日 K 成交额计算流动性，开盘后自动切回实时成交额。随后做技术预评分，对前 30 名按每批最多 4 只、最多 3 个批次并发读取横向财务比较，缺失项再回退单股快照。结果公开八类因子、两阶段覆盖、批量/回退次数、流动性口径、过热惩罚、历史不足排除和缺失项中性处理。当前不支持历史股票池回放，不把排名描述成交易信号。

股票研究档案 Module 使用 Desk 现有 `research.equity-snapshot`、`market.announcements`、`market.reports`、`market.news` 与 `market.ohlcv`，组合项目 CZSC 技术结构形成单股证据底稿。它可引用产业链 Snapshot，但不新增 Desk 数据能力，也不生成评级、目标价或交易指令。

策略验证 Module 只调用 Desk 现有 `market.ohlcv`。它接收各研究 Module 已保存的点时信号包，统一下一交易日开盘执行、固定持有、等权、双边成本、65/35 时间切分、回撤与覆盖限制；不使用当前信息重建历史信号。

个股事件与资金 Module 支持两种入口：直接输入 A 股代码读取 Desk 已托管的公告、研报、新闻、融资融券、龙虎榜、大宗交易、股东、分红、解禁和主力资金接口；或接收 Desk Agent/Data 提供的结构化事件包。项目只做来源去重、时效、异常强度、方向和证券归并，逐项区分空结果与接口失败；不恢复项目抓取器，也不把强度分描述为收益预测。

研究组合 Module 只校验宿主提供的结构化研究状态。它集中观察理由、证伪条件、Snapshot 引用、目标研究暴露、行业与风险集中度；项目不持久化组合、不声明交易权限，也不恢复 MySQL attention。

CZSC、批量扫描、轮动快照与轮动实验使用可选 `asOf=YYYY-MM-DD`；产业链研究包使用必填 `as_of=YYYY-MM-DD`。成功分析响应包含 `snapshot`，记录稳定 `snapshot_id`、分析版本、参数、来源、coverage、freshness、输入摘要与结果摘要；页面只把适合 Agent 消费的摘要发布进 Desk Context。批量 Action 只创建任务，后续由 `GET/DELETE /api/v1/czsc/scans/{scan_id}` 轮询或取消，每个候选只携带紧凑结构摘要和单标的 `snapshot_id`。两个 Registry 都是有界进程内资源，重启后失效且不保存完整 K 线。

批量扫描没有新增 Module：`instock-czsc` 同时声明 `analysis.czsc` 与 `analysis.czsc.scan`。默认最多 2 个活动任务、单批 20 个代码、任务内 4 并发。候选分是公开标记的 InStock 启发式；取消不能强制中断已经发出的上游 HTTP 请求，任务会占用活动配额直到在途请求结算。

轮动 Module 声明发出 `security.selected`，CZSC Module 声明接收该事件。Bridge 完全复用 Desk Protocol 1.0 的版本化 Envelope；不要求 Desk 新增事件类型或改造 Shell。

轮动排名将申万 2021 一级行业指数与 ETF 解耦：行业指数负责动量、相对强弱、趋势和风险信号，ETF 负责量能、展示与下一交易日开盘执行。项目 Adapter 通过 Desk 标准数据服务网关调用现有 `market.ohlcv` / `market.overview` capability，不直连 Tushare，也不要求 Desk 新增接口。指数使用不复权口径；不可用时明确回退对应 ETF，并在 `signal_state`、`signal_failures` 与候选行中公开。`market.overview.sectors` 的行业资金净额只进入确认标签和证据；项目写入自身 SQLite 日度账本，按交易日同日覆盖并形成最多 5 日持续性。该确认不改变排名，历史截面也不复用当前资金快照。

轮动稳健性实验没有新增 Module。它作为 `instock-rotation` 的第二个 Action 手动运行，使用 Desk 最多 800 根历史日线，对 9 个参数组合做训练/样本外检验与成本压力测试；信号使用申万行业指数，收益使用对应 ETF，固定 ETF 池幸存者偏差、历史行业广度中性化和数据覆盖门槛均进入结构化限制字段。

产业链研究是独立的 `instock-industry-chain` Module。`analysis.industry-chain` 接收宿主提供的结构化产业链拓扑与点时证据包；InStock 只负责验证引用、按节点与瓶颈优先级排序候选并生成 Snapshot，不自行调用网站、行情 Skill、模型或 Agent。轮动页只保留跳转入口；产业链页通过项目侧 `window.InStockIndustryChainResearch` 适配器承接 Action 结果。这不修改或扩展 Desk Bridge Protocol。旧 `analysis.rotation.supply-chain` 与 `/api/v1/rotations/supply-chain-research` 仅作为迁移期 Adapter 保留。

市场概览、A/H 股候选、选股中心、股票研究、CZSC、轮动快照与实验均使用有界进程内结果缓存，普通加载可复用，`refresh=1` 强制重新计算。缓存重启后失效，不承担历史数据存储职责；真实重新计算后的完整结果另写入 SQLite 分析历史，服务重启后仍可浏览。

Newma-Desk 当前 OHLCV 只提供最近窗口且最多 800 根，没有原生历史截止日期。项目 Adapter 在本地过滤最近窗口，并在 Snapshot 的 `provenance.as_of_mode` 与 `limitations` 中公开降级方式。超出覆盖范围返回 422；历史轮动不会复用当前行业广度。

## Desk 托管运行时

```bash
cd /path/to/stock-czsc-integration
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-attached.txt

cd /path/to/newma-desk
npm run dev:stack
npm run dev:status -- --strict
```

附属环境不安装 `requirements.txt` 中的 MySQL、自动交易和旧 Web 诊断依赖。CZSC 官方声明的完整依赖闭包保持不变，以确保稳定版 `0.10.12` 的包合同与认证环境一致。

Desk 的 `instock` Adapter 会发现 `stock-czsc-integration` 工作区，注入跳过数据库、统一研究数据接口、精确父 Origin、CORS 与 `127.0.0.1:9988`，再启动 `.venv/bin/python instock/web/web_service.py`。需要覆盖位置或远程运行时才设置 `NEWMA_DESK_INSTOCK_WORKSPACE`、`NEWMA_DESK_INSTOCK_WEB_URL`；所有 Origin 必须是精确的 `http(s)://host[:port]`，不能包含路径。

附属态只注册 `/mods/*`、`/api/v1/*`、Suite Discovery 和静态资源，根路径重定向到 `/mods/market-workbench`。上游 `/instock/*`、旧页面别名与非版本化接口只属于连接原数据库的维护者诊断态，不进入 Newma-Desk 模组合同。

直接执行 Python 服务仅用于维护者定位运行时故障，不属于安装、生产启动或发布流程。

## 数据与 Agent

- 行情只通过 `MarketDataProvider` Interface 进入分析内核，默认 Adapter 为 `NewmaDeskMarketDataProvider`。
- `NEWMA_DESK_DATA_*` 是正式环境变量；`NEWMA_DOCK_*` 和 `VIBEDESK_*` 只作为兼容回退。
- 页面提供结构化 Context，供 Desk Mod Copilot 使用；项目不内置另一套通用 Agent、模型 Provider 或密钥配置。
- 当前无 Mod 持久化需求，因此不声明 Desk Storage namespace。
- 项目不要求 Desk 新增 Mod、行情参数或行业接口；只消费 Desk 已有数据与 Agent Interface。
