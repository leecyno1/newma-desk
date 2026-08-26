import { normalizeBuyBeforeDecisionSummary } from '@/lib/report-buy-before-decision'
import { buildReportRiskLevelGatePolicy } from '@/lib/report-risk-level-gate-policy'

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

export function normalizeFundReports(reports: unknown): Array<Record<string, unknown>> {
  if (!Array.isArray(reports)) return []
  return reports.map((report) => {
    const record = asRecord(report)
    const dataSources = asRecord(record.data_sources || record.dataSources)
    const generationParams = asRecord(record.generation_params || record.generationParams)
    const content = String(record.content || '')
    const summary = asRecord(dataSources.summary)
    const reportType = String(record.report_type || record.reportType || '')
    const targetType = String(record.target_type || record.targetType || '')
    const relatedCodes = reportCodes(record, dataSources)
    return {
      ...record,
      buyBeforeDecision: normalizeBuyBeforeDecisionSummary(dataSources.buy_before_decision, {
        content,
        summary,
      }),
      riskLevelGatePolicy: buildReportRiskLevelGatePolicy({
        targetType,
        reportType,
        relatedCodes,
        createdAt: String(record.created_at || record.createdAt || ''),
        content,
        dataSources,
        generationParams,
      }),
    }
  })
}
