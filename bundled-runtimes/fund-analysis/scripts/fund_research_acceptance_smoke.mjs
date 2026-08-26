import { spawnSync } from 'node:child_process'

const baseUrl = process.env.FRONTEND_BASE_URL || 'http://127.0.0.1:3000'

const staticChecks = [
  'scripts/fund_research_scope_smoke.mjs',
  'scripts/professional_fund_research_architecture_smoke.mjs',
  'scripts/redundant_dashboard_clients_removed_smoke.mjs',
  'scripts/platform_layered_architecture_smoke.mjs',
  'scripts/open_source_reuse_registry_smoke.mjs',
  'scripts/research_platform_registry_smoke.mjs',
  'scripts/fund_entity_standardization_smoke.mjs',
  'scripts/research_taxonomy_peer_groups_seed_smoke.mjs',
  'scripts/research_taxonomy_peer_groups_database_smoke.mjs',
  'scripts/single_fund_research_review_skill_smoke.mjs',
  'scripts/research_review_report_lib_smoke.mjs',
  'scripts/research_review_report_methodology_sections_smoke.mjs',
  'scripts/research_evidence_lib_smoke.mjs',
  'scripts/material_evidence_gate_tool_smoke.mjs',
  'scripts/peer_group_benchmark_tool_smoke.mjs',
  'scripts/explainable_peer_group_smoke.mjs',
  'scripts/benchmark_attribution_foundation_smoke.mjs',
  'scripts/benchmark_attribution_seed_smoke.mjs',
  'scripts/benchmark_attribution_database_smoke.mjs',
  'scripts/holding_deep_research_foundation_smoke.mjs',
  'scripts/manager_research_loop_foundation_smoke.mjs',
  'scripts/company_research_foundation_smoke.mjs',
  'scripts/methodology_config_foundation_smoke.mjs',
  'scripts/methodology_mapping_repository_smoke.mjs',
  'scripts/holding_style_drift_smoke.mjs',
  'scripts/portfolio_construction_smoke.mjs',
  'scripts/methodology_seed_data_smoke.mjs',
  'scripts/methodology_database_resolution_smoke.mjs',
  'scripts/comparison_research_score_tool_smoke.mjs',
  'scripts/comparison_research_summary_tool_smoke.mjs',
  'scripts/comparison_win_loss_audit_tool_smoke.mjs',
  'scripts/comparison_report_markdown_renderer_smoke.mjs',
  'scripts/comparison_buy_evidence_smoke.mjs',
  'scripts/market_fund_research_decision_smoke.mjs',
  'scripts/market_compare_basket_evidence_tool_smoke.mjs',
  'scripts/market_compare_basket_win_loss_tool_smoke.mjs',
  'scripts/market_current_page_shortlist_tool_smoke.mjs',
  'scripts/market_decision_explainer_tool_smoke.mjs',
  'scripts/market_promotion_queue_tool_smoke.mjs',
  'scripts/material_evidence_api_routes_smoke.mjs',
  'scripts/review_events_api_routes_smoke.mjs',
  'scripts/canonical_research_hrefs_smoke.mjs',
  'scripts/research_lists_api_routes_smoke.mjs',
  'scripts/research_candidates_api_routes_smoke.mjs',
  'scripts/research_candidates_evidence_tool_smoke.mjs',
  'scripts/research_api_canonical_routes_smoke.mjs',
  'scripts/dashboard_canonical_research_links_smoke.mjs',
  'scripts/active_pages_canonical_research_links_smoke.mjs',
  'scripts/dashboard_research_semantics_smoke.mjs',
  'scripts/manager_research_semantics_smoke.mjs',
  'scripts/comparison_research_semantics_smoke.mjs',
  'scripts/market_browser_smoke.mjs',
  'scripts/fund_detail_methodology_focus_smoke.mjs',
  'scripts/fund_detail_research_semantics_smoke.mjs',
  'scripts/nav_chart_no_mock_smoke.mjs',
  'scripts/fund_holding_exposure_smoke.mjs',
  'scripts/evidence_coverage_holdings_smoke.mjs',
  'scripts/evidence_coverage_transaction_source_smoke.mjs',
  'scripts/manager_tenure_report_smoke.mjs',
  'scripts/report_generation_trust_smoke.mjs',
  'scripts/report_search_embedding_trust_smoke.mjs',
  'scripts/fund_research_trading_copy_guard_smoke.mjs',
  'scripts/fund_comparison_smoke.mjs',
  'scripts/local_research_library_flow_smoke.mjs',
]

async function assertResearchApiReachable() {
  try {
    const response = await fetch(new URL('/api/funds?page=1&limit=1&sortBy=updatedAt&sortOrder=desc', baseUrl).toString(), {
      cache: 'no-store',
    })
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    const payload = await response.json().catch(() => ({}))
    if (!payload || !Array.isArray(payload.data)) {
      throw new Error('fund research API returned an invalid payload')
    }
  } catch (error) {
    throw new Error(`本地基金研究 API 不可达：${baseUrl}。请先启动 Next 服务后再运行验收烟测。${error instanceof Error ? ` (${error.message})` : ''}`)
  }
}

async function assertMergedRoutesRedirect() {
  for (const path of ['/investor-selection', '/sales-rules', '/alerts', '/pools', '/rankings']) {
    const response = await fetch(new URL(path, baseUrl).toString(), {
      redirect: 'manual',
      cache: 'no-store',
    })
    if (![307, 308].includes(response.status)) {
      throw new Error(`${path} should redirect after module merge, got HTTP ${response.status}`)
    }
  }
}

function runNodeScript(scriptPath) {
  const result = spawnSync(process.execPath, [scriptPath], {
    cwd: process.cwd(),
    env: {
      ...process.env,
      FRONTEND_BASE_URL: baseUrl,
    },
    stdio: 'inherit',
  })
  if (result.error) throw result.error
  if (result.status !== 0) {
    throw new Error(`${scriptPath} failed with exit ${result.status}`)
  }
}

console.log(`>>> 专业基金研究模块验收烟测：${baseUrl}`)

console.log('\n[1/3] 静态研究能力检查')
for (const scriptPath of staticChecks) {
  runNodeScript(scriptPath)
}

console.log('\n[2/3] 本地研究 API 可达性检查')
await assertResearchApiReachable()
console.log(`OK research API reachable ${baseUrl}`)

console.log('\n[3/3] 冗余入口合并检查')
await assertMergedRoutesRedirect()
console.log('OK redundant module routes redirect to canonical research surfaces')

console.log('\nOK professional fund research acceptance smoke passed')
