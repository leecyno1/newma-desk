import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { join } from 'node:path'

const root = fileURLToPath(new URL('..', import.meta.url))

function assertFile(relativePath) {
  const fullPath = join(root, relativePath)
  if (!existsSync(fullPath)) {
    throw new Error(`Missing required file: ${relativePath}`)
  }
  return readFileSync(fullPath, 'utf8')
}

function assertIncludes(content, expected, label) {
  if (!content.includes(expected)) {
    throw new Error(`${label} missing text: ${expected}`)
  }
}

const factorRoute = assertFile('app/api/investment-analysis/fund/[windCode]/factor-lens/route.ts')
assertIncludes(factorRoute, '/api/investment-analysis/fund/', 'factor lens BFF')

const attributionRoute = assertFile('app/api/investment-analysis/fund/[windCode]/attribution/route.ts')
assertIncludes(attributionRoute, '/api/investment-analysis/fund/', 'attribution BFF')

const unifiedAttributionRoute = assertFile('app/api/attribution/fund/[windCode]/route.ts')
assertIncludes(unifiedAttributionRoute, '/api/attribution/fund/', 'unified attribution BFF')

const advancedPage = assertFile('app/(dashboard)/analysis/advanced/AttributionWorkspace.tsx')
assertIncludes(advancedPage, '业绩归因', 'advanced analysis page')
assertIncludes(advancedPage, 'Barra 风格与风险暴露', 'advanced analysis page')
assertIncludes(advancedPage, '公开持仓统计风险', 'advanced analysis public risk evidence')
assertIncludes(advancedPage, '非正式 Barra', 'advanced analysis model boundary')
assertIncludes(advancedPage, 'Brinson 行业归因', 'advanced analysis page')
assertIncludes(advancedPage, '/api/attribution/fund/', 'advanced page must use unified attribution')
assertIncludes(advancedPage, '已保存归因历史', 'advanced page saved attribution history')
assertIncludes(advancedPage, '只有点击“现场运行”', 'advanced page explicit on-demand run')

const advancedRoute = assertFile('app/(dashboard)/analysis/advanced/page.tsx')
assertIncludes(advancedRoute, "autoRun={query.run === '1'}", 'advanced page must not silently rerun attribution')

const analysisHub = assertFile('app/(dashboard)/analysis/FundAnalysisWorkspace.tsx')
assertIncludes(analysisHub, '/analysis/advanced', 'analysis hub advanced entry')

console.log('OK unified fund attribution frontend BFF and page entry')
