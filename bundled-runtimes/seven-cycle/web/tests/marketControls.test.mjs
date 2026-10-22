import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'

const exports = {}
vm.runInNewContext(ts.transpileModule(readFileSync(new URL('../src/lib/marketControls.ts', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText, { exports, setTimeout, clearTimeout })
const { createMarketControls, marketControlAction, marketComparison } = exports
const plain = value => JSON.parse(JSON.stringify(value))
const tracks = [
  { id: 'sp500', dates: ['2020-01', '2021-08', '2026-07', '2026-08'], governedStack: [1, 2, 3, 4] },
  { id: 'dxy', dates: ['2026-07', '2026-08'], governedStack: [0, null] },
]
const initial = { view: 'heatmap', timeRange: '5y', selectedTrackIds: ['sp500', 'dxy'], forecastLayer: 'history-only', comparisonDate: '2026-07' }
const request = { view: '2d', timeRange: '20y', trackIds: ['dxy'], showForecast: true }
const target = { view: '2d', timeRange: '20y', selectedTrackIds: ['dxy'], forecastLayer: 'history-and-forecast', comparisonDate: null }

test('page and action share the window, complete-month fallback and partial-month selection', () => {
  assert.deepEqual(plain(marketComparison(tracks, '5y', null)), {
    visible: ['2026-07', '2026-08'], newest: '2026-08', effective: '2026-07',
  })
  assert.equal(marketComparison(tracks, '5y', '2026-08').effective, '2026-08')
  assert.equal(marketComparison(tracks, '5y', '2020-01').effective, '2026-07')
  assert.equal(marketComparison(tracks, 'all', '2020-01').effective, '2020-01')
  assert.equal(marketComparison([], 'all', null).effective, '')
})

test('action waits for the full committed configuration; same state is idempotent', async () => {
  const changes = []
  const controls = createMarketControls(state => changes.push(plain(state)))
  controls.commit(initial, tracks)
  let completed = false
  const pending = controls.perform(marketControlAction.id, request).then(result => { completed = true; return result })
  assert.deepEqual(changes, [target])
  controls.commit({ ...target, selectedTrackIds: ['sp500'] }, tracks)
  await Promise.resolve()
  assert.equal(completed, false)
  controls.commit(target, tracks)
  assert.deepEqual(plain(await pending), target)
  assert.deepEqual(plain(await controls.perform(marketControlAction.id, request)), target)
  assert.equal(changes.length, 1)
})

test('invalid IDs, hidden forecast and out-of-window dates never change the view', async () => {
  let changes = 0
  const controls = createMarketControls(() => changes++)
  await assert.rejects(controls.perform(marketControlAction.id, request), /尚未加载/)
  controls.commit(initial, tracks)
  for (const trackIds of [[], ['unknown'], ['sp500', 'sp500'], [null], Array(25).fill('sp500')]) {
    await assert.rejects(controls.perform(marketControlAction.id, { ...request, trackIds }), /轨道/)
  }
  await assert.rejects(controls.perform(marketControlAction.id, { ...request, view: 'heatmap' }), /只显示历史/)
  await assert.rejects(controls.perform(marketControlAction.id, { ...request, comparisonDate: '2026-07' }), /对比月份/)
  await assert.rejects(controls.perform(marketControlAction.id, {
    view: 'heatmap', timeRange: '5y', trackIds: ['sp500'], comparisonDate: '2020-01',
  }), /对比月份/)
  await assert.rejects(controls.perform(marketControlAction.id, { ...request, code: 'anything' }), /无效/)
  assert.equal(changes, 0)
})

test('manual edits and navigation cancel pending work; late commits do not revive it', async () => {
  const controls = createMarketControls(() => {})
  controls.commit(initial, tracks)
  const pending = controls.perform(marketControlAction.id, request)
  await assert.rejects(controls.perform(marketControlAction.id, request), /等待确认/)
  controls.cancel()
  controls.commit(target, tracks)
  await assert.rejects(pending, /结果未确认/)
})

test('heatmap acknowledgement reports the actual fallback month, not a hidden request', async () => {
  let applied
  const controls = createMarketControls(state => { applied = plain(state) })
  controls.commit(target, tracks)
  const pending = controls.perform(marketControlAction.id, { view: 'heatmap', timeRange: '5y', trackIds: ['sp500', 'dxy'] })
  assert.equal(applied.comparisonDate, '2026-07')
  assert.equal(applied.forecastLayer, 'history-only')
  controls.commit(initial, tracks)
  assert.deepEqual(plain(await pending), initial)
})
