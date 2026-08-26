import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const root = process.cwd()

function read(relativePath) {
  return readFileSync(join(root, relativePath), 'utf8')
}

const route = read('app/api/market/research-candidates/route.ts')
const acceptance = read('scripts/fund_research_acceptance_smoke.mjs')

for (const banned of [
  "import { buildBuyEvidence }",
  'buyEvidenceTool',
  'buildBuyEvidence(fund',
]) {
  if (route.includes(banned)) throw new Error(`research candidates API should not use legacy buy evidence dependency: ${banned}`)
}

for (const expected of [
  'researchEvidenceTool',
  'ResearchEvidenceToolOutput',
  'researchEvidenceTool.run',
]) {
  if (!route.includes(expected)) throw new Error(`research candidates API should use research evidence dependency: ${expected}`)
}

if (!acceptance.includes('research_candidates_evidence_tool_smoke.mjs')) {
  throw new Error('main acceptance should include research candidates evidence tool smoke')
}

console.log('OK research candidates API uses research evidence tool instead of legacy buy evidence dependency')
