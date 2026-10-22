import type { AssetCycleStateForecastData } from '../types'

export type ForecastHorizon = '1' | '3' | '6'
export type ForecastSort = 'status' | 'probability' | 'return' | 'volatility' | 'attribution'
export type ForecastAttribution = 'all' | 'stable' | 'mixed' | 'low_impact' | 'unstable'
export type AssetForecastViewState = {
  horizon: ForecastHorizon; query: string; majorCategory: string; category: string
  onlyQualified: boolean; attributionFilter: ForecastAttribution; sortKey: ForecastSort; selectedId: string | null
}
export const initialForecastView: AssetForecastViewState = {
  horizon: '6', query: '', majorCategory: '全部大类', category: '全部', onlyQualified: true,
  attributionFilter: 'all', sortKey: 'status', selectedId: null,
}

const stabilityRank = (value?: string) => ({ stable: 4, mixed: 3, low_impact: 2, unstable: 1 })[value ?? ''] ?? 0

// Rendering, Context and UI Actions share the same filters and actual fallback selection.
export function assetForecastView(data: AssetCycleStateForecastData, state: AssetForecastViewState) {
  const { horizon, query, majorCategory, category, onlyQualified, attributionFilter, sortKey, selectedId } = state
  const normalized = query.trim().toLowerCase()
  const visibleAssets = data.assets
    .filter(asset => asset.horizons[horizon])
    .filter(asset => majorCategory === '全部大类' || asset.majorCategory === majorCategory)
    .filter(asset => category === '全部' || asset.category === category)
    .filter(asset => !onlyQualified || asset.horizons[horizon].publicationQualified)
    .filter(asset => attributionFilter === 'all' || asset.horizons[horizon].cycleAttributionStability?.status === attributionFilter)
    .filter(asset => !normalized || `${asset.name} ${asset.category}`.toLowerCase().includes(normalized))
    .sort((left, right) => {
      const a = left.horizons[horizon], b = right.horizons[horizon]
      if (sortKey === 'probability') return (b.forecast?.probabilityUp ?? -Infinity) - (a.forecast?.probabilityUp ?? -Infinity)
      if (sortKey === 'return') return (b.forecast?.medianReturn ?? -Infinity) - (a.forecast?.medianReturn ?? -Infinity)
      if (sortKey === 'volatility') return (a.forecast?.conditionalVol ?? Infinity) - (b.forecast?.conditionalVol ?? Infinity)
      if (sortKey === 'attribution') return stabilityRank(b.cycleAttributionStability?.status) - stabilityRank(a.cycleAttributionStability?.status)
      return Number(b.publicationQualified) - Number(a.publicationQualified)
        || Number(Boolean(b.forecast)) - Number(Boolean(a.forecast))
        || (b.forecast?.probabilityUp ?? -Infinity) - (a.forecast?.probabilityUp ?? -Infinity)
    })
  const selected = visibleAssets.find(asset => asset.assetId === selectedId) ?? visibleAssets[0]
  const estimate = selected?.horizons[horizon]
  return {
    visibleAssets, selected,
    context: {
      layer: 'joint-state-forecast', horizonMonths: Number(horizon),
      filters: { query, majorCategory, category, onlyQualified, attributionFilter, sortKey },
      visibleAssetCount: visibleAssets.length,
      visibleAssets: visibleAssets.map(asset => ({ id: asset.assetId, name: asset.name, publicationQualified: asset.horizons[horizon].publicationQualified })),
      selectedAsset: selected && estimate ? {
        id: selected.assetId, name: selected.name, category: selected.category, majorCategory: selected.majorCategory,
        dataEnd: selected.dataEnd, freshnessRelativeToBuild: selected.freshnessStatus,
        publicationQualified: estimate.publicationQualified, status: estimate.status,
        publicationReasonCodes: estimate.publicationReasonCodes,
        estimateUsage: estimate.publicationQualified ? 'limited-published-estimate' : 'research-only-not-adopted',
        forecast: estimate.forecast, cycleAttribution: estimate.cycleAttribution ?? null,
        attributionStability: estimate.cycleAttributionStability ?? null,
      } : null,
      source: { generated: data.meta.generated, stateAsOf: data.meta.asOf, assetDataThrough: data.meta.assetDataThrough,
        refreshPolicy: '网页刷新只重读研究快照，不更新研究数据；current表示相对快照截点已对齐，不代表今日实时数据。',
        includedCycles: data.meta.includedCycles, stateClock: data.meta.stateClock, modelVersion: data.meta.modelVersion,
        definition: data.meta.definition, riskDefinition: data.meta.riskDefinition, stateIdentity: data.meta.stateIdentity },
      governance: data.governance,
      caveat: data.caveat,
      units: '收益、波动和概率均为小数比例；不是百分数数值。未通过发布门槛的研究值不得作为有效预测；本层与单周期历史映射分开。',
    },
  }
}

export const assetForecastAction = {
  id: 'research.configure-asset-forecast',
  label: '设置联合资产预测期限、筛选与选中资产（仅页面查询；省略筛选恢复默认）', available: true,
  inputSchema: {
    type: 'object', required: ['horizon'], additionalProperties: false,
    properties: {
      horizon: { type: 'string', enum: ['1', '3', '6'] },
      query: { type: 'string', default: '' },
      majorCategory: { type: 'string', default: '全部大类' }, category: { type: 'string', default: '全部' },
      onlyQualified: { type: 'boolean', default: true },
      attributionFilter: { type: 'string', enum: ['all', 'stable', 'mixed', 'low_impact', 'unstable'], default: 'all' },
      sortKey: { type: 'string', enum: ['status', 'probability', 'return', 'volatility', 'attribution'], default: 'status' },
      assetId: { type: 'string', description: '必须在目标筛选结果内；省略则选择结果首项' },
    },
  },
}

export function createAssetForecastControls(apply: (state: AssetForecastViewState) => void) {
  let current: AssetForecastViewState | null = null
  let data: AssetCycleStateForecastData | null = null
  let pending: { target: AssetForecastViewState; resolve: (value: ReturnType<typeof assetForecastView>['context']) => void
    reject: (error: Error) => void; timer: ReturnType<typeof setTimeout> } | undefined
  const matches = (a: AssetForecastViewState, b: AssetForecastViewState) => (Object.keys(initialForecastView) as (keyof AssetForecastViewState)[]).every(key => a[key] === b[key])
  const cancel = () => {
    if (!pending) return
    clearTimeout(pending.timer)
    pending.reject(new Error('页面已切换、被手动修改或等待超时，结果未确认'))
    pending = undefined
  }
  return {
    cancel,
    commit(state: AssetForecastViewState, loaded: AssetCycleStateForecastData | null) {
      current = state; data = loaded
      if (pending && data && matches(state, pending.target)) {
        clearTimeout(pending.timer)
        pending.resolve(assetForecastView(data, state).context)
        pending = undefined
      }
    },
    async perform(actionId: string, input: Record<string, unknown>) {
      if (actionId !== assetForecastAction.id) throw new Error('当前页面未注册该操作')
      if (!data || !current) throw new Error('联合资产预测尚未加载')
      if (pending) throw new Error('已有页面操作等待确认，请勿重复执行')
      if (Object.keys(input).some(key => !Object.keys(assetForecastAction.inputSchema.properties).includes(key))
        || !['1', '3', '6'].includes(input.horizon as string)
        || ['query', 'majorCategory', 'category', 'assetId'].some(key => input[key] !== undefined && typeof input[key] !== 'string')
        || (input.onlyQualified !== undefined && typeof input.onlyQualified !== 'boolean')
        || (input.attributionFilter !== undefined && !['all', 'stable', 'mixed', 'low_impact', 'unstable'].includes(input.attributionFilter as string))
        || (input.sortKey !== undefined && !['status', 'probability', 'return', 'volatility', 'attribution'].includes(input.sortKey as string))) throw new Error('预测期限或筛选参数无效')
      const { assetId, ...filters } = input
      const target: AssetForecastViewState = { ...initialForecastView, ...filters,
        horizon: input.horizon as ForecastHorizon, selectedId: (assetId as string | undefined) ?? null }
      if (target.majorCategory !== '全部大类' && !data.assets.some(asset => asset.majorCategory === target.majorCategory)) throw new Error('未知资产大类')
      if (target.category !== '全部' && !data.assets.some(asset => asset.category === target.category)) throw new Error('未知资产类别')
      const view = assetForecastView(data, target)
      if (target.selectedId !== null && !view.visibleAssets.some(asset => asset.assetId === target.selectedId)) throw new Error('目标资产不在所选期限和筛选结果内，请检查发布资格及筛选条件')
      if (matches(current, target)) return assetForecastView(data, current).context
      return new Promise<ReturnType<typeof assetForecastView>['context']>((resolve, reject) => {
        pending = { target, resolve, reject, timer: setTimeout(cancel, 5000) }
        try { apply(target) } catch (error) { cancel(); throw error }
      })
    },
  }
}
