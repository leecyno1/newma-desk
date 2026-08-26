# 专业基金研究平台架构（v1 历史说明）

> 当前规范架构已迁移到 `docs/architecture/professional-fund-research-module-v2.md`。v2 以公开学术研究、CFA Manager Selection、Morningstar 公开方法和中国证监会基金评价原则为基础，采用九段式流程与 `Gates + Pillars + Confidence`，不再以单一综合分数作为决策核心。本文件保留用于解释旧模块合并过程。

本模块定位为机构投资者的基金研究底座，不覆盖交易、购买或风控。页面、数据、工具和 AI 技能只回答三个问题：研究对象是谁、证据是否可信、研究结论如何复核与复用。

## 开源复用搜索结论

- 当前开源复用决策已落到 `lib/research-platform/open-source-references.ts`，每个候选项目必须标注 `decision`、`candidateModules` 和 `boundary`，页面或工具不能绕过这个注册表直接引入外部金融能力。
- OpenBB：适合作为公开金融数据接入与数据命名参考，优先借鉴 provider/adapter 模式，不直接引入交易或组合功能。
- AKShare：适合作为中国市场公开财经数据补充源，当前仅作为持仓穿透、公告和市场侧补证的候选 adapter；Tushare 仍是本项目基金主数据源。
- QuantStats：适合作为收益序列、回撤、滚动指标和研究图表方法参考；当前项目可先复用指标定义，不急于增加依赖。
- pyfolio / empyrical：适合作为绩效分解与时间序列统计参考，但项目不引入其交易组合语义。
- FinGPT / FinRobot：适合作为金融文本抽取、报告生成和 agent orchestration 参考；本项目只吸收“证据驱动生成”思想。
- Anthropic financial-services prompt patterns：适合作为“长文档 + 引用 + 审计”的金融研究提示词参考；本项目只复用证据约束，不引入财富管理、交易或投资建议工作流。
- FinanceToolkit：可参考其透明指标口径和 MCP 暴露方式，但当前模块不接入股票财报/交易型工具；若未来接入，只能作为 `DataAdapter` 或 `Tool`，不能让模型直接绕过 EvidenceLedger。
- Claude/Finance 类开源 agent 与 MCP 搜索结论：多数偏股票、宏观或交易数据查询；本基金研究模块先复用“工具可发现、输入输出结构化、报告由工具证据驱动”的架构思想，不引入会扩大范围的交易/组合工具。
- 本轮冗余入口治理新增 `canonicalResearchHref`：把 `/investor-selection`、`/pools`、`/rankings` 等旧入口统一正位到全市场研究库、研究清单视图和同类横评，避免页面内继续散落旧模块链接。
- 本轮路由正位和研究候选语义迁移不新增外部依赖：报告生成、历史净值回放和候选筛选已有本地深实现，优先迁移到 canonical research API；后续新增指标引擎时再按 QuantStats/empyrical 指标定义做薄适配。
- 本轮同类横评底座新增 `peer-group-benchmark` tool：借鉴 OpenBB 的 provider/adapter seam、QuantStats/Empyrical 的基准先对齐原则、FinRobot 的 tool-to-report 编排，但不引入大依赖，先把同类组、宽口径资产桶、基准映射和样本充分性集中到一个可复用 ToolResult。
- 本轮横评评分继续新增 `comparison-research-score` tool：借鉴 QuantStats/Empyrical 的风险收益指标拆解，把专业评分、研究证据、历史回放、回撤、压力体验和费用可比性集中成可审计权重与封顶规则；报告层只渲染结果，不再持有评分规则。
- 本轮横评摘要继续新增 `comparison-research-summary` tool：集中生成判断依据、排序原因和摘要缺口，避免报告构建器散落叙事规则。
- 本轮胜负线继续新增 `comparison-win-loss-audit` tool：复用本地 decisive audit，集中生成第一名对替代样本的胜负线、置信审计和反转条件；报告层只展示结构化审计结果。
- 本轮横评报告继续新增 `fund-comparison-report-markdown` renderer：把 Markdown 正文、份额文案和风险来源块从报告构建器拆出，报告构建器只负责数据编排。
- 本轮对比篮证据工作单继续新增 `market-compare-basket-evidence` tool：把已选基金的证据行、下一步动作和 TSV 从 Market 页面抽出，减少页面内证据导出规则。
- 本轮全市场对比篮继续新增 `market-compare-basket-win-loss` tool：把对比篮胜负分、研究分层、硬阻断、补证缺口和 TSV 从 Market 页面抽出，页面只采集状态并渲染 ToolResult。
- 本轮当前页短名单继续新增 `market-current-page-shortlist` tool：把短名单评分、分层、主动作和 TSV 从 Market 页面抽出，形成可被前端、脚本和 AI 复用的研究筛选工具。
- 本轮当前页决策解释继续新增 `market-decision-explainer` tool：把可行动比例、主动作、排序说明、金额门禁和复查队列优先级从 Market 页面抽出，页面只装配链接并渲染结果。
- 本轮全市场晋级队列继续新增 `market-promotion-queue` tool：把晋级分流、任务队列、门禁审计和 TSV 从 Market 页面抽出，页面只负责链接装配和交互。
- 本轮材料核验继续深挖 `material-evidence-gate` tool：把旧 `sales-rule-gate` 的门禁计算收敛为 canonical 材料证据核验，旧工具只作为兼容壳；Skill 和页面不再把销售规则作为独立研究模块。
- a-stock-data skill：可作为 A 股行业、公告、研报和主题数据补充参考，但基金研究模块只在持仓画像与基金经理研究中间接使用。

## 目标模块

1. 全市场研究库：基金主数据、份额合并、基金公司、产品线、策略标签和研究覆盖状态。
2. 基金画像：基础资料、净值序列、费用、基准、风格、持仓摘要和研究证据完整度。
3. 同类横评：peer group、基准映射、同类分位、收益来源和可解释差异。
4. 持仓画像：行业、主题、风格、集中度、换手和基金间持仓相似度。
5. 经理与公司研究：经理任期切片、共管产品、代表作、基金公司平台和产品线能力。
6. 研究报告生命周期：初评、复核、更新、归档、复用判断和失效提示。
7. 证据台账：公告、季报、年报、招募书、基金合同、调研纪要、数据来源与字段级可信度。
8. 数据接入：Tushare、公开公告、内部上传材料和未来可接入的 OpenBB-style adapter。

## 冗余模块合并

- 投资者选基合并到全市场研究库；研究平台不维护个人画像入口。
- 销售规则合并到证据台账；销售字段只作为材料证据，不作为购买门禁。
- 基金复查队列合并到证据台账；事件语义改为研究证据缺口。
- 基金池合并到全市场研究库；只保留研究覆盖清单，不维护购买漏斗。
- 基金排行榜合并到同类横评；只输出 peer diagnostics，不输出泛推荐榜。

## 分层方式

- Tools 层：material-evidence-gate、research-evidence、peer-group-benchmark、comparison-research-score、comparison-research-summary、comparison-win-loss-audit、market-compare-basket-evidence、market-compare-basket-win-loss、market-current-page-shortlist、market-decision-explainer、market-promotion-queue、holding-exposure-engine、manager-tenure-slicer、evidence-ledger-auditor、report-lifecycle-checker。
- Renderer 层：fund-comparison-report-markdown 等确定性渲染器，只消费结构化研究结果，不持有核心判断规则。
- 数据库底座：fund_entity、share_class_map、benchmark_map、peer_group、holding_snapshot、manager_tenure、company_profile、research_evidence、research_report_version。
- Skills 层：full-market-research、single-fund-research-review、peer-comparison、manager-company-research、evidence-repair、report-reuse。
- AI 大模型层：只消费 ToolResult、SkillRun 和 EvidenceLedger，生成摘要、反证问题、缺口清单和报告草稿，不直接改写事实。

## Canonical API 命名

- `/api/funds/[id]/research-review-report`：单基金研究复核报告入口，替代旧买前报告命名。
- `/api/funds/[id]/historical-nav-replay`：历史净值回放入口，替代旧购买模拟命名。
- 旧 API 暂保留为兼容层，后续页面和脚本只允许新增调用 canonical API。

## 下一轮填充顺序

1. 把购买/买前/销售规则语言统一改为研究复核、证据复核和材料核验。
2. 补 peer group 与 benchmark mapper，先让横评专业化。
3. 补 holding-exposure-engine，形成持仓画像。
4. 补 manager-company-research，把经理评价扩展到公司平台和产品线。
5. 补 report-lifecycle，把报告从一次性生成改成可复核资产。
