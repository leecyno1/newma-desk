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

function assertNotIncludes(content, unexpected, label) {
  if (content.includes(unexpected)) {
    throw new Error(`${label} should not include text: ${unexpected}`)
  }
}

const navChart = read('components/charts/NavChart.tsx')

assertIncludes(navChart, 'nav-chart-real-data-required', 'NAV chart real-data error state')
assertIncludes(navChart, '暂无真实净值数据', 'NAV chart empty real-data handling')
assertIncludes(navChart, '系统不会用随机曲线替代真实净值', 'NAV chart no-random boundary copy')
assertIncludes(navChart, 'setData([])', 'NAV chart clears data after fetch failure')
assertNotIncludes(navChart, 'generateMockData', 'NAV chart mock generator')
assertNotIncludes(navChart, 'Math.random', 'NAV chart random data fallback')
assertNotIncludes(navChart, '显示模拟数据', 'NAV chart mock data UI copy')
assertNotIncludes(navChart, '使用模拟数据用于演示', 'NAV chart mock fallback comment')

console.log('OK NAV chart refuses random mock data and requires real NAV evidence')
