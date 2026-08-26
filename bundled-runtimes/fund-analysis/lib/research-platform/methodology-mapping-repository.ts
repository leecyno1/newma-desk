import postgres from 'postgres'
import {
  methodologyConfigTool,
  unclassifiedMethodologyOutput,
  type MethodologyConfigInput,
  type MethodologyConfigOutput,
  type MethodologyDimension,
  type MethodologyTemplateKey,
} from './tools'

type JsonRecord = Record<string, unknown>

type MethodologyTemplateRow = {
  id: string
  key: string
  name: string
  fund_type: string
  asset_class: string | null
  active_passive: string | null
  description: string | null
  required_evidence: unknown
  benchmark_policy: unknown
  peer_policy: unknown
  attribution_policy: unknown
  holding_policy: unknown
  manager_policy: unknown
  company_policy: unknown
  source: string
  version: string
  is_active: boolean
  created_at: string
  updated_at: string
}

type MethodologyDimensionRow = {
  id: string
  template_id: string
  dimension_key: string
  name: string
  weight: string | number | null
  evidence_fields: string[] | null
  calculation_policy: unknown
  hard_gate: boolean
  display_order: number
  created_at: string
  updated_at: string
}

type MethodologyMappingRow = {
  id: string
  template_id: string
  strategy_family_id: string | null
  fund_type: string | null
  asset_class: string | null
  active_passive: string | null
  match_rules: unknown
  priority: number
  source: string
  created_at: string
  updated_at: string
}

export type MethodologyMappingRepositoryData = {
  templates: MethodologyTemplateRow[]
  dimensions: MethodologyDimensionRow[]
  mappings: MethodologyMappingRow[]
  loadedAt: string
  source: string
}

const supportedMethodologyTemplateKeys: MethodologyTemplateKey[] = [
  'active_equity',
  'fixed_income',
  'index_fund',
  'money_market',
  'qdii',
  'fof',
  'quant_fund',
]

let sqlClient: postgres.Sql | null = null
let repositoryPromise: Promise<MethodologyMappingRepositoryData> | null = null

function normalizeText(value: unknown) {
  return String(value ?? '').trim().toLowerCase()
}

function asRecord(value: unknown): JsonRecord {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as JsonRecord : {}
}

function asStringArray(value: unknown) {
  return Array.isArray(value) ? value.map((item) => String(item || '').trim()).filter(Boolean) : []
}

function asNumber(value: unknown) {
  if (value === null || value === undefined || value === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function scoreTextMatch(text: string, candidates: string[]) {
  return candidates.reduce((sum, candidate) => sum + (candidate && text.includes(normalizeText(candidate)) ? 1 : 0), 0)
}

function sql() {
  if (!sqlClient) {
    const databaseUrl = process.env.DATABASE_URL
    if (!databaseUrl) throw new Error('DATABASE_URL 未配置，无法读取方法论映射')
    sqlClient = postgres(databaseUrl, { max: 1 })
  }
  return sqlClient
}

function fallbackOutputForKey(key: MethodologyTemplateKey): MethodologyConfigOutput {
  const result = methodologyConfigTool.run({
    requestedTemplateKey: key,
    fundType: key,
    assetClass: key,
    activePassive: 'active',
    availableEvidence: ['asset_class', 'strategy_type'],
  })
  return result.data || {
    resolutionStatus: 'matched',
    templateKey: key,
    templateName: '研究模板待识别',
    matchRationale: '默认模板回退',
    dimensions: [],
    hardGateDimensions: [],
    missingEvidenceFields: [],
    readyForFormalReview: false,
    policy: {
      hardBoundary: '方法论模板只决定研究口径；证据不完整时只能输出补证方向，不输出申赎执行、资产配置或审批动作。',
      requiredFundTypes: supportedMethodologyTemplateKeys,
    },
  }
}

function buildFallbackRepository(): MethodologyMappingRepositoryData {
  return {
    templates: supportedMethodologyTemplateKeys.map((key) => {
      const output = fallbackOutputForKey(key)
      return {
        id: key,
        key,
        name: output.templateName,
        fund_type: key,
        asset_class: null,
        active_passive: null,
        description: output.policy.hardBoundary,
        required_evidence: output.missingEvidenceFields,
        benchmark_policy: null,
        peer_policy: null,
        attribution_policy: null,
        holding_policy: null,
        manager_policy: null,
        company_policy: null,
        source: 'fallback_tool',
        version: '1.0.0',
        is_active: true,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      }
    }),
    dimensions: [],
    mappings: [],
    loadedAt: new Date().toISOString(),
    source: 'fallback_tool',
  }
}

function templateFromRow(row: MethodologyTemplateRow) {
  return {
    key: row.key as MethodologyTemplateKey,
    name: row.name,
    text: [
      row.key,
      row.name,
      row.fund_type,
      row.asset_class,
      row.active_passive,
      row.description,
    ].map(normalizeText).join(' '),
  }
}

function matchMethodologyTemplateFromRows(
  input: MethodologyConfigInput,
  repository: MethodologyMappingRepositoryData,
) {
  const requestedKey = normalizeText(input.requestedTemplateKey)
  const templates = repository.templates.filter((row) => row.is_active !== false)
  const mappings = repository.mappings.slice().sort((left, right) => left.priority - right.priority)
  const categoryText = [
    input.fundType,
    input.assetClass,
    input.strategyFamilyKey,
  ].map(normalizeText).join(' ')
  const activePassiveText = normalizeText(input.activePassive)

  const requestedMatch = requestedKey
    ? templates.find((template) => template.key === requestedKey)
    : null
  if (requestedMatch) {
    return {
      template: requestedMatch,
      rationale: `按指定模板 ${requestedMatch.key} 匹配。`,
    }
  }

  const mappingCandidates = mappings
    .map((mapping) => {
      const template = templates.find((row) => row.id === mapping.template_id || row.key === mapping.template_id)
      if (!template) return null
      const rules = asRecord(mapping.match_rules)
      const aliases = [
        template.key,
        template.name,
        template.fund_type,
        template.asset_class || '',
        ...asStringArray(rules.aliases),
        String(rules.strategyFamilyKey || rules.strategy_family_key || ''),
        String(rules.fundType || rules.fund_type || mapping.fund_type || ''),
        String(rules.assetClass || rules.asset_class || mapping.asset_class || ''),
      ].filter(Boolean)
      const activePassiveAliases = [
        template.active_passive || '',
        String(rules.activePassive || rules.active_passive || mapping.active_passive || ''),
      ].filter(Boolean)
      return {
        template,
        categoryScore: scoreTextMatch(categoryText, aliases),
        activePassiveScore: scoreTextMatch(activePassiveText, activePassiveAliases),
        priority: mapping.priority,
      }
    })
    .filter((item): item is {
      template: MethodologyTemplateRow
      categoryScore: number
      activePassiveScore: number
      priority: number
    } => item !== null)
    .sort((left, right) => (
      right.categoryScore - left.categoryScore
      || right.activePassiveScore - left.activePassiveScore
      || left.priority - right.priority
    ))

  if (mappingCandidates[0] && mappingCandidates[0].categoryScore > 0) {
    return {
      template: mappingCandidates[0].template,
      rationale: `按数据库分类映射匹配 ${mappingCandidates[0].template.key}，主被动信息仅用于同类校验。`,
    }
  }

  const rowCandidates = templates
    .map((template) => ({
      template,
      score: scoreTextMatch(categoryText, [
        template.key,
        template.name,
        template.fund_type,
        template.asset_class || '',
      ]),
    }))
    .sort((left, right) => right.score - left.score)

  if (rowCandidates[0] && rowCandidates[0].score > 0) {
    return {
      template: rowCandidates[0].template,
      rationale: `按数据库模板字段匹配 ${rowCandidates[0].template.key}。`,
    }
  }

  return {
    template: null,
    rationale: '未识别到数据库分类映射，停止方法论匹配并要求补充分类证据。',
  }
}

function dimensionsForTemplate(repository: MethodologyMappingRepositoryData, templateId: string) {
  return repository.dimensions
    .filter((row) => row.template_id === templateId)
    .sort((left, right) => left.display_order - right.display_order)
    .map((row) => ({
      key: row.dimension_key,
      name: row.name,
      weight: asNumber(row.weight) ?? 0,
      hardGate: Boolean(row.hard_gate),
      evidenceFields: asStringArray(row.evidence_fields),
      reason: String(asRecord(row.calculation_policy).reason || asRecord(row.calculation_policy).note || `${row.name} 证据待补。`),
    }))
}

function resolveFromRepository(input: MethodologyConfigInput, repository: MethodologyMappingRepositoryData): MethodologyConfigOutput {
  const match = matchMethodologyTemplateFromRows(input, repository)
  if (!match.template) {
    return unclassifiedMethodologyOutput(match.rationale)
  }
  const templateKey = match.template.key as MethodologyTemplateKey
  if (!supportedMethodologyTemplateKeys.includes(templateKey)) {
    return unclassifiedMethodologyOutput(`数据库模板 ${match.template.key} 未纳入可审计方法论清单，停止评价。`)
  }
  const defaultOutput = fallbackOutputForKey(templateKey)
  const dimensions = dimensionsForTemplate(repository, match.template.id)
  const chosenDimensions = dimensions.length ? dimensions : defaultOutput.dimensions
  const evidence = new Set((Array.isArray(input.availableEvidence) ? input.availableEvidence : []).map((item) => normalizeText(item)).filter(Boolean))
  const missingEvidenceFields = Array.from(new Set(
    chosenDimensions.flatMap((dimension) => dimension.evidenceFields.filter((field) => !evidence.has(normalizeText(field)))),
  ))
  const hardGateDimensions = chosenDimensions.filter((dimension) => dimension.hardGate).map((dimension) => dimension.name)
  const hardGateMissing = chosenDimensions
    .filter((dimension) => dimension.hardGate)
    .flatMap((dimension) => dimension.evidenceFields.filter((field) => !evidence.has(normalizeText(field))))

  return {
    resolutionStatus: 'matched',
    templateKey,
    templateName: match.template.name,
    matchRationale: match.rationale,
    dimensions: chosenDimensions,
    hardGateDimensions,
    missingEvidenceFields,
    readyForFormalReview: hardGateMissing.length === 0,
    policy: {
      hardBoundary: String(match.template.description || defaultOutput.policy.hardBoundary || '方法论模板只决定研究口径；证据不完整时只能输出补证方向，不输出申赎执行、资产配置或审批动作。'),
      requiredFundTypes: supportedMethodologyTemplateKeys,
    },
  }
}

async function loadMethodologyMappingRepositoryInternal(): Promise<MethodologyMappingRepositoryData> {
  try {
    const database = sql()
    const [templates, dimensions, mappings] = await Promise.all([
      database<MethodologyTemplateRow[]>`
        SELECT
          id,
          key,
          name,
          fund_type,
          asset_class,
          active_passive,
          description,
          required_evidence,
          benchmark_policy,
          peer_policy,
          attribution_policy,
          holding_policy,
          manager_policy,
          company_policy,
          source,
          version,
          is_active,
          created_at::text,
          updated_at::text
        FROM research_methodology_templates
        ORDER BY updated_at DESC, key ASC
      `,
      database<MethodologyDimensionRow[]>`
        SELECT
          id,
          template_id,
          dimension_key,
          name,
          weight::text,
          evidence_fields,
          calculation_policy,
          hard_gate,
          display_order,
          created_at::text,
          updated_at::text
        FROM research_methodology_dimensions
        ORDER BY template_id ASC, display_order ASC, dimension_key ASC
      `,
      database<MethodologyMappingRow[]>`
        SELECT
          id,
          template_id,
          strategy_family_id,
          fund_type,
          asset_class,
          active_passive,
          match_rules,
          priority,
          source,
          created_at::text,
          updated_at::text
        FROM research_methodology_mappings
        ORDER BY priority ASC, updated_at DESC
      `,
    ])
    return {
      templates,
      dimensions,
      mappings,
      loadedAt: new Date().toISOString(),
      source: 'database',
    }
  } catch {
    return buildFallbackRepository()
  }
}

export async function loadMethodologyMappingRepository(forceRefresh = false) {
  if (!forceRefresh && repositoryPromise) return repositoryPromise
  repositoryPromise = loadMethodologyMappingRepositoryInternal()
  return repositoryPromise
}

export function resolveMethodologyConfigFromDataSync(
  input: MethodologyConfigInput,
  repository: MethodologyMappingRepositoryData | null | undefined = null,
): MethodologyConfigOutput {
  if (!repository || !repository.templates.length) {
    const fallback = methodologyConfigTool.run(input)
    return fallback.data || unclassifiedMethodologyOutput('方法论数据不可用，且无法确认基金分类。')
  }
  return resolveFromRepository(input, repository)
}

export async function resolveMethodologyConfigFromData(
  input: MethodologyConfigInput,
  repository?: MethodologyMappingRepositoryData | null,
): Promise<MethodologyConfigOutput> {
  const resolvedRepository = repository || await loadMethodologyMappingRepository()
  return resolveMethodologyConfigFromDataSync(input, resolvedRepository)
}
