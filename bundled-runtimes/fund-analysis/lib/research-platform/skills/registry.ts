import { FUND_RESEARCH_GUARDRAILS, type ResearchSkillManifest } from '../contracts'

export const researchSkills = [
  {
    name: 'full-market-screening',
    version: '1.0.0',
    purpose: '从全市场研究库生成可解释研究样本、补证清单和横评入口。',
    stages: [
      { key: 'query-market', tool: 'fund_profile.search', required: true, failureMode: 'block' },
      { key: 'condition-health', tool: 'screening-condition-health', required: true, failureMode: 'downgrade' },
      { key: 'material-evidence-preflight', tool: 'material-evidence-gate', required: true, failureMode: 'block' },
    ],
    outputDecision: ['research_ready', 'verify_first', 'blocked'],
    allowedSurfaces: ['page', 'api', 'agent', 'batch'],
    guardrails: [
      FUND_RESEARCH_GUARDRAILS.noTradingDirective,
      FUND_RESEARCH_GUARDRAILS.missingEvidenceBlocks,
      '全市场初筛只生成研究样本、补证队列和横评入口。',
    ],
  },
  {
    name: 'single-fund-research-review',
    version: '1.0.0',
    purpose: '对单只基金完成基础信息、材料核验、净值回放、持仓暴露和报告复核。',
    stages: [
      { key: 'fund-profile', tool: 'fund_profile.read', required: true, failureMode: 'block' },
      { key: 'material-evidence-gate', tool: 'material-evidence-gate', required: true, failureMode: 'block' },
      { key: 'research-evidence', tool: 'research-evidence', required: true, failureMode: 'downgrade' },
      { key: 'report', tool: 'report.generate_research_review', required: false, failureMode: 'observe_only' },
    ],
    outputDecision: ['research_ready', 'verify_first', 'blocked', 'historical_trace'],
    allowedSurfaces: ['page', 'api', 'agent', 'batch'],
    guardrails: [
      FUND_RESEARCH_GUARDRAILS.noTradingDirective,
      FUND_RESEARCH_GUARDRAILS.tushareFoundationBoundary,
      FUND_RESEARCH_GUARDRAILS.aiUsesSkillRun,
    ],
  },
  {
    name: 'fund-comparison',
    version: '1.0.0',
    purpose: '对候选基金做同类分位、费后回放、胜负线和替代关系核查。',
    stages: [
      { key: 'sample-preflight', tool: 'fund_compare.preflight', required: true, failureMode: 'block' },
      { key: 'nav-replay', tool: 'nav_replay.simulate', required: true, failureMode: 'downgrade' },
      { key: 'matrix', tool: 'fund_compare.matrix', required: true, failureMode: 'downgrade' },
    ],
    outputDecision: ['research_ready', 'verify_first', 'blocked', 'historical_trace'],
    allowedSurfaces: ['page', 'api', 'agent', 'batch'],
    guardrails: [
      FUND_RESEARCH_GUARDRAILS.noTradingDirective,
      FUND_RESEARCH_GUARDRAILS.missingEvidenceBlocks,
      '横评结果必须披露样本、费率、净值回放和胜负证据。',
    ],
  },
  {
    name: 'manager-evaluation',
    version: '1.0.0',
    purpose: '按基金经理任期、名下产品和反证清单评价管理证据。',
    stages: [
      { key: 'manager-profile', tool: 'manager.profile.read', required: true, failureMode: 'block' },
      { key: 'tenure-slice', tool: 'manager.tenure_slice', required: true, failureMode: 'downgrade' },
      { key: 'product-gates', tool: 'manager.product_gate_audit', required: true, failureMode: 'downgrade' },
    ],
    outputDecision: ['research_ready', 'verify_first', 'blocked', 'historical_trace'],
    allowedSurfaces: ['page', 'api', 'agent', 'batch'],
    guardrails: [
      FUND_RESEARCH_GUARDRAILS.noTradingDirective,
      FUND_RESEARCH_GUARDRAILS.missingEvidenceBlocks,
      '经理评价必须区分当前任期、历史产品和证据缺口。',
    ],
  },
  {
    name: 'report-reuse',
    version: '1.0.0',
    purpose: '判断历史报告今天是否只能回看、需重跑，或可作为研究留痕参考。',
    stages: [
      { key: 'reuse-assessment', tool: 'report-reuse-assessment', required: true, failureMode: 'downgrade' },
      { key: 'evidence-queue', tool: 'report.evidence_queue', required: false, failureMode: 'observe_only' },
    ],
    outputDecision: ['research_ready', 'verify_first', 'historical_trace'],
    allowedSurfaces: ['page', 'api', 'agent', 'batch'],
    guardrails: [
      FUND_RESEARCH_GUARDRAILS.noTradingDirective,
      '历史报告不能绕过今日材料核验、R1-R5、费用字段、开放状态和净值回放复核。',
      '可沿用仅表示研究留痕可参考。',
    ],
  },
  {
    name: 'evidence-repair',
    version: '1.0.0',
    purpose: '把材料核验、R1-R5、开放状态、净值和持仓缺口聚类为补证工作单。',
    stages: [
      { key: 'gap-audit', tool: 'evidence_coverage.audit', required: true, failureMode: 'downgrade' },
      { key: 'work-order', tool: 'evidence_repair.work_order', required: true, failureMode: 'observe_only' },
    ],
    outputDecision: ['verify_first', 'blocked', 'historical_trace'],
    allowedSurfaces: ['page', 'api', 'agent', 'batch'],
    guardrails: [
      FUND_RESEARCH_GUARDRAILS.noTradingDirective,
      FUND_RESEARCH_GUARDRAILS.tushareFoundationBoundary,
      '证据修复只补字段来源和复查状态，不输出配置或申赎动作。',
    ],
  },
] as const satisfies readonly ResearchSkillManifest[]

export type ResearchSkillName = (typeof researchSkills)[number]['name']

export function listResearchSkillManifests() {
  return researchSkills
}

export function getResearchSkillManifest(name: ResearchSkillName) {
  const skill = researchSkills.find((candidate) => candidate.name === name)
  if (!skill) throw new Error(`Unknown research skill: ${name}`)
  return skill
}
