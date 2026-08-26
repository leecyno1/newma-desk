import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { join } from 'node:path'

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

const fundsPage = read('app/(dashboard)/funds/page.tsx')

assertIncludes(fundsPage, 'fund-list-purchase-gate-radar', 'fund list purchase gate radar')
assertIncludes(fundsPage, '当前页研究门禁雷达', 'fund list research gate radar title')
assertIncludes(fundsPage, 'fund-list-purchase-action-queue', 'fund list purchase action queue')
assertIncludes(fundsPage, '基金列表研究行动队列', 'fund list research action queue title')
assertIncludes(fundsPage, 'fundListPurchaseQueue', 'fund list structured purchase queue')
assertIncludes(fundsPage, 'fundListPurchaseQueueTsv', 'fund list purchase action queue TSV model')
assertIncludes(fundsPage, 'copyFundListPurchaseQueueTsv', 'fund list purchase action queue TSV copy action')
assertIncludes(fundsPage, 'downloadFundListPurchaseQueueTsv', 'fund list purchase action queue TSV download action')
assertIncludes(fundsPage, 'fund-list-purchase-queue-copy-tsv', 'fund list purchase action queue TSV copy button')
assertIncludes(fundsPage, 'fund-list-purchase-queue-download-tsv', 'fund list purchase action queue TSV download button')
assertIncludes(fundsPage, '复制行动 TSV', 'fund list purchase action queue TSV copy label')
assertIncludes(fundsPage, '下载行动 TSV', 'fund list purchase action queue TSV download label')
assertIncludes(fundsPage, 'purchaseQueueTsvStatus', 'fund list purchase action queue TSV status')
assertIncludes(fundsPage, '已转下载 TSV', 'fund list purchase action queue TSV fallback label')
assertIncludes(fundsPage, '列表页不输出申赎指令；正式判断必须进入详情、横评和研究复核报告门禁', 'fund list action TSV keeps research hard boundary')
assertIncludes(fundsPage, 'salesRuleGapByCode', 'fund list sales-rule gap mapping')
assertIncludes(fundsPage, "pickBrowserParam('purchasePlan'", 'fund list initializes purchase-plan context from URL')
assertIncludes(fundsPage, 'plannedAmountSearchParams(purchasePlan, plannedAmount)', 'fund list derives planned amount aliases')
assertIncludes(fundsPage, "params.get('plannedAmount') || params.get(initialPurchasePlan === 'lump_sum' ? 'lumpSumAmount' : 'monthlyAmount')", 'fund list initializes planned amount from URL aliases')
assertIncludes(fundsPage, 'purchasePlan,', 'fund list query carries purchase plan to funds API')
assertIncludes(fundsPage, '...plannedAmountParams,', 'fund list query carries planned amount context')
assertIncludes(fundsPage, '}, [appliedSearch, page, plannedAmountParams, purchasePlan])', 'fund list reloads when purchase plan or amount changes')
assertIncludes(fundsPage, "codes: currentFundCodes.slice(0, 100).join(','), purchasePlan, ...plannedAmountParams", 'fund list sales-rule gap scan uses purchase-plan and amount context')
assertIncludes(fundsPage, "fetch('/api/evidence-coverage/review-events'", 'fund list material evidence scan reads review queue')
assertIncludes(fundsPage, "event.event_type === 'sales_rule_evidence' && event.status !== 'resolved'", 'fund list blocks active sales-rule review alerts')
assertIncludes(fundsPage, '复查队列未解决', 'fund list turns active review alerts into missing items')
assertIncludes(fundsPage, "gateSource: 'local.alert_events.sales_rule_evidence'", 'fund list records review-alert gate source')
assertIncludes(fundsPage, '复查队列读取失败：不能证明销售规则/R1-R5证据有效', 'fund list fails closed when review queue cannot be read')
assertIncludes(fundsPage, '复查队列补证', 'fund list action queue review alert label')
assertIncludes(fundsPage, '开复查队列', 'fund list routes review alert rows to review queue')
assertIncludes(fundsPage, '处理复查队列', 'fund list page-level action prioritizes review queue')
assertIncludes(fundsPage, "new URLSearchParams({ codes: fund.windCode, purchasePlan, ...plannedAmountParams })", 'fund list per-fund sales-rule workbench preserves planned amount')
assertIncludes(fundsPage, '补当前页缺口', 'fund list page-level sales-rule action')
assertIncludes(fundsPage, '用研究模型筛', 'fund list investor selection action')
assertIncludes(fundsPage, '销售规则硬缺口或复查队列未清零前，不能保存正式研究复核报告', 'fund list hard gate guardrail includes review queue')
assertIncludes(fundsPage, 'const fundsReturnHref = useMemo', 'fund list keeps current research return href')
assertIncludes(fundsPage, 'appendReturnTo(`/funds/${encodeURIComponent(fund.id)}?${detailContextQuery}`, fundsReturnHref)', 'fund list detail links preserve return path')
assertIncludes(fundsPage, "appendReturnTo(`/analysis/comparison?${new URLSearchParams", 'fund list comparison link preserves return path')
assertIncludes(fundsPage, "appendReturnTo('/analysis/comparison', fundsReturnHref)", 'fund list empty comparison link preserves return path')
assertIncludes(fundsPage, 'const investorSelectionHref = `/investor-selection?', 'fund list investor selection link preserves planned amount')
assertIncludes(fundsPage, 'const marketHref = `/market?', 'fund list market link preserves planned amount')
assertIncludes(fundsPage, 'const fundAnalysisHref = (fund: Fund)', 'fund list analysis link preserves planned amount')
assertIncludes(fundsPage, '当前研究口径', 'fund list displays current planned amount execution context')

console.log('OK fund list exposes research gate radar, action queue, and return-path context')
