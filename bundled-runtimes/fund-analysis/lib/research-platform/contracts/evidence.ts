export type EvidenceFreshness = 'fresh_30d' | 'snapshot' | 'derived' | 'stale' | 'missing'

export type EvidenceRef = {
  id: string
  label: string
  source: string
  sourceUpdatedAt?: string | null
  freshness: EvidenceFreshness
  field?: string
  subjectId?: string
  note?: string
}

export type EvidenceGapSeverity = 'hard_block' | 'verify_first' | 'observe'

export type EvidenceGap = {
  key: string
  label: string
  severity: EvidenceGapSeverity
  subjectId?: string
  reason: string
  requiredBeforeFormalReview: boolean
}

export type EvidenceLedger = {
  evidence: EvidenceRef[]
  gaps: EvidenceGap[]
  hardBlocks: string[]
}
