import type { ResearchStageId } from '../contracts'

export const PROFESSIONAL_METHODOLOGY_VERSION = '2.0.0'

export type MethodologySource = {
  id: string
  title: string
  authors: string
  year: number
  url: string
  contribution: string
  limitation: string
}

export type ProfessionalResearchStage = {
  id: ResearchStageId
  order: number
  name: string
  purpose: string
  requiredEvidence: string[]
  methods: string[]
  hardGates: string[]
  sourceIds: string[]
  existingAssets: string[]
}

export const methodologySources: MethodologySource[] = [
  {
    id: 'fama-french-2010',
    title: 'Luck versus Skill in the Cross-Section of Mutual Fund Returns',
    authors: 'Eugene F. Fama, Kenneth R. French',
    year: 2010,
    url: 'https://ideas.repec.org/a/bla/jfinan/v65y2010i5p1915-1947.html',
    contribution: '使用净费后收益、横截面分布与统计不确定性区分运气和技能。',
    limitation: '研究样本与市场制度主要来自美国；结论不能机械外推到所有中国公募类别。',
  },
  {
    id: 'carhart-1997',
    title: 'On Persistence in Mutual Fund Performance',
    authors: 'Mark M. Carhart',
    year: 1997,
    url: 'https://ideas.repec.org/a/bla/jfinan/v52y1997i1p57-82.html',
    contribution: '要求无幸存者偏差样本、因子调整与持续性置信判断，尤其重视持续落后基金的淘汰。',
    limitation: '经典四因子框架需要按资产类别和本地市场重新校准。',
  },
  {
    id: 'cremers-petajisto-2009',
    title: 'How Active Is Your Fund Manager? A New Measure That Predicts Performance',
    authors: 'K. J. Martijn Cremers, Antti Petajisto',
    year: 2009,
    url: 'https://ideas.repec.org/a/oup/rfinst/v22y2009i9p3329-3365.html',
    contribution: '用 Active Share 检查持仓与基准的偏离，识别可能的隐形指数化。',
    limitation: 'Active Share 是诊断证据，不是跨类别通用的独立评级。',
  },
  {
    id: 'berk-van-binsbergen-2015',
    title: 'Measuring Skill in the Mutual Fund Industry',
    authors: 'Jonathan B. Berk, Jules H. van Binsbergen',
    year: 2015,
    url: 'https://ideas.repec.org/a/eee/jfinec/v118y2015i1p1-20.html',
    contribution: '把基金规模、容量与创造的美元价值纳入技能评价，避免只看 alpha。',
    limitation: '价值增加口径依赖合适的机会成本基准与可靠规模数据。',
  },
  {
    id: 'sharpe-1992',
    title: 'Asset Allocation: Management Style and Performance Measurement',
    authors: 'William F. Sharpe',
    year: 1992,
    url: 'https://web.stanford.edu/~wfsharpe/art/sa/sa.htm',
    contribution: '用收益基础风格分析区分资产配置风格与证券选择，并观察风格漂移。',
    limitation: 'RBSA 是收益推断，需与持仓基础分析和合同基准交叉验证。',
  },
  {
    id: 'cfa-manager-selection-2026',
    title: 'Investment Manager Selection',
    authors: 'CFA Institute',
    year: 2026,
    url: 'https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/investment-manager-selection',
    contribution: '提供“投资范围—量化轨迹—投资尽调—运营尽调—持续监督”的专业选择主流程。',
    limitation: '框架需要结合中国公募披露、销售适当性与具体委托约束落地。',
  },
  {
    id: 'morningstar-medalist-2026',
    title: "What's Changing (and Not Changing) With the Morningstar Medalist Rating",
    authors: 'Morningstar',
    year: 2026,
    url: 'https://www.morningstar.com/funds/whats-changing-not-changing-with-morningstar-medalist-rating',
    contribution: '强调 People、Process、Parent、Price、类别相对评价、主动/被动分支与覆盖率门槛。',
    limitation: '属于公开评级方法说明，本项目只借鉴结构，不复制其专有评级或阈值。',
  },
  {
    id: 'csrc-fund-evaluation-rules',
    title: '证券投资基金评价业务管理暂行办法',
    authors: '中国证券监督管理委员会',
    year: 2009,
    url: 'http://www.csrc.gov.cn/csrc/c106256/c1653866/content.shtml',
    contribution: '确立长期、公平、全面、客观和方法一致的基金评价原则，反对单指标误导。',
    limitation: '监管规则定义评价底线，不替代研究机构自己的证据与尽调责任。',
  },
]

export const professionalResearchStages: ProfessionalResearchStage[] = [
  {
    id: 'universe-identity',
    order: 1,
    name: '研究范围与身份',
    purpose: '先定义可比较的基金实体、份额类别、生命周期和主动/被动属性。',
    requiredEvidence: ['基金实体与份额映射', '成立/终止时间', '策略与资产类别', '费用类别'],
    methods: ['份额合并', 'point-in-time 研究范围', '保留终止基金', '主动/被动分支'],
    hardGates: ['身份无法归一', '生命周期未知', '策略类别不可判定'],
    sourceIds: ['carhart-1997', 'cfa-manager-selection-2026', 'csrc-fund-evaluation-rules'],
    existingAssets: ['FundEntity', 'FundShareClass', 'FundLifecycleEvent', 'fund-entity-standardization'],
  },
  {
    id: 'evidence-quality',
    order: 2,
    name: '证据与数据质量',
    purpose: '记录来源、时点、数据版本、覆盖率、缺失和血缘，先判断证据能否支持结论。',
    requiredEvidence: ['as-of 时间', '来源与版本', '字段覆盖率', '缺失原因', '可复现快照'],
    methods: ['字段级证据账本', '覆盖率门槛', '新鲜度与异常检查', '快照重放'],
    hardGates: ['关键字段缺失', '数据时点错配', '来源不可追溯'],
    sourceIds: ['morningstar-medalist-2026', 'csrc-fund-evaluation-rules'],
    existingAssets: ['DataSourceSnapshot', 'MetricSnapshot', 'EvidenceLedger', 'material-evidence-gate'],
  },
  {
    id: 'peer-benchmark',
    order: 3,
    name: '同类组与基准',
    purpose: '建立类别同类、合同基准、风格基准和可解释的比较样本。',
    requiredEvidence: ['同类组规则', '基准映射', '样本数量', '风格与规模分层'],
    methods: ['category peer', 'benchmark suitability', 'RBSA 基准复核', '样本充分性检查'],
    hardGates: ['同类组不可解释', '基准明显不适配', '样本过薄却输出优势结论'],
    sourceIds: ['sharpe-1992', 'cfa-manager-selection-2026', 'morningstar-medalist-2026'],
    existingAssets: ['PeerGroup', 'PeerGroupMember', 'BenchmarkMapping', 'peer-group-benchmark'],
  },
  {
    id: 'quantitative-evaluation',
    order: 4,
    name: '量化轨迹评价',
    purpose: '用净费后、滚动、因子调整和有不确定性的指标评价轨迹，而不是追逐单期收益。',
    requiredEvidence: ['净费后收益', '滚动窗口', '回撤与修复期', '上/下行捕获', '因子暴露', '规模与费用'],
    methods: ['bootstrap alpha', 'factor-adjusted return', 'persistence', 'capture ratio', 'value added'],
    hardGates: ['只按短期收益排名', '忽略费用', '幸存者偏差', '无不确定性披露'],
    sourceIds: ['fama-french-2010', 'carhart-1997', 'berk-van-binsbergen-2015', 'cfa-manager-selection-2026'],
    existingAssets: ['MetricSnapshot', 'FactorExposure', 'PerformanceAttribution', 'benchmark-attribution'],
  },
  {
    id: 'holdings-style',
    order: 5,
    name: '持仓、风格与容量',
    purpose: '交叉验证基金实际持仓、风格漂移、集中度、主动程度和容量约束。',
    requiredEvidence: ['定期持仓', '合同/风格基准', '行业与因子暴露', '集中度', '规模与流动性'],
    methods: ['Active Share', 'HBSA/RBSA', 'style drift', 'look-through', 'capacity review'],
    hardGates: ['持仓数据过期却下确定结论', '明显风格漂移未解释', '容量风险未评估'],
    sourceIds: ['cremers-petajisto-2009', 'sharpe-1992', 'berk-van-binsbergen-2015'],
    existingAssets: ['Holding', 'HoldingLookthroughSnapshot', 'HoldingSimilarity', 'holding-deep-research'],
  },
  {
    id: 'qualitative-due-diligence',
    order: 6,
    name: '投资与运营尽调',
    purpose: '把 People、Process、Parent、Price、载体与运营完整性放在同一尽调框架。',
    requiredEvidence: ['经理任期切片', '团队与人员稳定性', '投资流程', '公司治理', '费用与载体', '运营控制'],
    methods: ['People/Process/Parent/Price', 'investment DDQ', 'operational DDQ', 'key-person review'],
    hardGates: ['关键人员无法核验', '流程与持仓行为矛盾', '运营完整性重大缺口'],
    sourceIds: ['cfa-manager-selection-2026', 'morningstar-medalist-2026'],
    existingAssets: ['ManagerTenureSlice', 'ManagerTransitionEvent', 'FundCompanyResearchProfile', 'manager-research-loop'],
  },
  {
    id: 'decision-governance',
    order: 7,
    name: '研究决策治理',
    purpose: '记录论点、反证、置信度、复核人、版本和结论反转条件。',
    requiredEvidence: ['研究论点', '关键反证', '未解决问题', '反转条件', '方法论版本'],
    methods: ['evidence-weighted judgement', 'Type I/II error review', '版本化决策记录'],
    hardGates: ['无反证', '无方法版本', '把模型输出直接当最终结论'],
    sourceIds: ['cfa-manager-selection-2026', 'csrc-fund-evaluation-rules'],
    existingAssets: ['ResearchReport', 'AIAnalysisReport', 'ResearchMethodologyTemplate'],
  },
  {
    id: 'monitoring',
    order: 8,
    name: '持续监控与复核',
    purpose: '在经理、持仓、风格、风险、费用或数据状态变化时触发有原因的复核任务。',
    requiredEvidence: ['上次结论', '触发事件', '影响范围', '责任人', '复核期限'],
    methods: ['event-driven review', 'thesis drift', 'style/risk/fee triggers'],
    hardGates: ['重大变化未触发复核', '使用失效证据维持旧结论'],
    sourceIds: ['cfa-manager-selection-2026', 'morningstar-medalist-2026'],
    existingAssets: ['FundChangeHistory', 'FundCompanyResearchEvent', 'AlertRule', 'AlertEvent'],
  },
  {
    id: 'methodology-audit',
    order: 9,
    name: '方法论与审计',
    purpose: '发布可复现、可版本化、可复核的方法论和研究快照。',
    requiredEvidence: ['方法说明', '版本变更', '输入快照', '计算口径', '审阅轨迹'],
    methods: ['methodology versioning', 'reproducible snapshot', 'audit trail', 'coverage certification'],
    hardGates: ['口径静默变化', '输入不可重放', '结论无法追溯'],
    sourceIds: ['csrc-fund-evaluation-rules', 'morningstar-medalist-2026', 'fama-french-2010'],
    existingAssets: ['ResearchMethodologyTemplate', 'ResearchMethodologyDimension', 'ResearchMethodologyMapping'],
  },
]

export function methodologySourceById(sourceId: string) {
  return methodologySources.find((source) => source.id === sourceId)
}

export function methodologyStageById(stageId: ResearchStageId) {
  return professionalResearchStages.find((stage) => stage.id === stageId)
}
