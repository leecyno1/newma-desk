import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

const root = process.cwd()

function read(relativePath) {
  const fullPath = join(root, relativePath)
  if (!existsSync(fullPath)) throw new Error(`Missing required file: ${relativePath}`)
  return readFileSync(fullPath, 'utf8')
}

function assertIncludes(content, expected, label) {
  if (!content.includes(expected)) throw new Error(`${label} missing: ${expected}`)
}

function assertNotIncludes(content, forbidden, label) {
  if (content.includes(forbidden)) throw new Error(`${label} should not include: ${forbidden}`)
}

const tool = read('lib/research-platform/tools/peer-group-benchmark.ts')
const registry = read('lib/research-platform/tools/registry.ts')
const index = read('lib/research-platform/tools/index.ts')
const comparisonReport = read('lib/fund-comparison-report.ts')
const comparisonReportMarkdown = read('lib/fund-comparison-report-markdown.ts')

assertIncludes(tool, "const toolName = 'peer-group-benchmark'", 'peer benchmark tool declares stable tool name')
assertIncludes(tool, "domain: 'comparison'", 'peer benchmark tool lives in comparison domain')
assertIncludes(tool, 'OpenBB provider/adapter 分层', 'peer benchmark tool records OpenBB reference')
assertIncludes(tool, 'QuantStats/Empyrical 基准对齐后再做绩效比较', 'peer benchmark tool records performance benchmark reference')
assertIncludes(tool, 'FinRobot tool-to-report 编排', 'peer benchmark tool records agent orchestration reference')
assertIncludes(tool, '同类组缺失或样本不足时，只能输出研究观察', 'peer benchmark tool blocks false peer advantage')
assertIncludes(tool, 'sampleStatus', 'peer benchmark tool exposes sample status')
assertIncludes(tool, 'primaryBenchmark', 'peer benchmark tool exposes benchmark mapping')
assertIncludes(tool, 'broadAssetBucket', 'peer benchmark tool exposes broad asset bucket')
assertIncludes(tool, 'explainablePeerKey', 'peer benchmark tool exposes explainable peer key')
assertIncludes(tool, 'matchedRules', 'peer benchmark tool exposes matched peer rules')
assertIncludes(tool, 'missingRules', 'peer benchmark tool exposes missing peer rules')
assertIncludes(tool, 'benchmarkMappingRationale', 'peer benchmark tool explains benchmark mapping rationale')
assertIncludes(tool, '资产类别、策略族谱、主动/被动、风格、规模和成立年限分层', 'peer benchmark tool enforces explainable peer dimensions')
assertNotIncludes(tool, '购买建议', 'peer benchmark tool must not output purchase advice')

assertIncludes(registry, 'peerGroupBenchmarkTool', 'research tool registry includes peer benchmark tool')
assertIncludes(index, 'PeerBenchmarkOutput', 'research tool index exports peer benchmark types')

assertIncludes(comparisonReport, 'peerGroupBenchmarkTool.run', 'comparison report uses peer benchmark tool')
assertIncludes(comparisonReport, 'peerBenchmarkByCode', 'comparison report consumes benchmark classification map')
assertIncludes(comparisonReportMarkdown, '同类组/基准映射', 'comparison report renderer renders peer benchmark summary')
assertIncludes(comparisonReportMarkdown, '基准映射：', 'comparison report renderer renders item benchmark line')
assertIncludes(comparisonReport, 'peerBenchmarkBoundary', 'comparison report carries peer benchmark boundary')

console.log('OK peer group benchmark tool is registered and used by comparison reports')
