import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'

const exports = {}
vm.runInNewContext(ts.transpileModule(readFileSync(new URL('../src/lib/pageSession.ts', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText, { exports, URL })
const { pageRoute, restorePageRoute, readPageSession, writePageSession, pageChoice, pageFlag, pageText } = exports

test('embedded default entry restores the last page; explicit deep links and standalone URLs win', () => {
  assert.equal(restorePageRoute('/', '/assets?cycle=C5', true), '/assets?cycle=C5')
  assert.equal(restorePageRoute('/?__newma_mod_version=0.1.5', '/assets?cycle=C5', true), '/assets?cycle=C5')
  assert.equal(restorePageRoute('/?cycle=C4&__newma_mod_version=0.1.5', '/assets?cycle=C5', true), '/?cycle=C4')
  assert.equal(restorePageRoute('/cycles?cycle=C2#forecast-extension', '/assets', true), '/cycles?cycle=C2#forecast-extension')
  assert.equal(restorePageRoute('/', '/assets', false), '/')
  assert.equal(restorePageRoute('/forecast', '/assets', false), '/forecast')
})

test('stored navigation cannot leave the project or preserve credentials/unknown URL fields', () => {
  for (const target of ['https://example.org/', '//example.org/', '/\\example.org/', '/unknown']) assert.equal(pageRoute(target), null)
  assert.equal(pageRoute('/assets?cycle=C7&token=do-not-store#unknown'), '/assets?cycle=C7')
  assert.equal(pageRoute('/cycles?cycle=C99'), '/cycles')
})

test('tab session restores public preferences without sharing host/user/workspace scopes', () => {
  const data = new Map()
  const storage = { getItem: key => data.get(key) ?? null, setItem: (key, value) => data.set(key, value) }
  const scope = JSON.stringify(['https://host.test', 'synthetic-user', 'workspace-A', 'seven-cycle-research'])
  writePageSession(storage, scope, { route: '/assets?cycle=C5', views: { 'assets.forecast': { horizon: '3', majorCategory: '商品', onlyQualified: true } } })
  const restored = readPageSession(storage, scope)
  assert.equal(restored.route, '/assets?cycle=C5')
  assert.equal(restored.views['assets.forecast'].horizon, '3')
  for (const other of ['standalone', scope.replace('workspace-A', 'workspace-B'), scope.replace('host.test', 'other.test'), scope.replace('synthetic-user', 'other-user')]) {
    assert.equal(readPageSession(storage, other).route, '/')
    assert.equal(Object.keys(readPageSession(storage, other).views).length, 0)
  }
})

test('unavailable or malformed storage does not stop ordinary browsing', () => {
  const blocked = { getItem() { throw new Error('blocked') }, setItem() { throw new Error('blocked') } }
  assert.equal(readPageSession(blocked, 'test').route, '/')
  assert.doesNotThrow(() => writePageSession(blocked, 'test', { route: '/', views: {} }))
  assert.equal(readPageSession({ getItem: () => '{broken' }, 'test').route, '/')
  assert.equal(pageChoice('invalid', ['1', '3', '6'], '6'), '6')
  assert.equal(pageFlag('false', true), true)
  assert.equal(pageText({ secret: true }), '')
})
