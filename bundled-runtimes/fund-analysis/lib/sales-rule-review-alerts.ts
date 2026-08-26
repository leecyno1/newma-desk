import { backendApiBaseUrl } from '@/lib/backend-api'

type RawAlertEvent = {
  id?: string
  fund_id?: string | null
  event_type?: string
  severity?: string
  title?: string
  message?: string
  status?: string
  details?: unknown
}

export type ActiveSalesRuleEvidenceAlert = {
  id: string
  fundCode: string
  severity: string
  title: string
  message: string
}

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

function stringValue(value: unknown) {
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  return ''
}

function alertFundCode(event: RawAlertEvent) {
  const details = asRecord(event.details)
  return (
    stringValue(details.wind_code) ||
    stringValue(details.fund_code) ||
    stringValue(event.fund_id)
  ).toUpperCase()
}

export async function fetchActiveSalesRuleEvidenceAlertForCode(windCode: string): Promise<ActiveSalesRuleEvidenceAlert | null> {
  const alertMap = await fetchActiveSalesRuleEvidenceAlertsForCodes([windCode])
  return alertMap.get(windCode.trim().toUpperCase())?.[0] || null
}

export async function fetchActiveSalesRuleEvidenceAlertsForCodes(windCodes: string[]): Promise<Map<string, ActiveSalesRuleEvidenceAlert[]>> {
  const normalizedCodes = Array.from(new Set(windCodes.map((code) => code.trim().toUpperCase()).filter(Boolean)))
  const result = new Map<string, ActiveSalesRuleEvidenceAlert[]>()
  if (!normalizedCodes.length) return result
  const targetCodes = new Set(normalizedCodes)

  const alertsUrl = new URL('/api/alerts', backendApiBaseUrl)
  const response = await fetch(alertsUrl, { cache: 'no-store' })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(payload.detail || payload.error || '复查队列读取失败')
  }

  const events = Array.isArray(payload.events) ? payload.events as RawAlertEvent[] : []
  events
    .filter((item) => item.event_type === 'sales_rule_evidence' && item.status !== 'resolved')
    .forEach((event) => {
      const fundCode = alertFundCode(event)
      if (!targetCodes.has(fundCode)) return
      const current = result.get(fundCode) || []
      current.push({
        id: stringValue(event.id),
        fundCode,
        severity: stringValue(event.severity) || 'medium',
        title: stringValue(event.title) || '销售规则/R1-R5证据待补',
        message: stringValue(event.message) || '销售规则、R1-R5来源、费率或赎回规则存在过期/待补事件。',
      })
      result.set(fundCode, current)
    })
  return result
}
