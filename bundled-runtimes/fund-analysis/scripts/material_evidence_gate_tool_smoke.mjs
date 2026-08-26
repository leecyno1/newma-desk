import { readFileSync, existsSync } from 'node:fs'
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

function assertNotIncludes(content, unexpected, label) {
  if (content.includes(unexpected)) throw new Error(`${label} should not include: ${unexpected}`)
}

const tool = read('lib/research-platform/tools/material-evidence-gate.ts')
const toolRegistry = read('lib/research-platform/tools/registry.ts')
const toolIndex = read('lib/research-platform/tools/index.ts')
const skillRegistry = read('lib/research-platform/skills/registry.ts')
const singleFundSkill = read('lib/research-platform/skills/single-fund-research-review.ts')
const platformSmoke = read('scripts/research_platform_registry_smoke.mjs')
const acceptance = read('scripts/fund_research_acceptance_smoke.mjs')
const layeredArchitecture = read('docs/architecture/fund-research-platform-layered-architecture.md')

assertIncludes(tool, "name: 'material-evidence-gate'", 'material evidence tool manifest')
assertIncludes(tool, '材料核验', 'material evidence tool uses research evidence language')
assertIncludes(tool, 'buildSalesRuleMissingItems', 'material evidence tool owns canonical missing-item assembly')
assertIncludes(tool, 'material-evidence-gate:${input.windCode}', 'material evidence tool emits canonical evidence ids')
assertNotIncludes(tool, 'salesRuleGateTool.run', 'material evidence tool should not delegate to legacy sales-rule gate')
assertIncludes(toolRegistry, 'materialEvidenceGateTool', 'tool registry includes material evidence gate')
assertIncludes(toolIndex, 'materialEvidenceGateTool', 'tool index exports material evidence gate')
assertIncludes(skillRegistry, "tool: 'material-evidence-gate'", 'skill registry uses material evidence gate')
assertIncludes(singleFundSkill, 'materialEvidenceGateTool.run', 'single fund skill calls material evidence gate')
assertIncludes(platformSmoke, 'materialEvidenceGateTool', 'platform registry smoke checks material evidence gate')
assertIncludes(acceptance, 'material_evidence_gate_tool_smoke.mjs', 'main acceptance includes material evidence smoke')

const activeRegistryCode = [toolRegistry, skillRegistry, singleFundSkill].join('\n')
assertNotIncludes(activeRegistryCode, 'salesRuleGateTool.run', 'active platform registry and skill runtime')
assertNotIncludes(activeRegistryCode, "tool: 'sales-rule-gate'", 'active skill manifests')
assertIncludes(layeredArchitecture, 'material-evidence-gate.ts', 'layered architecture names canonical material evidence seam')
assertNotIncludes(layeredArchitecture, 'sales-rule-gate.ts', 'layered architecture should not recommend legacy sales-rule gate file')

console.log('OK material evidence gate replaces sales-rule gate in active research platform')
