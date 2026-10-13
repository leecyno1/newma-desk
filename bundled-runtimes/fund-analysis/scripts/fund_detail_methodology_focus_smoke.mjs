import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { join } from 'node:path'

const root = fileURLToPath(new URL('..', import.meta.url))

function read(relativePath) {
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

function assertNotIncludes(content, forbidden, label) {
  if (content.includes(forbidden)) {
    throw new Error(`${label} should not include: ${forbidden}`)
  }
}

const simpleDetailClient = read('app/(dashboard)/funds/[id]/SimpleFundDetailClient.tsx')
const methodologyTool = read('lib/research-platform/tools/methodology-config.ts')

// 详情页现行方法论界面是类别专属评价方法卡：维度、方法版本与边界说明
// 由后端方法论配置下发（methodologyConfigTool 体系），前端只做证据展示。
assertIncludes(simpleDetailClient, 'const methodology = evaluation.methodology', 'fund detail reads category-specific evaluation methodology')
assertIncludes(simpleDetailClient, '评价方法', 'fund detail labels the evaluation methodology card')
assertIncludes(simpleDetailClient, 'methodology.dimensions.map', 'fund detail renders methodology dimensions')
assertIncludes(simpleDetailClient, 'methodology.boundary', 'fund detail renders the methodology boundary from config')
assertIncludes(simpleDetailClient, '方法版本：{evaluation.calculationMethod || evaluation.methodologyVersion', 'fund detail discloses the methodology version')
assertNotIncludes(simpleDetailClient, '投委会', 'fund detail methodology must not add governance workflow')

// 方法论配置工具属 research-platform 共享层，继续守护其研究口径边界。
assertIncludes(methodologyTool, '方法论配置只决定基金研究证据口径，不生成申赎执行、资产配置或审批动作', 'methodology config tool keeps research-scope boundary')

console.log('OK fund detail shows category-specific methodology with config-driven boundary')
