import type { AssetStatisticsData } from '../types'

export type AssetHistoryState = {
  cycleId: string; phase: string; query: string; category: string; confidence: string
  sortKey: 'impact' | 'spread' | 'oos' | 'name'; selectedId: string | null
}

export function initialAssetHistory(cycleId = 'C4'): AssetHistoryState {
  return { cycleId, phase: 'recovery', query: '', category: '全部', confidence: '全部',
    sortKey: cycleId === 'C4' ? 'impact' : 'oos', selectedId: null }
}

// One derivation feeds both historical tables, Context and the action receipt.
// Research mappings retain their existing camelCase rows; C4 keeps its source schema.
export function assetHistoryView(data: AssetStatisticsData, state: AssetHistoryState) {
  const { cycleId, phase, query, category, confidence, sortKey, selectedId } = state
  const c4 = cycleId === 'C4'
  const mapping = data.researchMappings?.[cycleId]?.assetMapping ?? data.stateMappings?.[cycleId]
  const available = c4 || Boolean(mapping && mapping.status !== 'legacy_mapping_rebuild_required')
  const phaseLabels: Record<string, string> = c4 ? data.phase_labels : mapping?.phaseLabels ?? data.researchPhaseLabels ?? {
    recovery: '复苏', expansion: '扩张', slowdown: '放缓', contraction: '收缩',
  }
  const assets: any[] = !available ? [] : c4 ? data.assets : mapping.assets.filter((asset: any) => asset.eligible)
  const categories = ['全部', ...new Set<string>(assets.map(asset => asset.category))]
  const normalized = query.trim().toLowerCase()
  const rows = assets.filter(asset => category === '全部' || asset.category === category)
    .filter(asset => confidence === '全部' || asset.confidence === confidence)
    .filter(asset => !normalized || `${asset.name} ${asset.category}`.toLowerCase().includes(normalized))
    .sort((a, b) => {
      if (sortKey === 'name') return a.name.localeCompare(b.name, 'zh-CN')
      if (sortKey === 'oos') return ((c4 ? b.oos_r2 : b.oosR2) ?? -Infinity) - ((c4 ? a.oos_r2 : a.oosR2) ?? -Infinity)
      if (!c4) return (b.phaseSpread ?? -Infinity) - (a.phaseSpread ?? -Infinity)
      const impact = (asset: any) => asset.impact_bps_per_1sigma == null ? -Infinity : Math.abs(asset.impact_bps_per_1sigma)
      return impact(b) - impact(a)
    })
  const id = (asset: any): string => c4 ? asset.asset_id : asset.assetId
  const selected = rows.find(asset => id(asset) === selectedId) ?? null
  return {
    rows, selected, categories, phaseLabels, available,
    context: {
      cycleId, layer: c4 ? 'historical-c4-statistics' : mapping?.kind === 'state_association' ? 'historical-state-association' : 'research-phase-mapping',
      status: mapping?.status ?? data.publication[cycleId] ?? 'blocked', available,
      phase: available ? phase : null, phaseLabel: available ? phaseLabels[phase] ?? null : null,
      filters: available ? { query, category, confidence, sortKey } : null,
      visibleAssetCount: rows.length,
      visibleAssets: rows.map(asset => ({ id: id(asset), name: asset.name, category: asset.category })),
      currentState: mapping?.currentState ?? null,
      selectedAsset: selected ? {
        id: id(selected), name: selected.name, category: selected.category,
        dataIdentity: (c4 ? selected.data_identity : selected.dataIdentity) ?? null,
        phaseStatistics: (c4 ? selected.phase_stats : selected.phaseStats)?.[phase] ?? null,
        oosR2: (c4 ? selected.oos_r2 : selected.oosR2) ?? null,
      } : null,
      caveat: available ? '单周期历史统计/研究关联，不是上方联合预测，不证明因果关系或有效资产预测。' : '该周期未发布资产统计或旧映射须重建，只展示阻断说明。',
    },
  }
}

export const assetHistoryAction = {
  id: 'research.configure-asset-history', available: true,
  label: '查询单周期历史资产统计（不刷新数据；省略筛选恢复该周期默认，省略assetId关闭详情）',
  inputSchema: {
    type: 'object', required: ['cycleId'], additionalProperties: false,
    properties: {
      cycleId: { type: 'string', enum: ['C1', 'C2', 'C3', 'C4', 'C5', 'C6', 'C7'] },
      phase: { type: 'string', enum: ['recovery', 'expansion', 'downturn', 'slowdown', 'contraction'], description: 'C4放缓为downturn；其余映射为slowdown。阻断周期只可传cycleId。' },
      query: { type: 'string' }, category: { type: 'string' },
      confidence: { type: 'string', enum: ['全部', 'high', 'medium', 'low'] },
      sortKey: { type: 'string', enum: ['impact', 'spread', 'oos', 'name'], description: 'impact仅C4，spread仅其他历史映射' },
      assetId: { type: 'string', description: '使用availableHistoryCycles中目标cycleId的assets[].id；各周期ID可不同，不可拿当前周期ID替换目标ID。必须在目标筛选内。' },
    },
  },
}

export function createAssetHistoryControls(apply: (state: AssetHistoryState) => void) {
  let current: AssetHistoryState | null = null
  let data: AssetStatisticsData | null = null
  type Context = ReturnType<typeof assetHistoryView>['context']
  let pending: { target: AssetHistoryState; resolve: (result: Context) => void; reject: (error: Error) => void; timer: ReturnType<typeof setTimeout> } | undefined
  const matches = (a: AssetHistoryState, b: AssetHistoryState) => (Object.keys(a) as (keyof AssetHistoryState)[]).every(key => a[key] === b[key])
  const cancel = () => {
    if (!pending) return
    clearTimeout(pending.timer)
    pending.reject(new Error('页面已切换、被手动修改或等待超时，结果未确认'))
    pending = undefined
  }
  return {
    cancel,
    commit(state: AssetHistoryState, loaded: AssetStatisticsData | null) {
      current = state; data = loaded
      if (pending && data && matches(state, pending.target)) {
        clearTimeout(pending.timer)
        pending.resolve(assetHistoryView(data, state).context)
        pending = undefined
      }
    },
    async perform(actionId: string, input: Record<string, unknown>): Promise<Context> {
      if (actionId !== assetHistoryAction.id) throw new Error('当前页面未注册该操作')
      if (!current || !data) throw new Error('历史统计数据尚未加载')
      if (pending) throw new Error('已有页面操作等待确认，请勿重复执行')
      if (typeof input.cycleId !== 'string' || !/^C[1-7]$/.test(input.cycleId) || !(input.cycleId in data.publication)
        || Object.entries(input).some(([key, value]) => !(key in assetHistoryAction.inputSchema.properties) || typeof value !== 'string')) throw new Error('历史查询参数无效')
      const { assetId, ...filters } = input
      const target = { ...initialAssetHistory(input.cycleId), ...filters, selectedId: (assetId as string | undefined) ?? null } as AssetHistoryState
      const view = assetHistoryView(data, target)
      if (!view.available && Object.keys(input).some(key => key !== 'cycleId')) throw new Error('该周期统计被阻断，只可切换查看说明，不能设置隐藏筛选或资产')
      if (view.available && (!Object.keys(view.phaseLabels).includes(target.phase)
        || !['全部', 'high', 'medium', 'low'].includes(target.confidence)
        || !(target.cycleId === 'C4' ? ['impact', 'oos', 'name'] : ['spread', 'oos', 'name']).includes(target.sortKey)
        || !view.categories.includes(target.category))) throw new Error('相位、类别或排序不属于目标周期的可见控件')
      if (target.selectedId !== null && !view.selected) throw new Error('目标资产不在筛选结果中')
      if (matches(current, target)) return view.context
      return new Promise((resolve, reject) => {
        pending = { target, resolve, reject, timer: setTimeout(cancel, 5000) }
        try { apply(target) } catch { cancel() }
      })
    },
  }
}
