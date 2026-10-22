import type { MarketTrack } from '../types'
import type { SurfaceView, TimeRange } from '../components/MarketSurfacePlot'

export const marketControlAction = {
  id: 'research.configure-market',
  label: '设置市场视图、时间范围和1至24条轨道（仅页面查询；热图不含预测）',
  available: true,
  inputSchema: {
    type: 'object', required: ['view', 'timeRange', 'trackIds'], additionalProperties: false,
    properties: {
      view: { type: 'string', enum: ['heatmap', '3d', '2d'] },
      timeRange: { type: 'string', enum: ['5y', '20y', '50y', 'all'] },
      trackIds: { type: 'array', minItems: 1, maxItems: 24, uniqueItems: true, items: { type: 'string' } },
      showForecast: { type: 'boolean', default: false },
      comparisonDate: { type: 'string', pattern: '^\\d{4}-(0[1-9]|1[0-2])$', description: '仅热图；须在所选轨道和时间窗口中，省略则自动选择最近完整覆盖月' },
    },
  },
}

type ComparisonTrack = Pick<MarketTrack, 'dates' | 'governedStack'>
const monthIndex = (value: string) => {
  const [year, month] = value.split('-').map(Number)
  return year * 12 + month
}

// The page and Action use the same date window and fallback, including partial coverage.
export function marketComparison(tracks: ComparisonTrack[], range: TimeRange, requested: string | null) {
  const dates = [...new Set(tracks.flatMap(track => track.dates))].sort()
  const newest = dates.at(-1) ?? ''
  const months = range === '5y' ? 60 : range === '20y' ? 240 : range === '50y' ? 600 : Infinity
  const visible = dates.filter(date => monthIndex(date) > monthIndex(newest) - months)
  const complete = [...visible].reverse().find(date => monthIndex(newest) - monthIndex(date) <= 12
    && tracks.every(track => {
      const index = track.dates.indexOf(date)
      return index >= 0 && Number.isFinite(track.governedStack[index])
    }))
  return { visible, newest, effective: requested && visible.includes(requested) ? requested : complete ?? newest }
}

export type MarketViewState = {
  view: SurfaceView
  timeRange: TimeRange
  selectedTrackIds: string[]
  forecastLayer: 'history-only' | 'history-and-forecast'
  comparisonDate: string | null
}

const matches = (left: MarketViewState, right: MarketViewState) => left.view === right.view
  && left.timeRange === right.timeRange && left.forecastLayer === right.forecastLayer
  && left.comparisonDate === right.comparisonDate
  && left.selectedTrackIds.length === right.selectedTrackIds.length
  && left.selectedTrackIds.every((id, index) => id === right.selectedTrackIds[index])

export function createMarketControls(apply: (state: MarketViewState) => void) {
  let current: MarketViewState | null = null
  let tracks: MarketTrack[] = []
  let pending: { target: MarketViewState; resolve: (state: MarketViewState) => void
    reject: (error: Error) => void; timer: ReturnType<typeof setTimeout> } | undefined
  const cancel = (message = '页面已切换或被手动修改，操作结果未确认') => {
    if (!pending) return
    clearTimeout(pending.timer)
    pending.reject(new Error(message))
    pending = undefined
  }
  return {
    cancel,
    commit(state: MarketViewState | null, availableTracks: MarketTrack[]) {
      current = state
      tracks = availableTracks
      if (pending && state && matches(state, pending.target)) {
        clearTimeout(pending.timer)
        pending.resolve({ ...state, selectedTrackIds: [...state.selectedTrackIds] })
        pending = undefined
      }
    },
    async perform(actionId: string, input: Record<string, unknown>): Promise<MarketViewState> {
      if (actionId !== marketControlAction.id) throw new Error('当前页面未注册该操作')
      if (!current) throw new Error('市场研究数据尚未加载')
      if (pending) throw new Error('已有页面操作等待确认，请勿重复执行')
      if (Object.keys(input).some(key => !['view', 'timeRange', 'trackIds', 'showForecast', 'comparisonDate'].includes(key))
        || !['heatmap', '3d', '2d'].includes(input.view as string)
        || !['5y', '20y', '50y', 'all'].includes(input.timeRange as string)
        || (input.showForecast !== undefined && typeof input.showForecast !== 'boolean')) {
        throw new Error('视图、时间范围或预测开关无效')
      }
      const ids = input.trackIds
      if (!Array.isArray(ids) || !ids.length || ids.length > 24 || new Set(ids).size !== ids.length
        || ids.some(id => typeof id !== 'string' || !tracks.some(track => track.id === id))) {
        throw new Error('请选择1至24条已加载的轨道，不接受空、重复或未知轨道')
      }
      if (input.view === 'heatmap' && input.showForecast === true) throw new Error('热图只显示历史观测；预测请使用2D或3D视图')
      const comparison = marketComparison(tracks.filter(track => ids.includes(track.id)), input.timeRange as TimeRange, null)
      if (input.comparisonDate !== undefined && (input.view !== 'heatmap'
        || typeof input.comparisonDate !== 'string' || !comparison.visible.includes(input.comparisonDate))) {
        throw new Error('对比月份必须在热图所选轨道的时间窗口内')
      }
      const target: MarketViewState = {
        view: input.view as SurfaceView, timeRange: input.timeRange as TimeRange, selectedTrackIds: [...ids],
        forecastLayer: input.showForecast === true ? 'history-and-forecast' : 'history-only',
        comparisonDate: input.view === 'heatmap' ? (input.comparisonDate as string | undefined) ?? comparison.effective : null,
      }
      if (matches(current, target)) return { ...current, selectedTrackIds: [...current.selectedTrackIds] }
      return new Promise((resolve, reject) => {
        pending = { target, resolve, reject, timer: setTimeout(() => cancel('页面状态更新超时，结果未确认，请检查当前页'), 5000) }
        try { apply(target) } catch (error) { cancel(error instanceof Error ? error.message : '页面状态更新失败') }
      })
    },
  }
}
