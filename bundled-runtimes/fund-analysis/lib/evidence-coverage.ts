import postgres from 'postgres'
import { materialEvidenceHref } from '@/lib/research-platform/routes'

type CoverageLevel = 'strong' | 'partial' | 'weak'

export type EvidenceCoverageDimension = {
  key: string
  label: string
  group: '基础研究' | '经理评价' | '研究复核' | '研究增强'
  covered: number
  total: number
  coverage: number
  level: CoverageLevel
  requiredBeforeBuy: boolean
  description: string
  actionHref: string
  actionLabel: string
}

export type EvidenceCoverageGapFund = {
  id: string
  windCode: string
  name: string
  type: string | null
  navDate: string | null
  updatedAt: string | null
  gapCount: number
  requiredGapCount: number
  gaps: string[]
}

export type EvidenceCoveragePayload = {
  totalFunds: number
  coverageScore: number
  generatedAt: string
  source: string
  dimensions: EvidenceCoverageDimension[]
  groupSummary: Array<{
    group: EvidenceCoverageDimension['group']
    averageCoverage: number
    missingCount: number
    requiredMissingCount: number
  }>
  priorityQueue: Array<{
    key: string
    label: string
    missing: number
    coverage: number
    requiredBeforeBuy: boolean
    actionHref: string
  }>
  gapFunds: EvidenceCoverageGapFund[]
}

let sqlClient: postgres.Sql | null = null

function sql() {
  if (!sqlClient) {
    const databaseUrl = process.env.DATABASE_URL
    if (!databaseUrl) throw new Error('DATABASE_URL 未配置，无法读取基金证据覆盖率')
    sqlClient = postgres(databaseUrl, {
      max: 3,
      idle_timeout: 20,
      connect_timeout: 10,
    })
  }
  return sqlClient
}

function numberValue(value: unknown) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function percent(covered: number, total: number) {
  if (total <= 0) return 0
  return Math.round((covered / total) * 1000) / 10
}

function levelFromCoverage(value: number): CoverageLevel {
  if (value >= 80) return 'strong'
  if (value >= 45) return 'partial'
  return 'weak'
}

function dimension(
  key: string,
  label: string,
  group: EvidenceCoverageDimension['group'],
  covered: number,
  total: number,
  requiredBeforeBuy: boolean,
  description: string,
  actionHref: string,
  actionLabel: string,
): EvidenceCoverageDimension {
  const coverage = percent(covered, total)
  return {
    key,
    label,
    group,
    covered,
    total,
    coverage,
    level: levelFromCoverage(coverage),
    requiredBeforeBuy,
    description,
    actionHref,
    actionLabel,
  }
}

async function tableExists(tableName: string) {
  const rows = await sql()`
    SELECT to_regclass(${`public.${tableName}`}) IS NOT NULL AS exists
  `
  return Boolean(rows[0]?.exists)
}

async function columnExists(tableName: string, columnName: string) {
  const rows = await sql()`
    SELECT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = ${tableName}
        AND column_name = ${columnName}
    ) AS exists
  `
  return Boolean(rows[0]?.exists)
}

// 覆盖率聚合需对全量基金逐行执行多个相关子查询（约 60-90 秒），
// 且数据每日才变化一次：加 5 分钟 TTL 缓存 + 并发去重（inflight 复用）。
const EVIDENCE_COVERAGE_CACHE_TTL_MS = 5 * 60 * 1000
let evidenceCoverageCache: { data: EvidenceCoveragePayload; expiresAt: number } | null = null
let evidenceCoverageInflight: Promise<EvidenceCoveragePayload> | null = null

export async function getEvidenceCoverage(): Promise<EvidenceCoveragePayload> {
  if (evidenceCoverageCache && evidenceCoverageCache.expiresAt > Date.now()) {
    return evidenceCoverageCache.data
  }
  if (evidenceCoverageInflight) {
    return evidenceCoverageInflight
  }
  evidenceCoverageInflight = computeEvidenceCoverage()
    .then((data) => {
      evidenceCoverageCache = { data, expiresAt: Date.now() + EVIDENCE_COVERAGE_CACHE_TTL_MS }
      return data
    })
    .finally(() => {
      evidenceCoverageInflight = null
    })
  return evidenceCoverageInflight
}

async function computeEvidenceCoverage(): Promise<EvidenceCoveragePayload> {
  const [
    hasFundNav,
    hasManagers,
    hasSalesRules,
    hasResearchProfiles,
    hasMetricSnapshots,
    hasAiReports,
    hasHoldings,
  ] = await Promise.all([
    tableExists('fund_nav'),
    tableExists('managers'),
    tableExists('fund_sales_rules'),
    tableExists('fund_research_profiles'),
    tableExists('metric_snapshots'),
    tableExists('ai_analysis_reports'),
    tableExists('holdings'),
  ])
  const [holdingsHasWindCode, holdingsHasFundId] = hasHoldings
    ? await Promise.all([
        columnExists('holdings', 'wind_code'),
        columnExists('holdings', 'fund_id'),
      ])
    : [false, false]
  const salesSourceIdentityClause = `(
              (
                NULLIF(source_url, '') IS NOT NULL
                AND LOWER(TRIM(source_url)) NOT IN (
                  '-', '--', 'na', 'n/a', 'none', 'null', 'unknown', 'tbd', 'todo',
                  'placeholder', 'sample', 'example', 'demo', 'mock', 'test',
                  '待补', '待核', '待确认', '暂无', '无', '示例', '样例', '测试',
                  '占位', '来源待补', '待补来源', '链接待补', '待补链接',
                  '示例链接', '样例链接', '测试链接', '占位链接'
                )
                AND LOWER(TRIM(source_url)) NOT LIKE 'https://example.%'
                AND LOWER(TRIM(source_url)) NOT LIKE 'http://example.%'
              )
              OR (
                NULLIF(notes, '') IS NOT NULL
                AND LOWER(TRIM(notes)) NOT IN (
                  '-', '--', 'na', 'n/a', 'none', 'null', 'unknown', 'tbd', 'todo',
                  'placeholder', 'sample', 'example', 'demo', 'mock', 'test',
                  '待补', '待核', '待确认', '暂无', '无', '示例', '样例', '测试',
                  '占位', '来源待补', '待补来源', '备注待补', '待补备注'
                )
              )
            )`

  const salesJoin = hasSalesRules
    ? `LEFT JOIN (
	      SELECT
	          wind_code,
	          BOOL_OR(
	            purchase_status <> 'unknown'
	            AND source_updated_at IS NOT NULL
	            AND source_updated_at >= CURRENT_DATE - INTERVAL '30 days'
	            AND source_updated_at <= CURRENT_DATE
	            AND COALESCE(LOWER(platform), '') NOT LIKE '%tushare%'
	            AND COALESCE(LOWER(source_url), '') NOT LIKE '%tushare.fund_basic%'
	            AND ${salesSourceIdentityClause}
	          ) AS has_purchase_status,
	          BOOL_OR(
	            purchase_fee_rate IS NOT NULL
	            AND source_updated_at IS NOT NULL
	            AND source_updated_at >= CURRENT_DATE - INTERVAL '30 days'
	            AND source_updated_at <= CURRENT_DATE
	            AND COALESCE(LOWER(platform), '') NOT LIKE '%tushare%'
	            AND COALESCE(LOWER(source_url), '') NOT LIKE '%tushare.fund_basic%'
	            AND ${salesSourceIdentityClause}
	          ) AS has_purchase_fee,
          BOOL_OR(
            jsonb_array_length(COALESCE(redemption_fee_rules, '[]'::jsonb)) > 0
            AND source_updated_at IS NOT NULL
            AND source_updated_at >= CURRENT_DATE - INTERVAL '30 days'
            AND source_updated_at <= CURRENT_DATE
            AND COALESCE(LOWER(platform), '') NOT LIKE '%tushare%'
            AND COALESCE(LOWER(source_url), '') NOT LIKE '%tushare.fund_basic%'
            AND ${salesSourceIdentityClause}
          ) AS has_redemption_rule,
	          BOOL_OR(
	            min_purchase_amount IS NOT NULL
	            AND source_updated_at IS NOT NULL
	            AND source_updated_at >= CURRENT_DATE - INTERVAL '30 days'
	            AND source_updated_at <= CURRENT_DATE
	            AND COALESCE(LOWER(platform), '') NOT LIKE '%tushare%'
	            AND COALESCE(LOWER(source_url), '') NOT LIKE '%tushare.fund_basic%'
	            AND ${salesSourceIdentityClause}
	          ) AS has_min_purchase,
	          BOOL_OR(
	            daily_limit_amount IS NOT NULL
	            AND source_updated_at IS NOT NULL
	            AND source_updated_at >= CURRENT_DATE - INTERVAL '30 days'
	            AND source_updated_at <= CURRENT_DATE
	            AND COALESCE(LOWER(platform), '') NOT LIKE '%tushare%'
	            AND COALESCE(LOWER(source_url), '') NOT LIKE '%tushare.fund_basic%'
	            AND ${salesSourceIdentityClause}
	          ) AS has_daily_limit,
	          BOOL_OR(
	            sales_service_fee_rate IS NOT NULL
	            AND source_updated_at IS NOT NULL
	            AND source_updated_at >= CURRENT_DATE - INTERVAL '30 days'
	            AND source_updated_at <= CURRENT_DATE
	            AND COALESCE(LOWER(platform), '') NOT LIKE '%tushare%'
	            AND COALESCE(LOWER(source_url), '') NOT LIKE '%tushare.fund_basic%'
	            AND ${salesSourceIdentityClause}
	          ) AS has_sales_service_fee,
          BOOL_OR(
            NULLIF(UPPER(risk_level), '') ~ '^R[1-5]$'
            AND source_updated_at IS NOT NULL
            AND source_updated_at >= CURRENT_DATE - INTERVAL '30 days'
            AND source_updated_at <= CURRENT_DATE
            AND COALESCE(LOWER(platform), '') NOT LIKE '%tushare%'
            AND COALESCE(LOWER(source_url), '') NOT LIKE '%tushare.fund_basic%'
            AND ${salesSourceIdentityClause}
          ) AS has_risk_level,
	          BOOL_OR(
	            (supports_sip IS NOT NULL OR min_sip_amount IS NOT NULL)
	            AND source_updated_at IS NOT NULL
	            AND source_updated_at >= CURRENT_DATE - INTERVAL '30 days'
	            AND source_updated_at <= CURRENT_DATE
	            AND COALESCE(LOWER(platform), '') NOT LIKE '%tushare%'
	            AND COALESCE(LOWER(source_url), '') NOT LIKE '%tushare.fund_basic%'
	            AND ${salesSourceIdentityClause}
	          ) AS has_sip_rule
        FROM fund_sales_rules
        GROUP BY wind_code
      ) sales ON sales.wind_code = funds.wind_code`
    : `LEFT JOIN (
        SELECT
          NULL::text AS wind_code,
          false AS has_purchase_status,
          false AS has_purchase_fee,
          false AS has_redemption_rule,
          false AS has_min_purchase,
          false AS has_daily_limit,
          false AS has_sales_service_fee,
          false AS has_risk_level,
          false AS has_sip_rule
        WHERE false
      ) sales ON false`

  const managerDetailSelect = hasManagers
    ? `EXISTS (
        SELECT 1
        FROM managers manager
        WHERE manager.wind_code = ANY(funds.manager_ids)
           OR manager.name = ANY(funds.manager_ids)
      ) AS manager_detail_ready`
    : `false AS manager_detail_ready`

  const navSeriesSelect = hasFundNav
    ? `EXISTS (
        SELECT 1
        FROM fund_nav nav
        WHERE nav.wind_code = funds.wind_code
        LIMIT 1
      ) AS nav_series_ready`
    : `false AS nav_series_ready`

  const researchProfileSelect = hasResearchProfiles
    ? `EXISTS (
        SELECT 1
        FROM fund_research_profiles profile
        WHERE profile.wind_code = funds.wind_code
        LIMIT 1
      ) AS research_profile_ready`
    : `false AS research_profile_ready`

  const metricSnapshotSelect = hasMetricSnapshots
    ? `EXISTS (
        SELECT 1
        FROM metric_snapshots metric
        WHERE metric.target_type = 'fund'
          AND metric.target_id = funds.wind_code
        LIMIT 1
      ) AS metric_snapshot_ready`
    : `false AS metric_snapshot_ready`

  const reportSelect = hasAiReports
    ? `EXISTS (
        SELECT 1
        FROM ai_analysis_reports report
        WHERE report.target_type = 'fund'
          AND (report.target_id = funds.wind_code OR report.target_id = funds.id::text)
        LIMIT 1
      ) AS report_ready`
    : `false AS report_ready`

  const holdingFundPredicate = [
    holdingsHasWindCode ? 'holding.wind_code = funds.wind_code' : '',
    holdingsHasFundId ? 'holding.fund_id = funds.id::text' : '',
  ].filter(Boolean).join(' OR ')

  const holdingSelect = hasHoldings && holdingFundPredicate
    ? `((
        SELECT COUNT(*)
        FROM holdings holding
        WHERE (${holdingFundPredicate})
          AND NULLIF(holding.quarter, '') IS NOT NULL
          AND NULLIF(holding.stock_code, '') IS NOT NULL
          AND holding.weight IS NOT NULL
          AND holding.weight > 0
      ) >= 5) AS holding_ready`
    : `false AS holding_ready`

  const coverageSql = `
    WITH base AS (
      SELECT
        funds.id,
        funds.wind_code,
        funds.name,
        funds.type,
        funds.nav_date,
        funds.updated_at,
        (
          NULLIF(funds.name, '') IS NOT NULL
          AND NULLIF(funds.type, '') IS NOT NULL
          AND funds.establishment_date IS NOT NULL
        ) AS identity_ready,
        (funds.nav IS NOT NULL AND funds.nav_date IS NOT NULL) AS nav_ready,
        (funds.nav_date >= CURRENT_DATE - INTERVAL '30 days') AS nav_fresh_ready,
        (funds.total_asset IS NOT NULL AND funds.total_asset > 0) AS asset_ready,
        (
          COALESCE(funds.cardinality, 0) > 0
        ) AS manager_link_ready,
        ${managerDetailSelect},
        (
          NULLIF(funds.raw_data#>>'{info,management_fee}', '') IS NOT NULL
          AND NULLIF(funds.raw_data#>>'{info,custodian_fee}', '') IS NOT NULL
        ) AS fee_ready,
        (
          funds.performance_data IS NOT NULL
          AND funds.performance_data <> '{}'::jsonb
          AND (
            NULLIF(funds.performance_data->>'annualized_return_1y', '') IS NOT NULL
            OR NULLIF(funds.performance_data->>'total_return', '') IS NOT NULL
            OR NULLIF(funds.performance_data->>'sharpe_ratio', '') IS NOT NULL
          )
        ) AS performance_ready,
        (
          funds.risk_metrics IS NOT NULL
          AND funds.risk_metrics <> '{}'::jsonb
          AND (
            NULLIF(funds.risk_metrics->>'max_drawdown_1y', '') IS NOT NULL
            OR NULLIF(funds.risk_metrics->>'max_drawdown', '') IS NOT NULL
            OR NULLIF(funds.risk_metrics->>'annualized_volatility_1y', '') IS NOT NULL
            OR NULLIF(funds.risk_metrics->>'volatility', '') IS NOT NULL
            OR NULLIF(funds.risk_metrics->>'sharpe_ratio', '') IS NOT NULL
          )
        ) AS risk_ready,
        ${navSeriesSelect},
        ${researchProfileSelect},
        ${metricSnapshotSelect},
        ${reportSelect},
        ${holdingSelect},
        COALESCE(sales.has_purchase_status, false) AS purchase_status_ready,
        COALESCE(sales.has_purchase_fee, false) AS purchase_fee_ready,
        COALESCE(sales.has_redemption_rule, false) AS redemption_rule_ready,
        COALESCE(sales.has_min_purchase, false) AS min_purchase_ready,
        COALESCE(sales.has_daily_limit, false) AS daily_limit_ready,
        COALESCE(sales.has_sales_service_fee, false) AS sales_service_fee_ready,
        COALESCE(sales.has_risk_level, false) AS risk_level_ready,
        COALESCE(sales.has_sip_rule, false) AS sip_rule_ready
      FROM (
        SELECT funds.*, cardinality(manager_ids) AS cardinality
        FROM funds
      ) funds
      ${salesJoin}
    )
    SELECT
      COUNT(*)::int AS total,
      COUNT(*) FILTER (WHERE identity_ready)::int AS identity_ready,
      COUNT(*) FILTER (WHERE nav_ready)::int AS nav_ready,
      COUNT(*) FILTER (WHERE nav_fresh_ready)::int AS nav_fresh_ready,
      COUNT(*) FILTER (WHERE asset_ready)::int AS asset_ready,
      COUNT(*) FILTER (WHERE performance_ready)::int AS performance_ready,
      COUNT(*) FILTER (WHERE risk_ready)::int AS risk_ready,
      COUNT(*) FILTER (WHERE nav_series_ready)::int AS nav_series_ready,
      COUNT(*) FILTER (WHERE manager_link_ready)::int AS manager_link_ready,
      COUNT(*) FILTER (WHERE manager_detail_ready)::int AS manager_detail_ready,
      COUNT(*) FILTER (WHERE fee_ready)::int AS fee_ready,
      COUNT(*) FILTER (WHERE purchase_status_ready)::int AS purchase_status_ready,
      COUNT(*) FILTER (WHERE purchase_fee_ready)::int AS purchase_fee_ready,
      COUNT(*) FILTER (WHERE redemption_rule_ready)::int AS redemption_rule_ready,
      COUNT(*) FILTER (WHERE min_purchase_ready)::int AS min_purchase_ready,
      COUNT(*) FILTER (WHERE daily_limit_ready)::int AS daily_limit_ready,
      COUNT(*) FILTER (WHERE sales_service_fee_ready)::int AS sales_service_fee_ready,
      COUNT(*) FILTER (WHERE risk_level_ready)::int AS risk_level_ready,
      COUNT(*) FILTER (WHERE sip_rule_ready)::int AS sip_rule_ready,
      COUNT(*) FILTER (WHERE research_profile_ready)::int AS research_profile_ready,
      COUNT(*) FILTER (WHERE metric_snapshot_ready)::int AS metric_snapshot_ready,
      COUNT(*) FILTER (WHERE holding_ready)::int AS holding_ready,
      COUNT(*) FILTER (WHERE report_ready)::int AS report_ready
    FROM base
  `

  const gapSql = `
    WITH base AS (
      SELECT
        funds.id::text AS id,
        funds.wind_code,
        funds.name,
        funds.type,
        funds.nav_date,
        funds.updated_at,
        (funds.nav IS NOT NULL AND funds.nav_date IS NOT NULL) AS nav_ready,
        (funds.nav_date >= CURRENT_DATE - INTERVAL '30 days') AS nav_fresh_ready,
        (funds.total_asset IS NOT NULL AND funds.total_asset > 0) AS asset_ready,
        (COALESCE(funds.cardinality, 0) > 0) AS manager_link_ready,
        (
          NULLIF(funds.raw_data#>>'{info,management_fee}', '') IS NOT NULL
          AND NULLIF(funds.raw_data#>>'{info,custodian_fee}', '') IS NOT NULL
        ) AS fee_ready,
        (
          funds.performance_data IS NOT NULL
          AND funds.performance_data <> '{}'::jsonb
          AND (
            NULLIF(funds.performance_data->>'annualized_return_1y', '') IS NOT NULL
            OR NULLIF(funds.performance_data->>'total_return', '') IS NOT NULL
            OR NULLIF(funds.performance_data->>'sharpe_ratio', '') IS NOT NULL
          )
        ) AS performance_ready,
        (
          funds.risk_metrics IS NOT NULL
          AND funds.risk_metrics <> '{}'::jsonb
          AND (
            NULLIF(funds.risk_metrics->>'max_drawdown_1y', '') IS NOT NULL
            OR NULLIF(funds.risk_metrics->>'max_drawdown', '') IS NOT NULL
            OR NULLIF(funds.risk_metrics->>'annualized_volatility_1y', '') IS NOT NULL
            OR NULLIF(funds.risk_metrics->>'volatility', '') IS NOT NULL
            OR NULLIF(funds.risk_metrics->>'sharpe_ratio', '') IS NOT NULL
          )
        ) AS risk_ready,
        ${navSeriesSelect},
        ${holdingSelect},
        COALESCE(sales.has_purchase_status, false) AS purchase_status_ready,
        COALESCE(sales.has_purchase_fee, false) AS purchase_fee_ready,
        COALESCE(sales.has_redemption_rule, false) AS redemption_rule_ready,
        COALESCE(sales.has_min_purchase, false) AS min_purchase_ready,
        COALESCE(sales.has_daily_limit, false) AS daily_limit_ready,
        COALESCE(sales.has_sales_service_fee, false) AS sales_service_fee_ready,
        COALESCE(sales.has_risk_level, false) AS risk_level_ready,
        COALESCE(sales.has_sip_rule, false) AS sip_rule_ready
      FROM (
        SELECT funds.*, cardinality(manager_ids) AS cardinality
        FROM funds
      ) funds
      ${salesJoin}
    ),
    gaps AS (
      SELECT
        *,
        ARRAY_REMOVE(ARRAY[
          CASE WHEN NOT nav_ready THEN '最新净值' END,
          CASE WHEN NOT nav_fresh_ready THEN '净值新鲜度' END,
          CASE WHEN NOT nav_series_ready THEN '净值序列' END,
          CASE WHEN NOT asset_ready THEN '基金规模' END,
          CASE WHEN NOT performance_ready THEN '绩效指标' END,
          CASE WHEN NOT risk_ready THEN '风险指标' END,
          CASE WHEN NOT holding_ready THEN '持仓明细' END,
          CASE WHEN NOT manager_link_ready THEN '基金经理' END,
          CASE WHEN NOT fee_ready THEN '管理/托管费' END,
          CASE WHEN NOT purchase_status_ready THEN '申购状态' END,
          CASE WHEN NOT purchase_fee_ready THEN '申购费率' END,
          CASE WHEN NOT redemption_rule_ready THEN '赎回规则' END,
          CASE WHEN NOT min_purchase_ready THEN '最低申购' END,
          CASE WHEN NOT daily_limit_ready THEN '限购金额' END,
          CASE WHEN NOT sales_service_fee_ready THEN '销售服务费' END,
          CASE WHEN NOT risk_level_ready THEN '风险等级来源背书' END,
          CASE WHEN NOT sip_rule_ready THEN '定投规则' END
        ], NULL) AS gaps,
        (
          (CASE WHEN NOT purchase_status_ready THEN 1 ELSE 0 END) +
          (CASE WHEN NOT purchase_fee_ready THEN 1 ELSE 0 END) +
          (CASE WHEN NOT redemption_rule_ready THEN 1 ELSE 0 END) +
          (CASE WHEN NOT min_purchase_ready THEN 1 ELSE 0 END) +
          (CASE WHEN NOT daily_limit_ready THEN 1 ELSE 0 END) +
          (CASE WHEN NOT sales_service_fee_ready THEN 1 ELSE 0 END) +
          (CASE WHEN NOT risk_level_ready THEN 1 ELSE 0 END) +
          (CASE WHEN NOT sip_rule_ready THEN 1 ELSE 0 END)
        ) AS required_gap_count
      FROM base
    )
    SELECT
      id,
      wind_code,
      name,
      type,
      nav_date,
      updated_at,
      CARDINALITY(gaps)::int AS gap_count,
      required_gap_count::int,
      gaps
    FROM gaps
    WHERE CARDINALITY(gaps) > 0
    ORDER BY required_gap_count DESC, CARDINALITY(gaps) DESC, updated_at DESC NULLS LAST
    LIMIT 30
  `

  const [coverageRows, gapRows] = await Promise.all([
    sql().unsafe(coverageSql),
    sql().unsafe(gapSql),
  ])

  const row = coverageRows[0] as Record<string, unknown> | undefined
  const total = numberValue(row?.total)
  const dimensions = [
    dimension('identity', '基金基础身份', '基础研究', numberValue(row?.identity_ready), total, false, '名称、类型和成立日期是否完整。', '/market', '去全市场浏览'),
    dimension('nav', '最新净值', '基础研究', numberValue(row?.nav_ready), total, false, '单位净值和净值日期是收益回放、回撤计算的入口。', '/market?hasNav=false', '查看缺净值基金'),
    dimension('nav_fresh', '净值新鲜度', '基础研究', numberValue(row?.nav_fresh_ready), total, false, '净值日期在 30 天内，避免用旧价格做研究。', '/market?sortBy=updatedAt&sortOrder=asc', '查看旧数据'),
    dimension('nav_series', '净值序列', '基础研究', numberValue(row?.nav_series_ready), total, false, '有净值序列才能做持有体验回放和窗口收益。', '/market?hasNav=true', '补净值序列'),
    dimension('asset', '基金规模', '基础研究', numberValue(row?.asset_ready), total, false, '规模用于容量、清盘风险和流动性判断。', '/market?assetMin=0&sortBy=totalAsset&sortOrder=asc', '查看规模缺口'),
    dimension('performance', '绩效指标', '基础研究', numberValue(row?.performance_ready), total, false, '近一年收益、夏普等指标支撑筛选排序。', '/market?hasPerformance=false', '查看缺绩效基金'),
    dimension('risk', '风险指标', '基础研究', numberValue(row?.risk_ready), total, false, '最大回撤、波动率等指标支撑适配和风险控制。', '/market?sortBy=risk&sortOrder=desc', '查看高风险/缺风险'),
    dimension('manager_link', '经理归属', '经理评价', numberValue(row?.manager_link_ready), total, false, '基金需要关联现任经理，才能进入经理评价。', '/market?hasManager=false', '查看缺经理基金'),
    dimension('manager_detail', '经理履历', '经理评价', numberValue(row?.manager_detail_ready), total, false, '经理表含任期、公司、履历等评价基础字段。', '/managers', '查看基金经理'),
    dimension('fee', '管理/托管费', '研究复核', numberValue(row?.fee_ready), total, false, 'Tushare 基础费率用于成本初筛。', '/market?hasFee=false', '查看缺费率基金'),
    dimension('holding', '持仓明细', '研究复核', numberValue(row?.holding_ready), total, false, '至少 5 条带季度、股票和权重的持仓，支撑前十大集中度与行业暴露判断。', '/market', '查看持仓缺口'),
    dimension('purchase_status', '申购状态', '研究复核', numberValue(row?.purchase_status_ready), total, true, '销售平台开放、暂停或限购状态必须有 30 天内来源背书。', materialEvidenceHref(), '维护材料证据'),
    dimension('purchase_fee', '申购费率', '研究复核', numberValue(row?.purchase_fee_ready), total, true, '申购费及折扣影响真实配置成本，必须有 30 天内来源背书。', materialEvidenceHref(), '补申购费'),
    dimension('redemption_rule', '赎回规则', '研究复核', numberValue(row?.redemption_rule_ready), total, true, '赎回费通常依赖持有期，必须有 30 天内来源背书。', materialEvidenceHref(), '补赎回规则'),
    dimension('min_purchase', '最低申购', '研究复核', numberValue(row?.min_purchase_ready), total, true, '起购金额影响计划金额是否可执行，必须有 30 天内来源背书。', materialEvidenceHref(), '补起购金额'),
    dimension('daily_limit', '限购金额', '研究复核', numberValue(row?.daily_limit_ready), total, true, '限购直接决定计划金额是否可执行，必须有 30 天内来源背书。', materialEvidenceHref(), '补限购信息'),
    dimension('sales_service_fee', '销售服务费', '研究复核', numberValue(row?.sales_service_fee_ready), total, true, '销售服务费影响 C 类与短持成本，必须有 30 天内来源背书。', materialEvidenceHref(), '补销售服务费'),
    dimension('risk_level', '风险等级来源背书', '研究复核', numberValue(row?.risk_level_ready), total, true, 'R1-R5 必须来自销售平台、基金合同或可追溯公告，且来源日期在 30 天研究复核窗口内；Tushare fund_basic 不计入覆盖。', materialEvidenceHref({ scope: 'market', focus: 'risk_level', queueMode: 'high_score_missing_risk', purchasePlan: 'sip' }), '补风险等级来源'),
    dimension('sip_rule', '定投规则', '研究复核', numberValue(row?.sip_rule_ready), total, true, '定投支持状态和定投起点用于研究方式假设与执行约束判断，必须有 30 天内来源背书。', materialEvidenceHref(), '补定投规则'),
    dimension('research_profile', '研究画像', '研究增强', numberValue(row?.research_profile_ready), total, false, '基准、同类池和风格标签用于避免跨类误比。', '/analysis', '进入基金研究'),
    dimension('metric_snapshot', '滚动指标快照', '研究增强', numberValue(row?.metric_snapshot_ready), total, false, '滚动窗口指标支持持有体验与同类分位分析。', '/analysis/comparison', '看同类横评'),
    dimension('report', '研究报告', '研究增强', numberValue(row?.report_ready), total, false, '已生成的本地研究报告可作为后续复核材料。', '/reports', '查看报告'),
  ]

  const weightedScore = dimensions.reduce((sum, item) => {
    const weight = item.requiredBeforeBuy ? 1.4 : item.group === '基础研究' ? 1.1 : 1
    return sum + item.coverage * weight
  }, 0)
  const weightSum = dimensions.reduce((sum, item) => sum + (item.requiredBeforeBuy ? 1.4 : item.group === '基础研究' ? 1.1 : 1), 0)

  const groups = Array.from(new Set(dimensions.map((item) => item.group)))
  const groupSummary = groups.map((group) => {
    const items = dimensions.filter((item) => item.group === group)
    return {
      group,
      averageCoverage: Math.round((items.reduce((sum, item) => sum + item.coverage, 0) / Math.max(items.length, 1)) * 10) / 10,
      missingCount: items.reduce((sum, item) => sum + Math.max(0, item.total - item.covered), 0),
      requiredMissingCount: items
        .filter((item) => item.requiredBeforeBuy)
        .reduce((sum, item) => sum + Math.max(0, item.total - item.covered), 0),
    }
  })

  return {
    totalFunds: total,
    coverageScore: Math.round((weightedScore / Math.max(weightSum, 1)) * 10) / 10,
    generatedAt: new Date().toISOString(),
    source: 'local.postgres.funds_plus_merged_sales_rules',
    dimensions,
    groupSummary,
    priorityQueue: dimensions
      .map((item) => ({
        key: item.key,
        label: item.label,
        missing: Math.max(0, item.total - item.covered),
        coverage: item.coverage,
        requiredBeforeBuy: item.requiredBeforeBuy,
        actionHref: item.actionHref,
      }))
      .filter((item) => item.missing > 0)
      .sort((left, right) => {
        if (left.requiredBeforeBuy !== right.requiredBeforeBuy) return left.requiredBeforeBuy ? -1 : 1
        if (left.coverage !== right.coverage) return left.coverage - right.coverage
        return right.missing - left.missing
      })
      .slice(0, 8),
    gapFunds: gapRows.map((gapRow) => ({
      id: String(gapRow.id || gapRow.wind_code || ''),
      windCode: String(gapRow.wind_code || ''),
      name: String(gapRow.name || ''),
      type: gapRow.type ? String(gapRow.type) : null,
      navDate: gapRow.nav_date ? String(gapRow.nav_date).slice(0, 10) : null,
      updatedAt: gapRow.updated_at ? new Date(String(gapRow.updated_at)).toISOString() : null,
      gapCount: numberValue(gapRow.gap_count),
      requiredGapCount: numberValue(gapRow.required_gap_count),
      gaps: Array.isArray(gapRow.gaps) ? gapRow.gaps.map(String) : [],
    })),
  }
}
