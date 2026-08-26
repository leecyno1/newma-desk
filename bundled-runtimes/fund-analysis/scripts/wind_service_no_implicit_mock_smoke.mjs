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

const windService = read('backend/services/wind_service.py')
const standaloneWindService = read('backend/wind_service/main.py')
const acceptance = read('scripts/fund_research_acceptance_smoke.mjs')

assertIncludes(windService, 'WindDataService can only run in explicit mock_mode', 'wind service does not silently enter dev mock')
assertIncludes(windService, 'def _raise_real_data_error', 'wind service has explicit real-data error gate')
assertIncludes(windService, '已阻止 mock 回退，不能用模拟数据生成基金研究证据', 'wind service blocks implicit mock evidence')
assertIncludes(windService, 'return self._raise_real_data_error(f"基金基本信息 {wind_code}", e)', 'wind fund info real-mode error blocks mock fallback')
assertIncludes(windService, 'return self._raise_real_data_error(f"基金列表 {fund_type or \'ALL\'}", e)', 'wind fund list real-mode error blocks mock fallback')
assertIncludes(windService, 'return self._raise_real_data_error(f"基金净值 {wind_code}", e)', 'wind NAV real-mode error blocks mock fallback')
assertIncludes(windService, 'return self._raise_real_data_error(f"基金经理信息 {manager_id}", e)', 'wind manager info real-mode error blocks mock fallback')
assertIncludes(windService, 'return self._raise_real_data_error(f"基金业绩指标 {wind_code}", e)', 'wind performance real-mode error blocks mock fallback')
assertIncludes(windService, 'return self._raise_real_data_error(f"基金风险指标 {wind_code}", e)', 'wind risk real-mode error blocks mock fallback')
assertIncludes(windService, 'return self._raise_real_data_error(f"基金持仓 {wind_code} {quarter}", e)', 'wind holdings real-mode error blocks empty fallback')
assertIncludes(windService, 'raise RuntimeError(f"缺少 Barra 因子 {factor}")', 'wind style factors do not default missing exposure to zero')
assertIncludes(windService, 'return self._raise_real_data_error(f"基金风格因子 {wind_code} {factor}", factor_error)', 'wind style factor error blocks mock fallback')
assertIncludes(standaloneWindService, 'status_code=501', 'standalone wind service refuses fake endpoint data')
assertIncludes(standaloneWindService, '已阻止返回模拟基金数据', 'standalone fund endpoint blocks simulated data')
assertIncludes(standaloneWindService, '已阻止返回模拟基金经理数据', 'standalone manager endpoint blocks simulated data')
assertNotIncludes(standaloneWindService, '测试基金-', 'standalone wind service has no fake fund name')
assertNotIncludes(standaloneWindService, '测试基金公司', 'standalone wind service has no fake company')
assertNotIncludes(standaloneWindService, '张三', 'standalone wind service has no fake manager')
assertIncludes(acceptance, 'scripts/wind_service_no_implicit_mock_smoke.mjs', 'fund research acceptance includes wind no-implicit-mock smoke')

console.log('OK Wind service real-mode errors cannot silently fall back to mock evidence')
