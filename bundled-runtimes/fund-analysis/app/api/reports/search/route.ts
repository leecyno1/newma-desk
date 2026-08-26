import { NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'

type SearchRequest = {
  query?: string
  limit?: number
}

type SearchResult = {
  id: string
  title: string
  summary: string
  reportDate: string
  source: string
  tags: string[]
  managerId: string | null
  similarity: string
  targetId?: string
  targetType?: string
  reportType?: string
  reportTypeLabel?: string
  purchasePlan?: 'lump_sum' | 'sip'
  plannedAmount?: number | null
  actionHref?: string
  relatedCodes?: string[]
  decisionSummary?: {
    readyCount?: number
    verifyFirstCount?: number
    blockedCount?: number
    salesRuleGapCount?: number
    evidenceGrade?: string
    verdict?: string
    totalFunds?: number
    decisionFundName?: string
    decisionFundCode?: string
    decisionBasis?: string
    decisionReturn?: number | null
    decisionDrawdown?: number | null
    topPurchaseDecisionLabel?: string
    topPurchaseDecisionAction?: string
    topPurchaseDecisionReason?: string
    sourceDecisionCards?: Array<{
      windCode: string
      fundName: string
      label: string
      latestConclusion: string
      nextAction: string
      bullets: string[]
      hardBoundary: string
      reviewFreshnessStatus?: string
      reviewFreshnessLabel?: string
      reviewFreshnessDetail?: string
    }>
    replayEvidenceGateStatus?: string
    replayEvidenceGateLabel?: string
    replayEvidenceGateMissingEvidence?: string[]
    replayEvidenceGatePassCount?: number
    replayEvidenceGateVerifyCount?: number
  }
  currentSalesRuleGate?: {
    status: 'ready' | 'blocked' | 'unknown'
    missingCount: number | null
    missingItems: string[]
    actionHref: string
    source: string
    blockedFunds?: number
  }
  riskLevelGatePolicy?: {
    status: string
    label: string
    detail: string
    tone: 'emerald' | 'amber' | 'slate'
    requiresRegeneration: boolean
    effectiveDate: string
    signals?: string[]
  }
}

function textScore(query: string, fields: string[]) {
  const normalizedQuery = query.trim().toLowerCase()
  const text = fields.join(' ').toLowerCase()
  if (!normalizedQuery) return 0
  if (text.includes(normalizedQuery)) return 1
  const tokens = normalizedQuery.split(/\s+/u).filter(Boolean)
  if (tokens.length === 0) return 0
  const matched = tokens.filter((token) => text.includes(token)).length
  return matched / tokens.length
}

function sanitizeText(value: unknown, maxLength = 500) {
  return String(value || '')
    .replace(/[\u0000-\u001F\u007F-\u009F]/gu, ' ')
    .replace(/\s+/gu, ' ')
    .trim()
    .slice(0, maxLength)
}

function normalizeGeneratedReport(report: Record<string, unknown>, query: string): SearchResult {
  const tags = Array.isArray(report.tags) ? report.tags.map((tag) => sanitizeText(tag, 80)).filter(Boolean) : []
  const title = sanitizeText(report.title, 160)
  const summary = sanitizeText(report.summary || report.content, 500)
  const source = sanitizeText(report.source || '本地生成报告', 120)
  const reportTypeLabel = sanitizeText(report.reportTypeLabel, 120)
  const score = textScore(query, [title, summary, source, tags.join(' '), reportTypeLabel])
  const decisionSummary = report.decisionSummary && typeof report.decisionSummary === 'object'
    ? report.decisionSummary as SearchResult['decisionSummary']
    : undefined
  const currentSalesRuleGate = report.currentSalesRuleGate && typeof report.currentSalesRuleGate === 'object'
    ? report.currentSalesRuleGate as SearchResult['currentSalesRuleGate']
    : undefined
  const riskLevelGatePolicy = report.riskLevelGatePolicy && typeof report.riskLevelGatePolicy === 'object'
    ? report.riskLevelGatePolicy as SearchResult['riskLevelGatePolicy']
    : undefined
  return {
    id: String(report.id || ''),
    title,
    summary,
    reportDate: String(report.reportDate || report.createdAt || ''),
    source,
    tags,
    managerId: report.managerId ? String(report.managerId) : null,
    similarity: score.toFixed(4),
    targetId: report.targetId ? String(report.targetId) : '',
    targetType: report.targetType ? String(report.targetType) : '',
    reportType: report.reportType ? String(report.reportType) : '',
    reportTypeLabel,
    purchasePlan: report.purchasePlan === 'lump_sum' ? 'lump_sum' : report.purchasePlan === 'sip' ? 'sip' : undefined,
    plannedAmount: Number.isFinite(Number(report.plannedAmount)) && Number(report.plannedAmount) > 0 ? Number(report.plannedAmount) : null,
    actionHref: report.actionHref ? String(report.actionHref) : '',
    relatedCodes: Array.isArray(report.relatedCodes)
      ? report.relatedCodes.map((code) => String(code || '').trim().toUpperCase()).filter(Boolean)
      : [],
    decisionSummary,
    currentSalesRuleGate,
    riskLevelGatePolicy,
  }
}

function normalizeResearchReport(report: Record<string, unknown>, query: string): SearchResult {
  const tags = Array.isArray(report.tags) ? report.tags.map((tag) => sanitizeText(tag, 80)).filter(Boolean) : []
  const keyPoints = Array.isArray(report.key_points) ? report.key_points.map((point) => sanitizeText(point, 160)) : []
  const title = sanitizeText(report.title, 160)
  const summary = sanitizeText(report.summary, 500)
  const source = sanitizeText(report.source || '调研报告库', 120)
  const score = textScore(query, [title, summary, source, tags.join(' '), keyPoints.join(' ')])
  return {
    id: String(report.id || ''),
    title,
    summary,
    reportDate: String(report.report_date || report.created_at || ''),
    source,
    tags,
    managerId: report.manager_id ? String(report.manager_id) : null,
    similarity: score.toFixed(4),
  }
}

async function searchReports(query: string, limit: number, requestUrl: string) {
  const origin = new URL(requestUrl).origin
  const generatedUrl = new URL('/api/reports', origin)
  generatedUrl.searchParams.set('search', query)
  generatedUrl.searchParams.set('limit', String(Math.min(100, Math.max(limit, 20))))

  const researchUrl = new URL('/api/research-reports/', backendApiBaseUrl)
  researchUrl.searchParams.set('keyword', query)
  researchUrl.searchParams.set('page_size', String(Math.min(50, Math.max(limit, 20))))

  const [generatedResponse, researchResponse] = await Promise.all([
    fetch(generatedUrl, { cache: 'no-store' }),
    fetch(researchUrl, { cache: 'no-store' }),
  ])

  const generatedPayload = await generatedResponse.json().catch(() => ({}))
  const researchPayload = await researchResponse.json().catch(() => ({}))

  const generatedResults = generatedResponse.ok
    ? ((generatedPayload.data || []) as Record<string, unknown>[]).map((report) => normalizeGeneratedReport(report, query))
    : []
  const researchResults = researchResponse.ok
    ? ((researchPayload.data || []) as Record<string, unknown>[]).map((report) => normalizeResearchReport(report, query))
    : []

  return [...generatedResults, ...researchResults]
    .filter((report) => report.id && Number(report.similarity) > 0)
    .sort((left, right) => Number(right.similarity) - Number(left.similarity))
    .slice(0, limit)
}

export async function POST(request: Request) {
  try {
    const body: SearchRequest = await request.json()
    const query = (body.query || '').trim()
    const limit = Math.max(1, Math.min(50, Number(body.limit || 10)))

    if (!query) {
      return NextResponse.json({ error: '请提供搜索查询' }, { status: 400 })
    }

    const results = await searchReports(query, limit, request.url)
    return NextResponse.json({
      query: sanitizeText(query, 120),
      mode: 'local_full_text',
      results,
      count: results.length,
    })
  } catch (error) {
    console.error('报告搜索失败:', error)
    return NextResponse.json(
      { error: '报告搜索失败', details: error instanceof Error ? error.message : '未知错误' },
      { status: 500 },
    )
  }
}

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url)
    const query = (searchParams.get('q') || searchParams.get('query') || '').trim()
    const limit = Math.max(1, Math.min(50, Number(searchParams.get('limit') || 10)))
    if (!query) {
      return NextResponse.json({ error: '请提供搜索查询' }, { status: 400 })
    }
    const results = await searchReports(query, limit, request.url)
    return NextResponse.json({
      query: sanitizeText(query, 120),
      mode: 'local_full_text',
      results,
      count: results.length,
    })
  } catch (error) {
    console.error('报告搜索失败:', error)
    return NextResponse.json(
      { error: '报告搜索失败', details: error instanceof Error ? error.message : '未知错误' },
      { status: 500 },
    )
  }
}
