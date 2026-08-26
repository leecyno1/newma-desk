import type { EvidenceGap, EvidenceRef } from './evidence'
import type { ResearchAction } from './actions'

export type SkillDecision = 'research_ready' | 'verify_first' | 'blocked' | 'historical_trace'
export type SkillSurface = 'page' | 'api' | 'agent' | 'batch'
export type SkillFailureMode = 'block' | 'downgrade' | 'observe_only'

export type SkillStageManifest = {
  key: string
  tool: string
  required: boolean
  failureMode: SkillFailureMode
}

export type ResearchSkillManifest = {
  name: string
  version: string
  purpose: string
  stages: SkillStageManifest[]
  outputDecision: SkillDecision[]
  allowedSurfaces: SkillSurface[]
  guardrails: string[]
}

export type ReportArtifact = {
  id?: string
  title: string
  artifactType: 'report' | 'tsv' | 'memo' | 'work_order'
  href?: string
  summary: string
}

export type SkillRun<Subject = unknown> = {
  skillName: string
  subject: Subject
  decision: SkillDecision
  evidence: EvidenceRef[]
  gaps: EvidenceGap[]
  actions: ResearchAction[]
  reports?: ReportArtifact[]
  guardrails: string[]
}
