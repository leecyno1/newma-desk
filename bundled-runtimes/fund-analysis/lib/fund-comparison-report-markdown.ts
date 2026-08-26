import { strictRiskLevelSourcePolicyMarkdownLines } from '@/lib/report-risk-level-source-policy'
import type { FundComparisonReport } from './fund-comparison-report'

function percentText(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '待补'
  return `${(Number(value) * 100).toFixed(2)}%`
}

function feeText(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '待补'
  return `${Number(value).toFixed(2)}%`
}

function shareClassLine(info: Omit<FundComparisonReport, 'markdown'>['items'][number]['shareClassInfo']) {
  if (!info || info.siblingCount < 2) return '未发现同基金多份额样本'
  return `${info.baseName} · 当前${info.classType}类；同基金 ${info.siblingCount} 份额（${info.siblingCodes.slice(0, 6).join('、')}），需先比较申购费、销售服务费、赎回费和持有期。`
}

export function renderFundComparisonMarkdown(payload: Omit<FundComparisonReport, 'markdown'>) {
  const lines = [
    '# 基金横向比较报告',
    '',
    `- 生成时间：${payload.generatedAt}`,
    `- 指标窗口：${payload.metricWindow}`,
    `- 对比代码：${payload.codes.join('、')}`,
    `- 研究画像：${payload.context.profileLabel} · ${payload.context.horizonLabel} · ${payload.context.purchasePlanLabel}${payload.context.plannedAmount ? ` · 计划金额 ${payload.context.plannedAmount.toLocaleString('zh-CN')} 元` : ''}`,
    `- 数据来源：${payload.source}`,
    '',
    '## 本轮结论',
    '',
    `- 对比基金数：${payload.summary.totalFunds}`,
    `- 暂不进入研究：${payload.summary.blockedCount} 只`,
    `- 需先补证：${payload.summary.verifyFirstCount} 只`,
    `- 研究证据较完整：${payload.summary.strongEvidenceCount} 只`,
    `- 平均研究证据分：${payload.summary.averageEvidenceScore}`,
    `- 当前相对领先样本：${payload.summary.leadingFundName ? `${payload.summary.leadingFundName}（${payload.summary.leadingFundCode}）` : '暂无'}`,
    `- 费用可比性：${payload.summary.feeComparableCount}/${payload.summary.totalFunds} 只费用证据可用于初步横比；${payload.summary.feeGapCount} 只仍需补销售/费率证据`,
    `- 材料核验硬缺口：${payload.summary.salesHardGapCount} 只；高优先级 ${payload.summary.salesHighPriorityGapCount} 只`,
    `- 同类组/基准映射：${payload.summary.peerGroupCount} 个同类组，${payload.summary.benchmarkCount} 个基准；${payload.summary.peerInsufficientSampleCount} 只样本不足或同类组待补`,
    `- 同类边界：${payload.summary.peerBenchmarkBoundary}`,
    ...strictRiskLevelSourcePolicyMarkdownLines(payload.riskLevelSourcePolicy),
    `- 同基金多份额：${payload.summary.shareClassGroupCount} 组 / ${payload.summary.shareClassFundCount} 个份额样本；存在时必须先做份额成本比较，不能把 A/C/I 等份额当作互不相关产品直接按收益排名。`,
    '',
    '## 研究复核结论',
    '',
    `- 优先核查对象：${payload.summary.decisionFundName ? `${payload.summary.decisionFundName}（${payload.summary.decisionFundCode}）` : '暂无'}`,
    `- 判断依据：${payload.summary.decisionBasis}`,
    `- 横评研究评分：${payload.summary.decisionScore ?? '待补'}`,
    `- 次优样本：${payload.summary.decisionRunnerUpName ? `${payload.summary.decisionRunnerUpName}（${payload.summary.decisionRunnerUpCode}）` : '暂无'}`,
	    `- 分差：${payload.summary.decisionScoreGap ?? '待补'}`,
	    `- 回放结果：收益 ${percentText(payload.summary.decisionReturn)}；回撤 ${percentText(payload.summary.decisionDrawdown)}（有费用后证据时优先采用费用后收益）`,
	    `- 压力体验：${payload.items.find((item) => item.windCode === payload.summary.decisionFundCode)?.purchaseSimulation?.stressScore ?? '待补'} 分；最长亏损等待 ${payload.items.find((item) => item.windCode === payload.summary.decisionFundCode)?.purchaseSimulation?.longestUnderwaterDays == null ? '待补' : `${Math.round(payload.items.find((item) => item.windCode === payload.summary.decisionFundCode)?.purchaseSimulation?.longestUnderwaterDays || 0)} 天`}；最差三个月 ${percentText(payload.items.find((item) => item.windCode === payload.summary.decisionFundCode)?.purchaseSimulation?.worstThreeMonthReturn)}`,
    `- 排序原因：${payload.summary.decisionReasons.length ? payload.summary.decisionReasons.join('；') : '暂无'}`,
    `- 可能反转条件：${payload.summary.decisionRecheckTriggers.length ? payload.summary.decisionRecheckTriggers.join('；') : '暂无'}`,
    `- 测算证据门禁：通过 ${payload.summary.replayEvidenceGatePassCount} 只；待补/只观察 ${payload.summary.replayEvidenceGateVerifyCount} 只。门禁未过的回放不能作为正式研究结论。`,
    `- 费用边界：${payload.summary.feeGapCount > 0 ? '存在费用缺口，当前领先只代表历史净值回放或指标领先，不代表费用后真实领先。' : '当前对比样本费用证据暂未发现明显缺口，仍需复核销售平台实时费率。'}`,
    `- 研究门禁：${payload.summary.verifyFirstCount} 只需先补证，${payload.summary.salesHardGapCount} 只存在材料核验硬缺口，${payload.summary.blockedCount} 只存在阻断。`,
    '- 结论边界：该对象只是优先核查样本，不构成操作指令；申赎状态、费率、适当性和来源材料仍必须复核。',
    '',
    '## 横评置信审计',
    '',
    `- 审计问题：${payload.summary.decisiveAudit.title}`,
    `- 当前置信度：${payload.summary.decisiveAudit.confidence}；通过 ${payload.summary.decisiveAudit.passCount}/${payload.summary.decisiveAudit.totalCount} 条胜负线。`,
    `- 硬边界：${payload.summary.decisiveAudit.boundary}`,
    ...payload.summary.decisiveAudit.items.map((item) => `- ${item.label}：${item.passed ? '通过' : '待复核'}；${item.detail}`),
    '',
    '## 决策胜负线',
    '',
    payload.summary.decisionWinLossLines.length
      ? `- 胜负线样本：${payload.summary.decisionWinLossLines.length} 组；任一材料核验未补齐时只保留研究态横评，不保存正式研究结论。`
      : '- 胜负线样本：待补；至少需要两个可比基金。',
    ...payload.summary.decisionWinLossLines.flatMap((line) => [
      `- 对 ${line.challengerName}（${line.challengerCode}）：${line.label}，${line.passedChecks}/${line.totalChecks} 关；${line.summary}`,
      ...line.thresholds.map((threshold) => `  - ${threshold.label}：${threshold.passed ? '过线' : '待证明'}；${threshold.detail}`),
    ]),
    '',
    '## 基金明细',
    '',
  ]

  payload.items.forEach((item, index) => {
    lines.push(
      `### ${index + 1}. ${item.fundName}（${item.windCode}）`,
      '',
      `- 类型/同类组：${item.fundType || '待补'} / ${item.peerGroup || '待补'}（${item.broadAssetBucket || '资产桶待补'}）`,
      `- 基准映射：${item.primaryBenchmark || '待补'}；来源 ${item.peerGroupSource}；样本 ${item.peerCount ?? '待补'} 只；${item.peerSampleNote}`,
      `- 专业评分：${item.professionalScore ?? '待补'}；等级：${item.professionalGrade || '待补'}`,
      `- 申购状态：${item.operationLabel}`,
      `- 研究证据：${item.evidenceScore}；必补 ${item.requiredMissingCount} 项`,
	      `- 横评研究评分：${item.decisionScore}`,
	      `- 研究评分拆解：${item.decisionScoreBreakdown.length ? item.decisionScoreBreakdown.map((part) => `${part.label}+${part.contribution.toFixed(1)}（${part.note}）`).join('；') : '暂无'}`,
	      `- 压力体验：${item.purchaseSimulation?.stressScore ?? '待补'} 分；最长亏损等待 ${item.purchaseSimulation?.longestUnderwaterDays == null ? '待补' : `${Math.round(item.purchaseSimulation.longestUnderwaterDays)} 天`}；最差三个月 ${percentText(item.purchaseSimulation?.worstThreeMonthReturn)}`,
	      `- 研究评分封顶：${item.decisionScoreCaps.length ? item.decisionScoreCaps.join('；') : '无'}`,
      `- 评分依据：${item.decisionScoreReasons.length ? item.decisionScoreReasons.join('；') : '暂无'}`,
      `- 费用：管理费 ${feeText(item.managementFee)}；托管费 ${feeText(item.custodianFee)}`,
      `- 同基金多份额：${shareClassLine(item.shareClassInfo)}`,
      `- 费用可比性：${item.feeComparable ? '可初步横比' : `不可直接费后横比：${item.feeGapReason}`}`,
      `- 材料核验硬缺口：${item.salesRuleMissingCount ? `${item.salesRuleMissingCount} 项（${item.salesRuleMissingItems.slice(0, 6).join('、')}）` : '暂无硬缺口'}`,
      `- 领先维度：${item.leadingMetrics.length ? item.leadingMetrics.join('、') : '暂无明确领先维度'}`,
      `- 体验回放：一次性收益 ${percentText(item.purchaseSimulation?.lumpSumReturn)} / 回撤 ${percentText(item.purchaseSimulation?.lumpSumMaxDrawdown)}；定投收益 ${percentText(item.purchaseSimulation?.sipReturn)} / 账户回撤 ${percentText(item.purchaseSimulation?.sipMaxAccountDrawdown)}`,
      `- 测算采信门禁：${item.purchaseSimulation?.evidenceGateLabel || '待补'}；${item.purchaseSimulation?.evidenceGateHardBoundary || '未返回测算门禁，不能把回放当成正式研究结论'}；缺口 ${item.purchaseSimulation?.evidenceGateMissingEvidence.length ? item.purchaseSimulation.evidenceGateMissingEvidence.join('、') : '暂无'}`,
      `- 费用后回放：覆盖 ${item.purchaseSimulation?.feeAdjustedCoverage || 'none'}；一次性 ${percentText(item.purchaseSimulation?.lumpSumFeeAdjustedReturn)} / 费用 ${item.purchaseSimulation?.lumpSumFeeAdjustedTotalFee ?? '待补'}；定投 ${percentText(item.purchaseSimulation?.sipFeeAdjustedReturn)} / 费用 ${item.purchaseSimulation?.sipFeeAdjustedTotalFee ?? '待补'}；缺口 ${item.purchaseSimulation?.feeAdjustedMissingItems.length ? item.purchaseSimulation.feeAdjustedMissingItems.join('、') : '暂无'}`,
      `- 缺口：${item.missingItems.length ? item.missingItems.slice(0, 6).join('、') : '暂无明显缺口'}`,
      `- 当前判断：${item.conclusion}`,
      `- 下一步：${item.nextActions.length ? item.nextActions.join('；') : '进入单基金研究复核'}`,
      '',
    )
  })

  lines.push(
    '## 横评提示',
    '',
    '- 同类分位优先于跨类型绝对值比较；跨类型基金只能作为研究线索，不能直接替代正式研究判断。',
    '- 同基金 A/C/I/H 等份额必须先放在同一基金份额框架下比较成本、持有期和销售服务费，再进入跨基金横评。',
    '- 申赎状态、费率、风险等级和来源材料缺失时，不输出正式研究结论。',
    '- 本报告只服务基金筛选、基金分析和研究复核，不构成收益承诺或组合配置依据。',
  )

  return lines.join('\n')
}
