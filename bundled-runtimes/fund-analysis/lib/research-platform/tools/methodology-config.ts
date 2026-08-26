import { FUND_RESEARCH_GUARDRAILS, type ResearchTool } from '../contracts'
import { createToolResult } from './tooling'

export type MethodologyTemplateKey =
  | 'active_equity'
  | 'fixed_income'
  | 'index_fund'
  | 'money_market'
  | 'qdii'
  | 'fof'
  | 'quant_fund'

export type MethodologyResolutionKey = MethodologyTemplateKey | 'unclassified'

export type MethodologyConfigInput = {
  fundType?: string | null
  assetClass?: string | null
  activePassive?: string | null
  strategyFamilyKey?: string | null
  requestedTemplateKey?: MethodologyTemplateKey | string | null
  availableEvidence?: string[] | null
}

export type MethodologyDimension = {
  key: string
  name: string
  weight: number
  hardGate: boolean
  evidenceFields: string[]
  reason: string
}

export type MethodologyConfigOutput = {
  resolutionStatus: 'matched' | 'unclassified'
  templateKey: MethodologyResolutionKey
  templateName: string
  matchRationale: string
  dimensions: MethodologyDimension[]
  hardGateDimensions: string[]
  missingEvidenceFields: string[]
  readyForFormalReview: boolean
  policy: {
    hardBoundary: string
    requiredFundTypes: MethodologyTemplateKey[]
  }
}

const toolName = 'methodology-config'
const version = '1.0.0'

const templates: Record<MethodologyTemplateKey, {
  name: string
  aliases: string[]
  assetHints: string[]
  activePassiveHints: string[]
  dimensions: MethodologyDimension[]
}> = {
  active_equity: {
    name: '主动权益基金研究模板',
    aliases: ['主动权益', '权益', '股票型', '混合型', 'active_equity'],
    assetHints: ['equity', '股票', '权益'],
    activePassiveHints: ['active', '主动'],
    dimensions: [
      { key: 'benchmark_attribution', name: '基准与归因', weight: 22, hardGate: true, evidenceFields: ['benchmark_mapping', 'excess_return', 'style_exposure', 'industry_attribution'], reason: '主动权益必须解释超额收益来自配置、选股、风格还是残差。' },
      { key: 'peer_group', name: '同类池', weight: 16, hardGate: true, evidenceFields: ['peer_group_policy', 'asset_class', 'style_tags', 'scale_bucket'], reason: '同类池决定排名和分位是否可解释。' },
      { key: 'holding_lookthrough', name: '持仓穿透', weight: 18, hardGate: true, evidenceFields: ['top_holdings', 'industry_exposure', 'concentration', 'turnover'], reason: '主动权益研究要看行业/主题/集中度和重仓变化。' },
      { key: 'manager', name: '基金经理', weight: 22, hardGate: true, evidenceFields: ['tenure_slice', 'representative_fund', 'style_drift'], reason: '经理任期和代表作是主动权益能力识别核心。' },
      { key: 'company', name: '基金公司', weight: 12, hardGate: false, evidenceFields: ['product_line', 'research_team', 'platform_capability'], reason: '公司平台用于解释能力可复制性。' },
      { key: 'fee_tracking', name: '费用与跟踪误差', weight: 10, hardGate: false, evidenceFields: ['fee_rate', 'tracking_error'], reason: '费用和波动拖累影响长期持有体验，但不是交易判断。' },
    ],
  },
  fixed_income: {
    name: '固收基金研究模板',
    aliases: ['固收', '债券', '纯债', '二级债', 'fixed_income'],
    assetHints: ['fixed income', 'bond', '债券', '固收'],
    activePassiveHints: ['active', '主动'],
    dimensions: [
      { key: 'credit_exposure', name: '信用暴露', weight: 24, hardGate: true, evidenceFields: ['rating_distribution', 'issuer_concentration', 'default_history'], reason: '固收收益不能脱离信用下沉和主体集中度解释。' },
      { key: 'duration_curve', name: '久期与曲线暴露', weight: 18, hardGate: true, evidenceFields: ['duration', 'yield_curve_exposure', 'leverage'], reason: '久期、杠杆和曲线位置决定利率风险来源。' },
      { key: 'benchmark_attribution', name: '基准与归因', weight: 16, hardGate: true, evidenceFields: ['bond_benchmark', 'carry_return', 'capital_gain'], reason: '固收归因要拆票息、资本利得和信用利差。' },
      { key: 'peer_group', name: '同类池', weight: 14, hardGate: true, evidenceFields: ['bond_type', 'duration_bucket', 'credit_bucket'], reason: '纯债、短债、二级债不可混池比较。' },
      { key: 'manager', name: '基金经理', weight: 14, hardGate: false, evidenceFields: ['tenure_slice', 'drawdown_control'], reason: '经理研究侧重回撤控制和信用风险处理。' },
      { key: 'company', name: '基金公司', weight: 14, hardGate: false, evidenceFields: ['fixed_income_team', 'credit_research_platform'], reason: '固收更依赖平台信用研究和交易支持能力。' },
    ],
  },
  index_fund: {
    name: '指数基金研究模板',
    aliases: ['指数', 'ETF', '被动', 'index_fund'],
    assetHints: ['index', '指数', 'ETF'],
    activePassiveHints: ['passive', '被动'],
    dimensions: [
      { key: 'fee_tracking', name: '费用与跟踪误差', weight: 28, hardGate: true, evidenceFields: ['expense_ratio', 'tracking_error', 'tracking_difference'], reason: '指数基金核心是低成本和低偏离。' },
      { key: 'benchmark_attribution', name: '基准与归因', weight: 22, hardGate: true, evidenceFields: ['index_benchmark', 'replication_method', 'tracking_difference'], reason: '必须确认跟踪标的、复制方式和偏离来源。' },
      { key: 'liquidity_scale', name: '规模与流动性', weight: 18, hardGate: true, evidenceFields: ['aum', 'turnover', 'creation_redemption'], reason: '规模和流动性影响指数产品可持续性和偏离。' },
      { key: 'holding_lookthrough', name: '持仓穿透', weight: 14, hardGate: false, evidenceFields: ['constituents', 'weight_deviation'], reason: '持仓用于验证是否贴合指数。' },
      { key: 'peer_group', name: '同类池', weight: 10, hardGate: true, evidenceFields: ['same_index_peers', 'share_class'], reason: '指数产品优先同指数横评。' },
      { key: 'company', name: '基金公司', weight: 8, hardGate: false, evidenceFields: ['index_product_line', 'operations_capability'], reason: '被动产品更关注运营和产品线能力。' },
    ],
  },
  money_market: {
    name: '货币基金研究模板',
    aliases: ['货币', '现金管理', 'money_market'],
    assetHints: ['money', 'money_market', '货币', '现金管理'],
    activePassiveHints: ['active', '主动'],
    dimensions: [
      { key: 'income_competitiveness', name: '收益竞争力', weight: 35, hardGate: true, evidenceFields: ['seven_day_annualized_yield', 'annualized_return'], reason: '货币基金需同时观察七日年化收益率和较长窗口收益中枢。' },
      { key: 'capital_preservation', name: '本金保护', weight: 30, hardGate: true, evidenceFields: ['max_drawdown'], reason: '净值回撤是货币基金稳定性评价的硬证据。' },
      { key: 'income_stability', name: '收益稳定性', weight: 15, hardGate: false, evidenceFields: ['annualized_volatility', 'positive_return_ratio'], reason: '波动和正收益比例用于识别收益中枢是否稳定。' },
      { key: 'liquidity_scale', name: '规模与流动性', weight: 10, hardGate: true, evidenceFields: ['aum'], reason: '规模是流动性管理和赎回承接能力的代理证据。' },
      { key: 'data_quality', name: '数据质量', weight: 10, hardGate: false, evidenceFields: ['source_freshness'], reason: '短周期收益指标必须保留来源与时点。' },
    ],
  },
  qdii: {
    name: 'QDII 基金研究模板',
    aliases: ['QDII', '海外', '全球', '港股', '美股', 'qdii'],
    assetHints: ['qdii', '海外', '全球', '港股', '美股'],
    activePassiveHints: ['active', 'passive', '主动', '被动'],
    dimensions: [
      { key: 'region_currency', name: '汇率与区域暴露', weight: 22, hardGate: true, evidenceFields: ['region_exposure', 'currency_exposure', 'fx_policy'], reason: 'QDII 必须把区域市场和汇率暴露拆开。' },
      { key: 'benchmark_attribution', name: '基准与归因', weight: 18, hardGate: true, evidenceFields: ['global_benchmark', 'local_market_return', 'fx_return'], reason: '海外基金超额要区分市场、汇率和主动贡献。' },
      { key: 'holding_lookthrough', name: '持仓穿透', weight: 18, hardGate: true, evidenceFields: ['overseas_holdings', 'sector_exposure', 'country_exposure'], reason: '海外持仓穿透决定主题和区域风险解释。' },
      { key: 'peer_group', name: '同类池', weight: 14, hardGate: true, evidenceFields: ['region_bucket', 'asset_class', 'active_passive'], reason: '不同市场和币种不可简单横评。' },
      { key: 'manager', name: '基金经理', weight: 14, hardGate: false, evidenceFields: ['overseas_tenure', 'advisor_role'], reason: '需区分境内经理、海外顾问和团队贡献。' },
      { key: 'company', name: '基金公司', weight: 14, hardGate: false, evidenceFields: ['qdii_quota', 'overseas_platform'], reason: 'QDII 研究要看海外投研和额度/运营能力。' },
    ],
  },
  fof: {
    name: 'FOF 基金研究模板',
    aliases: ['FOF', '基金中基金', '养老', 'fof'],
    assetHints: ['fof', '基金中基金', '养老'],
    activePassiveHints: ['active', '主动'],
    dimensions: [
      { key: 'underlying_lookthrough', name: '底层基金穿透', weight: 28, hardGate: true, evidenceFields: ['underlying_funds', 'lookthrough_asset_allocation', 'double_fee'], reason: 'FOF 首先要穿透到底层基金和资产配置。' },
      { key: 'asset_allocation', name: '资产配置归因', weight: 20, hardGate: true, evidenceFields: ['allocation_policy', 'rebalance_history', 'allocation_effect'], reason: 'FOF 收益主要来自资产配置和基金选择。' },
      { key: 'peer_group', name: '同类池', weight: 14, hardGate: true, evidenceFields: ['risk_target', 'equity_center', 'holding_period'], reason: 'FOF 要按风险目标和权益中枢构建同类池。' },
      { key: 'manager', name: '基金经理', weight: 16, hardGate: false, evidenceFields: ['fof_tenure', 'fund_selection_record'], reason: '经理评价侧重资产配置纪律和基金筛选能力。' },
      { key: 'company', name: '基金公司', weight: 12, hardGate: false, evidenceFields: ['fof_team', 'fund_research_platform'], reason: 'FOF 更依赖基金研究平台和产品准入能力。' },
      { key: 'fee_tracking', name: '费用与跟踪误差', weight: 10, hardGate: false, evidenceFields: ['management_fee', 'underlying_fee'], reason: '双重费率会侵蚀长期收益解释。' },
    ],
  },
  quant_fund: {
    name: '量化基金研究模板',
    aliases: ['量化', '指数增强', '市场中性', 'quant_fund'],
    assetHints: ['quant', '量化', '指数增强'],
    activePassiveHints: ['active', '主动'],
    dimensions: [
      { key: 'model_stability', name: '模型稳定性', weight: 24, hardGate: true, evidenceFields: ['factor_decay', 'ic_stability', 'capacity_signal'], reason: '量化基金必须验证模型有效性、衰减和容量约束。' },
      { key: 'benchmark_attribution', name: '基准与归因', weight: 20, hardGate: true, evidenceFields: ['benchmark_mapping', 'factor_attribution', 'residual_return'], reason: '指数增强和量化策略要拆因子、行业和残差。' },
      { key: 'holding_lookthrough', name: '持仓穿透', weight: 16, hardGate: true, evidenceFields: ['holding_count', 'industry_neutrality', 'turnover'], reason: '持仓数量、换手和中性约束影响收益稳定性。' },
      { key: 'peer_group', name: '同类池', weight: 14, hardGate: true, evidenceFields: ['strategy_type', 'benchmark_index', 'hedging_policy'], reason: '量化多头、指数增强、市场中性不能混池。' },
      { key: 'manager', name: '基金经理', weight: 12, hardGate: false, evidenceFields: ['team_change', 'model_owner'], reason: '需识别模型团队而非只看挂名经理。' },
      { key: 'company', name: '基金公司', weight: 14, hardGate: false, evidenceFields: ['quant_platform', 'data_infrastructure'], reason: '量化能力依赖数据、工程和交易研究平台。' },
    ],
  },
}

function normalizeText(value: unknown) {
  return String(value ?? '').trim()
}

function normalizedEvidence(input: MethodologyConfigInput) {
  return new Set((Array.isArray(input.availableEvidence) ? input.availableEvidence : []).map((item) => normalizeText(item).toLowerCase()).filter(Boolean))
}

function inferTemplate(input: MethodologyConfigInput): { key: MethodologyTemplateKey | null; rationale: string } {
  const requested = normalizeText(input.requestedTemplateKey) as MethodologyTemplateKey
  if (requested in templates) return { key: requested, rationale: `按指定模板 ${requested} 匹配。` }

  const categoryText = [
    input.fundType,
    input.assetClass,
    input.strategyFamilyKey,
  ].map(normalizeText).join(' ').toLowerCase()
  const activePassiveText = normalizeText(input.activePassive).toLowerCase()

  const matched = (Object.entries(templates) as Array<[MethodologyTemplateKey, typeof templates[MethodologyTemplateKey]]>)
    .map(([key, template]) => ({
      key,
      categoryScore: [
        ...template.aliases,
        ...template.assetHints,
      ].reduce((sum, hint) => sum + (categoryText.includes(hint.toLowerCase()) ? 1 : 0), 0),
      activePassiveScore: template.activePassiveHints.reduce(
        (sum, hint) => sum + (activePassiveText.includes(hint.toLowerCase()) ? 1 : 0),
        0,
      ),
    }))
    .sort((left, right) => right.categoryScore - left.categoryScore || right.activePassiveScore - left.activePassiveScore)[0]

  if (matched && matched.categoryScore > 0) return { key: matched.key, rationale: `按基金类型、资产类别或策略族谱匹配 ${matched.key}，主被动信息仅用于同类匹配校验。` }
  return { key: null, rationale: '未识别到清晰基金分类，停止方法论匹配并要求补充分类证据。' }
}

export function unclassifiedMethodologyOutput(rationale: string): MethodologyConfigOutput {
  return {
    resolutionStatus: 'unclassified',
    templateKey: 'unclassified',
    templateName: '基金分类待确认',
    matchRationale: rationale,
    dimensions: [],
    hardGateDimensions: ['基金分类'],
    missingEvidenceFields: ['fund_classification'],
    readyForFormalReview: false,
    policy: {
      hardBoundary: '未确认基金分类时不选择任何评价模板；只输出分类证据缺口，不输出默认综合评分。',
      requiredFundTypes: ['active_equity', 'fixed_income', 'index_fund', 'money_market', 'qdii', 'fof', 'quant_fund'],
    },
  }
}

export const methodologyConfigTool: ResearchTool<MethodologyConfigInput, MethodologyConfigOutput> = {
  manifest: {
    name: toolName,
    version,
    domain: 'fund',
    purpose: '为主动权益、固收、指数、货币、QDII、FOF、量化基金选择差异化研究模板，输出评价维度、硬门槛和证据缺口。',
    inputSchema: 'MethodologyConfigInput',
    outputSchema: 'MethodologyConfigOutput',
    evidencePolicy: 'derived_metric',
    canRunBatch: true,
    sideEffects: ['none'],
    guardrails: [
      FUND_RESEARCH_GUARDRAILS.noTradingDirective,
      FUND_RESEARCH_GUARDRAILS.missingEvidenceBlocks,
      '不能用同一套评价维度覆盖所有基金类型；必须按策略、资产类别、主被动和产品结构切换方法论。',
      '方法论配置只决定基金研究证据口径，不生成申赎执行、资产配置或审批动作。',
    ],
  },
  run(input) {
    const match = inferTemplate(input)
    if (!match.key) {
      const output = unclassifiedMethodologyOutput(match.rationale)
      return createToolResult(toolName, version, input, output, {
        ok: false,
        hardBlocks: ['基金分类证据不足，不能选择评价方法。'],
        evidence: [],
        gaps: [{
          key: 'methodology-config:unclassified:fund_classification',
          label: '基金分类待补',
          severity: 'hard_block',
          subjectId: normalizeText(input.strategyFamilyKey) || normalizeText(input.fundType) || undefined,
          reason: '需要资产类别、策略族谱、主动/被动或跟踪标的等分类证据。',
          requiredBeforeFormalReview: true,
        }],
        nextActions: [{
          key: 'methodology-config:unclassified:fund_classification',
          label: '补齐基金分类证据',
          href: '/analysis',
          priority: 'high',
          reason: '分类是选择类别专属评价方法的硬门禁。',
        }],
      })
    }
    const template = templates[match.key]
    const evidence = normalizedEvidence(input)
    const missingEvidenceFields = Array.from(new Set(
      template.dimensions.flatMap((dimension) => dimension.evidenceFields.filter((field) => !evidence.has(field.toLowerCase()))),
    ))
    const hardGateDimensions = template.dimensions.filter((dimension) => dimension.hardGate).map((dimension) => dimension.name)
    const hardGateMissing = template.dimensions
      .filter((dimension) => dimension.hardGate)
      .flatMap((dimension) => dimension.evidenceFields.filter((field) => !evidence.has(field.toLowerCase())))
    const output: MethodologyConfigOutput = {
      resolutionStatus: 'matched',
      templateKey: match.key,
      templateName: template.name,
      matchRationale: match.rationale,
      dimensions: template.dimensions,
      hardGateDimensions,
      missingEvidenceFields,
      readyForFormalReview: hardGateMissing.length === 0,
      policy: {
        hardBoundary: '研究模板只定义基金研究评价口径；证据不完整时只能输出补证清单和研究假设，不输出申赎执行、资产配置或审批流程。',
        requiredFundTypes: ['active_equity', 'fixed_income', 'index_fund', 'money_market', 'qdii', 'fof', 'quant_fund'],
      },
    }

    return createToolResult(toolName, version, input, output, {
      ok: output.readyForFormalReview,
      hardBlocks: hardGateMissing.length ? [`${template.name}硬门槛证据未齐：${Array.from(new Set(hardGateMissing)).join('、')}`] : [],
      evidence: [
        {
          id: `methodology-config:${match.key}`,
          label: `${template.name} 方法论配置`,
          source: 'methodology_config_tool',
          freshness: 'derived',
          subjectId: normalizeText(input.strategyFamilyKey) || normalizeText(input.fundType) || match.key,
          note: `${match.rationale} 硬门槛：${hardGateDimensions.join('、')}。`,
        },
      ],
      gaps: missingEvidenceFields.map((field) => ({
        key: `methodology-config:${match.key}:${field}`,
        label: `${field}待补`,
        severity: hardGateMissing.includes(field) ? 'hard_block' : 'verify_first',
        subjectId: normalizeText(input.strategyFamilyKey) || undefined,
        reason: `${field}是${template.name}的评价证据字段。`,
        requiredBeforeFormalReview: hardGateMissing.includes(field),
      })),
      nextActions: missingEvidenceFields.map((field) => ({
        key: `methodology-config:${match.key}:${field}`,
        label: `补齐${field}`,
        href: '/analysis',
        priority: hardGateMissing.includes(field) ? 'high' : 'medium',
        reason: `${template.name}需要该字段支撑对应研究维度。`,
      })),
    })
  },
}
