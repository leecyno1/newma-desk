import type { NewmaDeskPageContext } from './bridge'

export const FUND_RESEARCH_WORKSPACE_IDS = [
  'discover',
  'research',
  'analysis',
  'recommendations',
  'advanced',
  'portfolio',
] as const

export type FundResearchWorkspaceId = (typeof FUND_RESEARCH_WORKSPACE_IDS)[number]

export type FundSelection = {
  symbol: string
  name?: string
  assetType: 'fund' | 'etf'
}

export type FundResearchCapability = {
  name: string
  purpose: string
  evidence: string
}

export type FundResearchWorkspace = {
  id: FundResearchWorkspaceId
  modId: string
  title: string
  shortTitle: string
  purpose: string
  primaryHref: string
  primaryLabel: string
  capabilities: FundResearchCapability[]
  actions: Array<{ id: string; label: string; inputSchema?: unknown }>
}

const fundSymbolSchema = {
  type: 'object',
  required: ['symbol'],
  properties: { symbol: { type: 'string', minLength: 1, maxLength: 24 } },
  additionalProperties: false,
}

const analysisSchema = {
  type: 'object',
  required: ['windCode'],
  properties: {
    windCode: { type: 'string', minLength: 1, maxLength: 24 },
    question: { type: 'string', maxLength: 1000 },
  },
  additionalProperties: false,
}

export const fundResearchWorkspaces: FundResearchWorkspace[] = [
  {
    id: 'discover',
    modId: 'fund-discover',
    title: '找基金',
    shortTitle: '找基金',
    purpose: '搜索真实基金，查看净值曲线、基金详情和同类指标，并选择多只基金比较。',
    primaryHref: '/discover',
    primaryLabel: '打开基金浏览器',
    capabilities: [
      { name: '基金搜索', purpose: '按代码、名称和类别查找基金', evidence: '基金基础数据与最新净值' },
      { name: '基金详情', purpose: '查看净值曲线、收益和风险指标', evidence: '真实净值序列与指标快照' },
      { name: '基金比较', purpose: '横向比较同类基金', evidence: '同类组与统一评价口径' },
    ],
    actions: [
      { id: 'fund.search', label: '搜索基金' },
      { id: 'fund.research.snapshot', label: '读取基金研究快照', inputSchema: fundSymbolSchema },
      { id: 'fund.compare', label: '比较多只基金' },
    ],
  },
  {
    id: 'research',
    modId: 'fund-research-library',
    title: '调研库',
    shortTitle: '调研库',
    purpose: '连接本地调研纪要，按基金经理归档，提取并人工确认基金分类和风格标签。',
    primaryHref: '/research',
    primaryLabel: '打开调研库',
    capabilities: [
      { name: '本地文件夹', purpose: '扫描用户指定的调研纪要目录', evidence: '本地文件路径与扫描时间' },
      { name: '经理归类', purpose: '把纪要关联到基金经理和基金', evidence: '纪要原文与人工确认关系' },
      { name: '风格标签', purpose: '刻画理念、能力圈和风险意识', evidence: '原文引用、模型状态与置信度' },
    ],
    actions: [
      { id: 'fund.research.snapshot', label: '读取综合研究快照', inputSchema: fundSymbolSchema },
    ],
  },
  {
    id: 'analysis',
    modId: 'fund-ai-analysis',
    title: 'AI 分析',
    shortTitle: 'AI 分析',
    purpose: '用户现场运行基金评价，综合基金数据、调研纪要和业绩归因，并保存分析历史。',
    primaryHref: '/analysis',
    primaryLabel: '打开现场分析',
    capabilities: [
      { name: '单基金评价', purpose: '分析基金优势、风险和证据缺口', evidence: '统一基金研究快照' },
      { name: '业绩归因支持', purpose: '把 Barra 和 Brinson 结果加入评价', evidence: '归因状态、覆盖率和残差' },
      { name: '分析历史', purpose: '保存每次现场分析结果', evidence: '输入、版本、模型和生成时间' },
    ],
    actions: [
      { id: 'fund.analysis.run', label: '运行基金分析', inputSchema: analysisSchema },
      { id: 'fund.research.snapshot', label: '读取分析证据', inputSchema: fundSymbolSchema },
    ],
  },
  {
    id: 'recommendations',
    modId: 'fund-recommendations',
    title: '基金推荐',
    shortTitle: '基金推荐',
    purpose: '按基金类别和主流风格标签，从同类基金中返回不超过十只真实候选。',
    primaryHref: '/recommendations',
    primaryLabel: '打开基金推荐',
    capabilities: [
      { name: '类别筛选', purpose: '只在同类基金中生成候选', evidence: '基金分类目录与同类组' },
      { name: '风格筛选', purpose: '按已确认的风格标签缩小候选', evidence: '持仓、收益行为和纪要标签' },
      { name: '候选解释', purpose: '展示入选理由、风险和数据缺口', evidence: '完整评价与数据日期' },
    ],
    actions: [
      { id: 'fund.recommendations.list', label: '读取候选基金' },
      { id: 'fund.compare', label: '比较候选基金' },
    ],
  },
  {
    id: 'advanced',
    modId: 'fund-attribution',
    title: '业绩归因',
    shortTitle: '业绩归因',
    purpose: '查看 Barra 风格与风险暴露、Brinson 配置与选择效应，以及公开持仓覆盖和残差。',
    primaryHref: '/analysis/advanced',
    primaryLabel: '打开业绩归因',
    capabilities: [
      { name: 'Barra 证据', purpose: '查看可核验的行业和风格暴露', evidence: '真实披露持仓或正式因子库' },
      { name: 'Brinson 归因', purpose: '解释配置、选择和交互效应', evidence: '上一季度持仓与真实基准行情' },
      { name: '证据门禁', purpose: '数据不足时明确不可用或部分可用', evidence: '覆盖率、残差和缺失项' },
    ],
    actions: [
      { id: 'fund.attribution.run', label: '运行业绩归因', inputSchema: fundSymbolSchema },
      { id: 'fund.research.snapshot', label: '读取基金研究快照', inputSchema: fundSymbolSchema },
    ],
  },
  {
    id: 'portfolio',
    modId: 'fund-portfolio',
    title: '基金组合',
    shortTitle: '基金组合',
    purpose: '构建研究型基金组合，设置目标权重，检查组合风险、回测表现、偏离监控和交易清单。',
    primaryHref: '/portfolio',
    primaryLabel: '打开基金组合',
    capabilities: [
      { name: '目标配置', purpose: '按同类基金组设置目标权重并校验合计', evidence: '组合目标配置与权重校验' },
      { name: '组合分析', purpose: '查看重叠、风格暴露和相关性', evidence: '真实基金持仓、净值与同类评价' },
      { name: '回测监控', purpose: '回测历史风险收益并识别目标偏离', evidence: '基金净值序列、实际权重与监控快照' },
    ],
    actions: [],
  },
]

export function isFundResearchWorkspace(value: string): value is FundResearchWorkspaceId {
  return FUND_RESEARCH_WORKSPACE_IDS.includes(value as FundResearchWorkspaceId)
}

export function fundResearchWorkspaceById(workspaceId: FundResearchWorkspaceId) {
  return fundResearchWorkspaces.find((workspace) => workspace.id === workspaceId)!
}

export function buildFundResearchPageContext(input: {
  workspace: FundResearchWorkspace
  selection?: FundSelection | null
  filters?: Record<string, unknown>
  asOf?: string
  tasks?: NewmaDeskPageContext['tasks']
}): NewmaDeskPageContext {
  return {
    view: { id: input.workspace.modId, title: input.workspace.title },
    visibleBlocks: [
      { id: 'fund-selection-summary', type: 'summary', title: input.workspace.purpose },
      { id: 'fund-selection-capabilities', type: 'table', title: '可用能力' },
      { id: 'fund-selection-actions', type: 'actions', title: '可执行操作' },
    ],
    selection: input.selection ? {
      symbol: input.selection.symbol,
      name: input.selection.name ?? input.selection.symbol,
      market: 'CN',
      assetType: input.selection.assetType,
    } : {},
    filters: input.filters ?? {},
    data: {
      asOf: input.asOf ?? new Date().toISOString(),
      source: 'fund-analysis/fund-research-snapshot',
      freshness: 'fresh',
      summary: {
        workspace: input.workspace.id,
        capabilities: input.workspace.capabilities,
        productScope: 'browse-research-evaluate-attribute-recommend-compose',
        restrictions: ['no-trading', 'no-suitability', 'no-investment-decision'],
      },
    },
    actions: input.workspace.actions.map((action) => ({ ...action, available: true })),
    tasks: input.tasks ?? [],
  }
}
