import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('..', import.meta.url))
const searchRoots = ['app', 'lib', 'backend']
const forbiddenTradingCopy = [
  '可直接购买',
  '直接购买',
  '直接下单',
  '再下单',
  '下单指令',
  '下单建议',
  '建议买入',
  '买入建议',
  '买入结论',
  '建议卖出',
  '卖出建议',
  '建议加仓',
  '加仓建议',
  '建议减仓',
  '减仓建议',
  '重仓买入',
  '申购建议',
  '赎回建议',
  '交易建议',
  '立即买入',
  '推荐买入',
  '购买推荐',
]
const allowedExtensions = new Set(['.ts', '.tsx', '.js', '.jsx', '.py', '.md'])

function extensionOf(path) {
  const index = path.lastIndexOf('.')
  return index >= 0 ? path.slice(index) : ''
}

function* walk(dir) {
  for (const entry of readdirSync(dir)) {
    if (['node_modules', '.next', '.git', '__pycache__'].includes(entry)) continue
    const fullPath = join(dir, entry)
    const stat = statSync(fullPath)
    if (stat.isDirectory()) {
      yield* walk(fullPath)
    } else if (allowedExtensions.has(extensionOf(fullPath))) {
      yield fullPath
    }
  }
}

for (const searchRoot of searchRoots) {
  for (const filePath of walk(join(root, searchRoot))) {
    const content = readFileSync(filePath, 'utf8')
    for (const phrase of forbiddenTradingCopy) {
      if (content.includes(phrase)) {
        throw new Error(`${relative(root, filePath)} contains trading copy: ${phrase}`)
      }
    }
  }
}

console.log('OK fund research module has no direct trading-copy phrases')
