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

function assertExcludes(content, unexpected, label) {
  if (content.includes(unexpected)) {
    throw new Error(`${label} contains forbidden text: ${unexpected}`)
  }
}

const dataSyncRoute = read('backend/routes/data_sync.py')
const rollingMetricService = read('backend/services/rolling_metric_service.py')
const navEvidenceService = read('backend/services/fund_nav_evidence_service.py')
const metricFactory = read('backend/services/metric_factory.py')
const tushareService = read('backend/services/tushare_service.py')
const rankingMetricScript = read('backend/scripts/sync_fund_ranking_metrics.py')
const batchSyncScript = read('backend/scripts/batch_sync_production.py')
const fullSyncScript = read('backend/scripts/sync_tushare_and_generate_reports.py')
const classificationIngestionService = read('backend/services/fund_classification_ingestion_service.py')
const classificationSyncScript = read('backend/scripts/sync_fund_classification_universe.py')
const classificationSyncShell = read('scripts/update_fund_classification.sh')
const universeSyncShell = read('scripts/update_fund_universe.sh')
const rankingMetricShell = read('scripts/update_fund_ranking_metrics.sh')
const packageJson = read('package.json')

assertIncludes(dataSyncRoute, 'from services.rolling_metric_service import RollingMetricService', 'data sync imports rolling metric calculator')
assertIncludes(dataSyncRoute, 'ROLLING_NAV_HISTORY_DAYS = 365 * 4', 'data sync covers the longest rolling metric window')
assertIncludes(dataSyncRoute, 'timedelta(days=ROLLING_NAV_HISTORY_DAYS)', 'data sync requests enough NAV and benchmark history')
assertIncludes(dataSyncRoute, 'FundNavDataEnrichmentService', 'data sync enriches NAV with category evaluation evidence')
assertIncludes(dataSyncRoute, 'FundClassificationIngestionService', 'data sync materializes high-confidence classification before NAV enrichment')
assertIncludes(dataSyncRoute, 'benchmark_code=nav_enrichment.get("benchmark_code")', 'data sync passes the mapped benchmark into rolling metrics')
assertIncludes(dataSyncRoute, 'benchmark_data_status") != "not_checked"', 'data sync preserves prior NAV evidence when NAV was not checked')
assertIncludes(dataSyncRoute, '"rolling_metrics": rolling_metrics', 'data sync returns rolling metric result')
assertIncludes(dataSyncRoute, '净值已同步，但滚动指标样本不足', 'data sync warns when NAV cannot support metrics')
assertIncludes(rollingMetricService, 'min_observation_ratio: float = 0.6', 'rolling metric service has observation threshold')
assertIncludes(rollingMetricService, 'metric_repo.upsert_metric', 'rolling metric service persists MetricSnapshot')
assertIncludes(rollingMetricService, 'mapped_benchmark', 'rolling metric service prefers normalized benchmark mappings')
assertIncludes(navEvidenceService, 'derive_money_market_facts', 'NAV evidence derives money-market short-horizon facts')
assertIncludes(navEvidenceService, 'attach_benchmark_nav', 'NAV evidence aligns real benchmark dates')
assertIncludes(navEvidenceService, 'nav_shape_conflicts_with_declared_fund_type', 'NAV evidence blocks fund-type conflicts')
assertIncludes(navEvidenceService, 'mapping_missing', 'NAV evidence exposes missing benchmark mapping')
assertIncludes(metricFactory, 'item.get("accum_nav") or item.get("adj_nav")', 'metric factory prefers consistent accumulated NAV for return metrics')
assertIncludes(tushareService, '"adj_nav": adjusted_nav', 'Tushare NAV sync keeps adjusted NAV evidence')
assertIncludes(tushareService, '("accum_nav", "adj_nav", "unit_nav")', 'Tushare NAV sync chooses one consistent performance column')
assertIncludes(tushareService, 'def get_benchmark_nav', 'Tushare adapter exposes index benchmark NAV')
assertIncludes(tushareService, 'tushare.index_daily', 'Tushare benchmark rows retain source lineage')
assertIncludes(tushareService, 'DR007.IB', 'Tushare adapter requests the interbank DR007 evidence code')
assertIncludes(tushareService, 'annualized_rate', 'Tushare adapter keeps rate evidence typed separately from NAV')
assertIncludes(tushareService, '"total_netasset": _as_float(row.get("total_netasset"))', 'Tushare NAV sync keeps asset evidence when available')
assertIncludes(rankingMetricScript, '同步基金筛选榜单所需的真实净值与滚动指标', 'ranking metric sync script documents research-only scope')
assertIncludes(rankingMetricScript, 'build_fund_metric_payload', 'ranking metric sync writes performance and risk JSON for screener sorting')
assertIncludes(rankingMetricScript, 'FundNavDataEnrichmentService', 'ranking metric sync preserves money-market and benchmark evidence')
assertIncludes(rankingMetricScript, 'FundClassificationIngestionService', 'ranking metric sync refreshes standardized classification before benchmark lookup')
assertIncludes(rankingMetricScript, '--peer-evaluation-coverage', 'ranking metric sync can backfill category-relative evaluation coverage')
assertIncludes(rankingMetricScript, 'default=0', 'peer coverage backfill must not stop at a fixed ten-fund sample')
assertIncludes(rankingMetricScript, 'round_robin_peer_candidates', 'peer coverage backfill must allocate the total limit fairly across categories')
assertIncludes(rankingMetricScript, 'save_enrichment_metric_facts', 'money-market evidence must enter the unified metric panel')
assertIncludes(rankingMetricScript, 'tracking_difference', 'ranking metric sync mirrors real relative metrics into fund evaluation facts')
assertIncludes(rankingMetricScript, 'wind_code LIKE', 'ranking metric sync defaults to public fund codes with fund_nav coverage')
assertIncludes(batchSyncScript, 'TushareDataService(strict_no_mock=True)', 'production batch sync rejects mock evaluation inputs')
assertExcludes(batchSyncScript, 'score_fund(', 'production batch sync must not run legacy unclassified scoring')
assertExcludes(fullSyncScript, '"info": item', 'universe sync must not overwrite detailed fund info with a shallow record')
assertIncludes(classificationIngestionService, '_enhanced_index_candidate', 'classification ingestion separates supported enhanced index funds')
assertIncludes(classificationIngestionService, 'unsupported_or_ambiguous_index_enhanced_benchmark', 'classification ingestion gates unregistered enhanced benchmarks')
assertIncludes(classificationIngestionService, 'declared_benchmark_exact_alias', 'classification ingestion requires exact declared index evidence')
assertIncludes(classificationSyncScript, '--apply', 'classification sync defaults to preview and requires an explicit write flag')
assertIncludes(classificationSyncShell, 'sync_fund_classification_universe.py', 'classification sync shell invokes the standardized ingestion pipeline')
assertIncludes(universeSyncShell, 'sync_fund_classification_universe.py --apply', 'universe sync refreshes standardized classification after source ingestion')
assertIncludes(packageJson, 'funds:sync-classification', 'package exposes classification synchronization')
assertIncludes(rankingMetricShell, 'sync_fund_ranking_metrics.py', 'ranking metric shell invokes Python sync')
assertIncludes(packageJson, 'funds:update-ranking-metrics', 'package exposes ranking metric sync command')
assertIncludes(packageJson, 'funds:backfill-peer-evaluation', 'package exposes peer evaluation coverage backfill')

console.log('OK real data sync persists rolling metrics for peer percentile evidence')
