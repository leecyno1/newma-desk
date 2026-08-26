type JsonRecord = Record<string, unknown>

function record(value: unknown): JsonRecord {
  return value && typeof value === 'object' ? value as JsonRecord : {}
}

export function analysisEvidenceMetadata(dataSources: JsonRecord) {
  const snapshot = record(dataSources.research_snapshot)
  const assessment = record(dataSources.assessment_summary ?? snapshot.assessment_summary)
  const style = record(assessment.style_evidence)
  const research = record(assessment.research_evidence)
  const attribution = record(assessment.attribution_evidence)

  return {
    evaluation_score: assessment.score ?? null,
    evaluation_grade: assessment.grade ?? null,
    peer_rank: assessment.peer_rank ?? null,
    peer_count: assessment.peer_count ?? null,
    evaluation_verdict: assessment.verdict ?? null,
    style_evidence_status: style.status ?? null,
    style_evidence_scope: style.scope ?? null,
    style_evidence_quarter: style.quarter ?? null,
    style_labels: Array.isArray(style.labels) ? style.labels : [],
    memo_style_labels: Array.isArray(style.memo_labels) ? style.memo_labels : [],
    research_evidence_status: research.status ?? null,
    research_evidence_note: research.note ?? null,
    attribution_evidence_status: attribution.status ?? null,
    attribution_evidence_headline: attribution.headline ?? null,
    attribution_evidence_detail: attribution.detail ?? null,
    attribution_disclosure_coverage: attribution.coverage ?? null,
    formal_barra_ready: attribution.formal_barra_ready ?? false,
    barra_descriptor_ready: attribution.barra_descriptor_ready ?? false,
  }
}
