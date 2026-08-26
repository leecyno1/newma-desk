import type { EvidenceGap, EvidenceRef, ResearchAction, ToolResult, ToolResultAudit } from '../contracts'

export function stableHash(input: unknown) {
  const text = JSON.stringify(input, Object.keys(input as Record<string, unknown> || {}).sort())
  let hash = 0
  for (let index = 0; index < text.length; index += 1) {
    hash = ((hash << 5) - hash + text.charCodeAt(index)) | 0
  }
  return Math.abs(hash).toString(36)
}

export function createToolResult<T>(
  tool: string,
  version: string,
  input: unknown,
  data: T,
  options: {
    ok?: boolean
    evidence?: EvidenceRef[]
    gaps?: EvidenceGap[]
    hardBlocks?: string[]
    nextActions?: ResearchAction[]
  } = {},
): ToolResult<T> {
  const hardBlocks = options.hardBlocks || []
  const gaps = options.gaps || []
  const audit: ToolResultAudit = {
    tool,
    version,
    inputHash: stableHash(input),
    generatedAt: new Date().toISOString(),
  }
  return {
    ok: options.ok ?? hardBlocks.length === 0,
    data,
    evidence: options.evidence || [],
    gaps,
    hardBlocks,
    nextActions: options.nextActions || [],
    audit,
  }
}
