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

const targetTypeLabel = (targetType: string | null | undefined) => {
  if (targetType === 'fund') return '基金'
  if (targetType === 'fund_pool') return '研究清单'
  if (targetType === 'manager') return '基金经理'
  return '研究对象'
}

const cleanReportContent = (content: string) =>
  content
    .replace(/^<!--[\s\S]*?-->\s*/u, '')
    .replace(/^好的[，,][\s\S]*?---\s*/u, '')
    .trim()

const asRecord = (value: unknown): Record<string, unknown> => {
  if (typeof value === 'string') {
    try {
      const parsed = JSON.parse(value)
      return parsed && typeof parsed === 'object' ? parsed as Record<string, unknown> : {}
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

function reportCodes(record: Record<string, unknown>, dataSources: Record<string, unknown>) {
  const items = Array.isArray(dataSources.items) ? dataSources.items : []
  const members = Array.isArray(dataSources.members) ? dataSources.members : []
  const fund = asRecord(dataSources.fund)
  return Array.from(new Set([
    String(record.target_id || record.targetId || '').trim().toUpperCase(),
    String(fund.windCode || fund.wind_code || '').trim().toUpperCase(),
    ...asStringArray(dataSources.codes),
    ...items.map((item) => String(asRecord(item).windCode || '').trim().toUpperCase()),
    ...members.map((member) => String(asRecord(member).windCode || '').trim().toUpperCase()),
  ].filter((code) => /^[0-9A-Z]{6,12}\.(OF|SH|SZ|BJ)$/i.test(code))))
}

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params
    const response = await fetch(`${backendApiBaseUrl}/api/reports/${encodeURIComponent(id)}`, {
      cache: 'no-store',
    })
    const payload = await response.json().catch(() => ({}))

    if (!response.ok) {
      return NextResponse.json(
        { error: payload.detail || payload.error || '分析报告不存在或暂时不可用' },
        { status: response.status }
      )
    }

    const timelineResponse = await fetch(
      `${backendApiBaseUrl}/api/reports/${encodeURIComponent(id)}/timeline`,
      { cache: 'no-store' },
    ).catch(() => null)
    const timeline = timelineResponse?.ok
      ? await timelineResponse.json().catch(() => null)
      : null

    const generationParams = asRecord(payload.generation_params ?? payload.metadata)
    const dataSources = asRecord(payload.data_sources)
    const codes = Array.isArray(dataSources.codes) ? dataSources.codes.map(String).filter(Boolean) : []
    const targetType = payload.target_type ?? payload.targetType ?? 'fund'
    const reportType = payload.report_type ?? payload.reportType
    const content = cleanReportContent(payload.content ?? '')
    const riskLevelGatePolicy = buildReportRiskLevelGatePolicy({
      targetType: String(targetType || ''),
      reportType: String(reportType || ''),
      relatedCodes: reportCodes(payload, dataSources),
      createdAt: String(payload.created_at ?? payload.createdAt ?? ''),
      content: String(payload.content || ''),
      dataSources,
      generationParams,
    })
    return NextResponse.json({
      id: payload.id,
      reportType: reportTypeLabel(reportType),
      targetType,
      targetTypeLabel: targetTypeLabel(targetType),
      targetId: payload.target_id ?? payload.targetId ?? '',
      compareId: payload.compare_id ?? payload.compareId ?? null,
      content,
      prompt: payload.prompt ?? '',
      riskLevelGatePolicy,
      metadata: {
        ...generationParams,
        ...analysisEvidenceMetadata(dataSources),
        dataSources,
        model: generationParams.model ?? generationParams.llmModel ?? '未知模型',
        llmModel: generationParams.model ?? generationParams.llmModel ?? '未知模型',
        generatedAt: payload.created_at ?? payload.createdAt ?? generationParams.generatedAt ?? null,
        includeReports: Array.isArray(payload.research_reports_used) && payload.research_reports_used.length > 0,
        reportsCount: Array.isArray(payload.research_reports_used) ? payload.research_reports_used.length : 0,
        codes,
      },
      timeline,
      createdAt: payload.created_at ?? payload.createdAt ?? null,
    })
  } catch (error) {
    console.error('获取分析报告失败:', error)
    return NextResponse.json({ error: '获取分析报告失败' }, { status: 500 })
  }
}

export async function DELETE() {
  return NextResponse.json(
    { error: '分析报告持久化暂未启用' },
    { status: 405 }
  )
}
