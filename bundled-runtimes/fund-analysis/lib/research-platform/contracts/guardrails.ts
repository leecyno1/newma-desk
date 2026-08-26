export const FUND_RESEARCH_GUARDRAILS = {
  noTradingDirective: '仅输出基金研究动作，不输出申赎操作指令或直接执行结论。',
  missingEvidenceBlocks: '缺失、过期或来源不合格的关键证据必须进入 gaps 或 hardBlocks，不得默认为正向。',
  tushareFoundationBoundary: 'Tushare fund_basic 只可作为基金基础状态来源，不可作为 R1-R5、费率、申赎或销售执行字段来源。',
  aiUsesSkillRun: 'AI 大模型只能消费 ToolResult、SkillRun 和 EvidenceLedger，不绕过工具门禁直接改写事实。',
  pageAsRenderer: '页面只渲染研究结果，不承载唯一核心规则。',
} as const

export const FUND_RESEARCH_FORBIDDEN_COPY = [
  ['建', '议', '买', '入'].join(''),
  ['买', '入', '建', '议'].join(''),
  ['推', '荐', '买', '入'].join(''),
  ['交', '易', '建', '议'].join(''),
  ['直', '接', '购', '买'].join(''),
  ['直', '接', '下', '单'].join(''),
] as const

export function assertFundResearchGuardrails(text: string) {
  const hit = FUND_RESEARCH_FORBIDDEN_COPY.find((phrase) => text.includes(phrase))
  if (hit) throw new Error(`fund research copy violates guardrail: ${hit}`)
}
