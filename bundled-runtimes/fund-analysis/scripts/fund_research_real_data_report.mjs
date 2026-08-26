const backendBaseUrl = process.env.BACKEND_API_URL || process.env.NEXT_PUBLIC_BACKEND_API_URL || 'http://127.0.0.1:8005'
const frontendBaseUrl = process.env.FRONTEND_BASE_URL || 'http://127.0.0.1:3000'

function parseArgs(argv) {
  const options = {
    codes: [],
    limit: Number(process.env.REPORT_COUNT || 3),
    includeResearch: false,
    reportDepth: process.env.REPORT_DEPTH || 'standard',
  }

  for (const arg of argv) {
    if (arg.startsWith('--limit=')) {
      const parsed = Number(arg.slice('--limit='.length))
      if (Number.isFinite(parsed) && parsed > 0) options.limit = Math.min(20, Math.floor(parsed))
      continue
    }
    if (arg === '--include-research') {
      options.includeResearch = true
      continue
    }
    if (arg.startsWith('--depth=')) {
      options.reportDepth = arg.slice('--depth='.length) || options.reportDepth
      continue
    }
    options.codes.push(...arg.split(',').map((item) => item.trim()).filter(Boolean))
  }

  if (process.env.FUND_CODES) {
    options.codes.unshift(...process.env.FUND_CODES.split(',').map((item) => item.trim()).filter(Boolean))
  }

  options.codes = Array.from(new Set(options.codes.map((code) => code.toUpperCase()))).slice(0, options.limit)
  return options
}

async function fetchJson(baseUrl, path, init) {
  const response = await fetch(new URL(path, baseUrl), {
    cache: 'no-store',
    ...init,
  })
  const text = await response.text()
  let payload = {}
  try {
    payload = text ? JSON.parse(text) : {}
  } catch {
    payload = { raw: text }
  }
  if (!response.ok) {
    const detail = payload.detail || payload.error || payload.message || text || `HTTP ${response.status}`
    const error = new Error(Array.isArray(detail) ? detail.join('; ') : String(detail))
    error.status = response.status
    error.payload = payload
    throw error
  }
  return payload
}

async function assertServices() {
  const health = await fetchJson(backendBaseUrl, '/api/health')
  if (health.mock_mode) {
    throw new Error('后端当前是 mock_mode=true。请先配置 TUSHARE_TOKEN 并重启后端，再跑真实数据报告。')
  }

  await fetchJson(frontendBaseUrl, '/api/reports?limit=1').catch((error) => {
    throw new Error(`前端报告 API 不可达：${frontendBaseUrl} (${error.message})`)
  })

  return health
}

async function pickCodes(limit) {
  const payload = await fetchJson(backendBaseUrl, `/api/funds?page=1&page_size=${limit}&sort_by=updated_at&sort_order=desc`)
  return (payload.funds || [])
    .map((fund) => String(fund.wind_code || fund.windCode || '').trim().toUpperCase())
    .filter(Boolean)
    .slice(0, limit)
}

async function syncFund(code) {
  try {
    const payload = await fetchJson(backendBaseUrl, `/api/data-sync/funds/${encodeURIComponent(code)}`)
    return {
      ok: true,
      managerCount: Number(payload.manager_count || 0),
      warnings: payload.warnings || [],
      errors: [],
    }
  } catch (error) {
    const fund = await fetchJson(backendBaseUrl, `/api/funds/${encodeURIComponent(code)}`).catch(() => null)
    if (!fund) {
      return {
        ok: false,
        managerCount: 0,
        warnings: [],
        errors: [error.message],
      }
    }
    return {
      ok: true,
      degraded: true,
      managerCount: Array.isArray(fund.fund?.manager_ids || fund.manager_ids) ? (fund.fund?.manager_ids || fund.manager_ids).length : 0,
      warnings: [`同步接口返回告警/错误，但本地已有 ${code}，继续生成研究报告：${error.message}`],
      errors: [],
    }
  }
}

async function generateFundReport(code, options) {
  const params = new URLSearchParams({
    include_research: String(options.includeResearch),
    report_depth: options.reportDepth,
  })
  const payload = await fetchJson(
    backendBaseUrl,
    `/api/reports/fund/${encodeURIComponent(code)}?${params.toString()}`,
    { method: 'POST' },
  )
  if (!payload.id) {
    throw new Error(`${code} 报告已生成但未写入本地 PostgreSQL，不能算完成闭环`)
  }
  return payload
}

async function verifyReportVisible(reportId) {
  const payload = await fetchJson(frontendBaseUrl, `/api/reports/${encodeURIComponent(reportId)}`)
  return String(payload.id || '') === String(reportId) && Boolean(payload.content || payload.summary)
}

const options = parseArgs(process.argv.slice(2))

console.log(`>>> 真实数据同步 + 基金研究报告生成`)
console.log(`后端：${backendBaseUrl}`)
console.log(`前端：${frontendBaseUrl}`)

const health = await assertServices()
console.log(`OK 后端数据源：${health.data_source}，mock_mode=${health.mock_mode}`)

const codes = options.codes.length ? options.codes : await pickCodes(options.limit)
if (!codes.length) {
  throw new Error('没有可用基金代码。可通过 FUND_CODES=260104.OF,519674.OF 指定。')
}

const results = []
for (const code of codes.slice(0, options.limit)) {
  console.log(`\n[${code}] 同步 Tushare 数据到本地`)
  const syncResult = await syncFund(code)
  if (!syncResult.ok) {
    results.push({ code, status: 'sync_failed', errors: syncResult.errors })
    console.log(`FAIL ${code} 同步失败：${syncResult.errors.join('; ')}`)
    continue
  }
  if (syncResult.warnings.length) {
    for (const warning of syncResult.warnings.slice(0, 3)) console.log(`WARN ${warning}`)
  }
  console.log(`OK ${code} 本地数据可用，经理数=${syncResult.managerCount}`)

  console.log(`[${code}] 生成并保存基金研究报告`)
  try {
    const report = await generateFundReport(code, options)
    const visible = await verifyReportVisible(report.id)
    if (!visible) {
      throw new Error(`报告 ${report.id} 已写入后端，但前端报告详情暂未读取到`)
    }
    const metadata = report.metadata || {}
    results.push({
      code,
      status: 'ok',
      reportId: report.id,
      mode: metadata.mode,
      provider: metadata.provider,
      model: metadata.model,
      wordCount: metadata.word_count,
    })
    console.log(`OK ${code} 报告已保存：${report.id} · ${metadata.mode || 'unknown'} · ${metadata.word_count || 0} 字符`)
  } catch (error) {
    results.push({ code, status: 'report_failed', errors: [error.message] })
    console.log(`FAIL ${code} 报告生成失败：${error.message}`)
  }
}

const failed = results.filter((item) => item.status !== 'ok')
console.log('\n>>> 结果汇总')
for (const item of results) {
  if (item.status === 'ok') {
    console.log(`OK ${item.code} report=${item.reportId} mode=${item.mode} provider=${item.provider} model=${item.model}`)
  } else {
    console.log(`FAIL ${item.code} status=${item.status} errors=${(item.errors || []).join('; ')}`)
  }
}

if (failed.length) {
  throw new Error(`${failed.length}/${results.length} 个基金未完成真实数据报告闭环`)
}

console.log('\nOK real data fund research reports generated and visible locally')
