import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'

const exports = {}
vm.runInNewContext(ts.transpileModule(readFileSync(new URL('../src/lib/assetForecastView.ts', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText, { exports, setTimeout, clearTimeout })
const { assetForecastView, initialForecastView, createAssetForecastControls, assetForecastAction } = exports
const estimate = (publicationQualified, medianReturn) => ({ publicationQualified, status: publicationQualified ? 'limited' : 'blocked',
  publicationReasonCodes: publicationQualified ? [] : ['did_not_beat_all_baselines'],
  forecast: { medianReturn, probabilityUp: 0.5, conditionalVol: 0.2 }, cycleAttributionStability: { status: 'mixed' } })
const data = { meta: { asOf: '2026-07', assetDataThrough: '2026-07', includedCycles: ['C4', 'C5', 'C7'] },
  governance: { publicationStatus: 'limited' }, caveat: 'synthetic fixture, not investment research', assets: [
    { assetId: 'bond', name: '测试债券', majorCategory: '债券', category: '国债', dataEnd: '2026-06', freshnessStatus: 'source_lag', horizons: { '6': estimate(true, 0), '1': estimate(false, null) } },
    { assetId: 'equity', name: '测试股票', majorCategory: '股票', category: '指数', dataEnd: '2026-07', freshnessStatus: 'current', horizons: { '6': estimate(false, 0.1), '1': estimate(true, 0.05) } },
  ] }

test('the same view supplies displayed rows, fallback selection and publication evidence', () => {
  const view = assetForecastView(data, initialForecastView)
  assert.equal(view.visibleAssets.length, 1)
  assert.equal(view.selected.assetId, 'bond')
  assert.equal(view.context.selectedAsset.forecast.medianReturn, 0)
  assert.equal(view.context.selectedAsset.freshnessRelativeToBuild, 'source_lag')
  assert.equal(view.context.source.assetDataThrough, '2026-07')
  assert.match(view.context.source.refreshPolicy, /不代表今日实时数据/)
  assert.equal(view.context.layer, 'joint-state-forecast')
  const changed = assetForecastView(data, { ...initialForecastView, horizon: '1', selectedId: 'bond' })
  assert.equal(changed.context.selectedAsset.id, 'equity')
  assert.equal(changed.context.horizonMonths, 1)
})

test('blocked research stays explicitly unqualified; empty filters have no ghost selection', () => {
  const view = assetForecastView(data, { ...initialForecastView, onlyQualified: false, selectedId: 'equity' })
  assert.equal(view.context.selectedAsset.estimateUsage, 'research-only-not-adopted')
  assert.equal(view.context.selectedAsset.publicationQualified, false)
  const empty = assetForecastView(data, { ...initialForecastView, majorCategory: '股票', selectedId: 'bond' })
  assert.equal(empty.context.visibleAssetCount, 0)
  assert.equal(empty.context.selectedAsset, null)
  assert.equal(data.assets[0].assetId, 'bond')
})

test('actions resolve only on committed state, returning the actual selected asset', async () => {
  let applied
  let complete = false
  const controls = createAssetForecastControls(value => { applied = value })
  controls.commit(initialForecastView, data)
  const request = controls.perform(assetForecastAction.id, { horizon: '1', assetId: 'equity' }).then(value => { complete = true; return value })
  assert.equal(applied.selectedId, 'equity')
  controls.commit(initialForecastView, data)
  await Promise.resolve()
  assert.equal(complete, false)
  controls.commit(applied, data)
  const result = await request
  assert.equal(result.selectedAsset.id, 'equity')
  assert.equal(result.selectedAsset.forecast.medianReturn, 0.05)
  assert.equal((await controls.perform(assetForecastAction.id, { horizon: '1', assetId: 'equity' })).selectedAsset.id, 'equity')
})

test('unknown or filtered-out assets are rejected instead of selecting a different asset', async () => {
  let changes = 0
  const controls = createAssetForecastControls(() => changes++)
  await assert.rejects(controls.perform(assetForecastAction.id, { horizon: '6' }), /尚未加载/)
  controls.commit(initialForecastView, data)
  for (const input of [{ horizon: '6', assetId: 'equity' }, { horizon: '6', assetId: 'missing' }, { horizon: '6', assetId: 'bond', query: '股票' }]) {
    await assert.rejects(controls.perform(assetForecastAction.id, input), /不在所选期限/)
  }
  await assert.rejects(controls.perform(assetForecastAction.id, { horizon: '12' }), /无效/)
  await assert.rejects(controls.perform(assetForecastAction.id, { horizon: '6', majorCategory: '不存在' }), /未知/)
  await assert.rejects(controls.perform(assetForecastAction.id, { horizon: '6', onlyQualified: 'false' }), /无效/)
  await assert.rejects(controls.perform(assetForecastAction.id, { horizon: '6', selectedId: 'equity' }), /无效/)
  assert.equal(changes, 0)
})

test('manual changes cancel pending requests and do not revive them on a late commit', async () => {
  let applied
  const controls = createAssetForecastControls(value => { applied = value })
  controls.commit(initialForecastView, data)
  const request = controls.perform(assetForecastAction.id, { horizon: '1' })
  await assert.rejects(controls.perform(assetForecastAction.id, { horizon: '1' }), /等待确认/)
  controls.cancel()
  controls.commit(applied, data)
  await assert.rejects(request, /未确认/)
})
