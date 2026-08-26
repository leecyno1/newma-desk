import type { CamelFund } from '@/lib/backend-api'

export type Fund = CamelFund

export type MarketResearchCheckStatus = 'ready' | 'verify' | 'blocked'

export type MarketResearchChecklistItem = {
  key: 'foundation' | 'performance' | 'risk' | 'manager' | 'holdings' | 'sales_rules'
  label: string
  status: MarketResearchCheckStatus
  detail: string
}

export type MarketResearchChecklist = {
  status: 'complete' | 'repair' | 'blocked'
  label: string
  passCount: number
  items: MarketResearchChecklistItem[]
  firstGap: string
  backendLabel: string
  backendPrimaryGap: string
}

export type MarketScreeningScore = {
  total: number
  grade: 'A' | 'B' | 'C' | 'D'
  label: string
  isAvailable: boolean
  details: string[]
}

export type ShareClassInfo = {
  groupKey: string
  groupName: string
  siblingCodes: string[]
  siblingCount: number
  displayFund: boolean
}

type UnknownRecord = Record<string, unknown>

function asRecord(value: unknown): UnknownRecord {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as UnknownRecord : {}
}

export function textValue(value: unknown, fallback = '') {
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  return fallback
}

export function numberValue(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function nestedValue(value: unknown, keys: string[]) {
  let current: unknown = value
  for (const key of keys) {
    const record = asRecord(current)
    current = record[key]
  }
  return current
}

export function firstNumber(value: unknown, paths: string[][]) {
  for (const path of paths) {
    const parsed = numberValue(nestedValue(value, path))
    if (parsed !== null) return parsed
  }
  return null
}

export function firstText(value: unknown, paths: string[][]) {
  for (const path of paths) {
    const parsed = textValue(nestedValue(value, path))
    if (parsed) return parsed
  }
  return ''
}

export function getReturn1y(fund: Fund) {
  return firstNumber(fund, [
    ['performanceData', 'return1y'],
    ['performanceData', 'return_1y'],
    ['rollingMetrics', 'return1y'],
    ['rollingMetrics', 'return_1y'],
  ])
}

export function getMaxDrawdown1y(fund: Fund) {
  return firstNumber(fund, [
    ['riskMetrics', 'maxDrawdown1y'],
    ['riskMetrics', 'max_drawdown_1y'],
    ['rollingMetrics', 'maxDrawdown1y'],
    ['rollingMetrics', 'max_drawdown_1y'],
  ])
}

export function getSharpe1y(fund: Fund) {
  return firstNumber(fund, [
    ['riskMetrics', 'sharpe1y'],
    ['riskMetrics', 'sharpe_1y'],
    ['rollingMetrics', 'sharpe1y'],
    ['rollingMetrics', 'sharpe_1y'],
  ])
}

export function getFeeValue(fund: Fund) {
  return firstNumber(fund, [
    ['feeInfo', 'totalFeeRate'],
    ['feeInfo', 'total_fee_rate'],
    ['feeInfo', 'managementFeeRate'],
    ['feeInfo', 'management_fee_rate'],
    ['salesRule', 'salesServiceFee'],
    ['salesRule', 'sales_service_fee'],
  ])
}

export function holdingCount(fund: Fund) {
  return firstNumber(fund, [['holdingCount'], ['holding_count']]) || 0
}

export function hasHoldingEvidence(fund: Fund) {
  return holdingCount(fund) >= 5
}

export function operationStatus(fund: Fund) {
  const value = fund.operationStatus
  if (typeof value === 'string') {
    return {
      status: /终止|清算|封闭|blocked/i.test(value) ? 'blocked' : /暂停|限制|watch/i.test(value) ? 'watch' : 'open',
      label: value,
      reason: value,
    }
  }
  const record = asRecord(value)
  const rawStatus = textValue(record.status || record.code || record.state)
  const label = textValue(record.label || record.name || record.reason, rawStatus || '状态待核')
  return {
    status: /blocked|terminated|liquidat/i.test(rawStatus) ? 'blocked' : /watch|suspend|limit/i.test(rawStatus) ? 'watch' : 'open',
    label,
    reason: textValue(record.reason || record.detail, label),
  }
}

function evidenceAvailable(value: unknown) {
  if (Array.isArray(value)) return value.length > 0
  if (value && typeof value === 'object') return Object.keys(value as UnknownRecord).length > 0
  return value !== null && value !== undefined && value !== ''
}

function managerCount(fund: Fund) {
  const managers = Array.isArray(fund.managers) ? fund.managers : []
  return managers.length || fund.managerIds.length
}

function backendChecklist(fund: Fund) {
  const record = asRecord(fund.marketResearchChecklist)
  const status = textValue(record.status)
  const passCount = numberValue(record.passCount ?? record.pass_count)
  const primaryGap = textValue(record.primaryGap ?? record.primary_gap)
  return {
    label: status === 'complete'
      ? '后端体检通过'
      : status === 'blocked'
        ? '后端体检阻断'
        : status === 'repair'
          ? '后端体检待补'
          : passCount === null
            ? '后端体检待扫描'
            : `后端体检 ${passCount}/6`,
    primaryGap,
  }
}

export function buildMarketResearchChecklist(fund: Fund, salesRuleComplete = false): MarketResearchChecklist {
  const operation = operationStatus(fund)
  const foundationReady = Boolean(fund.windCode && fund.name && fund.establishmentDate && fund.totalAsset !== null)
  const performanceReady = evidenceAvailable(fund.performanceData) && getReturn1y(fund) !== null
  const riskReady = evidenceAvailable(fund.riskMetrics) && getMaxDrawdown1y(fund) !== null
  const managerReady = managerCount(fund) > 0
  const holdingsReady = hasHoldingEvidence(fund)
  const items: MarketResearchChecklistItem[] = [
    {
      key: 'foundation',
      label: '基础',
      status: operation.status === 'blocked' ? 'blocked' : foundationReady ? 'ready' : 'verify',
      detail: operation.status === 'blocked' ? operation.reason : foundationReady ? '身份、规模与成立日期可核验' : '身份、规模或成立日期待补',
    },
    {
      key: 'performance',
      label: '绩效',
      status: performanceReady ? 'ready' : 'verify',
      detail: performanceReady ? '滚动收益证据可核验' : '滚动收益证据待补',
    },
    {
      key: 'risk',
      label: '风险',
      status: riskReady ? 'ready' : 'verify',
      detail: riskReady ? '回撤与风险指标可核验' : '回撤与风险指标待补',
    },
    {
      key: 'manager',
      label: '经理',
      status: managerReady ? 'ready' : 'verify',
      detail: managerReady ? '经理任职证据可核验' : '经理任职证据待补',
    },
    {
      key: 'holdings',
      label: '持仓',
      status: holdingsReady ? 'ready' : 'verify',
      detail: holdingsReady ? `已核验 ${holdingCount(fund)} 条持仓` : '持仓暴露待补',
    },
    {
      key: 'sales_rules',
      label: '销售规则',
      status: salesRuleComplete ? 'ready' : 'verify',
      detail: salesRuleComplete ? '材料核验与风险等级来源相对完整' : '材料核验、R1-R5 或来源日期待补',
    },
  ]
  const blocked = items.filter((item) => item.status === 'blocked')
  const verify = items.filter((item) => item.status === 'verify')
  const status = blocked.length ? 'blocked' : verify.length ? 'repair' : 'complete'
  const backend = backendChecklist(fund)
  return {
    status,
    label: status === 'complete' ? '六灯通过' : status === 'blocked' ? '体检阻断' : `待补 ${verify.length} 灯`,
    passCount: items.filter((item) => item.status === 'ready').length,
    items,
    firstGap: blocked[0]?.detail || verify[0]?.detail || '基础、绩效、风险、经理、持仓和销售规则均有可核验证据',
    backendLabel: backend.label,
    backendPrimaryGap: backend.primaryGap,
  }
}

export function getMarketScreeningScore(fund: Fund): MarketScreeningScore {
  const directScore = numberValue(fund.screeningScore)
  const evidenceCoverage = numberValue(fund.evidenceCoverageScore)
  const return1y = getReturn1y(fund)
  const drawdown = getMaxDrawdown1y(fund)
  const sharpe = getSharpe1y(fund)
  const availableInputs = [directScore, evidenceCoverage, return1y, drawdown, sharpe].filter((value) => value !== null).length
  if (directScore === null && availableInputs < 2) {
    return {
      total: 0,
      grade: 'D',
      label: '数据待补',
      isAvailable: false,
      details: ['数据库全市场初筛分待补', '缺失值不按中性分处理'],
    }
  }
  const derived = directScore ?? Math.max(0, Math.min(100,
    (evidenceCoverage ?? 0) * 0.45
    + Math.max(-20, Math.min(30, (return1y ?? 0) * 100)) * 0.7
    + Math.max(0, 25 - Math.abs(drawdown ?? 0) * 100) * 0.8
    + Math.max(0, Math.min(20, (sharpe ?? 0) * 10)),
  ))
  const total = Math.round(derived)
  const grade = total >= 85 ? 'A' : total >= 70 ? 'B' : total >= 55 ? 'C' : 'D'
  return {
    total,
    grade,
    label: grade === 'A' ? '优先复核' : grade === 'B' ? '可继续研究' : grade === 'C' ? '先补证/横评' : '低优先级',
    isAvailable: true,
    details: ['数据库全市场初筛分', '收益30 / 回撤20 / 夏普20 / 基础证据20 / 费率10'],
  }
}

function shareClassGroupName(name: string) {
  return name
    .replace(/[（(]\s*[A-Z类份额人民币美元]+\s*[)）]$/iu, '')
    .replace(/[\s-]*(A|B|C|D|E|F|H|I|O|R|Y)类?$/iu, '')
    .replace(/[\s-]*(人民币|美元)(现汇|现钞)?$/u, '')
    .trim()
}

export function buildShareClassInfoByCode(funds: Fund[]) {
  const groups = new Map<string, Fund[]>()
  for (const fund of funds) {
    const groupKey = `${shareClassGroupName(fund.name).toLowerCase()}::${fund.type}`
    groups.set(groupKey, [...(groups.get(groupKey) || []), fund])
  }
  const result = new Map<string, ShareClassInfo>()
  for (const [groupKey, groupFunds] of groups) {
    const sorted = [...groupFunds].sort((left, right) => {
      const leftFee = getFeeValue(left)
      const rightFee = getFeeValue(right)
      if (leftFee === null && rightFee !== null) return 1
      if (leftFee !== null && rightFee === null) return -1
      return (leftFee ?? 0) - (rightFee ?? 0) || left.windCode.localeCompare(right.windCode)
    })
    const siblingCodes = sorted.map((fund) => fund.windCode)
    sorted.forEach((fund, index) => {
      result.set(fund.windCode.toUpperCase(), {
        groupKey,
        groupName: shareClassGroupName(fund.name),
        siblingCodes,
        siblingCount: Math.max(0, siblingCodes.length - 1),
        displayFund: index === 0,
      })
    })
  }
  return result
}
