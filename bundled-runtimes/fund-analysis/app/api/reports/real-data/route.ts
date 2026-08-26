import { NextResponse } from 'next/server'
import postgres from 'postgres'
import { backendApiBaseUrl } from '@/lib/backend-api'
import { getSalesRuleGapsForCodes } from '@/lib/sales-rule-gaps'
import { materialEvidenceHref } from '@/lib/research-platform/routes'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

const MAX_CODES = 10

type RealDataReportRequest = {
  codes?: unknown
  includeResearch?: unknown
  reportDepth?: unknown
  purchasePlan?: unknown
  plannedAmount?: unknown
}

type PurchasePlan = 'lump_sum' | 'sip'

let sqlClient: postgres.Sql | null = null

function sql() {
  if (!sqlClient) {
    const databaseUrl = process.env.DATABASE_URL
    if (!databaseUrl) return null
    sqlClient = postgres(databaseUrl, {
      max: 2,
      idle_timeout: 20,
      connect_timeout: 10,
    })
  }
  return sqlClient
}

function normalizeCodes(value: unknown) {
  const rawCodes = Array.isArray(value)
    ? value
    : typeof value === 'string'
      ? value.split(/[\s,，;；]+/u)
      : []

  return Array.from(new Set(
    rawCodes
      .map((code) => String(code || '').trim().toUpperCase())
      .filter((code) => /^[0-9A-Z]{6,12}\.(OF|SH|SZ|BJ)$/i.test(code)),
  )).slice(0, MAX_CODES)
}

function normalizePurchasePlan(value: unknown): PurchasePlan {
  return value === 'lump_sum' ? 'lump_sum' : 'sip'
}

function defaultPlannedAmountForPlan(purchasePlan: PurchasePlan) {
  return purchasePlan === 'lump_sum' ? 10000 : 1000
}

function normalizePlannedAmount(value: unknown, purchasePlan: PurchasePlan) {
  const amount = Number(value)
  return Number.isFinite(amount) && amount > 0 ? Math.round(amount) : defaultPlannedAmountForPlan(purchasePlan)
}

function purchaseContextParams(purchasePlan: PurchasePlan, plannedAmount: number) {
  const params = new URLSearchParams({
    purchasePlan,
    plannedAmount: String(plannedAmount),
    [purchasePlan === 'lump_sum' ? 'lumpSumAmount' : 'monthlyAmount']: String(plannedAmount),
  })
  return params
}

function salesRuleNextActionForPlan(purchasePlan: PurchasePlan) {
  return purchasePlan === 'lump_sum'
    ? '先补齐申购、赎回、起购金额、限购和销售风险等级。'
    : '先补齐申购、赎回、定投、限购和销售风险等级。'
}

function safeDetail(payload: Record<string, unknown>, fallback: string) {
  const detail = payload.detail || payload.error || payload.message
  if (Array.isArray(detail)) return detail.join('；')
  return detail ? String(detail) : fallback
}

async function fetchBackendJson(path: string, init?: RequestInit) {
  const response = await fetch(`${backendApiBaseUrl}${path}`, {
    cache: 'no-store',
    ...init,
  })
  const payload = await response.json().catch(() => ({})) as Record<string, unknown>
  if (!response.ok) {
    throw new Error(safeDetail(payload, `${path} 请求失败`))
  }
  return payload
}

async function syncFund(windCode: string) {
  const payload = await fetchBackendJson(`/api/data-sync/funds/${encodeURIComponent(windCode)}`)
  return {
    managerCount: Number(payload.manager_count || 0),
    managerIds: Array.isArray(payload.manager_ids) ? payload.manager_ids.map(String) : [],
    warnings: Array.isArray(payload.warnings) ? payload.warnings.map(String) : [],
  }
}

async function generateReport(
  windCode: string,
  options: {
    includeResearch: boolean
    reportDepth: string
    purchasePlan: PurchasePlan
    plannedAmount: number
  },
) {
  const params = new URLSearchParams({
    include_research: String(options.includeResearch),
    report_depth: options.reportDepth,
    purchase_plan: options.purchasePlan,
    planned_amount: String(options.plannedAmount),
  })
  const payload = await fetchBackendJson(
    `/api/reports/fund/${encodeURIComponent(windCode)}?${params.toString()}`,
    { method: 'POST' },
  )
  const metadata = payload.metadata && typeof payload.metadata === 'object'
    ? payload.metadata as Record<string, unknown>
    : {}

  if (!payload.id) {
    throw new Error('报告已生成但未写入本地 PostgreSQL，不能算完成闭环')
  }

  return {
    id: String(payload.id),
    mode: String(metadata.mode || ''),
    provider: String(metadata.provider || ''),
    model: String(metadata.model || ''),
    wordCount: Number(metadata.word_count || 0),
    isModelGenerated: String(metadata.mode || '') === 'llm',
    purchasePlan: metadata.purchasePlan === 'lump_sum' ? 'lump_sum' : metadata.purchasePlan === 'sip' ? 'sip' : options.purchasePlan,
    plannedAmount: Number.isFinite(Number(metadata.plannedAmount)) && Number(metadata.plannedAmount) > 0 ? Number(metadata.plannedAmount) : options.plannedAmount,
    generationLabel: String(metadata.mode || '') === 'llm'
      ? '模型增强报告'
      : '本地证据报告',
  }
}

async function persistReportPurchasePlan(reportId: string, purchasePlan: PurchasePlan, plannedAmount: number) {
  const client = sql()
  if (!client) return false
  await client`
    UPDATE ai_analysis_reports
    SET
      generation_params = COALESCE(generation_params, '{}'::jsonb) || ${client.json({ purchasePlan, plannedAmount })}::jsonb,
      data_sources = jsonb_set(
        COALESCE(data_sources, '{}'::jsonb),
        '{summary}',
        COALESCE(data_sources->'summary', '{}'::jsonb) || ${client.json({ purchasePlan, plannedAmount })}::jsonb,
        true
      )
    WHERE id = ${reportId}
  `
  return true
}

async function getCurrentSalesRuleGate(windCode: string, purchasePlan: PurchasePlan, plannedAmount: number) {
  const payload = await getSalesRuleGapsForCodes([windCode], 1, { purchasePlan, plannedAmount })
  const gap = (payload.gaps || [])[0]
  const salesRuleParams = purchaseContextParams(purchasePlan, plannedAmount)
  salesRuleParams.set('codes', windCode)
  const salesRulesHref = materialEvidenceHref(salesRuleParams)
  if (!gap) {
    return {
      status: 'ready' as const,
      missingCount: 0,
      missingItems: [] as string[],
      actionHref: salesRulesHref,
      nextAction: '销售规则未检测到硬缺口；进入基金详情复核净值、费用、持仓和替代候选。',
      source: payload.source,
    }
  }
  return {
    status: 'blocked' as const,
    missingCount: gap.missingCount,
    missingItems: gap.missingItems,
    actionHref: salesRulesHref,
    nextAction: gap.nextAction || salesRuleNextActionForPlan(purchasePlan),
    source: payload.source,
  }
}

function buildBuyBeforeAction(windCode: string, reportId: string, purchasePlan: PurchasePlan, plannedAmount: number, gate: Awaited<ReturnType<typeof getCurrentSalesRuleGate>>) {
  if (gate.status === 'blocked') {
    return {
      status: '补证后再判断',
      label: '先补销售规则',
      href: `${gate.actionHref}&returnTo=${encodeURIComponent(`/reports/${reportId}`)}`,
      detail: `真实数据报告已保存，但销售规则仍缺 ${gate.missingCount} 项；补齐前只能作为研究观察，不能进入正式研究候选。`,
    }
  }
  return {
    status: '可进入研究复核',
    label: '进入基金详情',
    href: `/funds/${encodeURIComponent(windCode)}?profile=balanced&horizon=1to3y&${purchaseContextParams(purchasePlan, plannedAmount).toString()}`,
    detail: '真实数据已同步且销售规则未检测到硬缺口；继续复核净值回放、费用、持仓暴露和替代候选。',
  }
}

export async function POST(request: Request) {
  try {
    const body = await request.json().catch(() => ({})) as RealDataReportRequest
    const codes = normalizeCodes(body.codes)
    const purchasePlan = normalizePurchasePlan(body.purchasePlan)
    const plannedAmount = normalizePlannedAmount(body.plannedAmount, purchasePlan)
    if (!codes.length) {
      return NextResponse.json({ error: '请提供有效基金代码，例如 519674.OF' }, { status: 400 })
    }

    const health = await fetchBackendJson('/api/health')
    if (health.mock_mode) {
      return NextResponse.json({
        error: '后端当前仍是 Mock 模式，请配置 TUSHARE_TOKEN 并重启后端后再生成真实报告。',
        dataSource: health.data_source || 'unknown',
      }, { status: 409 })
    }

    const options = {
      includeResearch: Boolean(body.includeResearch),
      reportDepth: typeof body.reportDepth === 'string' && body.reportDepth.trim()
        ? body.reportDepth.trim()
        : 'standard',
      purchasePlan,
      plannedAmount,
    }

    const results = []
    for (const windCode of codes) {
      try {
        const sync = await syncFund(windCode)
        const report = await generateReport(windCode, options)
        await persistReportPurchasePlan(report.id, purchasePlan, plannedAmount)
        const currentSalesRuleGate = await getCurrentSalesRuleGate(windCode, purchasePlan, plannedAmount)
        const buyBeforeAction = buildBuyBeforeAction(windCode, report.id, purchasePlan, plannedAmount, currentSalesRuleGate)
        results.push({
          ok: true,
          windCode,
          purchasePlan,
          plannedAmount,
          sync,
          report,
          currentSalesRuleGate,
          buyBeforeAction,
          reportHref: `/reports/${encodeURIComponent(report.id)}`,
        })
      } catch (error) {
        results.push({
          ok: false,
          windCode,
          error: error instanceof Error ? error.message : '真实报告生成失败',
        })
      }
    }

    const failedCount = results.filter((item) => !item.ok).length
    return NextResponse.json({
      success: failedCount === 0,
      source: 'tushare_to_postgres_to_local_fund_report',
      dataSource: health.data_source || 'tushare',
      mockMode: Boolean(health.mock_mode),
      purchasePlan,
      plannedAmount,
      total: results.length,
      savedCount: results.length - failedCount,
      failedCount,
      results,
      timestamp: new Date().toISOString(),
    }, { status: failedCount ? 207 : 200 })
  } catch (error) {
    console.error('真实数据报告生成失败:', error)
    return NextResponse.json(
      { error: error instanceof Error ? error.message : '真实数据报告生成失败' },
      { status: 500 },
    )
  }
}
