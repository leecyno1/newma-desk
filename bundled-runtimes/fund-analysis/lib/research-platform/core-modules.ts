export type CoreResearchModule = {
  id: string
  label: string
  href: string
  purpose: string
  layer: 'database' | 'tool' | 'skill' | 'ai-surface'
}

export type MergedResearchRoute = {
  from: string
  to: string
  reason: string
}

export {
  PROFESSIONAL_METHODOLOGY_VERSION,
  professionalResearchStages,
} from '@/lib/fund-research/methodology'

export const coreResearchModules: CoreResearchModule[] = [
  {
    id: 'research-universe',
    label: '全市场研究库',
    href: '/market',
    purpose: '统一承载基金主数据、研究覆盖状态、份额合并、策略标签、market-current-page-shortlist 当前页短名单、market-decision-explainer 当前页决策解释、market-promotion-queue 晋级分流、market-compare-basket-evidence 对比篮证据和 market-compare-basket-win-loss 对比篮研究分层。',
    layer: 'ai-surface',
  },
  {
    id: 'fund-profile',
    label: '基金画像',
    href: '/funds',
    purpose: '沉淀单基金基础资料、净值、费用、基准、风格和证据完整度。',
    layer: 'skill',
  },
  {
    id: 'peer-comparison',
    label: '同类横评',
    href: '/analysis/comparison',
    purpose: '通过 peer-group-benchmark、comparison-research-score、comparison-research-summary、comparison-win-loss-audit 与 market-compare-basket-win-loss 构建同类组、研究评分、摘要原因、胜负线和收益来源解释。',
    layer: 'skill',
  },
  {
    id: 'holding-exposure',
    label: '持仓画像',
    href: '/evidence-coverage',
    purpose: '分析行业、主题、风格、集中度、换手和持仓相似度。',
    layer: 'tool',
  },
  {
    id: 'manager-and-company-research',
    label: '经理与公司研究',
    href: '/managers',
    purpose: '评价经理任期切片、共管产品、代表作和基金公司平台能力。',
    layer: 'skill',
  },
  {
    id: 'research-report-lifecycle',
    label: '研究报告生命周期',
    href: '/reports',
    purpose: '管理初评、复核、更新、归档、复用判断和失效提示。',
    layer: 'ai-surface',
  },
  {
    id: 'evidence-ledger',
    label: '数据证据',
    href: '/evidence-coverage',
    purpose: '维护字段级来源、可信度、缺口和材料核验台账。',
    layer: 'database',
  },
  {
    id: 'data-ingestion',
    label: '数据接入',
    href: '/evidence-coverage',
    purpose: '接入 Tushare、公开材料、上传文档和未来 OpenBB-style adapter。',
    layer: 'tool',
  },
]

export const mergedResearchRoutes: MergedResearchRoute[] = [
  {
    from: '/investor-selection',
    to: '/market',
    reason: '个人研究画像入口合并到全市场研究库，保留研究筛选，不保留投顾式选基。',
  },
  {
    from: '/sales-rules',
    to: '/evidence-coverage',
    reason: '销售字段下沉为材料证据核验，不作为独立申赎门禁模块。',
  },
  {
    from: '/alerts',
    to: '/evidence-coverage',
    reason: '复查事件合并为研究证据缺口，不维护申赎前事件队列。',
  },
  {
    from: '/pools',
    to: '/market',
    reason: '候选/观察状态合并为研究覆盖清单，不维护申赎漏斗。',
  },
  {
    from: '/rankings',
    to: '/analysis/comparison',
    reason: '排行榜合并为同类横评，输出 peer diagnostics 而非泛推荐榜。',
  },
]

export { openSourceReuseReferences as reusableOpenSourceReferences } from './open-source-references'
