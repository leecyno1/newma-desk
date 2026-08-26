export type ComparisonWinLossThreshold = {
  key: string
  label: string
  passed: boolean
  detail: string
}

export type ComparisonWinLossLine = {
  challengerCode: string
  challengerName: string
  status: string
  label: string
  summary: string
  thresholds: ComparisonWinLossThreshold[]
  passedChecks: number
  totalChecks: number
}

export type ComparisonDecisiveAuditItem = {
  label: string
  passed: boolean
  detail: string
}

export type ComparisonDecisiveAudit = {
  title: string
  confidence: string
  passCount: number
  totalCount: number
  items: ComparisonDecisiveAuditItem[]
  boundary: string
}

function numberValue(value: unknown) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function stringValue(value: unknown) {
  return String(value ?? '').trim()
}

function asRecord(value: unknown): Record<string, unknown> {
  if (value && typeof value === 'object') return value as Record<string, unknown>
  return {}
}

function thresholdByKey(line: ComparisonWinLossLine | undefined, key: string) {
  return line?.thresholds.find((threshold) => threshold.key === key)
}

export function normalizeComparisonWinLossLines(value: unknown): ComparisonWinLossLine[] {
  if (!Array.isArray(value)) return []
  return value
    .map((item) => {
      const record = asRecord(item)
      const thresholds = Array.isArray(record.thresholds)
        ? record.thresholds
            .map((threshold) => {
              const thresholdRecord = asRecord(threshold)
              return {
                key: stringValue(thresholdRecord.key) || stringValue(thresholdRecord.label),
                label: stringValue(thresholdRecord.label) || '胜负线',
                passed: Boolean(thresholdRecord.passed),
                detail: stringValue(thresholdRecord.detail) || '证据待补',
              }
            })
            .filter((threshold) => threshold.key || threshold.label || threshold.detail)
        : []
      const totalChecks = numberValue(record.totalChecks) ?? thresholds.length
      const passedChecks = numberValue(record.passedChecks) ?? thresholds.filter((threshold) => threshold.passed).length
      return {
        challengerCode: stringValue(record.challengerCode).toUpperCase(),
        challengerName: stringValue(record.challengerName) || stringValue(record.challengerCode) || '替代基金',
        status: stringValue(record.status) || 'close',
        label: stringValue(record.label) || '胜负待复核',
        summary: stringValue(record.summary) || '胜负线证据待补。',
        thresholds,
        passedChecks,
        totalChecks,
      }
    })
    .filter((line) => line.challengerCode || line.challengerName || line.thresholds.length)
}

export function buildComparisonDecisiveAudit(winLossLines: ComparisonWinLossLine[]): ComparisonDecisiveAudit {
  const firstLine = winLossLines[0]
  const score = thresholdByKey(firstLine, 'score')
  const returnReplay = thresholdByKey(firstLine, 'return')
  const drawdown = thresholdByKey(firstLine, 'risk')
  const stress = thresholdByKey(firstLine, 'stress')
  const evidence = thresholdByKey(firstLine, 'evidence')
  const salesRules = thresholdByKey(firstLine, 'sales_rules')
  const cost = thresholdByKey(firstLine, 'cost')
  const salesRulesReady = Boolean(salesRules?.passed && cost?.passed)
  const items: ComparisonDecisiveAuditItem[] = firstLine
    ? [
        {
          label: '分差安全垫',
          passed: Boolean(score?.passed),
          detail: score?.detail || '缺少第一名与第二名的决策分差，不能判断安全垫。',
        },
        {
          label: '费后回放收益',
          passed: Boolean(returnReplay?.passed),
          detail: returnReplay?.detail || '缺真实回放收益，不采信静态收益排序。',
        },
        {
          label: '回撤不劣于替代',
          passed: Boolean(drawdown?.passed),
          detail: drawdown?.detail || '缺回撤回放，无法判断风险体验。',
        },
        {
          label: '压力体验不落后',
          passed: Boolean(stress?.passed),
          detail: stress?.detail || '缺压力体验，无法判断真实持有舒适度。',
        },
        {
          label: '证据完整度不落后',
          passed: Boolean(evidence?.passed),
          detail: evidence?.detail || '研究证据分不能弱于第二名；缺证据不按中性处理。',
        },
        {
          label: '材料核验可正式横评',
          passed: salesRulesReady,
          detail: salesRulesReady
            ? '双方材料核验和费用证据可进入下一层复核。'
            : salesRules?.detail || cost?.detail || '任一方 R1-R5、来源材料或费用证据未清零，只能研究态横评。',
        },
      ]
    : []
  const passCount = items.filter((item) => item.passed).length
  const confidence = !firstLine
    ? '样本不足'
    : !salesRulesReady
      ? '仅补证观察'
      : passCount >= 5
        ? '领先较稳'
        : passCount >= 3
          ? '领先待复核'
          : '领先很脆弱'
  return {
    title: '第一名能否真的赢第二名',
    confidence,
    passCount,
    totalCount: items.length,
    items,
    boundary: '至少同时看分差、费后回放、回撤、压力体验、证据完整度和材料核验；任一硬门禁未过时，横评只能作为研究观察。',
  }
}
