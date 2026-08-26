import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import ts from 'typescript'

const root = process.cwd()
const read = (path) => readFileSync(join(root, path), 'utf8')
const json = (path) => JSON.parse(read(path))
const assert = (condition, message) => { if (!condition) throw new Error(message) }

function loadTypeScriptModule(path) {
  const compiled = ts.transpileModule(read(path), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    fileName: path,
  }).outputText
  const loadedModule = { exports: {} }
  new Function('module', 'exports', 'require', compiled)(loadedModule, loadedModule.exports, () => {
    throw new Error(`Unexpected dependency while loading ${path}`)
  })
  return loadedModule.exports
}

const suite = json('desk/suite.json')
const dataService = json('desk/data-service.json')
const view = json('desk/views/fund-selection.view.json')
const bridgeSource = read('lib/newma-desk/bridge.ts')
const contextSource = read('lib/newma-desk/context.ts')
const moduleSource = read('app/(desk)/mod/fund-research/[workspace]/FundResearchDeskModule.tsx')
const adapterSource = read('lib/newma-desk/use-fund-research-desk-adapter.ts')
const architecture = read('docs/architecture/professional-fund-research-module-v2.md')

assert(suite.schemaVersion === '1.0', 'Suite schemaVersion must be 1.0')
assert(suite.id === 'professional-fund-research-suite', 'Suite ID must remain stable')
assert(suite.name === '基金选择助手', 'Suite must use the simple product name')
assert(suite.runtime.defaultBaseUrl === 'http://127.0.0.1:3000', 'Suite must use the active frontend port')
assert(!JSON.stringify(suite).includes('127.0.0.1:3001'), 'Fund Suite must never use the Orchestra port')
assert(suite.agentWorkspace === undefined, 'Standalone project must not claim the Newma Desk source tree')
assert(suite.manifest.schemaVersion === '1.1', 'Manifest must use version 1.1')
assert(suite.manifest.compatibility.level === 3, 'Suite pages must keep Level 3 Context')
assert(suite.manifest.navigation.directory?.id === suite.id, 'Suite must remain one complete Desk project')
assert(suite.manifest.navigation.project?.id === 'fund-research', 'Suite must use the standard fund-research domain')
assert(suite.pages.length === 6, 'Suite must expose six focused pages')
assert(suite.pages.find((page) => page.id === 'fund-recommendations')?.name === '基金推荐', 'Suite must use the current recommendation name')

const expectedPages = [
  ['fund-discover', '/mod/fund-research/discover'],
  ['fund-research-library', '/mod/fund-research/research'],
  ['fund-ai-analysis', '/mod/fund-research/analysis'],
  ['fund-recommendations', '/mod/fund-research/recommendations'],
  ['fund-attribution', '/mod/fund-research/advanced'],
  ['fund-portfolio', '/mod/fund-research/portfolio'],
]
assert(JSON.stringify(suite.pages.map((page) => [page.id, page.route])) === JSON.stringify(expectedPages), 'Suite page catalog drifted')

const expectedActions = [
  'fund.search',
  'fund.research.snapshot',
  'fund.compare',
  'fund.attribution.run',
  'fund.analysis.run',
  'fund.recommendations.list',
]
assert(JSON.stringify(Object.keys(suite.manifest.actions)) === JSON.stringify(expectedActions), 'Suite action catalog drifted')

const permissions = new Set(suite.manifest.permissions)
for (const [actionId, action] of Object.entries(suite.manifest.actions)) {
  assert(permissions.has(action.permission), `${actionId} permission is not declared`)
  assert(action.binding.type === 'data', `${actionId} must bind to a real data capability`)
  assert(action.binding.service === 'fund-analysis-data', `${actionId} must use the isolated fund data service`)
  assert(dataService.capabilities[action.binding.capability], `${actionId} capability missing from data-service.json`)
}

assert(dataService.id === 'fund-analysis-data', 'Desk data service must use the project-scoped ID')
assert(dataService.baseUrl === 'http://127.0.0.1:8005/api/newma-desk', 'Data service must use the real fund backend')
assert(dataService.healthPath === '/health', 'Health path must resolve below the Newma backend adapter')
assert(dataService.capabilities['fund.compare'].path === '/fund-compare', 'Desk compare must use the fixed Newma capability route')
assert(read('backend/routes/newma_desk.py').includes('FundBrowserService().browse'), 'Desk fund search must call the real fund browser service')
assert(read('backend/routes/newma_desk.py').includes('PerformanceAttributionService().analyze'), 'Desk attribution must call the real attribution service')
assert(!existsSync(join(root, 'scripts/register_newma_desk.mjs')), 'Fund project must not publish itself into Desk')
assert(!read('package.json').includes('newma:register'), 'Package scripts must not bypass desk-mods review')
assert(!JSON.stringify(suite).match(/DATABASE_URL|api[_-]?key|secret|token/i), 'Suite must not expose credentials')
assert(!JSON.stringify(dataService).match(/DATABASE_URL|api[_-]?key|secret|token/i), 'Data descriptor must not expose credentials')

assert(view.version === '1.0', 'View must use ViewSpec 1.0')
assert(view.blocks.some((block) => block.type === 'table'), 'View must expose capabilities as a table')
assert(view.blocks.some((block) => block.type === 'actions'), 'View must expose actions')

const forbidden = ['fund.due-diligence.evaluate', 'fund.monitoring.review', 'fund.methodology.audit', '准入初筛', '尽调工作台', '监控复核', '每日基金研究驾驶舱']
const activeDeskSurface = [JSON.stringify(suite), contextSource, moduleSource, adapterSource].join('\n')
for (const phrase of forbidden) assert(!activeDeskSurface.includes(phrase), `Removed Desk concept returned: ${phrase}`)

for (const phrase of [
  "'discover'", "'research'", "'analysis'", "'recommendations'", "'advanced'",
  'buildFundResearchPageContext', 'visibleBlocks', 'capabilities', 'no-trading', 'no-investment-decision',
]) assert(contextSource.includes(phrase), `Context missing: ${phrase}`)

for (const phrase of [
  'data-vibe-page="1.0"', 'data-vibe-mod-id={workspace.modId}',
  'security.selected', 'publishContext', '{children}',
]) assert([moduleSource, adapterSource].some((source) => source.includes(phrase)), `Desk module missing: ${phrase}`)

const bridge = loadTypeScriptModule('lib/newma-desk/bridge.ts')
const hello = bridge.buildHelloMessage('fund-discover')
assert(hello.type === 'vibedesk:hello', 'Bridge must start with vibedesk:hello')
assert(hello.capabilities.includes('context') && hello.capabilities.includes('theme'), 'Bridge must advertise context and theme')

const init = {
  type: 'vibedesk:init', protocolVersion: '1.0', instanceId: 'instance-1', modId: 'fund-discover',
  user: { id: 'user-1' }, workspace: { id: 'workspace-1' },
  environment: { theme: 'dark', locale: 'zh-CN', timezone: 'Asia/Shanghai' },
  gateways: { actions: 'http://127.0.0.1:8911/api/actions', agent: 'http://127.0.0.1:8911/api/agent', model: 'http://127.0.0.1:8911/api/model', data: 'http://127.0.0.1:8911/api/data' },
  grants: { permissions: ['research.read'], actions: ['fund.search'] },
}
assert(bridge.isDeskInitMessage(init, 'fund-discover'), 'Bridge must validate a correct init message')
assert(!bridge.isDeskInitMessage({ ...init, modId: 'wrong-mod' }, 'fund-discover'), 'Bridge must reject a mismatched modId')
assert(bridge.buildAckMessage(init).instanceId === init.instanceId, 'Bridge must acknowledge the negotiated instance')

const eventPayload = bridge.buildFundSelectionEventPayload({ symbol: ' 000390.of ', name: '华安动态灵活配置', assetType: 'fund' })
assert(eventPayload.symbol === '000390.OF', 'Fund event symbol must be normalized')
assert(eventPayload.assetType === 'fund' && eventPayload.market === 'CN', 'Fund event must follow security.selected')

for (const phrase of ['window.location.ancestorOrigins', 'message.source !== window.parent', 'message.origin !== parentOrigin', 'vibedesk:context-request', 'vibedesk:action-request']) {
  assert(bridgeSource.includes(phrase), `Bridge contract missing: ${phrase}`)
}

assert(architecture.includes('不包含准入工作流、尽调、持续监控、投资决策'), 'Architecture must record the removed product scope')
console.log('OK fund selection Suite passes Newma Desk compatibility checks')
