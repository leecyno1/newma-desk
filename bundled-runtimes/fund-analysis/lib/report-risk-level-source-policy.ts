export const STRICT_RISK_LEVEL_SOURCE_POLICY_SIGNALS = [
  'R1-R5 来源背书',
  '30天来源窗口',
  '销售风险等级（R1-R5 30天来源背书）',
  'Tushare fund_basic 排除',
  '销售平台/基金合同来源',
]

export type StrictRiskLevelSourcePolicy = {
  label: string
  status: 'source_backed_30d' | 'blocked_missing_stale_or_excluded'
  sourceBacked: boolean
  hardGate: true
  windowDays: 30
  scopeLabel: string
  totalCount: number
  blockedCount: number
  acceptableSources: string[]
  excludedSources: string[]
  signals: string[]
}

export function buildStrictRiskLevelSourcePolicy({
  sourceBacked,
  scopeLabel,
  totalCount,
  blockedCount,
}: {
  sourceBacked: boolean
  scopeLabel: string
  totalCount: number
  blockedCount: number
}): StrictRiskLevelSourcePolicy {
  return {
    label: '销售风险等级（R1-R5 30天来源背书）',
    status: sourceBacked ? 'source_backed_30d' : 'blocked_missing_stale_or_excluded',
    sourceBacked,
    hardGate: true,
    windowDays: 30,
    scopeLabel,
    totalCount,
    blockedCount,
    acceptableSources: ['销售平台', '基金合同', '招募说明书'],
    excludedSources: ['Tushare fund_basic'],
    signals: STRICT_RISK_LEVEL_SOURCE_POLICY_SIGNALS,
  }
}

export function strictRiskLevelSourcePolicyMarkdownLines(policy: StrictRiskLevelSourcePolicy) {
  return [
    `- R1-R5 来源背书：${policy.sourceBacked ? `${policy.scopeLabel}已通过` : `${policy.scopeLabel}未通过`}；30天来源窗口：${policy.sourceBacked ? '全部来源日期在 30 天内' : `${policy.blockedCount} 个对象缺失、无来源、来源过期或来源被排除`}`,
    `- 销售风险等级（R1-R5 30天来源背书）：${policy.sourceBacked ? '销售平台/基金合同来源已背书，仍需研究复核时确认实时状态' : '缺失、无来源、来源过期或来源被排除，正式路径硬阻断'}`,
    '- Tushare fund_basic 不能作为 R1-R5 风险等级来源；只允许作为基金基础档案辅助字段。',
  ]
}
