import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'

const source = readFileSync(new URL('../src/lib/vibedesk.ts', import.meta.url), 'utf8')
const code = ts.transpileModule(source.replaceAll('import.meta.env', '__env'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText
const host = 'http://127.0.0.1:5892'
const modId = 'seven-cycle-research'
const flush = () => new Promise(resolve => setImmediate(resolve))
const page = id => ({ view: { id, title: id }, visibleBlocks: [], selection: {}, filters: {}, data: {}, actions: [], tasks: [] })

function bridge({ configured = host, embedded = true, theme } = {}) {
  const messages = []
  const listeners = new Map()
  const root = {
    dataset: theme ? { theme } : {},
    style: { setProperty() {}, removeProperty() {} },
    classList: { toggle() {} },
  }
  const parent = { postMessage: (message, origin) => messages.push({ ...message, origin }) }
  const window = {
    parent,
    self: {},
    top: {},
    location: { origin: 'http://127.0.0.1:14174', ancestorOrigins: ['https://untrusted.example'] },
    addEventListener: (name, handler) => listeners.set(name, handler),
    dispatchEvent() {},
    matchMedia: () => ({ matches: true, addEventListener() {} }),
  }
  if (!embedded) window.top = window.self
  const exports = {}
  vm.runInNewContext(code, {
    exports, window,
    document: { documentElement: root, referrer: 'https://untrusted.example/embed' },
    __env: { VITE_NEWMA_DESK_PARENT_ORIGIN: configured },
    URL, crypto: { randomUUID: () => 'published-context' },
    CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options.detail } },
  })
  const send = (data, origin = host, sender = parent) => listeners.get('message')?.({ data, origin, source: sender })
  const init = (instanceId = 'first', extra = {}, origin = host) => send({
    type: 'vibedesk:init', modId, instanceId, protocolVersion: '1.0', environment: { theme: 'dark' }, ...extra,
  }, origin)
  const request = (type = 'context', extra = {}) => send({
    type: `vibedesk:${type}-request`, modId, instanceId: 'first', requestId: 'read-1', maxBytes: 65536, ...extra,
  })
  return { exports, messages, root, init, request, send }
}

test('standalone defaults to light and preserves an explicit theme', () => {
  assert.equal(bridge({ embedded: false }).root.dataset.theme, 'light')
  assert.equal(bridge({ embedded: false, theme: 'dark' }).root.dataset.theme, 'dark')
  assert.equal(bridge({ embedded: false }).exports.getPageSessionScope(), 'standalone')
})

test('only validated host identity selects a view session; reinit of the same identity does not reset it', () => {
  const b = bridge()
  const scopes = []
  const unsubscribe = b.exports.subscribePageSession(() => scopes.push(b.exports.getPageSessionScope()))
  const identity = { user: { id: 'synthetic-user' }, workspace: { id: 'workspace-A' } }
  b.init('bad', identity, 'https://untrusted.example')
  assert.equal(scopes.length, 0)
  b.init('first', identity)
  assert.equal(scopes[0], JSON.stringify([host, 'synthetic-user', 'workspace-A', modId]))
  b.exports.registerVibeDeskContextProvider(() => page('assets'))
  b.init('first', { ...identity, environment: { theme: 'light' } })
  assert.equal(scopes.length, 1)
  b.init('second', { ...identity, workspace: { id: 'workspace-B' } })
  assert.equal(scopes.length, 2)
  unsubscribe()
})

test('referrer, ancestor and sender-declared gateway cannot authorize a parent', () => {
  // Explicit empty configuration selects the same-origin default.
  const local = bridge({ configured: '' })
  local.send({ type: 'vibedesk:config', gatewayOrigin: 'https://untrusted.example', theme: 'dark' }, 'https://untrusted.example')
  local.init('bad', {}, 'https://untrusted.example')
  assert.equal(local.root.dataset.theme, 'light')
  assert.ok(local.messages.every(m => m.origin === 'http://127.0.0.1:14174'))
  assert.equal(local.messages.some(m => m.type === 'vibedesk:ack'), false)
})

test('wrong source, origin, mod and empty instance cannot initialize or change theme', () => {
  const b = bridge()
  b.init('first', { modId: 'other' })
  b.init(' ')
  b.init('first', {}, 'https://untrusted.example')
  b.send({ type: 'vibedesk:config', theme: 'dark' }, host, {})
  assert.equal(b.messages.some(m => m.type === 'vibedesk:ack'), false)
  assert.equal(b.root.dataset.theme, 'light')
  b.init()
  assert.equal(b.root.dataset.theme, 'dark')
  assert.equal(b.messages.at(-1).type, 'vibedesk:ack')
})

test('current context responds with matching identity; wrong instance is ignored', async () => {
  const b = bridge()
  b.exports.registerVibeDeskContextProvider(() => page('cycles'))
  b.init()
  b.request('context', { instanceId: 'other' })
  await flush()
  assert.equal(b.messages.some(m => m.type === 'vibedesk:context'), false)
  b.request()
  await flush()
  const result = b.messages.at(-1)
  assert.equal(result.context.view.id, 'cycles')
  assert.equal(result.requestId, 'read-1')
  assert.equal(result.instanceId, 'first')
})

test('pending context cannot be relabeled as a new host instance', async () => {
  const b = bridge()
  let resolve
  b.exports.registerVibeDeskContextProvider(() => new Promise(done => { resolve = done }))
  b.init()
  b.request()
  b.init('second')
  resolve(page('old-page'))
  await flush()
  assert.equal(b.messages.some(m => m.type === 'vibedesk:context'), false)
})

test('page replacement discards pending context and reports publication as superseded', async () => {
  const b = bridge()
  let resolve
  const unregister = b.exports.registerVibeDeskContextProvider(() => new Promise(done => { resolve = done }))
  b.init()
  const publishing = b.exports.publishVibeDeskContext()
  unregister()
  b.exports.registerVibeDeskContextProvider(() => page('cycles-C5'))
  resolve(page('market'))
  assert.equal(await publishing, false)
  assert.equal(b.messages.some(m => m.type === 'vibedesk:context'), false)
  assert.equal(await b.exports.publishVibeDeskContext(), true)
  assert.equal(b.messages.at(-1).context.view.id, 'cycles-C5')
})

test('pending visual capture is discarded after page replacement or host reinit', async () => {
  for (const change of ['page', 'instance']) {
    const b = bridge()
    let resolve
    const unregister = b.exports.registerVibeDeskVisualCaptureProvider(() => new Promise(done => { resolve = done }))
    b.init()
    b.request('visual-context')
    if (change === 'page') unregister()
    else b.init('second')
    resolve({ dataUrl: 'data:image/png;base64,YQ==', width: 1, height: 1 })
    await flush()
    assert.equal(b.messages.some(m => m.type === 'vibedesk:visual-context'), false)
  }
})

test('current visual capture returns a matched result', async () => {
  const b = bridge()
  b.exports.registerVibeDeskVisualCaptureProvider(() => ({ dataUrl: 'data:image/png;base64,YQ==', width: 1, height: 1 }))
  b.init()
  b.request('visual-context')
  await flush()
  assert.equal(b.messages.at(-1).ok, true)
  assert.equal(b.messages.at(-1).instanceId, 'first')
})

const actionRequest = {
  type: 'vibedesk:ui-action-request', modId, instanceId: 'first', requestId: 'action-1',
  actionId: 'research.select-cycle', input: { cycleId: 'C5' },
}

test('UI actions require session grants and a handler on the current page', async () => {
  const b = bridge()
  let calls = 0
  const unregister = b.exports.registerVibeDeskUiActionHandler(() => { calls += 1 })
  b.init()
  b.send(actionRequest)
  assert.equal(b.messages.at(-1).error.code, 'action_not_granted')
  assert.equal(calls, 0)
  b.init('first', { grants: { actions: [actionRequest.actionId] } })
  unregister()
  b.send(actionRequest)
  assert.equal(b.messages.at(-1).error.code, 'handler_unavailable')
})

test('UI success waits for operation completion and publishes fresh context first', async () => {
  const b = bridge()
  let resolve
  let selected = 'C4'
  b.exports.registerVibeDeskContextProvider(() => page(selected))
  b.exports.registerVibeDeskUiActionHandler(() => new Promise(done => { resolve = done }))
  b.init('first', { grants: { actions: [actionRequest.actionId] } })
  b.send(actionRequest)
  assert.equal(b.messages.some(m => m.type === 'vibedesk:ui-action-result'), false)
  selected = 'C5'
  resolve({ cycleId: selected })
  await flush()
  assert.equal(b.messages.at(-2).context.view.id, 'C5')
  assert.equal(b.messages.at(-1).ok, true)
  assert.equal(b.messages.at(-1).requestId, 'action-1')
})

test('UI actions reject invalid input and do not relabel late results', async () => {
  const b = bridge()
  let resolve
  b.exports.registerVibeDeskUiActionHandler(() => new Promise(done => { resolve = done }))
  b.init('first', { grants: { actions: [actionRequest.actionId] } })
  b.send({ ...actionRequest, input: [] })
  assert.equal(b.messages.at(-1).error.code, 'invalid_input')
  b.messages.length = 0
  b.send(actionRequest)
  b.init('second')
  resolve({ cycleId: 'C5' })
  await flush()
  assert.equal(b.messages.some(m => m.type === 'vibedesk:ui-action-result'), false)
})
