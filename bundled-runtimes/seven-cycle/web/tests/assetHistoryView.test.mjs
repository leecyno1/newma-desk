import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'

const exports = {}
vm.runInNewContext(ts.transpileModule(readFileSync(new URL('../src/lib/assetHistoryView.ts', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText, { exports, setTimeout, clearTimeout })
const { assetHistoryView, initialAssetHistory, assetHistoryAction, createAssetHistoryControls } = exports
// Synthetic control states, not a mutable research release or investment evidence.
const oil = { asset_id: '商品||原油', name: '原油', category: '商品', confidence: 'low',
  oos_r2: -0.1, impact_bps_per_1sigma: 12, phase_stats: { recovery: { count: 2, annual_return: 0.03 } } }
const mappedOil = { assetId: '商品::原油', name: '原油', category: '商品', confidence: 'low', eligible: true,
  oosR2: -0.2, phaseStats: { contraction: { count: 3, annualReturn: -0.04 } } }
const data = {
  publication: Object.fromEntries(['C1', 'C2', 'C3', 'C4', 'C5', 'C6', 'C7'].map(id => [id, id === 'C4' ? 'formal' : 'blocked'])),
  phase_labels: { recovery: '复苏', expansion: '扩张', downturn: '放缓', contraction: '收缩' },
  assets: [oil],
  researchMappings: Object.fromEntries(['C1', 'C3', 'C6'].map(id => [id, {
    assetMapping: { status: 'legacy_mapping_rebuild_required', assets: [mappedOil] },
  }])),
  stateMappings: { C5: { status: 'research_association_only', kind: 'state_association', currentState: 'neutral',
    phaseLabels: { recovery: '流动性修复', expansion: '流动性扩张', slowdown: '流动性降温', contraction: '流动性收紧' },
    assets: [mappedOil, { ...mappedOil, assetId: '商品::隐藏样本', name: '隐藏样本', eligible: false }],
  } },
}

test('C4 and other mappings use their actual phase labels and distinct row identities', () => {
  const c4 = assetHistoryView(data, initialAssetHistory())
  const c5 = assetHistoryView(data, initialAssetHistory('C5'))
  assert.equal(c4.rows.length, data.assets.length)
  assert.equal(c5.rows.length, data.stateMappings.C5.assets.filter(a => a.eligible).length)
  assert.equal(c5.context.phaseLabel, '流动性修复')
  assert.equal(c5.context.layer, 'historical-state-association')
  assert.equal(c5.context.currentState, data.stateMappings.C5.currentState)
  const oilC4 = c4.context.visibleAssets.find(asset => asset.name === '原油')
  const oilC5 = c5.context.visibleAssets.find(asset => asset.name === '原油')
  assert.notEqual(oilC4.id, oilC5.id)
  assert.equal(oilC5.id, data.stateMappings.C5.assets.find(asset => asset.name === '原油').assetId)
  const target = { ...initialAssetHistory('C5'), phase: 'contraction', selectedId: c5.rows[0].assetId }
  const view = assetHistoryView(data, target)
  assert.equal(view.context.phaseLabel, '流动性收紧')
  assert.equal(view.context.selectedAsset.phaseStatistics, view.selected.phaseStats.contraction)
})

test('C1/C3/C6 never expose hidden legacy rows, phases or stale selections', () => {
  for (const cycleId of ['C1', 'C3', 'C6']) {
    const view = assetHistoryView(data, { ...initialAssetHistory(cycleId), selectedId: data.assets[0].asset_id })
    assert.equal(view.available, false)
    assert.equal(view.context.phase, null)
    assert.equal(view.context.filters, null)
    assert.equal(view.context.visibleAssetCount, 0)
    assert.equal(view.context.selectedAsset, null)
  }
})

test('empty filters drop the previous selection without fabricating zero statistics', () => {
  const state = { ...initialAssetHistory(), selectedId: data.assets[0].asset_id }
  assert.ok(assetHistoryView(data, state).selected)
  const empty = assetHistoryView(data, { ...state, query: 'no-such-asset-acceptance' })
  assert.equal(empty.rows.length, 0)
  assert.equal(empty.context.selectedAsset, null)
})

test('a published historical mapping is queryable even when current prediction remains blocked', () => {
  const released = { ...data, researchMappings: { ...data.researchMappings,
    C3: { assetMapping: { ...data.stateMappings.C5, kind: 'phase_mapping', status: 'research_mapping_candidate' } },
  } }
  const view = assetHistoryView(released, { ...initialAssetHistory('C3'), selectedId: mappedOil.assetId })
  assert.equal(released.publication.C3, 'blocked')
  assert.equal(view.available, true)
  assert.equal(view.context.status, 'research_mapping_candidate')
  assert.equal(view.context.layer, 'research-phase-mapping')
  assert.equal(view.context.visibleAssetCount, 1)
  assert.equal(view.context.selectedAsset.id, mappedOil.assetId)
})

test('historical query resolves after commit and returns selected historical statistics', async () => {
  let applied, complete = false
  const controls = createAssetHistoryControls(state => { applied = state })
  const initial = initialAssetHistory()
  controls.commit(initial, data)
  const asset = assetHistoryView(data, initialAssetHistory('C5')).rows[0]
  const operation = controls.perform(assetHistoryAction.id, { cycleId: 'C5', phase: 'contraction', assetId: asset.assetId })
    .then(result => { complete = true; return result })
  controls.commit(initial, data)
  await Promise.resolve()
  assert.equal(complete, false)
  controls.commit(applied, data)
  const result = await operation
  assert.equal(result.cycleId, 'C5')
  assert.equal(result.selectedAsset.id, asset.assetId)
  assert.equal(result.selectedAsset.phaseStatistics, asset.phaseStats.contraction)
  const repeated = await controls.perform(assetHistoryAction.id, { cycleId: 'C5', phase: 'contraction', assetId: asset.assetId })
  assert.equal(repeated.selectedAsset.id, asset.assetId)
})

test('wrong-cycle controls and hidden or filtered-out assets cannot change the page', async () => {
  let changes = 0
  const controls = createAssetHistoryControls(() => changes++)
  await assert.rejects(controls.perform(assetHistoryAction.id, { cycleId: 'C4' }), /尚未加载/)
  controls.commit(initialAssetHistory(), data)
  for (const input of [
    { cycleId: 'C4', phase: 'slowdown' }, { cycleId: 'C5', phase: 'downturn' },
    { cycleId: 'C4', sortKey: 'spread' }, { cycleId: 'C5', sortKey: 'impact' },
    { cycleId: 'C4', category: 'unknown' }, { cycleId: 'C4', confidence: 'unknown' },
    { cycleId: 'C4', query: true }, { cycleId: 'C9' }, { cycleId: 'C4', hidden: 'yes' },
    { cycleId: 'C3', query: '' }, { cycleId: 'C1', phase: 'recovery' },
    { cycleId: 'C4', assetId: data.assets[0].asset_id, query: 'no-such-asset-acceptance' },
  ]) await assert.rejects(controls.perform(assetHistoryAction.id, input))
  assert.equal(changes, 0)
})

test('blocked cycle selection succeeds as a blocked page; cancelled work never revives', async () => {
  let applied
  const controls = createAssetHistoryControls(state => { applied = state })
  controls.commit(initialAssetHistory(), data)
  const blocked = controls.perform(assetHistoryAction.id, { cycleId: 'C3' })
  controls.commit(applied, data)
  assert.equal((await blocked).status, 'legacy_mapping_rebuild_required')
  const operation = controls.perform(assetHistoryAction.id, { cycleId: 'C5' })
  await assert.rejects(controls.perform(assetHistoryAction.id, { cycleId: 'C4' }), /等待确认/)
  controls.cancel()
  controls.commit(applied, data)
  await assert.rejects(operation, /结果未确认/)
})
