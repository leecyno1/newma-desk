const placeholderSourceTokens = new Set([
  '-',
  '--',
  '—',
  'na',
  'n/a',
  'none',
  'null',
  'unknown',
  'tbd',
  'todo',
  'placeholder',
  'sample',
  'example',
  'demo',
  'mock',
  'test',
  '待补',
  '待核',
  '待确认',
  '暂无',
  '无',
  '示例',
  '样例',
  '测试',
  '占位',
  '来源待补',
  '待补来源',
  '链接待补',
  '待补链接',
  '示例链接',
  '样例链接',
  '测试链接',
  '占位链接',
  '备注待补',
  '待补备注',
])

const placeholderHostPattern = /^(?:https?:\/\/)?(?:www\.)?(?:example\.(?:com|org|net)|placeholder(?:\.[a-z]+)?|mock(?:\.[a-z]+)?|demo(?:\.[a-z]+)?|sample(?:\.[a-z]+)?|test(?:\.[a-z]+)?)(?:[/?#].*)?$/iu

function compactSourceText(value: string) {
  return value
    .trim()
    .toLowerCase()
    .replace(/[\s　"'“”‘’`.,，。;；:：!?！？()[\]{}【】<>《》|/\\_·]+/gu, '')
}

export function isPlaceholderSalesRuleSourceText(value: unknown) {
  if (typeof value !== 'string') return false
  const text = value.trim()
  if (!text) return false
  const normalized = text.toLowerCase()
  const compacted = compactSourceText(text)
  return placeholderSourceTokens.has(normalized)
    || placeholderSourceTokens.has(compacted)
    || placeholderHostPattern.test(normalized)
}

export function hasValidSalesRuleSourceIdentityEvidence(input: {
  platform?: unknown
  sourceUrl?: unknown
  notes?: unknown
}) {
  const platform = typeof input.platform === 'string' ? input.platform.trim().toLowerCase() : ''
  const sourceUrl = typeof input.sourceUrl === 'string' ? input.sourceUrl.trim() : ''
  const normalizedSourceUrl = sourceUrl.toLowerCase()
  const notes = typeof input.notes === 'string' ? input.notes.trim() : ''
  if (platform.includes('tushare') || normalizedSourceUrl.includes('tushare.fund_basic')) return false
  return Boolean(
    (sourceUrl && !isPlaceholderSalesRuleSourceText(sourceUrl))
    || (notes && !isPlaceholderSalesRuleSourceText(notes)),
  )
}
