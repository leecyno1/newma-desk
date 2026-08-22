# 金融项目仓库吸收与十五栏填充方案

审计日期：2026-08-06
来源任务：`codex://threads/019ec372-1cda-79c1-ac7f-a51a969008ce`
机器可读清单：[`config/finance-project-intake.json`](../../config/finance-project-intake.json)

## 结论

本轮不是把高分 Skills 全部做成独立 Mod。17 个仓库中，当前只有 UZI 值得优先作为完整可视化项目试接；Day1Global 和其余报告型来源直接进入 Desk / Numa Agent，不再建设专门页面。其他高质量来源进入统一数据接口或 Agent 能力包。

这样处理有三个直接结果：

1. 遵守“完整项目不可拆分”：一个来源仓库只有一种接入形态和一个主栏目，完整应用只形成一个 Suite。
2. 控制服务和内存：91 个 Trading Skills、118 个 Anthropic Financial Services Skills、18 个 LLMQuant Skills 不会变成 227 个 Mod 或常驻进程。
3. 真正补齐产品，而非补齐菜单数字：数据和 Agent 能力可以服务多个栏目，但不会冒充已有可视化页面；仍缺页面的栏目明确进入 Desk 原生大模组建设队列。

GitHub Stars 只表示采用度，不是安全或适配评分。准入分采用仓库评审、代表性工作流、测试、依赖、来源可追溯性和对 Desk 的增量价值综合判断。

## 接入模式

| 模式 | 何时使用 | Desk 形态 |
| --- | --- | --- |
| `complete-suite` | 有完整运行时和连贯页面的应用 | 一个来源项目、一个 Suite、一个主栏目、一个服务地址 |
| `data-provider` | 主要价值是金融数据采集和归一 | 接入统一 Finance Data Router，不新增菜单页 |
| `agent-capability` | 主要价值是工作流、方法、脚本或报告模板 | Agent-only；在当前对话返回消息、折叠报告或 Artifact，不新增页面 |
| `reference-only` | 方法有价值，但来源、评分、依赖或重叠不适合直接运行 | 只吸收经过重写和验证的方法，不带入服务 |
| `reject` | 许可证、来源、数据权利、安全或可复现性不达标 | 不进入生产代码和默认运行环境 |

## 全仓库审计结果

| 仓库 | 分数 / Stars 快照 | 判定 | 主栏目 | 吸收方式 |
| --- | ---: | --- | --- | --- |
| `wbh604/UZI-Skill` | 86 / 6,005 | 第一优先 | 个股研究 | 整体转为 `uzi-suite`，默认关闭，完成安全与资源门槛后启用 |
| `simonlin1212/a-stock-data` | 88 / 8,391 | 采用 | 宏观面 | A 股免 Key 数据 Provider；服务行情、资金、公告、研报、基金和债券页面 |
| `simonlin1212/global-stock-data` | 88 / 1,444 | 采用 | 海外面 | 海外默认数据 Provider；供行情、全球研究、配置、ETF、个股和组合调用 |
| `LLMQuant/skills` | 84 / 185 | 可选采用 | 资产配置 | 通过统一 Agent / MCP 设置路由宏观、事件、ETF、利率信用、组合与风险能力 |
| `tradermonty/claude-trading-skills` | 86 / 2,575 | 选择性采用 | 量化研究 | 把市场宽度、筛选、技术、仓位、回撤、回测审查并入 Market / Vibe Trading Agent |
| `anthropics/financial-services` | 84 / 34,027 | 选择性采用 | 个股研究 | 吸收财报、催化剂、DCF、同业、债券、再平衡与 IC Memo 的合同和 View |
| `star23/Day1Global-Skills` | 79 / 1,015 | Agent-only | 海外面 | 五个报告工作流整体作为海外 Agent 能力包，不创建页面 |
| `AlphaGBM/skills` | 82 / 1,704 | 用户配置后可用 | 量化研究 | 仅作为期权数据 Provider；需要自有 API Key，不做默认依赖 |
| `RKiding/Awesome-finance-skills` | 77 / 2,752 | 参考 | 政策面 | 只评估新闻和报告方法；预测能力不作为投资信号 |
| `haskaomni/serenity-skill` | 79 / 620 | 选择性采用 | 个股研究 | 六套估值、买方备忘录、周期和市场健康框架进入现有研究 View |
| `himself65/finance-skills` | 79 / 3,119 | 选择性采用 | 海外面 | 吸收 yfinance、财报、ETF 折溢价、相关性、流动性和只读研究源 |
| `DayDreammy/tushare-openclaw-skill` | 95 / 16 | 有凭据时采用 | 宏观面 | 作为 Tushare 结构化数据 Provider，与免 Key 来源交叉校验 |
| `gaaiyun/pybroker-backtest-skill` | 90 / 0 | 不引入包装仓 | 量化研究 | 直接在 Vibe Trading 使用有来源的 PyBroker 库、Desk 数据和自有测试 |
| `ZhuLinsen/daily_stock_analysis` | 76 / 60,187 | 方法已吸收 | 个股研究 | 保留原生研究阶段、降级、历史和质量诊断；不复制 Agent、数据库和账户体系 |
| `OpenByteInc/QuantDinger` | 74 / 10,287 | 方法已吸收 | 量化研究 | 保留 Strategy Ledger、指标目录和实验归因；不复制交易、MCP、账户和支付服务 |
| `hello245m/free-stockdb` | 52 / 1,753 | 拒绝 | 市场面 | 发布物与源码不一致，且数据权利、完整性、鉴权和资源边界不足 |
| `infometa/workbuddyskills` | 58 / 175 | 拒绝 | 其他 | 仅作为发现线索；无仓库许可证，来源和认证不可移植 |

评分不能脱离来源风险理解。例如 PyBroker 包装 Skill 的旧测试分很高，但上游零 Stars 且未声明许可证，因此不能因为“90 分”就把包装仓部署进 Desk；正确做法是直接采用成熟的 PyBroker 库。

## 十五栏填充矩阵

| 一级栏目 | 当前完整项目 | 本轮可吸收能力 | 页面层结论 |
| --- | --- | --- | --- |
| 市场面 | 行情工具 | A Stock Data、Global Stock Data、Trading Skills、Finance Skills | 保留现有 Suite，增强数据与 Agent，不新建重复行情项目 |
| 宏观面 | Vibe Research | A Stock Data、Tushare、Anthropic FS、Serenity | 保留完整 Research，增强宏观、行业、财报和证据链 |
| 海外面 | 空 | Global Stock Data、LLMQuant、Finance Skills、Day1Global | 报告直接在 Agent 中生成；需要持续交互工作台时再建设原生大模组 |
| 资金面 | 空 | A Stock Data 资金/龙虎榜/两融、Trading Skills、AlphaEar 参考 | 需要 Desk 原生“资金研究”大模组，不能拆其他项目来占位 |
| 政策面 | 空 | A Stock Data 公告新闻、LLMQuant Events/Macro、只读社交研究 | 需要 Desk 原生“政策情报”大模组，统一来源与置信度 |
| 周期研究 | 周期叠加 | Serenity 周期阶段、LLMQuant Macro | 保留周期叠加完整项目，只增加事实和方法输入 |
| 资产配置 | 空 | LLMQuant Portfolio/Risk、Anthropic 再平衡 | 需要 Desk 原生“资产配置”大模组，承载均值方差、BL 和再平衡 |
| 战术择时 | 日历效应 | Trading Skills 行业/宽度、LLMQuant ETF、全球/A 股 Provider | 增强现有项目，不拆 Trading Skills 为多个 Mod |
| 个股研究 | 空 | UZI、Anthropic FS、Serenity、Finance Skills | 第一阶段整体接入 UZI；其他来源作为同页 Agent/View 能力 |
| 基金研究 | 空 | Tushare 基金、Global ETF、LLMQuant ETF、Anthropic Wealth | 需要 Desk 原生“基金研究”大模组，Provider 不冒充页面 |
| 债券研究 | 空 | Tushare 债券、LLMQuant Rates/Credit、Anthropic LSEG 方法 | 需要 Desk 原生“债券研究”大模组，避免绑定单一商业数据商 |
| 量化研究 | InStock、Vibe Trading | Trading Skills、PyBroker 库、LLMQuant Strategies、AlphaGBM 可选 | 继续增强 Vibe Trading，不引入重复量化服务 |
| 投决会 | Orchestra | Anthropic IC Memo、Serenity 买方 Memo | 保留 Orchestra，吸收结构和证据要求 |
| 交易、风控与组合管理 | Portfolio | LLMQuant Portfolio/Risk、Trading Skills 风控、Anthropic 再平衡 | 保留组合事实账本，Agent 不能越权下单 |
| 其他 | DeepSee | 无金融项目需要强行放入 | 继续仅作为完整工具项目兜底，不用于隐藏分类问题 |

当前七个空栏目中，UZI 可真实填充“个股研究”。Day1Global 只补充海外 Agent 报告能力，不用于填菜单。资金面、政策面、资产配置、基金研究、债券研究只有出现持续交互需求时才建设轻量原生大模组；一次性报告继续留在 Agent 中。

## 分阶段落地

### 阶段 1：UZI 整体试接

- 固定来源提交，作为一个 `uzi-suite` 进入“个股研究”。
- 一个隔离 Python 环境、一个服务地址、一个健康检查，不复制 Desk Agent。
- 所有上游页面、研究流程和人物框架保留在同一项目；人物框架标注为模拟方法，不代表本人观点。
- 禁止默认持久化浏览器 Cookie、Cloudflare Tunnel、系统级安装和任何券商执行。
- 行情、财务、公告和新闻改走 Desk Finance Data Router，并进入 Evidence Ledger。
- 通过主题、响应式、Agent Context、依赖审计和常驻资源预算后才能进入默认 Mods。

### 阶段 2：统一数据层

- `a-stock-data` 作为 A 股广覆盖免 Key Provider。
- `global-stock-data` 作为海外默认 Provider。
- Tushare 作为用户配置 Token 后的结构化校验 Provider。
- 每次结果统一返回来源、字段、截止时间、市场、币种、复权、缓存状态、降级链和缺口。
- Provider 不启动自己的 Agent、数据库、菜单或长期缓存服务。

### 阶段 3：Agent 能力包

- Market Agent：市场宽度、事件、宏观、技术结构、资金与新闻核验。
- Research Agent：财报、催化剂、估值、同业、论点、反证和研究备忘录。
- Trading Agent：筛选、回测审查、偏差检查、仓位、回撤和复盘。
- Portfolio / IC Agent：组合风险、再平衡、证据汇总与 IC Memo。
- 所有能力沿用用户统一 Agent 设置；不接受外部仓库自带模型配置和密钥系统。
- 报告型能力不增加页面：短结果直接回复，长报告折叠，图表或完整文档作为消息内 Artifact，需要时再保存到研究档案。
- 运行时按当前已发布 Mod 的栏目自动筛选 Agent-only 能力；例如 Day1Global 进入“海外面”和“个股研究”的 Agent 上下文，但永远不生成 Mod 页面。筛选发生在后端，浏览器不接收依赖、Provider 配置或 Secret 元数据。

### 阶段 4：按交互需求建设原生缺口

Day1Global 五个工作流固定由海外 Agent 调用。资金研究、政策情报、资产配置、基金研究、债券研究只有在筛选、比较、联动、持久状态等需求无法由对话完成时才建设页面。每个真正需要的大模组遵循“一项目、一服务、一地址、一隔离环境”，共享 Desk 数据、Agent、存储、事件和主题接口。

## 自动门槛

运行：

```bash
npm run finance:intake:check
```

校验会阻止：

- 同一个 GitHub 仓库重复登记或以多种形态进入 Desk；
- 完整项目被拆到多个一级栏目；
- 非 Suite 来源声明独立页面；
- 未锁定 40 位提交、非法栏目和重复 Suite ID；
- 拒绝或仅参考来源没有明确的重新评估门槛；
- 低于准入分的来源被静默标记为已采用。

清单是准入事实源，不是安装器。任何仓库在进入 `mods/store.json` 前，仍需通过依赖、安全、主题、响应式、Agent Context、来源证据和资源预算测试。
