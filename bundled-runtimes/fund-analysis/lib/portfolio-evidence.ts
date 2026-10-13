type Holding = { wind_code: string; weight: number | string | null }
export const portfolioHistoryMethodology = 'portfolio_adj_common_dates_v2'
export const portfolioHistoryUnavailable = '当前基金服务尚未接入已校验的复权与日期对齐算法，暂不展示历史数值。请切换至更新后的 Desk 捆绑后端；不能据此判断收益或风险为零。'
export function portfolioHistoryVerified(result: { methodology_version?: string; nav_basis?: string } | null | undefined) {
  return result?.methodology_version === portfolioHistoryMethodology && result.nav_basis === 'adj_nav'
}
type Target = { peer_group_key: string; target_weight: number | string }
type Drift = { wind_code: string; status: string; level: string | null }
type Monitor = {
  status: string
  target_assessable?: boolean
  weights_basis?: string
  rebalance_needed?: boolean | null
  target_deviations?: Array<{ peer_group_key: string; actual_weight: number | null; deviation: number | null; needs_rebalance: boolean | null }>
  style_drifts?: Drift[]
}

function number(value: unknown): number | null {
  if (value === null || value === undefined || value === '' || (typeof value !== 'number' && typeof value !== 'string')) return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

/** Evidence gate for both the bundled service and older standalone fund services. */
export function portfolioEvidence(holdings: Holding[], targets: Target[], weights?: Record<string, number>, monitor?: Monitor | null) {
  const values = holdings.map(item => number(item.weight))
  const savedWeightsComplete = holdings.length > 0 && values.every(value => value !== null && value >= 0 && value <= 1)
    && Math.abs(values.reduce<number>((sum, value) => sum + (value ?? 0), 0) - 1) <= 0.005
  const calculationMatchesSaved = savedWeightsComplete && !!weights && Object.keys(weights).length === holdings.length
    && holdings.every((item, i) => typeof weights[item.wind_code] === 'number' && Math.abs(weights[item.wind_code] - values[i]!) <= 0.000001)
  const targetValues = targets.map(item => number(item.target_weight))
  const targetsComplete = targets.length > 0 && new Set(targets.map(item => item.peer_group_key)).size === targets.length
    && targetValues.every(value => value !== null && value >= 0 && value <= 1)
    && Math.abs(targetValues.reduce<number>((sum, value) => sum + (value ?? 0), 0) - 1) <= 0.005
  const deviations = monitor?.target_deviations || []
  const targetAssessable = !!monitor && ['available', 'partial'].includes(monitor.status) && monitor.target_assessable !== false
    && monitor.weights_basis !== 'equal_weight_assumption' && savedWeightsComplete && targetsComplete
    && targets.every(target => deviations.some(row => row.peer_group_key === target.peer_group_key))
    && deviations.every(row => number(row.actual_weight) !== null && number(row.deviation) !== null && typeof row.needs_rebalance === 'boolean')
    && !deviations.some(row => row.peer_group_key === 'unclassified' && row.actual_weight !== 0)
  const driftRows = monitor?.style_drifts || []
  const assessed = holdings.filter(item => driftRows.some(row => row.wind_code === item.wind_code && row.status === 'available' && ['low', 'medium', 'high'].includes(row.level || '')))
  const alerts = assessed.filter(item => driftRows.some(row => row.wind_code === item.wind_code && row.status === 'available' && ['medium', 'high'].includes(row.level || '')))
  const rebalanceNeeded = targetAssessable ? deviations.some(row => row.needs_rebalance === true) : null
  const targetSummary = !targets.length ? '未配置目标，不能判断是否需要再平衡。'
    : !targetAssessable ? '权重、目标或分类证据不完整，暂不能判断配置偏离。'
    : rebalanceNeeded ? '配置偏离超阈值，需复核。' : '已检查配置偏离未超阈值，不代表整体风险低。'
  return {
    savedWeightsComplete, calculationMatchesSaved, targetAssessable, rebalanceNeeded,
    assessedCount: assessed.length, totalCount: holdings.length, alertCount: alerts.length,
    assessedWeight: savedWeightsComplete ? assessed.reduce((sum, item) => sum + Number(item.weight), 0) : null,
    missingCodes: holdings.filter(item => !assessed.some(row => row.wind_code === item.wind_code)).map(item => item.wind_code),
    summary: monitor ? `${targetSummary} 风格已判定 ${assessed.length}/${holdings.length} 只，${alerts.length} 只出现漂移信号。${assessed.length < holdings.length || !holdings.length ? '证据不足部分不能判断为稳定。' : '仅适用于返回的历史披露期，不代表当前持仓。'}` : '尚未运行监控。',
  }
}
