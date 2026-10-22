import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'

const source = readFileSync(new URL('../src/lib/cycleControls.ts', import.meta.url), 'utf8')
const exports = {}
vm.runInNewContext(ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText, { exports, setTimeout, clearTimeout })
const { createCycleControls, cycleControlAction } = exports
const initial = { cycleId: 'C4', cycleName: '库存周期', evidenceDetailsExpanded: false }
const target = { cycleId: 'C5', cycleName: '流动性周期', evidenceDetailsExpanded: true }

test('cycle selection resolves only after the requested view has committed', async () => {
  const changes = []
  const controls = createCycleControls((...input) => changes.push(input))
  controls.commit(initial)
  let completed = false
  const operation = controls.perform(cycleControlAction.id, { cycleId: 'C5', evidenceDetailsExpanded: true })
    .then(result => { completed = true; return result })
  assert.deepEqual(changes, [['C5', true]])
  await Promise.resolve()
  assert.equal(completed, false)
  controls.commit(initial)
  await Promise.resolve()
  assert.equal(completed, false)
  controls.commit(target)
  assert.deepEqual(JSON.parse(JSON.stringify(await operation)), target)
})

test('not-ready, invalid and concurrent requests do not change the page', async () => {
  let changes = 0
  const controls = createCycleControls(() => { changes += 1 })
  await assert.rejects(controls.perform(cycleControlAction.id, { cycleId: 'C5' }), /尚未加载/)
  controls.commit(initial)
  for (const input of [{ cycleId: 'C8' }, { cycleId: 'C5', code: 'anything' }, { cycleId: 'C5', evidenceDetailsExpanded: 'true' }]) {
    await assert.rejects(controls.perform(cycleControlAction.id, input), /C1至C7/)
  }
  assert.equal(changes, 0)
  const pending = controls.perform(cycleControlAction.id, { cycleId: 'C5' })
  await assert.rejects(controls.perform(cycleControlAction.id, { cycleId: 'C7' }), /等待确认/)
  controls.cancel()
  await assert.rejects(pending, /结果未确认/)
  assert.equal(changes, 1)
})

test('already committed selection is idempotent; manual changes cancel pending work', async () => {
  let changes = 0
  const controls = createCycleControls(() => { changes += 1 })
  controls.commit(initial)
  assert.equal((await controls.perform(cycleControlAction.id, { cycleId: 'C4' })).cycleId, 'C4')
  assert.equal(changes, 0)
  const pending = controls.perform(cycleControlAction.id, { cycleId: 'C5' })
  controls.cancel()
  controls.commit(target)
  await assert.rejects(pending, /手动修改/)
})
