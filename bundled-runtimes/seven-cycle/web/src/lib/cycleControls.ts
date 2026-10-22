export const cycleControlAction = {
  id: 'research.select-cycle',
  label: '切换研究周期并设置模型细节展示（仅页面查询，不刷新数据）',
  available: true,
  inputSchema: {
    type: 'object', required: ['cycleId'], additionalProperties: false,
    properties: {
      cycleId: { type: 'string', enum: ['C1', 'C2', 'C3', 'C4', 'C5', 'C6', 'C7'] },
      evidenceDetailsExpanded: { type: 'boolean', default: false },
    },
  },
}

export type CycleViewState = { cycleId: string; cycleName: string; evidenceDetailsExpanded: boolean }

// Completion is driven by the React page's committed state, not by setState.
export function createCycleControls(apply: (cycleId: string, expanded: boolean) => void) {
  let current: CycleViewState | null = null
  let pending: {
    cycleId: string; expanded: boolean; resolve: (state: CycleViewState) => void
    reject: (error: Error) => void; timer: ReturnType<typeof setTimeout>
  } | undefined
  const cancel = (message = '页面已切换或被手动修改，操作结果未确认') => {
    if (!pending) return
    clearTimeout(pending.timer)
    pending.reject(new Error(message))
    pending = undefined
  }
  return {
    cancel,
    commit(state: CycleViewState | null) {
      current = state
      if (pending && state?.cycleId === pending.cycleId && state.evidenceDetailsExpanded === pending.expanded) {
        clearTimeout(pending.timer)
        pending.resolve({ ...state })
        pending = undefined
      }
    },
    perform(actionId: string, input: Record<string, unknown>): Promise<CycleViewState> {
      if (actionId !== cycleControlAction.id) return Promise.reject(new Error('当前页面未注册该操作'))
      if (typeof input.cycleId !== 'string' || !/^C[1-7]$/.test(input.cycleId)
        || Object.keys(input).some(key => !['cycleId', 'evidenceDetailsExpanded'].includes(key))
        || (input.evidenceDetailsExpanded !== undefined && typeof input.evidenceDetailsExpanded !== 'boolean')) {
        return Promise.reject(new Error('请选择C1至C7，模型细节状态必须为布尔值'))
      }
      if (!current) return Promise.reject(new Error('周期研究数据尚未加载'))
      if (pending) return Promise.reject(new Error('已有页面操作等待确认，请勿重复执行'))
      const cycleId = input.cycleId
      const expanded = input.evidenceDetailsExpanded === true
      if (current.cycleId === cycleId && current.evidenceDetailsExpanded === expanded) return Promise.resolve({ ...current })
      return new Promise((resolve, reject) => {
        pending = { cycleId, expanded, resolve, reject,
          timer: setTimeout(() => cancel('页面状态更新超时，结果未确认，请检查当前页'), 5000) }
        try { apply(cycleId, expanded) } catch (error) {
          cancel(error instanceof Error ? error.message : '页面状态更新失败')
        }
      })
    },
  }
}
