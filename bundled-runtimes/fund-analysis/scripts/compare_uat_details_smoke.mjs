import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { join } from 'node:path'
import { buildYearlyChartData } from '../app/(dashboard)/compare/yearlyChartData.ts'

const root = fileURLToPath(new URL('..', import.meta.url))

function read(relativePath) {
  const fullPath = join(root, relativePath)
  if (!existsSync(fullPath)) {
    throw new Error(`Missing required file: ${relativePath}`)
  }
  return readFileSync(fullPath, 'utf8')
}

function assertIncludes(content, expected, label) {
  if (!content.includes(expected)) {
    throw new Error(`${label} missing text: ${expected}`)
  }
}

function assertNotIncludes(content, unexpected, label) {
  if (content.includes(unexpected)) {
    throw new Error(`${label} should not include text: ${unexpected}`)
  }
}

function assert(condition, message) {
  if (!condition) throw new Error(message)
}

// UAT Item 3：比较页读取研究快照必须显式请求已保存的归因证据（saved 优先、不触发现场计算）。
const comparisonPage = read('app/(dashboard)/compare/page.tsx')
assertIncludes(
  comparisonPage,
  '/research-snapshot?include_attribution=true&live_attribution=false',
  'comparison research snapshot fetch',
)
assertNotIncludes(
  comparisonPage,
  "fetch(`${backendApiBaseUrl}/api/funds/${encodeURIComponent(code)}/research-snapshot`, { cache: 'no-store' })",
  'comparison research snapshot fetch without attribution params',
)

// UAT Item 4：纪要证据层级字段是 evidence_scope（fund_specific / manager_level），必须优先读取。
assertIncludes(comparisonPage, 'memo.evidence_scope || memo.scope || memo.memo_scope', 'memo evidence scope reading order')

// UAT Item 1：年度区间必须携带真实起止日，供并柱可比性判断使用。
assertIncludes(comparisonPage, 'actual_start_date', 'comparison period mapping')
assertIncludes(comparisonPage, 'actual_end_date', 'comparison period mapping')
const comparisonClient = read('app/(dashboard)/compare/SimpleComparisonClient.tsx')
assertIncludes(comparisonClient, 'actualEndDate', 'comparison client period type')
assertIncludes(comparisonClient, 'buildYearlyChartData', 'comparison client must reuse the shared yearly chart builder')
assertIncludes(comparisonClient, '各基金净值截止日不同', 'comparison must disclose differing NAV cutoffs')

// UAT Item 2：短样本只缺滚动窗口时，回撤轨迹不能再被整体隐藏。
const derivedCharts = read('app/(dashboard)/funds/[id]/FundDerivedSeriesCharts.tsx')
assertNotIncludes(
  derivedCharts,
  "series.status === 'insufficient_evidence' || (!hasDrawdown && !hasRolling)",
  'derived series whole-section gate',
)

// UAT Item 1 逻辑：同一自然年度内净值截止日不一致的基金不得并柱。
function period(year, label, returnValue, coverageStatus, actualEndDate) {
  return { year, label, isYtd: true, return: returnValue, coverageStatus, actualEndDate }
}

const sameCutoffFunds = [
  { windCode: 'A.OF', periods: [period(2025, '2025 年初至今', 0.181, 'complete', '2025-09-19')] },
  { windCode: 'B.OF', periods: [period(2025, '2025 年初至今', 0.273, 'complete', '2025-09-19')] },
]
const sameCutoffRows = buildYearlyChartData(sameCutoffFunds, [2025])
assert(sameCutoffRows.length === 1, 'same-cutoff year must stay charted')
assert(sameCutoffRows[0]['A.OF'] === 18.1 && sameCutoffRows[0]['B.OF'] === 27.3, 'same-cutoff year must chart every complete fund')

const mixedCutoffFunds = [
  { windCode: 'A.OF', periods: [period(2025, '2025 年初至今', 0.181, 'complete', '2025-06-30')] },
  { windCode: 'B.OF', periods: [period(2025, '2025 年初至今', 0.273, 'complete', '2025-09-19')] },
]
const mixedCutoffRows = buildYearlyChartData(mixedCutoffFunds, [2025])
assert(mixedCutoffRows[0]['A.OF'] == null, 'earlier-cutoff fund must not be charted beside a later cutoff')
assert(mixedCutoffRows[0]['B.OF'] === 27.3, 'majority/latest cutoff group must stay charted')

const majorityFunds = [
  { windCode: 'A.OF', periods: [period(2025, '2025 年初至今', 0.181, 'complete', '2025-06-30')] },
  { windCode: 'B.OF', periods: [period(2025, '2025 年初至今', 0.152, 'complete', '2025-06-30')] },
  { windCode: 'C.OF', periods: [period(2025, '2025 年初至今', 0.273, 'complete', '2025-09-19')] },
]
const majorityRows = buildYearlyChartData(majorityFunds, [2025])
assert(majorityRows[0]['A.OF'] === 18.1 && majorityRows[0]['B.OF'] === 15.2, 'majority cutoff group must stay charted')
assert(majorityRows[0]['C.OF'] == null, 'single later-cutoff fund must not be charted beside an earlier cutoff')

const partialFunds = [
  { windCode: 'A.OF', periods: [period(2024, '2024 年', 0.1, 'complete', '2024-12-31')] },
  { windCode: 'B.OF', periods: [period(2024, '2024 年', 0.2, 'partial', '2024-09-30')] },
]
const partialRows = buildYearlyChartData(partialFunds, [2024])
assert(partialRows[0]['A.OF'] === 10 && partialRows[0]['B.OF'] == null, 'partial periods must never be charted')

const unknownCutoffFunds = [
  { windCode: 'A.OF', periods: [period(2023, '2023 年', 0.05, 'complete', '')] },
  { windCode: 'B.OF', periods: [period(2023, '2023 年', 0.07, 'complete', '')] },
]
const unknownCutoffRows = buildYearlyChartData(unknownCutoffFunds, [2023])
assert(unknownCutoffRows[0]['A.OF'] === 5 && unknownCutoffRows[0]['B.OF'] === 7, 'legacy payloads without cutoffs must keep the old chart behaviour')

const emptyRows = buildYearlyChartData(sameCutoffFunds, [])
assert(emptyRows.length === 0, 'no calendar years must yield no chart rows')

console.log('OK compare UAT details: attribution params, memo evidence scope, short-sample drawdown, yearly cutoff grouping')
