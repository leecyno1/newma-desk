import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('..', import.meta.url))
const scanRoots = ['app', 'backend/routes', 'backend/services', 'backend/tests', 'scripts']
const bannedPatterns = [
  { pattern: /投委会/g, label: '投委会' },
  { pattern: /governance/gi, label: 'governance' },
  { pattern: /investment_committee/gi, label: 'investment_committee' },
  { pattern: /ic_memo/gi, label: 'ic_memo' },
  // 研究型组合构建（等权/自定义权重、穿透分析）已随 V3.0 边界演进成为合法研究模块；
  // 但组合优化器、交易模拟与组合决策仍属越界，继续禁止。
  { pattern: /组合优化/g, label: '组合优化' },
  { pattern: /组合模拟/g, label: '组合模拟' },
  { pattern: /组合决策/g, label: '组合决策' },
  { pattern: /portfolio\/optimize/gi, label: 'portfolio/optimize' },
  { pattern: /投资决策/g, label: '投资决策' },
  { pattern: /投决/g, label: '投决' },
]
const allowedFiles = new Set([
  'scripts/fund_research_scope_smoke.mjs',
  'scripts/methodology_config_foundation_smoke.mjs',
  'scripts/methodology_mapping_repository_smoke.mjs',
  'scripts/methodology_seed_data_smoke.mjs',
  'scripts/methodology_database_resolution_smoke.mjs',
  'scripts/research_taxonomy_peer_groups_seed_smoke.mjs',
  'scripts/research_taxonomy_peer_groups_database_smoke.mjs',
  'scripts/benchmark_attribution_seed_smoke.mjs',
  'scripts/benchmark_attribution_database_smoke.mjs',
  'scripts/research_review_report_methodology_sections_smoke.mjs',
  'scripts/screening_methodology_integration_smoke.mjs',
  'scripts/fund_detail_methodology_focus_smoke.mjs',
  'scripts/newma_desk_fund_research_compat_smoke.mjs',
])

function listFiles(dir) {
  const fullDir = join(root, dir)
  const entries = readdirSync(fullDir)
  const files = []
  for (const entry of entries) {
    const fullPath = join(fullDir, entry)
    const relPath = relative(root, fullPath)
    const stat = statSync(fullPath)
    if (stat.isDirectory()) {
      if (entry === '__pycache__') continue
      files.push(...listFiles(relPath))
    } else if (/\.(ts|tsx|py|mjs|md|sh)$/.test(entry)) {
      files.push(relPath)
    }
  }
  return files
}

const violations = []
for (const scanRoot of scanRoots) {
  for (const file of listFiles(scanRoot)) {
    if (allowedFiles.has(file)) continue
    const content = readFileSync(join(root, file), 'utf8')
    const lines = content.split(/\r?\n/)
    for (const [lineIndex, line] of lines.entries()) {
      for (const item of bannedPatterns) {
        item.pattern.lastIndex = 0
        if (item.pattern.test(line)) {
          violations.push(`${file}:${lineIndex + 1} contains ${item.label}`)
        }
      }
    }
  }
}

if (violations.length > 0) {
  throw new Error(`Fund research scope violations:\\n${violations.join('\\n')}`)
}

console.log('OK fund research module excludes unrelated governance and portfolio-construction surfaces')
