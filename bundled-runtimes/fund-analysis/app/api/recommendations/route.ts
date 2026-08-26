import { NextResponse } from 'next/server'
import { backendApiBaseUrl, toCamelFund } from '@/lib/backend-api'

type UnknownRecord = Record<string, unknown>

function asRecord(value: unknown): UnknownRecord {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as UnknownRecord : {}
}

function pickRecord(value: unknown, keys: string[]) {
  const source = asRecord(value)
  return Object.fromEntries(keys.flatMap((key) => source[key] === undefined ? [] : [[key, source[key]]]))
}

function compactManagers(value: unknown) {
  return (Array.isArray(value) ? value : []).map((manager) => pickRecord(manager, [
    'manager_id', 'wind_code', 'name', 'company', 'management_years', 'begin_date', 'end_date', 'source',
  ]))
}

function compactResearchProfile(value: unknown) {
  return pickRecord(value, [
    'primary_benchmark', 'peer_group', 'peer_group_id', 'peer_group_key', 'style_label', 'strategy_tags',
    'manager_tenure_start', 'memo_style_suggestions', 'derived_style_evidence',
  ])
}

function compactStyleProfile(value: unknown) {
  const source = asRecord(value)
  return {
    ...pickRecord(source, ['primary_label', 'status', 'source']),
    primary_evidence: pickRecord(source.primary_evidence, [
      'value', 'status', 'source', 'basis', 'caveat', 'quarter', 'peer_group_name', 'sample_size', 'data_source',
    ]),
    bond_holding_style: pickRecord(source.bond_holding_style, [
      'period_count', 'required_periods', 'secondary_labels', 'formal_classification_ready', 'data_source',
    ]),
    fof_holding_style: pickRecord(source.fof_holding_style, [
      'report_date', 'disclosed_fund_count', 'disclosed_nav_ratio', 'top5_nav_ratio',
      'concentration_label', 'classification_coverage', 'dominant_classification',
    ]),
  }
}

function compactScoring(value: unknown) {
  const source = asRecord(value)
  const dimensions = asRecord(source.dimension_scores)
  return {
    ...pickRecord(source, ['overall_score', 'overall_grade', 'status', 'methodology_version', 'missing_items']),
    dimension_scores: Object.fromEntries(Object.entries(dimensions).map(([key, dimension]) => [
      key,
      pickRecord(dimension, ['score', 'weight', 'included_in_score']),
    ])),
    data_quality: pickRecord(source.data_quality, ['score', 'status']),
  }
}

function toRecommendationFund(value: unknown) {
  const snapshot = asRecord(value)
  const fund = asRecord(snapshot.fund)
  const snapshotEvaluation = asRecord(snapshot.evaluation)
  const scoring = asRecord(snapshotEvaluation.evaluation)
  return toCamelFund({
    ...pickRecord(fund, [
      'id', 'wind_code', 'name', 'type', 'nav', 'nav_date', 'total_asset', 'establishment_date',
      'company', 'contract_benchmark', 'management_fee', 'custodian_fee', 'manager_ids',
      'performance_data', 'risk_metrics', 'peer_return_metrics', 'classification_ready', 'evaluation_ready',
    ]),
    managers: compactManagers(snapshot.managers),
    research_profile: compactResearchProfile(snapshot.research_profile),
    style_profile: compactStyleProfile(snapshot.style_profile),
    peer_percentiles: {
      metrics: {
        professional_score: asRecord(asRecord(scoring.peer_percentiles).professional_score),
      },
    },
    professional_scoring: {
      ...compactScoring(scoring),
      status: snapshotEvaluation.status || snapshot.status || 'unavailable',
      methodology_version: snapshotEvaluation.methodology_version,
      missing_items: snapshotEvaluation.missing_items,
    },
    recommendation_evidence: snapshot.recommendation_evidence,
  })
}

export async function GET(request: Request) {
  const url = new URL(request.url)
  const category = url.searchParams.get('category')?.trim() || ''
  const style = url.searchParams.get('style')?.trim() || ''
  if (!category) {
    return NextResponse.json({ error: '请先选择基金类别' }, { status: 400 })
  }

  try {
    const backendParams = new URLSearchParams({ peer_group: category, limit: '10' })
    if (style) backendParams.set('style', style)
    const response = await fetch(`${backendApiBaseUrl}/api/funds/recommendation-candidates?${backendParams}`, { cache: 'no-store' })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(payload.detail?.message || payload.detail || '基金数据库不可用')

    return NextResponse.json({
      data: ((payload.candidates || []) as Record<string, unknown>[]).map(toRecommendationFund),
      category,
      style: style || null,
      peerUniverseCount: Number(payload.peer_universe_count || 0),
      evidenceEligibleCount: Number(payload.evidence_eligible_count || 0),
      longTermReadyCount: Number(payload.long_term_ready_count || 0),
      styleMatchedCount: Number(payload.style_matched_count || 0),
      excludedCount: Number(payload.excluded_count || 0),
      excludedReasonCounts: asRecord(payload.excluded_reason_counts),
      availableStyles: Array.isArray(payload.available_styles) ? payload.available_styles : [],
      availableStyleOptions: Array.isArray(payload.available_style_options)
        ? payload.available_style_options
        : [],
      payloadProfile: 'recommendation_candidate_compact_v1',
      methodologyVersion: String(payload.methodology_version || ''),
      source: String(payload.source || 'full_peer_group_category_evaluation'),
    })
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : '无法读取同类基金评价' },
      { status: 503 },
    )
  }
}
