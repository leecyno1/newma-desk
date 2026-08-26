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

const skill = read('lib/research-platform/skills/single-fund-research-review.ts')
const skillsIndex = read('lib/research-platform/skills/index.ts')
const skillRegistry = read('lib/research-platform/skills/registry.ts')
const toolRegistry = read('lib/research-platform/tools/registry.ts')

assertIncludes(skill, 'runSingleFundResearchReviewSkill', 'single fund research review skill exposes runner')
assertIncludes(skill, 'SingleFundResearchReviewSubject', 'single fund research review skill exposes typed subject')
assertIncludes(skill, 'researchEvidenceTool.run', 'single fund research review skill calls research evidence tool')
assertIncludes(skill, 'materialEvidenceGateTool.run', 'single fund research review skill checks material evidence fields')
assertIncludes(skill, "decision: 'blocked'", 'single fund research review skill can hard block')
assertIncludes(skill, "decision: 'verify_first'", 'single fund research review skill can downgrade to verify first')
assertIncludes(skill, "decision: 'research_ready'", 'single fund research review skill can mark research ready')
assertIncludes(skill, 'SkillRun<SingleFundResearchReviewSubject>', 'single fund research review skill returns typed SkillRun')
assertIncludes(skill, '研究复核', 'single fund research review skill uses research review language')
assertIncludes(skill, '材料核验', 'single fund research review skill uses evidence verification language')
assertIncludes(skill, 'FUND_RESEARCH_GUARDRAILS.noTradingDirective', 'single fund research review skill carries no-directive guardrail')
assertIncludes(skillsIndex, 'runSingleFundResearchReviewSkill', 'skills index exports research review runner')
assertIncludes(skillRegistry, 'single-fund-research-review', 'skill registry includes research review manifest')
assertIncludes(skillRegistry, "{ key: 'research-evidence', tool: 'research-evidence'", 'skill manifest uses research evidence tool')
assertIncludes(toolRegistry, 'researchEvidenceTool', 'tool registry includes research evidence tool')

for (const banned of [
  'single-fund-pre-purchase',
  'runSingleFundPrePurchaseSkill',
  'SingleFundPrePurchaseSubject',
  'BuyEvidence',
  'buyEvidence',
  'buy-evidence',
  'pre_purchase',
  'pre-purchase',
  'purchase',
  'buy',
  '买前',
  '购买',
  '申赎操作',
]) {
  assertNotIncludes(skill, banned, 'single fund research review skill language')
}

console.log('OK single fund research review skill composes evidence ToolResults into research-only SkillRun')
