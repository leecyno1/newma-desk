import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import vm from 'node:vm'
import * as jsxRuntime from 'react/jsx-runtime'
import { renderToStaticMarkup } from 'react-dom/server'
import ts from 'typescript'

const code = ts.transpileModule(readFileSync(new URL('../src/pages/AuditPage.tsx', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
}).outputText

function renderSources(c2C3Sources) {
  let provider
  const data = { meta: { asOf: '2026-10', generated: '2026-10-04' }, sources: [],
    governance: { cycles: [] }, calibrations: [], c2C3Sources }
  const exports = {}
  const icon = () => null
  const modules = {
    'react/jsx-runtime': jsxRuntime,
    react: { useEffect: effect => { effect() } },
    'lucide-react': { Archive: icon, Check: icon, ExternalLink: icon, FileClock: icon, ShieldAlert: icon },
    '../components/LoadingState': { default: icon },
    '../components/StatusBadge': { default: icon },
    '../hooks/useResearchData': { useResearchData: () => ({ data }) },
    '../lib/data': { loadAudit() {} },
    '../lib/vibedesk': {
      registerVibeDeskContextProvider: next => { provider = next; return () => {} },
      publishVibeDeskContext: () => Promise.resolve(true),
    },
  }
  vm.runInNewContext(code, { exports, require: name => {
    assert.ok(name in modules, `Unexpected page dependency: ${name}`)
    return modules[name]
  } })
  const html = renderToStaticMarkup(exports.default())
  return { html, context: provider() }
}

test('the audit page displays every World Bank cache and publishes the same source details', () => {
  // Synthetic cache metadata: rendering must not depend on a particular research snapshot.
  const source = { name: 'World Bank WDI', coverage: 'synthetic coverage', role: 'rendering test',
    url: 'https://data.worldbank.org/',
    caches: ['investment', 'growth', 'rates', 'inflation'].map((name, index) => ({
      cache: `data/test/wdi-${name}.json`, cacheUpdated: `2026-07-20T22:11:3${index}+08:00`, bytes: 42 + index,
    })),
  }
  assert.equal(source.caches.length, 4)
  const { html, context } = renderSources([source])
  assert.doesNotMatch(html, /Invalid Date/)
  for (const cache of source.caches) assert.ok(html.includes(cache.cache), cache.cache)
  const actual = context.data.summary.longPanelSources[0]
  assert.equal(actual.name, source.name)
  assert.equal(actual.caches.length, 4)
  assert.deepEqual(Array.from(actual.caches, item => item.cacheUpdated), source.caches.map(item => item.cacheUpdated))
  assert.ok(context.visibleBlocks.some(block => block.id === 'audit-long-panel-sources'))
})

test('the audit page still supports a single cached source', () => {
  const source = { name: 'JST', coverage: '1870–2020', role: 'historical research',
    url: 'https://example.org', cache: 'data/jst.dta', cacheUpdated: '2026-07-20T22:11:22+08:00', bytes: 42 }
  const { html, context } = renderSources([source])
  assert.ok(html.includes(source.cache))
  assert.doesNotMatch(html, /Invalid Date|未记录缓存时间/)
  assert.equal(context.data.summary.longPanelSources[0].caches[0].cacheUpdated, source.cacheUpdated)
})

test('missing or malformed cache times remain unknown rather than becoming dates', () => {
  const { html, context } = renderSources([
    { name: 'missing', caches: [{ cache: 'data/a.json' }] },
    { name: 'invalid', caches: [{ cache: 'data/b.json', cacheUpdated: 'not-a-date' }] },
    { name: 'no cache' },
  ])
  assert.doesNotMatch(html, /Invalid Date|1970/)
  assert.ok(html.includes('未记录缓存时间'))
  assert.ok(html.includes('未提供本地缓存记录'))
  assert.equal(context.data.summary.longPanelSources[0].caches[0].cacheUpdated, null)
  assert.equal(context.data.summary.longPanelSources[1].caches[0].cacheUpdated, null)
  assert.equal(context.data.summary.longPanelSources[2].caches.length, 0)
})
