import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { join } from 'node:path'

const root = fileURLToPath(new URL('..', import.meta.url))

function read(relativePath) {
  const fullPath = join(root, relativePath)
  if (!existsSync(fullPath)) throw new Error(`Missing required file: ${relativePath}`)
  return readFileSync(fullPath, 'utf8')
}

function assertIncludes(content, expected, label) {
  if (!content.includes(expected)) throw new Error(`${label} missing text: ${expected}`)
}

function assertNotIncludes(content, forbidden, label) {
  if (content.includes(forbidden)) throw new Error(`${label} should not include: ${forbidden}`)
}

const reportLib = read('lib/research-review-report.ts')

assertIncludes(reportLib, 'resolveMethodologyConfigFromDataSync', 'research report imports methodology repository')
assertIncludes(reportLib, 'buildReportMethodologySections', 'research report builds methodology sections')
assertIncludes(reportLib, 'methodologySectionLines', 'research report renders methodology section lines')
assertIncludes(reportLib, '## 2. 方法论模板与章节重点', 'research report has methodology section')
assertIncludes(reportLib, '主动权益基金研究模板', 'report supports active equity template')
assertIncludes(reportLib, '固收基金研究模板', 'report supports fixed income template')
assertIncludes(reportLib, '指数基金研究模板', 'report supports index template')
assertIncludes(reportLib, '货币基金研究模板', 'report supports money-market template')
assertIncludes(reportLib, 'QDII 基金研究模板', 'report supports QDII template')
assertIncludes(reportLib, 'FOF 基金研究模板', 'report supports FOF template')
assertIncludes(reportLib, '量化基金研究模板', 'report supports quant template')
assertIncludes(reportLib, '基准与归因', 'report methodology section carries benchmark attribution')
assertIncludes(reportLib, '信用暴露', 'report methodology section carries fixed income credit exposure')
assertIncludes(reportLib, '费用与跟踪误差', 'report methodology section carries index fee/tracking evidence')
assertIncludes(reportLib, '汇率与区域暴露', 'report methodology section carries QDII exposure')
assertIncludes(reportLib, '底层基金穿透', 'report methodology section carries FOF lookthrough')
assertIncludes(reportLib, '模型稳定性', 'report methodology section carries quant model stability')
assertIncludes(reportLib, '方法论模板只决定研究口径', 'report preserves methodology boundary')
assertNotIncludes(reportLib, '投委会', 'report methodology sections must not add governance workflow')

console.log('OK research review report renders methodology-driven sections')
