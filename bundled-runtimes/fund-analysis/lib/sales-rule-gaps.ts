import { backendApiBaseUrl } from '@/lib/backend-api'
import { getMergedSalesRulesByWindCodes, type SalesRule } from '@/lib/sales-rules'
import { salesRuleGateTool, type SalesRuleGateOutput } from '@/lib/research-platform/tools'
import { materialEvidenceHref } from '@/lib/research-platform/routes'

type PoolMember = {
  id?: string
  fund_id?: string
  fundId?: string
  fund_wind_code?: string
  fundWindCode?: string
  fund_name?: string
  fundName?: string
  fund_type?: string
  fundType?: string
  fund_total_asset?: number | string | null
  fundTotalAsset?: number | string | null
  status?: string
  evidence?: {
    buyEvidence?: {
      requiredMissingCount?: number
      completenessScore?: number
      conclusion?: string
    }
    investorContext?: {
      profileLabel?: string
      horizonLabel?: string
      purchasePlanLabel?: string
    }
    purchaseGate?: {
      label?: string
      cautionFlags?: string[]
      hardBlocks?: string[]
    }
  } | null
}

export type SalesRuleGap = {
  memberId?: string
  windCode: string
  fundName: string
  fundType: string
  totalAsset: number | string | null
  status: string
  priority: 'high' | 'medium' | 'low'
  missingItems: string[]
  missingCount: number
  evidenceMissingCount: number
  evidenceScore: number | null
  purchaseGateLabel: string
  investorContext: PoolMember['evidence'] extends infer Evidence
    ? Evidence extends { investorContext?: infer Context }
      ? Context | null
      : null
    : null
  ruleUpdatedAt: string | null
  ruleSourceUpdatedAt: string | null
  riskLevel: string | null
  riskLevelSourceBacked: boolean
  riskLevelEvidenceStatus: 'verified' | 'missing' | 'unsourced' | 'stale'
  riskLevelEvidenceLabel: string
  riskLevelEvidenceDetail: string
  executionAmountGate: SalesRuleExecutionAmountGate
  nextAction: string
}

export type SalesRuleGapPurchasePlan = 'lump_sum' | 'sip'

export type SalesRuleGapOptions = {
  purchasePlan?: SalesRuleGapPurchasePlan | null
  plannedAmount?: number | null
}

export type SalesRuleExecutionAmountGate = {
  plannedAmount: number | null
  status: 'pass' | 'blocked' | 'unknown'
  label: string
  detail: string
  advice: string
  actionLabel: string
  shortfallAmount: number | null
  suggestedAmount: number | null
  minPurchaseAmount: number | null
  minSipAmount: number | null
  dailyLimitAmount: number | null
}

export type SalesRuleGapsPayload = {
  source: string
  status: string
  totalMembers: number
  gapCount: number
  gaps: SalesRuleGap[]
  rules: Array<{
    windCode: string
    riskLevel: string | null
    riskLevelSourceBacked: boolean
    riskLevelEvidenceStatus: SalesRuleGap['riskLevelEvidenceStatus']
    riskLevelEvidenceLabel: string
    missingItems: string[]
    missingCount: number
    ruleUpdatedAt: string | null
    ruleSourceUpdatedAt: string | null
    executionAmountGate: SalesRuleExecutionAmountGate
  }>
  summary: {
    high: number
    medium: number
    low: number
  }
}

function normalizePurchasePlan(value: SalesRuleGapOptions['purchasePlan']) {
  return value === 'lump_sum' || value === 'sip' ? value : null
}

function normalizeWindCodes(windCodes: string[]) {
  return Array.from(
    new Set(
      windCodes
        .flatMap((code) => String(code || '').split(','))
        .map((code) => code.trim().toUpperCase())
        .filter((code) => /^[0-9A-Z]{6,12}\.(OF|SH|SZ|BJ)$/i.test(code)),
    ),
  )
}

const validPoolStatuses = new Set(['candidate', 'watch', 'core', 'rejected'])

function normalizePoolStatuses(status: string) {
  const statuses = String(status || 'candidate')
    .split(',')
    .map((item) => item.trim())
    .filter((item) => validPoolStatuses.has(item))
  return statuses.length ? Array.from(new Set(statuses)) : ['candidate']
}

function runSalesRuleGate(
  windCode: string,
  fundName: string,
  rule: SalesRule | null,
  options: SalesRuleGapOptions = {},
): SalesRuleGateOutput {
  const gate = salesRuleGateTool.run({
    windCode,
    fundName,
    rule,
    purchasePlan: normalizePurchasePlan(options.purchasePlan),
    plannedAmount: options.plannedAmount ?? null,
    actionHref: materialEvidenceHref({ codes: windCode }),
  })
  if (!gate.data) throw new Error(`销售规则门禁无输出：${windCode}`)
  return gate.data
}

function priorityOf(missingItems: string[], evidenceMissingCount: number): SalesRuleGap['priority'] {
  if (missingItems.includes('销售规则整条待补')) return 'high'
  if (missingItems.includes('销售风险等级') || missingItems.includes('限购金额') || missingItems.includes('销售服务费（30天来源背书）')) return 'high'
  if (missingItems.some((item) => item.startsWith('计划金额执行门禁'))) return 'high'
  if (evidenceMissingCount >= 4) return 'high'
  if (missingItems.length >= 3) return 'medium'
  return 'low'
}

async function fetchPoolMembers(status: string, limit: number) {
  const statuses = normalizePoolStatuses(status)
  const poolsResponse = await fetch(`${backendApiBaseUrl}/api/fund-pools`, { cache: 'no-store' })
  const poolsPayload = await poolsResponse.json().catch(() => ({}))
  if (!poolsResponse.ok) {
    throw new Error(poolsPayload.detail || poolsPayload.error || '读取研究清单失败')
  }

  const members: PoolMember[] = []
  const seenMemberIds = new Set<string>()
  for (const pool of poolsPayload.pools || []) {
    if (members.length >= limit) break
    const poolId = pool.id
    if (!poolId) continue
    for (const memberStatus of statuses) {
      if (members.length >= limit) break
      const membersResponse = await fetch(
        `${backendApiBaseUrl}/api/fund-pools/${encodeURIComponent(poolId)}/members?status=${encodeURIComponent(memberStatus)}`,
        { cache: 'no-store' },
      )
      const membersPayload = await membersResponse.json().catch(() => ({}))
      if (!membersResponse.ok) continue
      for (const member of membersPayload.members || []) {
        const memberKey = String(member.id || `${poolId}:${member.fund_wind_code || member.fundWindCode || member.fund_id || member.fundId || members.length}`)
        if (seenMemberIds.has(memberKey)) continue
        seenMemberIds.add(memberKey)
        members.push(member)
        if (members.length >= limit) break
      }
    }
  }
  return members.slice(0, limit)
}

async function fetchFundSnapshot(windCode: string) {
  try {
    const response = await fetch(`${backendApiBaseUrl}/api/funds/${encodeURIComponent(windCode)}`, {
      cache: 'no-store',
    })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(payload.detail || payload.error || '读取基金详情失败')
    return {
      windCode,
      fundName: payload.name || payload.fund_name || windCode,
      fundType: payload.type || payload.fund_type || '',
      totalAsset: payload.total_asset ?? payload.totalAsset ?? null,
    }
  } catch {
    return {
      windCode,
      fundName: windCode,
      fundType: '',
      totalAsset: null,
    }
  }
}

export async function getSalesRuleGapsForCodes(windCodes: string[], limit = 100, options: SalesRuleGapOptions = {}): Promise<SalesRuleGapsPayload> {
  const safeLimit = Math.max(1, Math.min(Number(limit) || 100, 300))
  const codes = normalizeWindCodes(windCodes).slice(0, safeLimit)
  const [rules, fundSnapshots] = await Promise.all([
    getMergedSalesRulesByWindCodes(codes),
    Promise.all(codes.map(fetchFundSnapshot)),
  ])
  const snapshotByCode = new Map(fundSnapshots.map((snapshot) => [snapshot.windCode, snapshot]))
  const ruleSummaries = codes.map((windCode) => {
    const rule = rules.get(windCode) || null
    const snapshot = snapshotByCode.get(windCode)
    const gate = runSalesRuleGate(windCode, snapshot?.fundName || windCode, rule, options)
    const missingItems = gate.missingItems
    const executionAmountGate = gate.executionAmountGate
    return {
      windCode,
      riskLevel: gate.riskEvidence.riskLevel || rule?.riskLevel || null,
      riskLevelSourceBacked: gate.riskEvidence.sourceBacked,
      riskLevelEvidenceStatus: gate.riskEvidence.status,
      riskLevelEvidenceLabel: gate.riskEvidence.label,
      riskLevelEvidenceDetail: gate.riskEvidence.detail,
      executionAmountGate,
      missingItems,
      missingCount: missingItems.length,
      ruleUpdatedAt: rule?.updatedAt || null,
      ruleSourceUpdatedAt: rule?.sourceUpdatedAt || null,
    }
  })

  const gaps = codes.map((windCode) => {
    const rule = rules.get(windCode) || null
    const snapshot = snapshotByCode.get(windCode)
    const gate = runSalesRuleGate(windCode, snapshot?.fundName || windCode, rule, options)
    const missingItems = gate.missingItems
    const executionAmountGate = gate.executionAmountGate
    const priority = priorityOf(missingItems, missingItems.length)
    return {
      windCode,
      fundName: snapshot?.fundName || windCode,
      fundType: snapshot?.fundType || '',
      totalAsset: snapshot?.totalAsset ?? null,
      status: 'explicit_codes',
      priority,
      missingItems,
      missingCount: missingItems.length,
      evidenceMissingCount: missingItems.length,
      evidenceScore: rule ? Math.max(0, 100 - missingItems.length * 12) : null,
      purchaseGateLabel: missingItems.length ? '代码级研究复核证据待补' : '销售规则相对完整',
      investorContext: null,
      ruleUpdatedAt: rule?.updatedAt || null,
      ruleSourceUpdatedAt: rule?.sourceUpdatedAt || null,
      riskLevel: gate.riskEvidence.riskLevel || rule?.riskLevel || null,
      riskLevelSourceBacked: gate.riskEvidence.sourceBacked,
      riskLevelEvidenceStatus: gate.riskEvidence.status,
      riskLevelEvidenceLabel: gate.riskEvidence.label,
      riskLevelEvidenceDetail: gate.riskEvidence.detail,
      executionAmountGate,
      nextAction: gate.nextAction,
    }
  }).filter((item) => item.windCode && item.missingItems.length > 0)
    .sort((left, right) => {
      const priorityWeight = { high: 3, medium: 2, low: 1 }
      return priorityWeight[right.priority] - priorityWeight[left.priority]
        || right.missingCount - left.missingCount
    })

  return {
    source: 'explicit_codes_plus_local_sales_rules',
    status: 'explicit_codes',
    totalMembers: codes.length,
    gapCount: gaps.length,
    gaps,
    rules: ruleSummaries,
    summary: {
      high: gaps.filter((item) => item.priority === 'high').length,
      medium: gaps.filter((item) => item.priority === 'medium').length,
      low: gaps.filter((item) => item.priority === 'low').length,
    },
  }
}

export async function getSalesRuleGaps(status = 'candidate', limit = 100, options: SalesRuleGapOptions = {}): Promise<SalesRuleGapsPayload> {
  const safeLimit = Math.max(1, Math.min(Number(limit) || 100, 300))
  const statuses = normalizePoolStatuses(status)
  const members = await fetchPoolMembers(status, safeLimit)
  const codes = members
    .map((member) => member.fund_wind_code || member.fundWindCode || member.fund_id || member.fundId || '')
    .filter(Boolean)
  const rules = await getMergedSalesRulesByWindCodes(codes)
  const ruleSummaries = codes.map((windCode) => {
    const rule = rules.get(windCode) || null
    const gate = runSalesRuleGate(windCode, windCode, rule, options)
    const missingItems = gate.missingItems
    const executionAmountGate = gate.executionAmountGate
    return {
      windCode,
      riskLevel: gate.riskEvidence.riskLevel || rule?.riskLevel || null,
      riskLevelSourceBacked: gate.riskEvidence.sourceBacked,
      riskLevelEvidenceStatus: gate.riskEvidence.status,
      riskLevelEvidenceLabel: gate.riskEvidence.label,
      riskLevelEvidenceDetail: gate.riskEvidence.detail,
      executionAmountGate,
      missingItems,
      missingCount: missingItems.length,
      ruleUpdatedAt: rule?.updatedAt || null,
      ruleSourceUpdatedAt: rule?.sourceUpdatedAt || null,
    }
  })

  const gaps = members.map((member) => {
    const windCode = member.fund_wind_code || member.fundWindCode || member.fund_id || member.fundId || ''
    const rule = rules.get(windCode) || null
    const fundName = member.fund_name || member.fundName || windCode
    const gate = runSalesRuleGate(windCode, fundName, rule, options)
    const missingItems = gate.missingItems
    const executionAmountGate = gate.executionAmountGate
    const evidenceMissingCount = member.evidence?.buyEvidence?.requiredMissingCount ?? missingItems.length
    const priority = priorityOf(missingItems, evidenceMissingCount)
    return {
      memberId: member.id,
      windCode,
      fundName,
      fundType: member.fund_type || member.fundType || '',
      totalAsset: member.fund_total_asset ?? member.fundTotalAsset ?? null,
      status: member.status || status,
      priority,
      missingItems,
      missingCount: missingItems.length,
      evidenceMissingCount,
      evidenceScore: member.evidence?.buyEvidence?.completenessScore ?? null,
      purchaseGateLabel: member.evidence?.purchaseGate?.label || '研究闸门待核',
      investorContext: member.evidence?.investorContext || null,
      ruleUpdatedAt: rule?.updatedAt || null,
      ruleSourceUpdatedAt: rule?.sourceUpdatedAt || null,
      riskLevel: gate.riskEvidence.riskLevel || rule?.riskLevel || null,
      riskLevelSourceBacked: gate.riskEvidence.sourceBacked,
      riskLevelEvidenceStatus: gate.riskEvidence.status,
      riskLevelEvidenceLabel: gate.riskEvidence.label,
      riskLevelEvidenceDetail: gate.riskEvidence.detail,
      executionAmountGate,
      nextAction: gate.nextAction,
    }
  }).filter((item) => item.windCode && item.missingItems.length > 0)
    .sort((left, right) => {
      const priorityWeight = { high: 3, medium: 2, low: 1 }
      return priorityWeight[right.priority] - priorityWeight[left.priority]
        || right.missingCount - left.missingCount
    })

  return {
    source: statuses.length > 1
      ? 'candidate_watch_pool_plus_local_sales_rules'
      : `${statuses[0]}_pool_plus_local_sales_rules`,
    status: statuses.join(','),
    totalMembers: members.length,
    gapCount: gaps.length,
    gaps,
    rules: ruleSummaries,
    summary: {
      high: gaps.filter((item) => item.priority === 'high').length,
      medium: gaps.filter((item) => item.priority === 'medium').length,
      low: gaps.filter((item) => item.priority === 'low').length,
    },
  }
}
