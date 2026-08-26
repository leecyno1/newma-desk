# 专业基金研究方法来源

本项目的方法论版本为 `2.0.0`。以下来源用于定义研究流程、证据门槛和尽调结构，不用于复制任何第三方专有评级，也不意味着其海外样本结论可不经验证地套用到中国公募基金。

## 学术研究

### Fama & French (2010) — Luck versus Skill in the Cross-Section of Mutual Fund Returns

- 公开摘要与文献信息：https://ideas.repec.org/a/bla/jfinan/v65y2010i5p1915-1947.html
- DOI：`10.1111/j.1540-6261.2010.01598.x`
- 项目采用：净费后评价、业绩分布、统计不确定性和 bootstrap 思路；不把观察到的 alpha 自动解释为技能。
- 边界：研究主要基于美国主动基金样本，中国公募需按本地因子、费用、交易和披露制度重估。

### Carhart (1997) — On Persistence in Mutual Fund Performance

- 公开摘要与文献信息：https://ideas.repec.org/a/bla/jfinan/v52y1997i1p57-82.html
- 项目采用：point-in-time 研究范围、保留终止基金、因子调整、持续性置信度和持续落后基金的淘汰门槛。
- 边界：经典四因子不是所有资产类别的通用模型，债券、QDII、商品与指数增强需使用各自因子体系。

### Cremers & Petajisto (2009) — How Active Is Your Fund Manager?

- 公开摘要与文献信息：https://ideas.repec.org/a/oup/rfinst/v22y2009i9p3329-3365.html
- 项目采用：Active Share、隐形指数化诊断、持仓与基准的交叉验证。
- 边界：Active Share 只是一项持仓证据，不能脱离策略类别、费用、容量和业绩不确定性形成统一总分。

### Berk & van Binsbergen (2015) — Measuring Skill in the Mutual Fund Industry

- 公开摘要与文献信息：https://ideas.repec.org/a/eee/jfinec/v118y2015i1p1-20.html
- 项目采用：把规模、容量和创造的价值纳入技能评价，避免只看收益率 alpha。
- 边界：value-added 结果依赖机会成本基准、规模时点和数据质量。

### Sharpe (1992) — Asset Allocation: Management Style and Performance Measurement

- 作者公开全文：https://web.stanford.edu/~wfsharpe/art/sa/sa.htm
- 项目采用：收益基础风格分析（RBSA）、风格暴露、拟合度和风格漂移；与持仓基础分析（HBSA）交叉验证。
- 边界：RBSA 是对历史收益的推断，不替代定期持仓、合同约束和经理访谈。

## 专业机构方法

### CFA Institute (2026) — Investment Manager Selection

- 公开学习页面：https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/investment-manager-selection
- 项目采用的主流程：研究范围 → 量化轨迹 → 投资尽调 → 运营尽调 → 决策治理 → 持续监督。
- 同时采用：Type I / Type II 选择错误、RBSA/HBSA、上下行捕获、回撤幅度与持续时间、People/Process/firm/fees/vehicle/operational integrity。

### Morningstar Medalist Methodology Update (2026)

- 公开方法说明：https://www.morningstar.com/funds/whats-changing-not-changing-with-morningstar-medalist-rating
- 项目采用：People、Process、Parent、Price，类别相对评价，主动/被动分支，固定门槛和数据覆盖率门槛。
- 边界：本项目不复制 Medalist 等级、专有模型或阈值，只采用公开的研究结构和透明度原则。

## 中国监管底线

### 中国证监会 — 证券投资基金评价业务管理暂行办法

- 官方页面：http://www.csrc.gov.cn/csrc/c106256/c1653866/content.shtml
- 项目采用：长期性、公平性、全面性、客观性和方法一致性；不使用单一指标误导基金评价。
- 落地：方法版本公开、输入快照可重放、同类口径一致、结论披露证据缺口与适用边界。

## 方法论结论

专业基金研究不是“把几个指标加权后排序”，而是：

1. 先建立无份额重复、尽量无幸存者偏差的研究范围。
2. 先检查证据、同类和基准是否有效。
3. 再评价净费后量化轨迹、持仓风格与容量。
4. 用投资尽调和运营尽调解释量化结果是否可持续。
5. 用硬门槛、分柱判断、反证和置信度形成可审计结论。
6. 用事件触发持续复核，而不是让旧评级无限期有效。
