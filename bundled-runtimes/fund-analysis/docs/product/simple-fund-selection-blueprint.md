# 普通用户基金选择产品蓝图

日期：2026-08-05

## 一句话目标

用户在三分钟内完成：找到基金 → 看懂表现 → 与同类比较 → 运行一次 AI 分析 → 得到最多十只带理由的候选基金。

## 用户实际看到的四个页面

### 1. 找基金

- 按代码、名称、公司、经理、类别和风格标签搜索。
- 基金详情展示基本资料、净值与回撤曲线、基准、经理、规模、费用、持仓摘要和调研纪要摘要。
- 最多选择六只基金比较。
- 比较只使用同类口径，显示收益、回撤、波动、Sharpe/Sortino、超额收益、跟踪误差、费用、规模、经理任期和风格标签。

### 2. 调研库

- 用户选择一个本地文件夹，系统索引 Markdown、TXT、PDF 和 DOCX 文件。
- 文件通过内容哈希去重并记录修改时间，不复制或改写原文件。
- LLM 从纪要中识别基金、基金经理、日期、投资理念、能力圈、风险意识和风格标签。
- 每个标签可以点回原文引用；基金或经理匹配不确定时由用户确认。

### 3. AI 分析

- 用户选择“分析一只基金”或“比较几只基金”，系统现场运行，不预先为全部基金生成报告。
- Agent 使用基金基础数据、净值指标、同类分位、调研纪要引用和业绩归因结果。
- 输出简单结论：基金是什么、历史表现如何、风险是什么、经理风格是什么、收益来自哪里、适合放入哪类候选组、仍缺什么证据。
- 每次运行保存为历史记录，可重新打开、继续追问和导出报告。

### 4. 标签推荐

- 用户先选择基金类别，再选择风格标签，例如“大盘成长”“价值”“均衡”“红利”“小盘”“行业主题”“低波稳健”。
- 系统返回最多十只候选基金，不展示购买金额或交易按钮。
- 每只候选展示五项摘要：同类表现、风险与回撤、业绩稳定性、经理与风格、费用与规模。
- 结果必须显示数据日期、推荐理由、主要风险、证据完整度和可替代基金。

## 七项后台能力

| 能力 | 简单职责 | 当前项目判断 |
| --- | --- | --- |
| 基金数据库 | 储存基金、份额、经理、净值、持仓、费用、基准和数据来源 | 基础较完整，需继续扩大真实数据覆盖 |
| 基金浏览器 | 列表、详情、净值图、筛选和多基金比较 | 已有多套页面，但入口和文案过度复杂，需要合并简化 |
| 调研纪要库 | 本地文件夹同步、经理归档、引用式 LLM 标签提取 | 已有上传、报告、向量和画像代码；缺本地文件夹同步与可靠实体匹配 |
| 综合基金数据库 | 合并量化事实、分类、经理画像、纪要标签和归因 | 模型基础存在，仍有重复字段和多套口径 |
| 业绩归因 | Brinson、风格/因子暴露及证据门禁 | 已有计算器、路由和表；真实行业权重、区间持仓和因子数据不足，暂不能称完整生产能力 |
| AI 分析 | 按需运行、引用证据、保留历史、Desk Agent 对话 | 已有 AI 报告表、生成接口和 Desk Bridge；需要收敛成单一分析会话 |
| 标签推荐 | 按类别与风格返回最多十只候选 | 已有筛选和排名代码，但混入购买门禁、观察池和尽调语义，需要重做为简单候选推荐 |

## 推荐引擎的简单规则

推荐不是让 AI 临时想一个公式。每类基金有固定且可解释的评价口径：

1. 数据门槛：分类、净值、基准、经理和关键指标必须达到最低覆盖。
2. 同类表现：使用三年和五年滚动收益、同类分位和基准超额，不追逐单年冠军。
3. 风险：最大回撤、波动、下行风险、回撤修复和风险调整收益。
4. 稳定性：滚动窗口胜率、排名持续性、经理任期内表现和风格漂移。
5. 成本与可用性：费率、规模、成立年限、份额重复和数据新鲜度。
6. 定性与归因：调研纪要中的经理理念、能力圈和风险意识，以及业绩归因是否支持其宣称风格。

系统内部可以生成透明的综合排序，但前台优先展示“为什么入选”和“有什么风险”，不只展示一个总分。

## 论文与行业方法带来的产品约束

| 来源 | 可采用的方法 | 对产品的约束 |
| --- | --- | --- |
| Sharpe, *Mutual Fund Performance* (1966) | 风险调整收益 | 不能只比较绝对收益 |
| Jensen, *The Performance of Mutual Funds in the Period 1945–1964* | 基准调整后的 alpha | 基准错误时不输出 alpha 结论 |
| Sharpe, *Asset Allocation: Management Style and Performance Measurement* (1992) | 收益基础风格分析（RBSA） | 纪要标签需与收益/持仓行为交叉验证 |
| Carhart, *On Persistence in Mutual Fund Performance* (1997) | 多因子与业绩持续性 | 短期赢家可能来自动量和费用，不直接推荐 |
| Fama & French, *Luck versus Skill in the Cross-Section of Mutual Fund Returns* (2010) | 区分技能与运气 | 推荐必须看滚动稳定性而非一次排名 |
| Cremers & Petajisto, *How Active Is Your Fund Manager?* | Active Share | 主动基金可用持仓偏离解释“是否真正主动” |
| Brinson, Hood & Beebower, *Determinants of Portfolio Performance* (1986) | 配置与选择归因 | 归因独立于推荐评分，为 AI 提供解释证据 |
| Morningstar Rating Methodology | 分类内风险调整收益比较 | 先分类、再同类比较，多周期而非单周期 |
| LSEG Lipper Global Classifications | 全球基金分类定义 | 分类是推荐和比较的第一层边界 |
| S&P SPIVA Persistence Scorecard | 检查历史领先是否持续 | 推荐页面必须提示过去领先不保证持续 |

### 公开来源

- https://doi.org/10.1086/294846
- https://doi.org/10.2139/ssrn.244153
- https://doi.org/10.3905/jpm.1992.409394
- https://doi.org/10.1111/j.1540-6261.1997.tb03808.x
- https://doi.org/10.1111/j.1540-6261.2010.01598.x
- https://doi.org/10.2139/ssrn.891719
- https://doi.org/10.2469/faj.v42.n4.39
- https://www.morningstar.com/content/dam/marketing/apac/au/pdfs/Legal/RatingMethodology_Factsheet.pdf
- https://lipperalpha.refinitiv.com/wp-content/uploads/2016/01/LipperGlobalClassifications2025.pdf
- https://www.spglobal.com/spdji/en/spiva/article/us-persistence-scorecard/

## 开源项目借鉴

| 项目 | 借鉴内容 | 不照搬的部分 |
| --- | --- | --- |
| AKShare | 中国基金与市场数据适配 | 不把单一公开接口视为稳定主数据源 |
| OpenBB | 多数据源统一接入、供页面和 Agent 共同消费 | 不引入与基金无关的全资产终端复杂度 |
| QuantStats | 收益、风险、回撤和滚动图表 | 不直接使用面向交易策略的整套报告界面 |
| pyfolio-reloaded | 风险分析与归因图表组织 | 不引入回测交易语义 |
| Portfolio Performance | 清楚的时间序列和比较交互 | 不开发个人持仓记账和交易管理 |
| deep-div/mutual-fund-screener | 简单筛选器与列表交互 | 不复制其地区数据源和用户系统 |
| mf-screener-ai | 证明 AI 可辅助实验 | 不采用“让多个 LLM 生成评分算法再平均”的做法 |

### 开源链接

- https://github.com/akfamily/akshare
- https://github.com/OpenBB-finance/OpenBB
- https://github.com/ranaroussi/quantstats
- https://github.com/stefan-jansen/pyfolio-reloaded
- https://github.com/portfolio-performance/portfolio
- https://github.com/deep-div/mutual-fund-screener
- https://github.com/as1605/mf-screener-ai

## 实施顺序

### 第一阶段：普通用户立即可用

1. 合并主导航，只保留找基金、调研库、AI 分析、标签推荐。
2. 修好基金浏览器、详情页、净值曲线和多基金比较。
3. 将现有筛选和排名改造成按类别与风格输出最多十只候选。

### 第二阶段：调研纪要成为真实数据源

1. 增加本地文件夹配置和增量索引。
2. 建立基金经理实体匹配、纪要引用和标签人工确认。
3. 将确认后的标签合并进综合基金数据库。

### 第三阶段：量化归因与 AI 分析闭环

1. 补齐 Brinson 所需的真实基准行业权重、区间持仓权重和行业收益。
2. 区分正式因子模型与普通风格暴露，禁止把简化模型标成 Barra。
3. 建立按需 AI 分析会话和历史记录，向牛马 Desk 暴露分析动作。

## 验收场景

用户搜索一只基金，能看到真实净值曲线和同类位置；选择三只同类基金完成比较；同步一份本地经理调研纪要并确认标签；点击“AI 分析”得到带引用和归因证据的结论；最后选择“大盘成长”标签，获得最多十只带理由、风险和数据日期的候选基金。
