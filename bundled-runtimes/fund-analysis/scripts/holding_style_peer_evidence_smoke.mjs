import fs from 'node:fs'

const file = fs.readFileSync('app/(dashboard)/funds/[id]/FundAttributionEvidence.tsx', 'utf8')
const holdingFile = fs.readFileSync('app/(dashboard)/funds/[id]/FundHoldingProfile.tsx', 'utf8')
const simpleDetailFile = fs.readFileSync('app/(dashboard)/funds/[id]/SimpleFundDetailClient.tsx', 'utf8')
const peerService = fs.readFileSync('backend/services/holding_style_peer_service.py', 'utf8')
const styleEvidenceFiles = `${file}\n${simpleDetailFile}`

for (const forbidden of ['value >= 1000', 'value >= 0.5', "case 'SIZE': return", "case 'BTOP': return"]) {
  if (file.includes(forbidden)) throw new Error(`fund detail must not use absolute style-label threshold: ${forbidden}`)
}

for (const required of ['peer_percentiles', 'percentile_label', '同季度同类样本不足', '不生成大盘、价值、成长或低波标签', '同类分位']) {
  if (!styleEvidenceFiles.includes(required)) throw new Error(`fund detail missing peer style evidence: ${required}`)
}

for (const required of ['MIN_MATERIAL_RELATIVE_RANGE', 'signal_status', '同类差异不显著', 'peer_percentile_neutral']) {
  if (!peerService.includes(required)) throw new Error(`holding style peer method missing materiality gate: ${required}`)
}

for (const required of ['同类差异不显著', '不强行贴大盘、小盘、价值或高低波标签']) {
  if (!simpleDetailFile.includes(required)) throw new Error(`fund detail missing neutral peer-style disclosure: ${required}`)
}

console.log('OK fund detail uses same-quarter peer percentiles instead of absolute style thresholds')

for (const required of ['invalid_weight_scale', '系统已清空错误净值权重', '只保留 Tushare 公布的“占股票市值比”']) {
  if (!holdingFile.includes(required)) throw new Error(`fund holding view missing invalid-scale disclosure: ${required}`)
}
