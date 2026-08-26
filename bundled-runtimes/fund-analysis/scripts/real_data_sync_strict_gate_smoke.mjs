import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { join } from 'node:path'

const root = fileURLToPath(new URL('..', import.meta.url))
const registry = readFileSync(join(root, 'backend/service_registry.py'), 'utf8')
const tushare = readFileSync(join(root, 'backend/services/tushare_service.py'), 'utf8')
const dataSync = readFileSync(join(root, 'backend/routes/data_sync.py'), 'utf8')

function assertIncludes(content, expected, label) {
  if (!content.includes(expected)) {
    throw new Error(`${label} missing text: ${expected}`)
  }
}

function assertNotIncludes(content, expected, label) {
  if (content.includes(expected)) {
    throw new Error(`${label} must not include text: ${expected}`)
  }
}

assertIncludes(registry, 'def get_strict_tushare_service()', 'service registry strict tushare provider')
assertIncludes(registry, 'TushareDataService(strict_no_mock=True)', 'service registry strict tushare construction')
assertIncludes(tushare, 'if strict_no_mock and mock_mode:', 'tushare strict constructor gate')
assertIncludes(tushare, 'Tushare strict_no_mock requires real data source', 'tushare strict error message')
assertIncludes(tushare, 'TUSHARE_TOKEN missing', 'tushare strict token diagnosis')
assertIncludes(dataSync, 'from service_registry import get_strict_tushare_service', 'data sync imports strict tushare provider')
assertIncludes(dataSync, 'data_svc = get_strict_tushare_service()', 'data sync uses strict real data provider')
assertNotIncludes(dataSync, 'get_data_service()', 'data sync must not use mock-capable provider')

console.log('OK real-data sync path requires strict Tushare and cannot fall back to mock')
