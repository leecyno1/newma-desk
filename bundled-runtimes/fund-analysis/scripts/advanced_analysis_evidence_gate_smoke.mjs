import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { join } from 'node:path'

const root = fileURLToPath(new URL('..', import.meta.url))
const brinson = readFileSync(join(root, 'backend/lib/brinson/attribution.py'), 'utf8')
const brinsonRoute = readFileSync(join(root, 'backend/routes/brinson.py'), 'utf8')
const barra = readFileSync(join(root, 'backend/lib/barra/factor_calculation.py'), 'utf8')
const barraRoute = readFileSync(join(root, 'backend/routes/barra.py'), 'utf8')
const attributionService = readFileSync(join(root, 'backend/services/performance_attribution_service.py'), 'utf8')
const investmentService = readFileSync(join(root, 'backend/services/investment_analysis_service.py'), 'utf8')
const advancedPage = readFileSync(join(root, 'app/(dashboard)/analysis/advanced/AttributionWorkspace.tsx'), 'utf8')

function assertIncludes(content, expected, label) {
  if (!content.includes(expected)) {
    throw new Error(`${label} missing text: ${expected}`)
  }
}

function assertNotIncludes(content, expected, label) {
  if (content.includes(expected)) {
    throw new Error(`${label} must not include text: ${expected}`)
  }
}

for (const [label, content] of [
  ['brinson attribution', brinson],
  ['barra factor calculation', barra],
]) {
  assertNotIncludes(content, 'import random', label)
  assertNotIncludes(content, 'random.uniform', label)
  assertNotIncludes(content, '_mock_', label)
}

assertNotIncludes(brinson, '_estimate_stock_return', 'brinson must not hash stock codes into fake returns')
assertNotIncludes(brinson, '_estimate_industry_returns', 'brinson must not invent industry returns')
assertNotIncludes(brinson, '_estimate_industry_return', 'brinson must not hard-code benchmark industry returns')
assertIncludes(brinson, 'status": "insufficient_evidence"', 'brinson missing evidence status')
assertIncludes(brinson, '基金行业权重缺失，不能计算 Brinson 配置与选择效应', 'brinson portfolio evidence gate')
assertIncludes(brinson, '基准行业权重缺失，不能计算 Brinson 配置效应', 'brinson benchmark evidence gate')
assertIncludes(brinson, '缺少基准行业收益', 'brinson industry return evidence gate')
assertNotIncludes(brinsonRoute, 'benchmark_return = 0.05', 'brinson route must not hard-code benchmark return')
assertIncludes(brinsonRoute, 'PerformanceAttributionService().analyze', 'legacy brinson route must use unified attribution')
assertIncludes(brinsonRoute, 'replacement_endpoint', 'legacy brinson route must disclose unified replacement')

assertNotIncludes(barra, '默认波动率暴露', 'barra must not default residual volatility exposure')
assertNotIncludes(barra, 'calculate_risk_decomposition', 'legacy barra definitions must not fabricate risk decomposition')
assertNotIncludes(barra, 'get_exposure_result', 'legacy barra definitions must not expose a second calculation path')
assertIncludes(barraRoute, 'PerformanceAttributionService().analyze', 'legacy barra route must use unified attribution')
assertIncludes(barraRoute, 'formal_model_ready', 'legacy barra route must preserve the formal-model evidence gate')

assertIncludes(attributionService, '缺少 {holding_quarter} 持仓，不能解释 {attribution_quarter} 的行业配置与选择效应。', 'unified brinson holding evidence gate')
assertIncludes(attributionService, '基金分类目录缺少有效基准，不能计算 Brinson 行业归因。', 'unified brinson benchmark evidence gate')
assertIncludes(attributionService, '未接入正式 Barra 风格因子库', 'unified barra factor evidence gate')
assertIncludes(attributionService, '缺少可核验的因子协方差矩阵和特异风险', 'unified barra risk evidence gate')

assertNotIncludes(investmentService, 'synthetic_75pct_beta', 'advanced attribution must not synthesize benchmark')
assertNotIncludes(investmentService, 'value * 0.75', 'advanced attribution must not scale fund returns into benchmark')
assertIncludes(investmentService, 'insufficient_benchmark_evidence', 'advanced attribution missing benchmark source')
assertIncludes(investmentService, '补齐可验证基准或同类收益序列后再运行主动归因。', 'advanced attribution missing benchmark recommendation')
assertIncludes(investmentService, '净值收益序列少于 60 个观测，因子镜头不输出正式评分', 'factor lens short sample gate')

assertIncludes(advancedPage, '正式因子缺失时，只展示公开持仓行业暴露', 'advanced page barra evidence warning')
assertIncludes(advancedPage, '净值行为分析只作为补充，不冒充正式模型', 'advanced page model scope warning')
assertIncludes(advancedPage, '这不是 Brinson', 'advanced page supplementary attribution warning')

console.log('OK advanced factor/attribution analysis refuses mock or synthetic evidence')
