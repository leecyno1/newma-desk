export type ReportRiskLevelGatePolicyStatus =
  | 'strict_30d_source_backed'
  | 'legacy_or_unmarked'
  | 'not_applicable'

export type ReportRiskLevelGatePolicy = {
  status: ReportRiskLevelGatePolicyStatus
  label: string
  detail: string
  tone: 'emerald' | 'amber' | 'slate'
  requiresRegeneration: boolean
  effectiveDate: string
  generatedAt: string
  signals: string[]
}

export const STRICT_RISK_LEVEL_GATE_EFFECTIVE_DATE = '2026-06-07'

function asRecord(value: unknown): Record<string, unknown> {
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

function jsonText(value: unknown) {
  try {
    return JSON.stringify(value || {})
  } catch {
    return ''
  }
}

function hasRelatedFundScope(targetType: string, reportType: string, relatedCodes: string[]) {
  if (relatedCodes.length > 0) return true
  if (targetType === 'fund' || targetType === 'fund_pool' || targetType === 'comparison') return true
  return reportType.includes('fund') || reportType.includes('comparison')
}

function strictRiskLevelSignals(text: string) {
  return [
    /R1-R5\s*来源背书/u.test(text) ? 'R1-R5 来源背书' : '',
    /30\s*天.{0,12}来源/u.test(text) || /30天来源背书/u.test(text) ? '30天来源窗口' : '',
    /销售风险等级（R1-R5 30天来源背书）/u.test(text) ? '销售风险等级（R1-R5 30天来源背书）' : '',
    /Tushare fund_basic.{0,40}(不可|不能).{0,30}(R1-R5|风险等级)/u.test(text) ? 'Tushare fund_basic 排除' : '',
    /风险等级.{0,20}(销售平台|基金合同).{0,20}来源/u.test(text) ? '销售平台/基金合同来源' : '',
  ].filter(Boolean)
}

export function buildReportRiskLevelGatePolicy({
  targetType,
  reportType,
  relatedCodes = [],
  createdAt,
  content,
  dataSources,
  generationParams,
}: {
  targetType: string
  reportType: string
  relatedCodes?: string[]
  createdAt?: string | null
  content?: string | null
  dataSources?: unknown
  generationParams?: unknown
}): ReportRiskLevelGatePolicy {
  const normalizedTargetType = String(targetType || '')
  const normalizedReportType = String(reportType || '')
  const normalizedCodes = Array.from(new Set(relatedCodes.map((code) => String(code || '').trim().toUpperCase()).filter(Boolean)))
  const generatedAt = String(createdAt || asRecord(generationParams).generatedAt || '')

  if (!hasRelatedFundScope(normalizedTargetType, normalizedReportType, normalizedCodes)) {
    return {
      status: 'not_applicable',
      label: 'R1-R5 不适用',
      detail: '这份报告没有可识别的基金研究对象；只作为研究资料，不承担销售风险等级门禁。',
      tone: 'slate',
      requiresRegeneration: false,
      effectiveDate: STRICT_RISK_LEVEL_GATE_EFFECTIVE_DATE,
      generatedAt,
      signals: [],
    }
  }

  const text = [
    content || '',
    jsonText(dataSources),
    jsonText(generationParams),
  ].join('\n')
  const signals = strictRiskLevelSignals(text)
  if (signals.length >= 2) {
    return {
      status: 'strict_30d_source_backed',
      label: '新 R1-R5 门禁',
      detail: '生成内容已包含 R1-R5 来源背书、30 天来源窗口或 Tushare fund_basic 排除信号；仍需按当前销售规则实时复核。',
      tone: 'emerald',
      requiresRegeneration: false,
      effectiveDate: STRICT_RISK_LEVEL_GATE_EFFECTIVE_DATE,
      generatedAt,
      signals,
    }
  }

  return {
    status: 'legacy_or_unmarked',
    label: '旧门禁/未标记',
    detail: '未检测到“R1-R5 30 天来源背书 + Tushare fund_basic 排除”的生成信号；这份历史报告不能证明已适配最新适当性门禁，需重新扫描销售规则或重跑报告。',
    tone: 'amber',
    requiresRegeneration: true,
    effectiveDate: STRICT_RISK_LEVEL_GATE_EFFECTIVE_DATE,
    generatedAt,
    signals,
  }
}
