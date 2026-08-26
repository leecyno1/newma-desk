export type OpenSourceReuseDecision =
  | 'adopt-as-adapter-pattern'
  | 'reuse-metric-definition'
  | 'reuse-agent-orchestration-pattern'
  | 'watch-only'

export type OpenSourceReuseReference = {
  id: string
  name: string
  sourceUrl: string
  checkedAt: string
  fit: string
  decision: OpenSourceReuseDecision
  reusablePattern: string
  candidateModules: string[]
  boundary: string
}

export const openSourceReuseReferences: OpenSourceReuseReference[] = [
  {
    id: 'openbb-odp',
    name: 'OpenBB Open Data Platform',
    sourceUrl: 'https://github.com/OpenBB-finance/OpenBB',
    checkedAt: '2026-06-11',
    fit: '金融数据 provider、REST、Python、MCP 和研究工作台多表面接入参考。',
    decision: 'adopt-as-adapter-pattern',
    reusablePattern: 'connect once, consume everywhere；把数据源接入、标准化输出和上层研究界面解耦。',
    candidateModules: ['data-ingestion', 'research-universe', 'evidence-ledger'],
    boundary: '只借鉴 provider/adapter 和 MCP 暴露方式，不引入申赎执行、组合执行或泛金融工作台范围。',
  },
  {
    id: 'akshare',
    name: 'AKShare',
    sourceUrl: 'https://github.com/akfamily/akshare',
    checkedAt: '2026-06-11',
    fit: '中国市场公开财经数据补充源，适合做基金持仓股票、公告和市场侧辅助数据的候选 adapter。',
    decision: 'watch-only',
    reusablePattern: '以薄 adapter 包装公开接口，输出字段必须进入 EvidenceLedger 后再被研究工具消费。',
    candidateModules: ['data-ingestion', 'holding-exposure', 'manager-and-company-research'],
    boundary: '当前 Tushare 是主数据源；AKShare 只能作为补充证据源，不绕过来源日期、字段可信度和材料核验。',
  },
  {
    id: 'financetoolkit',
    name: 'FinanceToolkit',
    sourceUrl: 'https://github.com/JerBouma/FinanceToolkit',
    checkedAt: '2026-06-11',
    fit: '透明财务与绩效指标口径参考，适合借鉴指标命名、分组和可解释输出。',
    decision: 'reuse-metric-definition',
    reusablePattern: '指标口径集中在 toolkit 层，由页面消费结构化结果而不是散落公式。',
    candidateModules: ['fund-profile', 'peer-comparison', 'research-report-lifecycle'],
    boundary: '不接入股票财报工具作为基金研究主路径；只复用指标组织方式和可解释输出思想。',
  },
  {
    id: 'quantstats-empyrical',
    name: 'QuantStats / empyrical',
    sourceUrl: 'https://github.com/quantopian/empyrical',
    checkedAt: '2026-06-18',
    fit: '收益序列、回撤、滚动风险收益指标和基准对齐口径参考。',
    decision: 'reuse-metric-definition',
    reusablePattern: '把收益/回撤/波动/下行风险等序列指标集中到深模块，报告只展示计算结果。',
    candidateModules: ['fund-profile', 'peer-comparison', 'research-report-lifecycle'],
    boundary: '不引入回测、申赎执行和组合归因语义；只复用基金净值研究所需指标定义。',
  },
  {
    id: 'quantstats-tearsheet',
    name: 'QuantStats tear sheet patterns',
    sourceUrl: 'https://github.com/ranaroussi/quantstats',
    checkedAt: '2026-06-18',
    fit: 'HTML 报告、收益序列图表和指标章节组织方式参考，适合报告生命周期与基金画像页面。',
    decision: 'reuse-metric-definition',
    reusablePattern: '报告只消费指标引擎输出，把图表、表格和口径说明作为 renderer seam，而不是把公式写进页面。',
    candidateModules: ['fund-profile', 'research-report-lifecycle', 'peer-comparison'],
    boundary: '不复用其交易组合 tearsheet 语义；只借鉴净值序列研究报告章节组织和指标展示口径。',
  },
  {
    id: 'microsoft-qlib',
    name: 'Microsoft Qlib',
    sourceUrl: 'https://github.com/microsoft/qlib',
    checkedAt: '2026-06-12',
    fit: 'AI-oriented quantitative research infrastructure reference，适合借鉴数据层、特征/指标流水线和研究实验组织方式。',
    decision: 'reuse-metric-definition',
    reusablePattern: '把数据 handler、特征计算、模型/评分实验和报告输出分层，避免把候选筛选、指标计算和页面文案堆在单一路由。',
    candidateModules: ['research-universe', 'fund-profile', 'peer-comparison', 'data-ingestion'],
    boundary: '不引入申赎执行、组合执行、回测执行和策略生产；只复用研究数据流水线与指标实验组织方式。',
  },
  {
    id: 'finrobot',
    name: 'FinRobot',
    sourceUrl: 'https://github.com/AI4Finance-Foundation/FinRobot',
    checkedAt: '2026-06-18',
    fit: '金融 AI agent、工具调用、报告生成和多层编排参考。',
    decision: 'reuse-agent-orchestration-pattern',
    reusablePattern: 'AI 只消费工具证据，报告结论由可审计 ToolResult 与 SkillRun 驱动。',
    candidateModules: ['research-report-lifecycle', 'manager-and-company-research', 'peer-comparison'],
    boundary: '不引入股票投研、执行策略或风险评估 agent；只复用证据驱动报告编排。',
  },
  {
    id: 'anthropic-financial-services-prompts',
    name: 'Anthropic financial services prompt patterns',
    sourceUrl: 'https://docs.anthropic.com/en/solutions/financial-services',
    checkedAt: '2026-06-18',
    fit: '金融研究问答、长文档分析、来源引用和审计口径参考。',
    decision: 'reuse-agent-orchestration-pattern',
    reusablePattern: '把模型限定为“引用证据、解释差异、列反证问题”，事实与门禁由 ToolResult 和 EvidenceLedger 给出。',
    candidateModules: ['research-report-lifecycle', 'evidence-ledger', 'manager-and-company-research'],
    boundary: '只复用金融服务提示词与证据约束模式，不接入泛财富管理、交易或投资建议工作流。',
  },
  {
    id: 'local-a-stock-data-skill',
    name: 'a-stock-data skill',
    sourceUrl: 'https://github.com/leecyno1/newma-desk',
    checkedAt: '2026-06-11',
    fit: '本地 A 股数据技能，可为基金持仓穿透、公告和行业主题补证提供参考。',
    decision: 'adopt-as-adapter-pattern',
    reusablePattern: '直连 HTTP 数据端点、字段归一化和来源可追踪；只在持仓画像或经理研究中作为补充 adapter。',
    candidateModules: ['holding-exposure', 'manager-and-company-research', 'evidence-ledger'],
    boundary: '基金研究模块不扩展成 A 股投研平台；股票数据只服务持仓解释和证据补齐。',
  },
]

export function openSourceReferencesForModule(moduleId: string) {
  return openSourceReuseReferences.filter((reference) => reference.candidateModules.includes(moduleId))
}
