export type BuyBeforeGateStatus = 'blocked_by_hard_gate' | 'verify_first' | 'research_ready' | string

export type BuyBeforeDecisionSummary = {
  status: BuyBeforeGateStatus
  label: string
  hardBlocks: string[]
  cautionFlags: string[]
  nextActions: string[]
}

const asRecord = (value: unknown): Record<string, unknown> => {
  if (typeof value === 'string') {
    try {
      const parsed = JSON.parse(value)
      return parsed && typeof parsed === 'object' ? parsed as Record<string, unknown> : {}
    } catch {
      return {}
    }
  }
  return value && typeof value === 'object' ? value as Record<string, unknown> : {}
}

const asTrimmedStringArray = (value: unknown) =>
  Array.isArray(value)
    ? value.map((item) => String(item || '').trim()).filter(Boolean)
    : []

const cleanMarkdownValue = (value: string) =>
  value
    .replace(/\*\*/g, '')
    .replace(/。$/u, '')
    .trim()

const splitSemicolonList = (value: string) =>
  cleanMarkdownValue(value)
    .split(/[；;]/u)
    .map((item) => item.trim())
    .filter(Boolean)

function isPlaceholderLine(value: string) {
  return (
    !value
    || value.includes('未发现硬阻断')
    || value.includes('未触发额外风险提示')
    || value.includes('待补')
  )
}

function extractBuyBeforeSection(content: string) {
  const start = content.indexOf(['## ', '买', '前总闸门结论'].join(''))
  if (start < 0) return ''
  const rest = content.slice(start)
  const nextSection = rest.slice(1).search(/\n##\s+/u)
  return nextSection >= 0 ? rest.slice(0, nextSection + 1) : rest
}

function parseMarkdownBuyBeforeDecision(content: string): BuyBeforeDecisionSummary | null {
  const section = extractBuyBeforeSection(content)
  if (!section) return null

  const statusLine = section.match(/-\s+\*\*状态\*\*：(.+?)(?:（([a-z_]+)）)?。?$/mu)
  const hardLine = section.match(/-\s+\*\*硬阻断\*\*：(.+)$/mu)
  const cautionLine = section.match(/-\s+\*\*风险提示\*\*：(.+)$/mu)
  const nextActions = Array.from(section.matchAll(/^\s+-\s+(.+)$/gmu))
    .map((match) => cleanMarkdownValue(match[1] || ''))
    .filter((item) => item && !item.startsWith('**'))

  const status = (statusLine?.[2] || '').trim()
  const label = cleanMarkdownValue(statusLine?.[1] || '')
  const hardText = cleanMarkdownValue(hardLine?.[1] || '')
  const cautionText = cleanMarkdownValue(cautionLine?.[1] || '')
  const hardBlocks = isPlaceholderLine(hardText) ? [] : splitSemicolonList(hardText)
  const cautionFlags = isPlaceholderLine(cautionText) ? [] : splitSemicolonList(cautionText)

  if (!status && !label && !hardBlocks.length && !cautionFlags.length && !nextActions.length) {
    return null
  }

  return {
    status: status || (hardBlocks.length ? 'blocked_by_hard_gate' : cautionFlags.length ? 'verify_first' : 'research_ready'),
    label: label || (hardBlocks.length ? '硬阻断：不能进入正式研究结论' : cautionFlags.length ? '先复核：只能作为研究观察样本' : '研究证据相对完整，仍需完成正式研究复核'),
    hardBlocks,
    cautionFlags,
    nextActions,
  }
}

export function normalizeBuyBeforeDecisionSummary(
  value: unknown,
  options: {
    content?: string
    summary?: unknown
  } = {},
): BuyBeforeDecisionSummary | null {
  const record = asRecord(value)
  const summary = asRecord(options.summary)
  const structured: BuyBeforeDecisionSummary = {
    status: String(record.status || summary.buyBeforeGateStatus || '').trim(),
    label: String(record.label || summary.buyBeforeGateLabel || '').trim(),
    hardBlocks: asTrimmedStringArray(record.hardBlocks),
    cautionFlags: asTrimmedStringArray(record.cautionFlags),
    nextActions: asTrimmedStringArray(record.nextActions),
  }

  if (
    structured.status
    || structured.label
    || structured.hardBlocks.length
    || structured.cautionFlags.length
    || structured.nextActions.length
  ) {
    return structured
  }

  return parseMarkdownBuyBeforeDecision(options.content || '')
}
