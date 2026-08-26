import type { EvidenceGap, EvidenceRef } from './evidence'
import type { ResearchAction } from './actions'

export type ToolResultAudit = {
  tool: string
  version: string
  inputHash: string
  generatedAt: string
}

export type ToolResult<T> = {
  ok: boolean
  data?: T
  evidence: EvidenceRef[]
  gaps: EvidenceGap[]
  hardBlocks: string[]
  nextActions: ResearchAction[]
  audit: ToolResultAudit
}

export type ResearchToolDomain = 'fund' | 'manager' | 'report' | 'pool' | 'evidence' | 'screening' | 'ranking' | 'comparison'
export type EvidencePolicy = 'strict_30d' | 'snapshot' | 'derived_metric' | 'narrative'
export type ToolSideEffect = 'none' | 'read_db' | 'write_report' | 'write_pool' | 'write_evidence'

export type ResearchToolManifest = {
  name: string
  version: string
  domain: ResearchToolDomain
  purpose: string
  inputSchema: string
  outputSchema: string
  evidencePolicy: EvidencePolicy
  canRunBatch: boolean
  sideEffects: ToolSideEffect[]
  guardrails: string[]
}

export type ResearchTool<Input, Output> = {
  manifest: ResearchToolManifest
  run(input: Input): ToolResult<Output>
}
