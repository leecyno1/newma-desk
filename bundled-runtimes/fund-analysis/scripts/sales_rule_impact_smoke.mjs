const baseUrl = process.env.FRONTEND_BASE_URL || 'http://127.0.0.1:3000'

function assert(condition, message) {
  if (!condition) throw new Error(message)
}

async function main() {
  const response = await fetch(`${baseUrl}/api/sales-rules/impact`, { cache: 'no-store' })
  const payload = await response.json().catch(() => ({}))
  assert(response.ok, `sales rule impact API failed: ${response.status} ${payload.error || ''}`)
  assert(Array.isArray(payload.profiles) && payload.profiles.length === 3, 'impact API must return three investor profiles')
  for (const key of ['conservative', 'balanced', 'aggressive']) {
    const profile = payload.profiles.find((item) => item.key === key)
    assert(profile, `missing profile ${key}`)
    assert(Number.isFinite(Number(profile.maxSalesRiskLevel)), `${key} maxSalesRiskLevel missing`)
    assert(Number.isFinite(Number(profile.matchedCount)), `${key} matchedCount missing`)
    assert(Number.isFinite(Number(profile.missingRiskCount)), `${key} missingRiskCount missing`)
    assert(typeof profile.actionHref === 'string' && profile.actionHref.includes('/sales-rules?scope=market'), `${key} actionHref missing`)
    assert(profile.actionHref.includes('purchasePlan=sip'), `${key} actionHref must carry purchasePlan`)
    assert(profile.actionHref.includes('returnTo='), `${key} actionHref must preserve returnTo`)
  }
  assert(Number.isFinite(Number(payload.summary?.riskLevelMissingCount)), 'summary.riskLevelMissingCount missing')
  assert(Number.isFinite(Number(payload.summary?.riskLevelCoverage)), 'summary.riskLevelCoverage missing')
  assert(String(payload.source || '').includes('source_backed_30d'), 'impact API must disclose source-backed 30d risk-level scope')
  assert(Array.isArray(payload.nextActions) && payload.nextActions.length >= 2, 'nextActions missing')
  assert(
    payload.nextActions.some((action) => String(action.label || '').includes('风险来源') || String(action.detail || '').includes('来源背书')),
    'nextActions must use risk-level source-backed copy',
  )
  for (const action of payload.nextActions) {
    if (String(action.href || '').includes('/sales-rules')) {
      assert(String(action.href).includes('purchasePlan=sip'), `${action.label || 'next action'} must carry purchasePlan`)
    }
  }
  const lumpResponse = await fetch(`${baseUrl}/api/sales-rules/impact?purchasePlan=lump_sum`, { cache: 'no-store' })
  const lumpPayload = await lumpResponse.json().catch(() => ({}))
  assert(lumpResponse.ok, `lump_sum impact API failed: ${lumpResponse.status} ${lumpPayload.error || ''}`)
  const lumpActionHref = String(lumpPayload.nextActions?.[0]?.href || '')
  const lumpProfileHref = String(lumpPayload.profiles?.find?.((item) => item.key === 'balanced')?.actionHref || '')
  assert(lumpActionHref.includes('purchasePlan=lump_sum'), 'impact API must preserve lump_sum in next action')
  assert(lumpProfileHref.includes('purchasePlan=lump_sum'), 'impact API must preserve lump_sum in profile action')
  assert(!lumpProfileHref.includes('purchasePlan=sip'), 'impact API lump_sum action must not leak sip')
  const amountResponse = await fetch(`${baseUrl}/api/sales-rules/impact?purchasePlan=lump_sum&plannedAmount=20000`, { cache: 'no-store' })
  const amountPayload = await amountResponse.json().catch(() => ({}))
  assert(amountResponse.ok, `amount-aware impact API failed: ${amountResponse.status} ${amountPayload.error || ''}`)
  const amountActionHref = String(amountPayload.nextActions?.[0]?.href || '')
  const amountProfileHref = String(amountPayload.profiles?.find?.((item) => item.key === 'balanced')?.actionHref || '')
  assert(amountActionHref.includes('plannedAmount=20000'), 'impact API next action must preserve plannedAmount')
  assert(amountActionHref.includes('lumpSumAmount=20000'), 'impact API next action must preserve lump-sum amount alias')
  assert(amountProfileHref.includes('plannedAmount=20000'), 'impact API profile action must preserve plannedAmount')
  assert(amountProfileHref.includes('lumpSumAmount=20000'), 'impact API profile action must preserve lump-sum amount alias')
  assert(decodeURIComponent(amountProfileHref).includes('returnTo=/market?'), 'impact API profile action must preserve market returnTo')
  console.log(`OK sales-rule impact smoke ${baseUrl}: total=${payload.totalFunds}, missingRisk=${payload.summary.riskLevelMissingCount}, coverage=${payload.summary.riskLevelCoverage}%`)
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
