import { readFileSync } from 'node:fs'

const apiRoute = readFileSync('app/api/recommendations/route.ts', 'utf8')
const coverageRoute = readFileSync('app/api/recommendations/coverage/route.ts', 'utf8')
const client = readFileSync('app/(dashboard)/recommendations/RecommendationClient.tsx', 'utf8')
const backendRoute = readFileSync('backend/routes/funds.py', 'utf8')
const backendService = readFileSync('backend/services/fund_recommendation_service.py', 'utf8')
const researchSnapshotService = readFileSync('backend/services/fund_research_snapshot_service.py', 'utf8')
const recommendationPage = readFileSync('app/(dashboard)/recommendations/page.tsx', 'utf8')
const backendMapper = readFileSync('lib/backend-api.ts', 'utf8')
const simpleFundView = readFileSync('lib/simple-fund-view.ts', 'utf8')
const categoryPresets = readFileSync('lib/fund-category-presets.ts', 'utf8')

function requireText(source, text, message) {
  if (!source.includes(text)) throw new Error(`${message}: ${text}`)
}

requireText(backendRoute, '@router.get("/recommendation-candidates")', 'backend candidate-group endpoint is missing')
requireText(backendRoute, '@router.get("/recommendation-coverage")', 'backend recommendation coverage endpoint is missing')
requireText(backendRoute, 'FundRecommendationService().build_candidate_group', 'backend endpoint must use the candidate-group service')
requireText(apiRoute, '/api/funds/recommendation-candidates', 'Next API must call the full peer-group candidate endpoint')
requireText(coverageRoute, '/api/funds/recommendation-coverage', 'coverage audit proxy must call the full backend coverage endpoint')
requireText(apiRoute, "backendParams.set('style', style)", 'Next API must pass style filtering to the backend')
requireText(apiRoute, 'compactStyleProfile(snapshot.style_profile)', 'Next API must compact the unified style projection for list cards')
requireText(apiRoute, 'recommendation_candidate_compact_v1', 'recommendation API must disclose the compact candidate payload')
requireText(apiRoute, 'professional_score: asRecord(asRecord(scoring.peer_percentiles).professional_score)', 'candidate cards must retain the professional-score peer percentile')
requireText(apiRoute, "status: snapshotEvaluation.status || snapshot.status || 'unavailable'", 'Next API must preserve evaluation status')
if (apiRoute.includes('candidate.research_snapshot')) {
  throw new Error('recommendation API must not merge raw candidates with nested research snapshots')
}
requireText(apiRoute, 'excludedReasonCounts', 'Next API must preserve candidate exclusion reasons')
requireText(backendService, 'excluded_reason_counts', 'backend must disclose candidate exclusion reasons')
requireText(backendService, '_manager_tenure_evidence', 'backend candidates must project current-manager tenure coverage')
requireText(backendService, 'FundResearchSnapshotService.project_multi_period_evidence', 'backend candidates must reuse the shared multi-period projection')
requireText(researchSnapshotService, 'def project_multi_period_evidence', 'research snapshot must own multi-period evidence')
requireText(client, 'recommendationEvidence(fund)', 'candidate cards must render backend recommendation evidence')
requireText(client, '经理任期证据', 'active-fund candidate cards must disclose manager-tenure coverage')
requireText(client, '评分证据', 'candidate cards must disclose score evidence coverage')
requireText(client, '长期证据', 'candidate cards must explain whether three-year evidence is complete')
requireText(client, '近 3 年年化', 'candidate cards must show long-term annualized return')
requireText(client, '同类第 {peerPosition.rank} / {peerPosition.peerCount}', 'candidate cards must show an understandable peer rank')
requireText(client, '管理+托管费', 'candidate cards must disclose the basic recurring fee')
requireText(simpleFundView, '部分证据评分', 'partial evaluations must be visibly labelled')
requireText(simpleFundView, 'const normalized = value * 100', 'ratio-based returns above 200% must keep the correct percent unit')
requireText(client, '不计分、不排名', 'partial manager tenure must stay out of recommendation ranking')
requireText(client, '主要风险', 'candidate cards must show risks')
requireText(client, '数据截至', 'candidate cards must disclose the evidence date')
requireText(client, '现场分析这只基金', 'candidate cards must link directly to on-demand fund analysis')
requireText(client, '一键加入当前候选', 'candidate group must support one-click watchlist collection')
requireText(client, '推荐入选：', 'watchlist collection must preserve recommendation reasons')
requireText(client, '同类组共', 'empty recommendation state must explain evidence gaps')
requireText(client, '数据准备情况', 'recommendation page must show category coverage')
requireText(client, '/api/recommendations/coverage', 'full coverage audit must load only from the client')
requireText(client, 'onToggle', 'full coverage audit must wait until the user expands it')
requireText(client, '你想先看哪一类', 'ordinary users need a plain-language category starting point')
requireText(categoryPresets, '大盘核心', 'recommendation page must expose common category presets')
requireText(categoryPresets, '偏股 FOF', 'recommendation page must expose FOF categories with real evaluation coverage')
requireText(categoryPresets, '平衡 FOF', 'recommendation page must expose balanced FOF categories')
requireText(categoryPresets, '偏债 FOF', 'recommendation page must expose bond-oriented FOF categories')
requireText(client, 'fundCategoryPresets', 'recommendation page must use the shared category presets')
requireText(client, '该类别暂无可核验的风格标签', 'empty style coverage must be explained honestly')
requireText(client, '不冒充已确认风格', 'memo suggestions must be visibly separated from confirmed styles')
requireText(client, '按风格继续缩小范围', 'recommendation page must expose quick style labels')
requireText(client, '匹配风格：{style}', 'candidate cards must show the selected matching style')
requireText(backendMapper, 'memoStyleSuggestions', 'frontend mapping must preserve memo style suggestion provenance')
requireText(backendMapper, 'derivedStyleEvidence', 'frontend mapping must preserve derived style provenance')
requireText(backendMapper, 'bondHoldingStyle', 'frontend mapping must preserve bond holding evidence')
requireText(client, '债券风格依据', 'candidate cards must disclose bond style evidence')
requireText(backendMapper, 'fofHoldingStyle', 'frontend mapping must preserve FOF look-through evidence')
requireText(backendMapper, 'recommendationManagerTenure', 'frontend mapping must preserve manager-tenure recommendation evidence')
requireText(client, 'FOF 穿透依据', 'candidate cards must disclose FOF look-through evidence')
requireText(client, '产品定位”不冒充持仓风格', 'derived positioning must be explained honestly')
requireText(client, '指标缺口只通过真实净值数据补齐', 'coverage UI must reject mock metric backfills')
requireText(recommendationPage, '/api/funds/recommendation-categories', 'recommendation page must use the fast category inventory')
if (recommendationPage.includes('/api/funds/recommendation-coverage')) {
  throw new Error('recommendation page must not block first paint on the full coverage audit')
}
requireText(client, 'void loadCandidates(category, nextStyle)', 'style changes must refresh the full peer candidate group')

for (const forbidden of [
  'MAX_EVALUATED_FUNDS',
  'Promise.all(matchingFunds.map',
  '.sort((left, right) => right.score - left.score)',
]) {
  if (apiRoute.includes(forbidden) || client.includes(forbidden)) {
    throw new Error(`recommendation flow still performs truncated or client-side selection: ${forbidden}`)
  }
}

const baseUrl = process.env.FRONTEND_BASE_URL || process.env.APP_BASE_URL || 'http://127.0.0.1:3000'
if (baseUrl) {
  const response = await fetch(new URL('/api/recommendations?category=%E6%8C%87%E6%95%B0-%E6%B2%AA%E6%B7%B1300', baseUrl), { cache: 'no-store' })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(`recommendation API returned HTTP ${response.status}: ${JSON.stringify(payload)}`)
  if (payload.source !== 'full_peer_group_category_evaluation') {
    throw new Error(`recommendation source is not full peer-group evaluation: ${JSON.stringify(payload)}`)
  }
  if (!Array.isArray(payload.data) || payload.data.length > 10) {
    throw new Error(`recommendation endpoint must return at most ten candidates: ${JSON.stringify(payload)}`)
  }
  if (payload.payloadProfile !== 'recommendation_candidate_compact_v1') {
    throw new Error(`recommendation endpoint did not return the compact list projection: ${JSON.stringify(payload)}`)
  }
  if (payload.data.some((fund) => fund.researchProfile?.peerGroup !== '指数-沪深300')) {
    throw new Error(`cross-category fund leaked into recommendations: ${JSON.stringify(payload)}`)
  }
  for (const fund of payload.data) {
    const evidence = fund.recommendationEvidence || {}
    if (!evidence.reasons?.length || !evidence.risks?.length || !evidence.dataAsOf) {
      throw new Error(`candidate evidence is incomplete: ${JSON.stringify(fund)}`)
    }
    if (!fund.professionalScoring?.status || !fund.professionalScoring?.dimension_scores) {
      throw new Error(`candidate score status or dimensions were lost in frontend mapping: ${JSON.stringify(fund)}`)
    }
  }

  const selectedStyle = '大盘'
  const styleResponse = await fetch(new URL(`/api/recommendations?category=${encodeURIComponent('混合型-偏股配置')}&style=${encodeURIComponent(selectedStyle)}`, baseUrl), { cache: 'no-store' })
  const stylePayload = await styleResponse.json().catch(() => ({}))
  if (!styleResponse.ok) throw new Error(`style recommendation API returned HTTP ${styleResponse.status}: ${JSON.stringify(stylePayload)}`)
  if (!Array.isArray(stylePayload.data) || stylePayload.data.length === 0 || stylePayload.data.length > 10) {
    throw new Error(`style recommendation must return one to ten real candidates: ${JSON.stringify(stylePayload)}`)
  }
  if (JSON.stringify(stylePayload).length > 200_000) {
    throw new Error(`style recommendation payload is too large for a candidate list: ${JSON.stringify(stylePayload).length} bytes`)
  }
  if (stylePayload.longTermReadyCount < 1) {
    throw new Error(`active-fund recommendation must disclose real three-year evidence coverage: ${JSON.stringify(stylePayload)}`)
  }
  for (const fund of stylePayload.data) {
    const profile = fund.researchProfile || {}
    const styleProfile = fund.styleProfile || {}
    const tags = [
      styleProfile.primaryLabel,
      ...(styleProfile.labelEvidence || []).map((item) => item?.value),
      profile.styleLabel,
      ...(profile.memoStyleSuggestions || []).map((item) => item?.value),
      ...(profile.derivedStyleEvidence || []).map((item) => item?.value),
    ].filter(Boolean)
    if (!tags.includes(selectedStyle)) {
      throw new Error(`style-filtered candidate lacks matching evidence: ${JSON.stringify(fund)}`)
    }
    if (profile.peerGroup !== '混合型-偏股配置') {
      throw new Error(`style filtering leaked across peer groups: ${JSON.stringify(fund)}`)
    }
    if (fund.peerPercentiles?.metrics?.professional_score?.percentile == null) {
      throw new Error(`candidate lost its professional-score peer percentile: ${JSON.stringify(fund)}`)
    }
    const managerTenure = fund.recommendationEvidence?.managerTenure
    if (!managerTenure?.applicable || !managerTenure?.status) {
      throw new Error(`active-fund recommendation lacks manager-tenure evidence: ${JSON.stringify(fund)}`)
    }
    if (managerTenure.coverageStatus === 'partial_since_data_start' && managerTenure.includedInScore) {
      throw new Error(`partial manager tenure leaked into recommendation score: ${JSON.stringify(fund)}`)
    }
    if (managerTenure.coverageStatus === 'partial_since_data_start' && fund.professionalScoring?.status !== 'partial') {
      throw new Error(`partial manager tenure must remain visible in score status: ${JSON.stringify(fund)}`)
    }
    const multiPeriod = fund.recommendationEvidence?.multiPeriod
    if (!multiPeriod?.status || multiPeriod.status === 'long_term_ready' && multiPeriod.annualizedReturn3y == null) {
      throw new Error(`recommendation lacks auditable multi-period evidence: ${JSON.stringify(fund)}`)
    }
  }
}

console.log('OK recommendation flow uses full peer-group evaluation and renders evidence-backed candidate groups')
