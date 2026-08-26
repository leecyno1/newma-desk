import { NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'
import { buildReportRiskLevelGatePolicy } from '@/lib/report-risk-level-gate-policy'
import { analysisEvidenceMetadata } from '@/lib/analysis-evidence-metadata'

const reportTypeLabel = (reportType: string | null | undefined) => {
  if (reportType === 'fund_evaluation_analysis') return '基金评价分析'
  if (reportType === 'fund_pool_shortlist_report') return '研究短名单报告'
  if (reportType === 'fund_pre_purchase_check') return '研究复核报告'
  if (reportType === 'fund_research_report') return '基金研究报告'
  if (reportType?.includes('manager')) return '基金经理研究报告'
  if (reportType?.includes('comparison')) return '对比研究报告'
  return '研究报告'
}

const cleanPreview = (content: string) =>
  content
    .replace(/^<!--[\s\S]*?-->\s*/u, '')
    .replace(/^好的[，,][\s\S]*?---\s*/u, '')
    .trim()

const asRecord = (value: unknown): Record<string, unknown> => {
  if (typeof value === 'string') {
    try {
      const parsed = JSON.parse(value)
      return parsed && typeof parsed === 'object' ? parsed : {}
    } catch {
      return {}
    }
  }
  return value && typeof value === 'object' ? value as Record<string, unknown> : {}
}

const asStringArray = (value: unknown) =>
  Array.isArray(value)
    ? value.map((item) => String(item || '').trim().toUpperCase()).filter(Boolean)
    : []

function reportCodes(report: Record<string, unknown>, dataSources: Record<string, unknown>) {
  const items = Array.isArray(dataSources.items) ? dataSources.items : []
  const members = Array.isArray(dataSources.members) ? dataSources.members : []
  const fund = asRecord(dataSources.fund)
  return Array.from(new Set([
    String(report.target_id || report.targetId || '').trim().toUpperCase(),
    String(fund.windCode || fund.wind_code || '').trim().toUpperCase(),
    ...asStringArray(dataSources.codes),
    ...items.map((item) => String(asRecord(item).windCode || '').trim().toUpperCase()),
    ...members.map((member) => String(asRecord(member).windCode || '').trim().toUpperCase()),
  ].filter((code) => /^[0-9A-Z]{6,12}\.(OF|SH|SZ|BJ)$/i.test(code))))
}

type MappedReport = {
  id: unknown
  reportType: string
  rawReportType: string
  targetType: unknown
  targetId: unknown
  compareId: null
  content: string
  metadata: Record<string, unknown>
  riskLevelGatePolicy: ReturnType<typeof buildReportRiskLevelGatePolicy>
  createdAt: unknown
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url)
  const page = parseInt(searchParams.get('page') || '1')
  const limit = parseInt(searchParams.get('limit') || '20')
  const targetType = searchParams.get('targetType')
  const reportType = searchParams.get('reportType')
  const search = (searchParams.get('search') || '').trim().toLowerCase()

  try {
    const backendUrl = new URL('/api/reports', backendApiBaseUrl)
    backendUrl.searchParams.set('page', String(page))
    backendUrl.searchParams.set('limit', String(limit))
    if (targetType) backendUrl.searchParams.set('target_type', targetType)
    if (reportType && reportType !== 'all') backendUrl.searchParams.set('report_type', reportType)

    const response = await fetch(backendUrl, { cache: 'no-store' })
    const payload = await response.json()
    if (!response.ok) {
      throw new Error(payload.detail || payload.error || '报告列表读取失败')
    }

    let reports: MappedReport[] = ((payload.reports || []) as Record<string, unknown>[]).map((report) => {
      const generationParams = asRecord(report.generation_params)
      const dataSources = asRecord(report.data_sources)
      const metadata = asRecord(report.metadata)
      const rawReportType = typeof report.report_type === 'string' ? report.report_type : ''
      const relatedCodes = reportCodes(report, dataSources)
      const content = cleanPreview(String(report.content || report.content_preview || ''))
      const riskLevelGatePolicy = buildReportRiskLevelGatePolicy({
        targetType: String(report.target_type || ''),
        reportType: rawReportType,
        relatedCodes,
        createdAt: String(report.created_at || ''),
        content: String(report.content || report.content_preview || ''),
        dataSources,
        generationParams,
      })
      return {
        id: report.id,
        reportType: reportTypeLabel(rawReportType),
        rawReportType,
        targetType: report.target_type,
        targetId: report.target_id,
        compareId: null,
        content,
        metadata: {
          ...generationParams,
          ...analysisEvidenceMetadata(dataSources),
          dataSource: dataSources.source ?? dataSources.data_source ?? null,
          mode:
            generationParams.mode ??
            dataSources.generation_mode ??
            metadata.mode ??
            null,
          model: generationParams.model ?? metadata.model ?? null,
          provider: generationParams.provider ?? metadata.provider ?? null,
        },
        riskLevelGatePolicy,
        createdAt: report.created_at,
      }
    })

    if (reportType && reportType !== 'all') {
      reports = reports.filter((report) => report.rawReportType === reportType)
    }
    if (search) {
      reports = reports.filter((report) =>
        [report.reportType, report.targetType, report.targetId, report.content, report.metadata?.mode, report.metadata?.provider]
          .join(' ')
          .toLowerCase()
          .includes(search),
      )
    }

    const total = (reportType && reportType !== 'all') || search ? reports.length : Number(payload.total || reports.length)
    return NextResponse.json({
      data: reports,
      pagination: {
        page,
        limit,
        total,
        totalPages: Math.max(1, Math.ceil(total / limit)),
      },
    })
  } catch (error) {
    console.error('读取研究报告列表失败:', error)
    return NextResponse.json(
      { error: error instanceof Error ? error.message : '报告列表读取失败' },
      { status: 500 },
    )
  }
}
