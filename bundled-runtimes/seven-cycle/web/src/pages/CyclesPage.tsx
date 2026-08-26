import { AlertTriangle, BarChart3, BookOpenCheck, CalendarDays, ChevronDown, FlaskConical, ShieldCheck } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import CycleForecastExtension from '../components/CycleForecastExtension'
import IndicatorContributionStudy from '../components/IndicatorContributionStudy'
import CycleResearchChart from '../components/CycleResearchChart'
import LoadingState from '../components/LoadingState'
import StatusBadge from '../components/StatusBadge'
import { useResearchData } from '../hooks/useResearchData'
import { loadCycleResearch } from '../lib/data'

const statusIcon = {
  formal: ShieldCheck,
  limited: FlaskConical,
  blocked: AlertTriangle,
  scenario_only: BookOpenCheck,
  calendar_only: CalendarDays,
}

const phaseNames: Record<string, string> = {
  recovery: '复苏',
  expansion: '扩张',
  slowdown: '放缓',
  contraction: '收缩',
}

function periodLabel(months: number) {
  return months >= 24 ? `${(months / 12).toFixed(months % 12 ? 1 : 0)} 年` : `${months} 个月`
}

export default function CyclesPage() {
  const { data, error } = useResearchData(loadCycleResearch)
  const [params, setParams] = useSearchParams()
  const requested = params.get('cycle')
  const [selected, setSelected] = useState(requested && /^C[1-7]$/.test(requested) ? requested : 'C4')
  const [showEvidenceDetails, setShowEvidenceDetails] = useState(false)
  const cycle = useMemo(() => data?.governance.cycles.find((item) => item.id === selected), [data, selected])

  useEffect(() => {
    if (requested && /^C[1-7]$/.test(requested) && requested !== selected) {
      setSelected(requested)
      setShowEvidenceDetails(false)
    }
  }, [requested, selected])

  if (!data || !cycle) return <LoadingState error={error} />
  const diagnostic = data.diagnostics?.[cycle.id]
  const c1 = data.C1
  const c1FiveYear = c1.directionValidation?.find((item: any) => item.horizonYears === 5)
  const c1TenYear = c1.directionValidation?.find((item: any) => item.horizonYears === 10)
  const c1RejectedBridges = c1.familyCoverage?.filter((item: any) => item.bridgeStatus === 'rejected') ?? []
  const longPanel = diagnostic?.longPanel
  const liquidityState = diagnostic?.liquidityState
  const liquidityForecast3 = liquidityState?.currentForecasts.find((row: any) => row.horizonMonths === 3)
  const liquidityForecast6 = liquidityState?.currentForecasts.find((row: any) => row.horizonMonths === 6)
  const liquidityForecast12 = liquidityState?.currentForecasts.find((row: any) => row.horizonMonths === 12)
  const liquidityForecastPath = liquidityState?.forecastPath ?? []
  const liquidityPathLow = liquidityForecastPath.reduce((lowest: any, point: any) => (
    !lowest || point.scenarioLevel < lowest.scenarioLevel ? point : lowest
  ), null)
  const liquidityPathLast = liquidityForecastPath.at(-1)
  const liquidityPathLabel = liquidityPathLow && liquidityPathLast
    ? liquidityPathLow.horizonMonths < liquidityPathLast.horizonMonths && liquidityPathLast.scenarioLevel > liquidityPathLow.scenarioLevel
      ? '先收紧、后修复'
      : liquidityPathLast.scenarioLevel < liquidityState.current.level ? '继续收紧' : '逐步改善'
    : '方向待确认'
  const riskAppetiteState = diagnostic?.riskAppetiteState
  const directionPublication = diagnostic?.directionPublication
  const researchStateAvailable = directionPublication?.status === 'limited'
  const Icon = researchStateAvailable ? FlaskConical : statusIcon[cycle.publication.historical]
  const regimeRefactor = diagnostic?.regimeRefactor
  const c2Regime = cycle.id === 'C2' ? regimeRefactor : null
  const c3Regime = cycle.id === 'C3' ? regimeRefactor : null
  const directionForecasts = c3Regime?.currentForecasts ?? longPanel?.currentForecasts
  const oneYearForecast = directionForecasts?.find((item: any) => item.horizonYears === 1)
  const twoYearForecast = directionForecasts?.find((item: any) => item.horizonYears === 2)
  const threeYearForecast = directionForecasts?.find((item: any) => item.horizonYears === 3)
  const partialNowcast = c3Regime?.partialNowcast ?? longPanel?.partialNowcast
  const familyAblation = longPanel?.familyAblation
  const independentOutcomes = longPanel?.independentOutcomeValidation
  const architectureComparison = c3Regime?.architectureComparison ?? longPanel?.architectureComparison
  const c2State = c2Regime?.state?.current
  const c2Geography = c2Regime?.geographicState
  const c2AssetMapping = c2Regime?.historicalAssetMapping
  const c2JointAsset = c2Regime?.jointAssetMapping
  const c2HierarchicalRisk = c2JointAsset?.hierarchicalRiskValidation
  const c2AssetClassValidation = c2HierarchicalRisk?.assetClassValidation
  const c2ConditionalPropagation = c2HierarchicalRisk?.conditionalPropagationValidation
  const c2BondRiskChannel = c2HierarchicalRisk?.historicalRiskChannels?.find((channel: any) => channel.channelId === 'c2_asymmetric_bond_downside_risk_3y')
  const c2ModernPressure = c2BondRiskChannel?.modernBridge
  const c2CurrentPressure = c2ModernPressure?.currentState
  const c2Transition = c2Regime?.state?.transitionEvidence
  const c2FamilyStates = c2Regime?.state?.familyStates
  const c2HistoricalDating = c2Regime?.historicalDating
  const mostSensitiveFamily = familyAblation?.groups?.reduce((current: any, item: any) => (
    !current || item.maximumAbsoluteCurrentProbabilityShift > current.maximumAbsoluteCurrentProbabilityShift
      ? item
      : current
  ), null)
  const phaseCandidate = diagnostic?.phaseCandidate
  const currentPhaseCandidate = phaseCandidate?.currentPhaseCandidate
  const geographicState = cycle.id === 'C2' ? c2Geography : phaseCandidate?.geographicState
  const mixedFrequencyPhase = currentPhaseCandidate?.validation?.mixedFrequencyPhase
  const phaseProbability = currentPhaseCandidate?.phaseProbability
  const familyConfirmation = currentPhaseCandidate?.validation?.familyConfirmation
  const familyAblationPhase = currentPhaseCandidate?.validation?.familyAblationPhase
  const governedBroadState = currentPhaseCandidate?.governedBroadState
  const periodRobustness = currentPhaseCandidate?.periodRobustness
  const factorArchitecture = currentPhaseCandidate?.factorArchitecture
  const structuralPosition = currentPhaseCandidate?.structuralPosition
  const exactPhasePublishable = currentPhaseCandidate?.exactPhaseStatus === 'limited'
  const latestHistoricalPhase = phaseCandidate?.history?.[phaseCandidate.history.length - 1]
  const currentAdaptivePeriod = currentPhaseCandidate?.current?.periodYears
  const currentAdaptivePeriodRange = periodRobustness?.periodRangeYears ?? (currentPhaseCandidate?.current
    ? [currentPhaseCandidate.current.periodLowYears, currentPhaseCandidate.current.periodHighYears]
    : null)
  const periodIdentificationLabel = currentPhaseCandidate?.periodIdentification?.status === 'family_disagreement'
    ? '指标家族分歧，精确周期未锁定'
    : currentPhaseCandidate?.current?.periodBoundaryShare >= 0.5
    ? '触及搜索边界，周期长度未锁定'
    : currentPhaseCandidate?.current?.periodSelectionStrength < 0.05
      ? '相位一致，但精确周期识别较弱'
      : '动态周期候选具备一定区分度'
  const expandedPeriodDiagnostic = currentPhaseCandidate?.periodIdentification?.expandedSearch
  const hasChart = ['C1', 'C4', 'C6'].includes(cycle.id) || Boolean(diagnostic)
  const selectCycle = (cycleId: string) => {
    setSelected(cycleId)
    setShowEvidenceDetails(false)
    setParams({ cycle: cycleId })
  }

  return (
    <div className="page cycles-page">
      <section className="page-heading">
        <div>
          <h1>七周期证据与历史曲线</h1>
          <p>中心长度只是先验。曲线来自指标家族合成、统计滤波与人工校准，不使用固定正弦模板。</p>
        </div>
        <div className="heading-meta"><span>证据基线 {data.governance.asOf}</span><span>历史 / 实时 / 预测 / 资产统计分层治理</span></div>
      </section>

      <section className="cycle-selector">
        {data.governance.cycles.map((item) => {
          const publication = data.diagnostics?.[item.id]?.directionPublication
          return (
            <button key={item.id} className={selected === item.id ? 'active' : ''} onClick={() => selectCycle(item.id)}>
              <span>{item.id}</span>
              <strong>{item.name}</strong>
              <small>{periodLabel(item.centerPriorMonths)}</small>
              {publication?.status === 'limited' ? <span className="status-badge status-research">{publication.badgeLabel}</span> : <StatusBadge status={item.publication.historical} />}
            </button>
          )
        })}
      </section>

      <section className="cycle-detail-layout">
        <div className="cycle-primary-panel">
          <div className="cycle-title-row">
            <div className={`cycle-status-icon ${researchStateAvailable ? 'status-research' : `status-${cycle.publication.historical}`}`}><Icon size={22} /></div>
            <div>
              <span>{cycle.id} · {periodLabel(cycle.centerPriorMonths)}中心先验</span>
              <h2>{cycle.name}</h2>
              <p>{cycle.role}</p>
            </div>
            {directionPublication?.status === 'limited' ? <span className="status-badge status-research">{directionPublication.badgeLabel}</span> : <StatusBadge status={cycle.publication.historical} />}
          </div>
          {hasChart ? (
            <>
              {cycle.id === 'C4' && data.C4Realtime.bridge_validation && (
                <div className="diagnostic-banner bridge-banner">
                  <ShieldCheck size={16} />
                  <div><strong>PMI/PPI 单边桥接已通过历史截点验证</strong><span>截至 {data.C4Realtime.latest.date} · {({ recovery: '复苏', expansion: '扩张', downturn: '放缓', contraction: '收缩' } as Record<string, string>)[data.C4Realtime.latest.rt_phase]} · 置信 {(data.C4Realtime.latest.confidence * 100).toFixed(0)}% · 6个月相位准确率 {(data.C4Realtime.bridge_validation.six_month_phase_accuracy * 100).toFixed(1)}%</span></div>
                </div>
              )}
              {cycle.id === 'C1' && (
                <div className="diagnostic-banner phase-candidate-banner">
                  <FlaskConical size={16} />
                  <div><strong>全球实体核心：位置未校准 · 动量{c1.currentState.momentumLabel}</strong><span>人工阶段仍为“{c1.phaseCalibration.phase}”；35—70年仅 {c1.frequencyValidation.significantFamilyCount}/{c1.frequencyValidation.familyCount} 个家族通过红噪声检验 · 当前覆盖 {(c1.coreCoverage.currentRatio * 100).toFixed(0)}%，其中已接受桥接 {(c1.coreCoverage.currentBridgeRatio * 100).toFixed(0)}%{c1RejectedBridges.length ? ` · ${c1RejectedBridges.length}项桥接被拒绝` : ''}</span></div>
                </div>
              )}
              {diagnostic && !liquidityState && !riskAppetiteState && (
                <div className="diagnostic-banner">
                  {cycle.id === 'C2' ? <FlaskConical size={16} /> : <AlertTriangle size={16} />}
                  {cycle.id === 'C2' && c2State ? (
                    <div><strong>C2 当前确认：{phaseNames[c2State.phase]}期</strong><span>截至 {c2Regime.meta.asOfPeriod} · 活动核心 {c2State.activity.toFixed(2)}σ · 转相证据 {(c2Transition.score * 100).toFixed(0)}/{(c2Transition.requiredScore * 100).toFixed(0)} · 按揭先修复，住房和投资未确认</span></div>
                  ) : cycle.id === 'C3' && c3Regime ? (
                    <div><strong>C3 当前研究状态：{phaseNames[c3Regime.state.current.phase]}期</strong><span>截至 {c3Regime.meta.asOfPeriod} · 双核心 {c3Regime.state.current.rawValue.toFixed(2)}σ · 动态周期 {c3Regime.state.current.periodYears.toFixed(1)}年 · 资产仅 {c3Regime.assetValidation.passedTargets}/{c3Regime.assetValidation.targetCount} 通道通过</span></div>
                  ) : longPanel ? (
                    <div><strong>跨国因子方向验证通过，外部结果与正式相位仍阻断</strong><span>截至 {oneYearForecast.asOfPeriod ?? oneYearForecast.asOfYear} · 1年因子上行概率 {(oneYearForecast.probabilityUp * 100).toFixed(0)}% · 3年因子上行概率 {(threeYearForecast.probabilityUp * 100).toFixed(0)}%</span></div>
                  ) : (
                    <div><strong>方向性诊断可用，正式周期仍阻断</strong><span>当前 {diagnostic.current.date} · {diagnostic.current.direction} · 诊断置信 {(diagnostic.current.diagnosticConfidence * 100).toFixed(0)}%</span></div>
                  )}
                </div>
              )}
              {partialNowcast?.validation?.status === 'passed_limited' && (
                <div className="diagnostic-banner bridge-banner">
                  <ShieldCheck size={16} />
                  <div><strong>{partialNowcast.asOfPeriod} 部分年度桥接通过历史截点验证</strong><span>{partialNowcast.coverageLabel} · 历史方向准确率 {(partialNowcast.validation.directionAccuracy * 100).toFixed(1)}% · MAE {partialNowcast.validation.mae.toFixed(2)}σ；{partialNowcast.carryLabel}</span></div>
                </div>
              )}
              {cycle.id === 'C3' && c3Regime && (
                <div className="diagnostic-banner phase-candidate-banner">
                  <FlaskConical size={16} />
                  <div><strong>当前稳健状态：低位修复</strong><span>{c3Regime.meta.asOfPeriod} · 三组搜索范围均识别为{phaseNames[c3Regime.state.current.phase]} · 周期 {c3Regime.state.parameterRobustness.periodRangeYears[0].toFixed(1)}—{c3Regime.state.parameterRobustness.periodRangeYears[1].toFixed(1)}年 · 100个月只作弱先验</span></div>
                </div>
              )}
              {!['C2', 'C3', 'C5', 'C7'].includes(cycle.id) && currentPhaseCandidate && governedBroadState?.status === 'limited_broad_state' && (
                <div className="diagnostic-banner phase-candidate-banner">
                  <FlaskConical size={16} />
                  <div><strong>当前稳健状态：{governedBroadState.label}</strong><span>{currentPhaseCandidate.asOfPeriod} · 多参数周期范围 {currentAdaptivePeriodRange?.[0].toFixed(1)}—{currentAdaptivePeriodRange?.[1].toFixed(1)}年 · {periodIdentificationLabel} · {exactPhasePublishable ? `四相位候选为${phaseNames[currentPhaseCandidate.current.phase]}` : '动量未确认，四相位概率与当前资产情景暂停'}</span></div>
                </div>
              )}
              {liquidityState?.status === 'state_direction_predictable' && (
                <div className="diagnostic-banner phase-candidate-banner">
                  <FlaskConical size={16} />
                  <div><strong>C5 当前状态：{liquidityState.current.regime}</strong><span>截至 {liquidityState.current.date} · 3/6/12个月主方向概率 {(Math.max(liquidityForecast3?.probabilityUp ?? 0, liquidityForecast3?.probabilityDown ?? 0) * 100).toFixed(0)}% / {(Math.max(liquidityForecast6?.probabilityUp ?? 0, liquidityForecast6?.probabilityDown ?? 0) * 100).toFixed(0)}% / {(Math.max(liquidityForecast12?.probabilityUp ?? 0, liquidityForecast12?.probabilityDown ?? 0) * 100).toFixed(0)}% · 资产增量 {liquidityState.assetValidation.summary.passedChannels}/{liquidityState.assetValidation.summary.totalChannels}</span></div>
                </div>
              )}
              {riskAppetiteState?.status === 'short_horizon_regime_predictable' && (
                <div className="diagnostic-banner phase-candidate-banner">
                  <FlaskConical size={16} />
                  <div><strong>C7 当前状态：{riskAppetiteState.current.regime}</strong><span>截至 {riskAppetiteState.current.date} · 未来仍处风险偏好区间概率：1个月 {((riskAppetiteState.forecastPath.find((row: any) => row.horizonMonths === 1)?.probabilityRiskOn ?? 0) * 100).toFixed(0)}% · 3个月 {((riskAppetiteState.forecastPath.find((row: any) => row.horizonMonths === 3)?.probabilityRiskOn ?? 0) * 100).toFixed(0)}% · 5个月 {((riskAppetiteState.forecastPath.find((row: any) => row.horizonMonths === 5)?.probabilityRiskOn ?? 0) * 100).toFixed(0)}%</span></div>
                </div>
              )}
              <CycleResearchChart cycleId={cycle.id} data={data} />
            </>
          ) : (
            <div className="blocked-chart-state">
              <AlertTriangle size={28} />
              <strong>证据未通过，禁止补画确定曲线</strong>
              <p>{cycle.publication.reason}</p>
              <span>中心先验 {periodLabel(cycle.centerPriorMonths)} 仍保留用于后续搜索，但不等于已识别周期。</span>
            </div>
          )}
          <div className="chart-method-note">
            {cycle.id === 'C1' && data.C1.caveat}
            {cycle.id === 'C4' && `历史：双边 Gaussian + Butterworth 集成；实时：PMI/PPI 指标桥接至 ${data.C4Realtime.latest.date}；预测：样本外验证通过的 Ridge，输入滞后 ${data.C4Forecast.meta.stale_months_at_build} 个月。`}
            {cycle.id === 'C6' && data.C6.caveat}
            {diagnostic && diagnostic.caveat}
            {!hasChart && '触及搜索边界、红噪声不显著或口径敏感时，系统拒绝自动给出单一最佳周期。'}
          </div>
        </div>

        <aside className={`evidence-panel ${showEvidenceDetails ? 'expanded' : 'compact'}`}>
          <div className="evidence-summary">
            <span>证据结论</span>
            <strong>{cycle.id === 'C1' ? c1.publication.claim : cycle.id === 'C2' && c2State ? '实时状态、历史定年和资产映射已分层。当前仍为收缩期；按揭信用出现修复，但住房动量、投资确认和地理广度不足，尚未形成复苏转相。' : cycle.id === 'C3' && c3Regime ? '投资脉冲—企业信用双核心处于低位修复；动态周期约10.1年。方向高准确率主要来自因子惯性，资产仅1/8通道通过。' : longPanel ? longPanel.publishableClaim : liquidityState ? `国内政策、信用传导和全球美元三层的3至12个月状态方向通过；NFCI当前${liquidityState.confirmation.current.status}，资产仅${liquidityState.assetValidation.summary.passedChannels}/${liquidityState.assetValidation.summary.totalChannels}个增量通道通过。` : riskAppetiteState ? '1至5个月未来状态处于风险偏好区间的概率通过递归样本外验证；该概率不等于状态继续上行，固定周期、6个月路径和资产收益映射不发布。' : cycle.evidence.summary}</strong>
          </div>
          <dl className="evidence-metrics">
            <div><dt>中心先验</dt><dd>{periodLabel(cycle.centerPriorMonths)}</dd></div>
            <div><dt>经验区间</dt><dd>{cycle.empiricalBandMonths ? `${periodLabel(cycle.empiricalBandMonths[0])}—${periodLabel(cycle.empiricalBandMonths[1])}` : '不发布'}</dd></div>
            {cycle.id === 'C1' && <div><dt>家族峰值中位</dt><dd>{c1.frequencyValidation.medianDominantPeriodYears.toFixed(1)} 年</dd></div>}
            {cycle.id === 'C1' && <div><dt>红噪声通过</dt><dd>{c1.frequencyValidation.significantFamilyCount}/{c1.frequencyValidation.familyCount} 家族</dd></div>}
            {cycle.id === 'C1' && <div><dt>当前核心覆盖</dt><dd>{(c1.coreCoverage.currentRatio * 100).toFixed(0)}%</dd></div>}
            {cycle.id === 'C1' && <div><dt>原始/桥接覆盖</dt><dd>{(c1.coreCoverage.currentDirectRatio * 100).toFixed(0)}% / {(c1.coreCoverage.currentBridgeRatio * 100).toFixed(0)}%</dd></div>}
            {cycle.id === 'C2' && c2State && <div><dt>当前直接相位</dt><dd>{phaseNames[c2State.phase]} · 已持续 {c2State.phaseDurationYears} 年</dd></div>}
            {cycle.id === 'C2' && c2State && <div><dt>1/2/3年动量</dt><dd>{c2State.slope1Y.toFixed(2)} / {c2State.slope2Y.toFixed(2)} / {c2State.slope3Y.toFixed(2)}</dd></div>}
            {cycle.id === 'C2' && c2Transition && <div><dt>转相证据</dt><dd>{(c2Transition.score * 100).toFixed(0)} / {(c2Transition.requiredScore * 100).toFixed(0)}</dd></div>}
            {cycle.id === 'C2' && c2HistoricalDating && <div><dt>历史峰谷间隔</dt><dd>中位 {c2HistoricalDating.medianIntervalYears.toFixed(1)} 年</dd></div>}
            {cycle.id === 'C2' && <div><dt>周期长度规则</dt><dd>200个月仅弱先验</dd></div>}
            {cycle.id === 'C3' && c3Regime && <div><dt>当前动态周期</dt><dd>{c3Regime.state.current.periodYears.toFixed(1)}年</dd></div>}
            {cycle.id === 'C3' && c3Regime && <div><dt>多规格周期范围</dt><dd>{c3Regime.state.parameterRobustness.periodRangeYears[0].toFixed(1)}—{c3Regime.state.parameterRobustness.periodRangeYears[1].toFixed(1)}年</dd></div>}
            {cycle.id === 'C3' && c3Regime && <div><dt>资产增量验证</dt><dd>{c3Regime.assetValidation.passedTargets}/{c3Regime.assetValidation.targetCount} 通道</dd></div>}
            {liquidityState && <div><dt>3/6/12月 AUC</dt><dd>{liquidityState.validation['3m'].auc.toFixed(2)} / {liquidityState.validation['6m'].auc.toFixed(2)} / {liquidityState.validation['12m'].auc.toFixed(2)}</dd></div>}
            {liquidityState && <div><dt>三层覆盖</dt><dd>{liquidityState.current.families.map((family: any) => `${family.signalCount}/${family.signalTotal}`).join(' / ')}</dd></div>}
            {liquidityState && <div><dt>NFCI确认</dt><dd>{liquidityState.confirmation.current.status}</dd></div>}
            {liquidityState && <div><dt>资产增量验证</dt><dd>{liquidityState.assetValidation.summary.passedChannels}/{liquidityState.assetValidation.summary.totalChannels} 通道</dd></div>}
            {!['C2', 'C3', 'C5', 'C7'].includes(cycle.id) && phaseCandidate && <div><dt>历史终点周期候选</dt><dd>{phaseCandidate.validation.latestDynamicPeriodYears.toFixed(1)}年 · 历史中位 {phaseCandidate.validation.dynamicPeriodMedianYears.toFixed(1)}年</dd></div>}
            {!['C2', 'C3', 'C5', 'C7'].includes(cycle.id) && periodRobustness && <div><dt>当前稳健周期范围</dt><dd>{periodRobustness.periodRangeYears[0].toFixed(1)}—{periodRobustness.periodRangeYears[1].toFixed(1)}年</dd></div>}
            {!['C2', 'C3', 'C5', 'C7'].includes(cycle.id) && phaseCandidate && <div><dt>周期识别状态</dt><dd>{periodIdentificationLabel}</dd></div>}
            {!liquidityState && !riskAppetiteState && <div><dt>家族中心</dt><dd>{cycle.evidence.family_centers_months.length ? cycle.evidence.family_centers_months.map(periodLabel).join(' / ') : '无稳定共识'}</dd></div>}
            <div><dt>证据状态</dt><dd>{cycle.evidence.evidence_status}</dd></div>
          </dl>
          <div className="cycle-evidence-actions">
            <Link to={`/assets?cycle=${cycle.id}`}><BarChart3 size={14} />查看 {cycle.id} 资产统计</Link>
            <button onClick={() => setShowEvidenceDetails((current) => !current)}>
              <ChevronDown size={14} />{showEvidenceDetails ? '收起模型细节' : '展开模型细节'}
            </button>
          </div>
          <div className="reason-code-list">
            <span>模型与门槛记录</span>
            {cycle.evidence.reason_codes.map((code) => <code key={code}>{code}</code>)}
          </div>
          <div className="layer-policy-table">
            <span>分层发布资格</span>
            {cycle.id === 'C1' && <div><span>长期结构背景说明</span><span className="status-badge status-research">低置信可用</span></div>}
            {longPanel && <div><span>1–3年因子方向概率</span><span className="status-badge status-research">研究可用</span></div>}
            {liquidityState && <div><span>3–12月状态方向</span><span className="status-badge status-research">研究可用</span></div>}
            {riskAppetiteState && <div><span>1–5个月风险区间概率</span><span className="status-badge status-research">研究可用</span></div>}
            {([
              ['historical', longPanel ? '正式历史相位' : '历史相位'],
              ['realtime', longPanel ? '正式实时相位' : '实时单边'],
              ['forecast', longPanel ? '精确路径预测' : '预测延伸'],
              ['asset_statistics', '资产统计'],
            ] as const).map(([key, label]) => (
              <div key={key}><span>{label}</span><StatusBadge status={cycle.publication[key]} /></div>
            ))}
          </div>
          <div className="policy-reason"><strong>{longPanel ? '正式相位仍阻断的原因' : '阻断/限制原因'}</strong><p>{cycle.publication.reason}</p></div>
          {cycle.id === 'C1' && (
            <div className="long-panel-card">
              <span>康波可验证性</span>
              <strong>已改为全球产出、生产率、技术扩散、资本形成、人口、全球连接和能源系统七类实体因子；金融资产不再进入核心。</strong>
              <div className="long-panel-probabilities">
                <div><small>5年方向准确率</small><b>{(c1FiveYear.accuracy * 100).toFixed(1)}%</b><em>当前方向 {c1FiveYear.currentDirection}</em></div>
                <div><small>10年方向准确率</small><b>{(c1TenYear.accuracy * 100).toFixed(1)}%</b><em>当前方向 {c1TenYear.currentDirection} · 仅{c1TenYear.sampleCount}例</em></div>
              </div>
              <dl>
                <div><dt>人工阶段校准</dt><dd>{c1.phaseCalibration.phase}</dd></div>
                <div><dt>量化动量</dt><dd>{c1.currentState.momentumLabel}</dd></div>
                <div><dt>长期配置用途</dt><dd>{c1.strategicAllocationGuidance.status === 'limited' ? '受限可用' : '阻断'}</dd></div>
                <div><dt>方法符号一致</dt><dd>{(c1.stability.methodLevelAgreement * 100).toFixed(1)}%</dd></div>
                <div><dt>当前数据时点</dt><dd>{c1.asOf}</dd></div>
              </dl>
              <div className="c1-asset-validation">
                <span>金融资产外部验证 · 不进入核心因子</span>
                {c1.strategicAllocationGuidance.researchRelationships.map((item: any) => (
                  <div key={item.asset}>
                    <strong>{item.asset}</strong>
                    <em>同期低频相关 {item.bandCorrelation.toFixed(2)}</em>
                    <em>最大相位差相关 {item.bestLagCorrelation.toFixed(2)}</em>
                    <small>仅 {item.effectiveLongWaves.toFixed(1)} 个有效长波</small>
                  </div>
                ))}
              </div>
              <p>{c1.strategicAllocationGuidance.currentAction}。当前总覆盖 {(c1.coreCoverage.currentRatio * 100).toFixed(0)}%，其中 {(c1.coreCoverage.currentBridgeRatio * 100).toFixed(0)}% 来自通过门槛的明确桥接。现代技术扩散桥接因重叠过短且相关性过低已被拒绝，修正后端点动量从“改善”降为“平稳”；同时5年与10年方向判断相反，且红噪声检验仍未通过。因此不能据此解锁资产配置。2026年“萧条末期”仍是人工研究校准，不是量化相位。剩余缺口：{c1.dataGaps[0]}</p>
            </div>
          )}
          {diagnostic && (
            <>
              {cycle.id === 'C2' && c2State ? (
                <div className="long-panel-card c2-direct-regime-card">
                  <span>C2 直接状态与资产揭示验证</span>
                  <strong>当前为{phaseNames[c2State.phase]}期。1年动量转正，但2年接近零、3年仍为负，因此不确认复苏转相。</strong>
                  <div className="long-panel-probabilities three-columns">
                    <div><small>未来1年因子上行</small><b>{(oneYearForecast.probabilityUp * 100).toFixed(0)}%</b><em>方向准确率 {(longPanel.validation['1y'].accuracy * 100).toFixed(0)}%</em></div>
                    <div><small>未来2年因子上行</small><b>{(twoYearForecast.probabilityUp * 100).toFixed(0)}%</b><em>方向准确率 {(longPanel.validation['2y'].accuracy * 100).toFixed(0)}%</em></div>
                    <div><small>未来3年因子上行</small><b>{(threeYearForecast.probabilityUp * 100).toFixed(0)}%</b><em>方向准确率 {(longPanel.validation['3y'].accuracy * 100).toFixed(0)}%</em></div>
                  </div>
                  <div className="c2-architecture-grid">
                    <div><span>活动核心</span><strong>{c2Regime.architecture.activityCore.join(' + ')}</strong><small>直接定义相位</small></div>
                    <div><span>确认层</span><strong>{c2Regime.architecture.confirmation.join(' + ')}</strong><small>不反向改变核心</small></div>
                    <div><span>结构压力</span><strong>{c2Regime.architecture.structuralPressure.join(' + ')}</strong><small>识别脆弱性</small></div>
                    <div><span>传播层</span><strong>{c2Regime.architecture.propagation.join(' + ')}</strong><small>验证经济外溢</small></div>
                  </div>
                  <div className="c2-region-state-grid">
                    {c2FamilyStates.families.filter((family: any) => family.currentEligible).map((family: any) => <div key={family.familyId}><strong>{family.label}</strong><span>{phaseNames[family.phase]}</span><em>{family.year} · {family.countryCount} 国</em><small>动量共识 {family.slopeConsensus.toFixed(2)}</small></div>)}
                  </div>
                  <dl>
                    <div><dt>历史共识峰谷</dt><dd>{c2HistoricalDating.turningPoints.length} 个</dd></div>
                    <div><dt>实时转相分数</dt><dd>{(c2Transition.score * 100).toFixed(0)} / {(c2Transition.requiredScore * 100).toFixed(0)}</dd></div>
                    <div><dt>银行危机覆盖</dt><dd>{(c2Regime.expertCalibration.crisisCoverage * 100).toFixed(1)}%</dd></div>
                    <div><dt>峰值精度</dt><dd>{(c2Regime.expertCalibration.peakPrecision * 100).toFixed(1)}%</dd></div>
                    <div><dt>危机中位领先</dt><dd>{c2Regime.expertCalibration.medianLeadYears} 年</dd></div>
                    <div><dt>历史资产FDR通过</dt><dd>{c2AssetMapping.summary.hacFdrPassed}/{c2AssetMapping.summary.eligibleAssets}</dd></div>
                    <div><dt>七周期联合资产单元</dt><dd>{c2JointAsset.passedCells}/{c2JointAsset.cellCount} 通过</dd></div>
                    <div><dt>现代资产暴露登记</dt><dd>{c2JointAsset.exposureRegistry.assetCount} 条</dd></div>
                    <div><dt>季度错位可验证</dt><dd>{c2JointAsset.cells['12mReturn'].exposureValidatedAssetCount}/{c2JointAsset.cells['12mReturn'].directCountryCandidateCount} 条</dd></div>
                    <div><dt>分层风险窗口</dt><dd>{c2HierarchicalRisk?.passedHorizons ?? 0}/{c2HierarchicalRisk?.horizonCount ?? 0} 通过</dd></div>
                    <div><dt>历史风险研究通道</dt><dd>{c2HierarchicalRisk?.passedHistoricalRiskChannels ?? 0} 条通过</dd></div>
                    <div><dt>当前宏观压力</dt><dd>{c2CurrentPressure?.label ?? '未开放'}</dd></div>
                  </dl>
                  <p>{c2JointAsset.framework.definition} 当前只实现客观统计链路，尚未通过正式映射门槛；不得把地产、银行、消费或科技按主观相关性直接指定为高映射资产。</p>
                  <div className="asset-forward-validation-grid c2-cycle-validation-grid">
                    {Object.entries(c2JointAsset.cells).map(([key, cell]: [string, any]) => (
                      <div key={key}>
                        <small>{cell.horizonMonths}个月{cell.target === 'return' ? '收益' : '风险'}</small>
                        <strong>{cell.status === 'insufficient_non_overlapping_history' ? '历史不足' : `${((cell.modelComparison.globalC2.positiveOosR2Share ?? 0) * 100).toFixed(0)}%`}</strong>
                        <span>{cell.status === 'insufficient_non_overlapping_history' ? '非重叠路径不足' : '全球C2 · R²为正资产'}</span>
                        <em>{cell.status === 'insufficient_non_overlapping_history' ? '36个月暂不判断' : `错位可验 ${cell.modelComparison.exposureWeightedC2.assetCount} 条 · 中位R² ${cell.modelComparison.exposureWeightedC2.medianOosR2?.toFixed(3) ?? '—'}`}</em>
                      </div>
                    ))}
                  </div>
                  {c2HierarchicalRisk && (
                    <div className="c2-geographic-panel">
                      <div className="family-ablation-heading">
                        <span>股票、国债、短票独立验证</span>
                        <b className="is-failed">{c2AssetClassValidation?.passedTargets ?? 0}/{c2AssetClassValidation?.targetCount ?? 0} 通道通过</b>
                      </div>
                      {c2AssetClassValidation?.classes.map((assetClass: any) => (
                        <div className="c2-historical-risk-channel" key={assetClass.category}>
                          <div className="family-ablation-heading"><span>{assetClass.category.replace('跨国', '')}目标</span><b className={assetClass.passedTargets ? '' : 'is-failed'}>{assetClass.passedTargets}/{assetClass.targetCount} 通过</b></div>
                          <div className="asset-forward-validation-grid c2-cycle-validation-grid">
                            {assetClass.targets.map((target: any) => (
                              <div key={`${target.targetId}-${target.horizonYears}`}>
                                <small>{target.horizonYears}年 · {target.label}</small>
                                <strong>{target.status === 'passed_historical_channel' ? '历史通道通过' : '增量失败'}</strong>
                                <span>C2 AUC {target.recursiveValidation.candidate.auc?.toFixed(3) ?? '—'} · 基线 {target.recursiveValidation.baseline.auc?.toFixed(3) ?? '—'}</span>
                                <em>Δ {target.recursiveValidation.aucDelta?.toFixed(3) ?? '—'} · Brier {target.recursiveValidation.brierImprovement?.toFixed(3) ?? '—'}</em>
                              </div>
                            ))}
                          </div>
                        </div>
                      ))}
                      {c2ConditionalPropagation && (
                        <div className="c2-conditional-propagation">
                          <div className="family-ablation-heading c2-legacy-audit-heading">
                            <span>条件传播终局验证</span>
                            <b className="is-failed">{c2ConditionalPropagation.passedChannels}/{c2ConditionalPropagation.channelCount} 通道通过</b>
                          </div>
                          <div className="asset-forward-validation-grid c2-cycle-validation-grid">
                            {c2ConditionalPropagation.scenarios.map((scenario: any) => {
                              const best = [...scenario.channels]
                                .filter((channel: any) => channel.recursiveValidation.aucDelta != null)
                                .sort((left: any, right: any) => right.recursiveValidation.aucDelta - left.recursiveValidation.aucDelta)[0]
                              return (
                                <div key={scenario.scenarioId}>
                                  <small>{scenario.label}</small>
                                  <strong>{scenario.passedChannels}/{scenario.channelCount} 通过</strong>
                                  <span>双改善 {scenario.positiveFullSampleChannels} 项 · 中位Δ {scenario.medianAucDelta?.toFixed(3) ?? '—'}</span>
                                  <em>{best ? `最强 ${best.category.replace('跨国', '')}${best.horizonYears}年${best.targetLabel} · Δ ${best.recursiveValidation.aucDelta.toFixed(3)}` : '无可比较通道'}</em>
                                </div>
                              )
                            })}
                          </div>
                          <p><strong>{c2ConditionalPropagation.conclusion}</strong> {c2ConditionalPropagation.caveat}</p>
                        </div>
                      )}
                      <div className="family-ablation-heading c2-legacy-audit-heading">
                        <span>旧联合下行风险模型</span>
                        <b className="is-failed">{c2HierarchicalRisk.passedHorizons}/{c2HierarchicalRisk.horizonCount} 窗口通过</b>
                      </div>
                      <div className="asset-forward-validation-grid c2-cycle-validation-grid">
                        {Object.values(c2HierarchicalRisk.horizons).map((horizon: any) => {
                          const persistence = horizon.architectures.asset_persistence
                          const hierarchy = horizon.architectures.country_hierarchy
                          return (
                            <div key={horizon.horizonYears}>
                              <small>未来 {horizon.horizonYears} 年高下行风险状态</small>
                              <strong>{horizon.status === 'passed_limited' ? '有限通过' : '增量失败'}</strong>
                              <span>资产惯性 AUC {persistence.auc.toFixed(3)}</span>
                              <em>国家分层 {hierarchy.auc.toFixed(3)} · Δ {horizon.incrementalVsPersistence.aucDelta >= 0 ? '+' : ''}{horizon.incrementalVsPersistence.aucDelta.toFixed(3)}</em>
                              <small>同时改善排序与校准 {horizon.incrementalVsPersistence.categorySupport}/{horizon.incrementalVsPersistence.categoryCount} 个资产大类</small>
                            </div>
                          )
                        })}
                      </div>
                      {c2BondRiskChannel && (
                        <div className="c2-historical-risk-channel">
                          <div className="family-ablation-heading">
                            <span>3年国债下行压力审计</span>
                            <b className={c2BondRiskChannel.status === 'passed_historical_stress' ? '' : 'is-failed'}>{c2BondRiskChannel.status === 'passed_historical_stress' ? '历史压力测试通过' : '风险口径修正后未通过'}</b>
                          </div>
                          <div className="asset-forward-validation-grid c2-cycle-validation-grid">
                            <div>
                              <small>递归年份样本外</small>
                              <strong>AUC {c2BondRiskChannel.recursiveValidation.candidate.auc.toFixed(3)}</strong>
                              <span>资产惯性 {c2BondRiskChannel.recursiveValidation.baseline.auc.toFixed(3)}</span>
                              <em>增量 {c2BondRiskChannel.recursiveValidation.aucDelta >= 0 ? '+' : ''}{c2BondRiskChannel.recursiveValidation.aucDelta.toFixed(3)}</em>
                            </div>
                            <div>
                              <small>概率校准</small>
                              <strong>Brier {c2BondRiskChannel.recursiveValidation.candidate.brier.toFixed(3)}</strong>
                              <span>较惯性变化 {c2BondRiskChannel.recursiveValidation.brierImprovement >= 0 ? '+' : ''}{c2BondRiskChannel.recursiveValidation.brierImprovement.toFixed(3)}</span>
                              <em>{c2BondRiskChannel.recursiveValidation.candidate.observations} 个观察</em>
                            </div>
                            <div>
                              <small>跨时期稳定性</small>
                              <strong>最低 AUC {Math.min(...c2BondRiskChannel.subperiods.map((period: any) => period.candidate.auc)).toFixed(3)}</strong>
                              <span>1950—1984 / 1985—2020</span>
                              <em>{c2BondRiskChannel.status === 'passed_historical_stress' ? '两段均改善排序和校准' : '跨时期结果不稳定'}</em>
                            </div>
                            <div>
                              <small>国家留一 · 2000年后</small>
                              <strong>AUC {c2BondRiskChannel.leaveCountryOut2000Plus.candidate.auc.toFixed(3)}</strong>
                              <span>增量 {c2BondRiskChannel.leaveCountryOut2000Plus.aucDelta >= 0 ? '+' : ''}{c2BondRiskChannel.leaveCountryOut2000Plus.aucDelta.toFixed(3)}</span>
                              <em>{c2BondRiskChannel.leaveCountryOut2000Plus.countryCount} 国 · {(c2BondRiskChannel.leaveCountryOut2000Plus.improvedCountryShare * 100).toFixed(0)}% 改善</em>
                            </div>
                          </div>
                          {c2ModernPressure && c2CurrentPressure && (
                            <div className="c2-modern-pressure-panel">
                              <div className="family-ablation-heading">
                                <span>现代结构与融资桥接</span>
                                <b>宏观状态可观察 · 资产映射阻断</b>
                              </div>
                              <div className="asset-forward-validation-grid c2-cycle-validation-grid">
                                <div><small>结构代理替换</small><strong>相关 {c2ModernPressure.structureProxyValidation.correlation.toFixed(3)}</strong><span>{c2ModernPressure.structureProxyValidation.countryCount} 国 · 2000—2020</span><em>方向一致 {(c2ModernPressure.structureProxyValidation.directionAgreement * 100).toFixed(1)}%</em></div>
                                <div><small>融资代理一致性</small><strong>相关 {c2ModernPressure.financingProxyValidation.correlation.toFixed(3)}</strong><span>{c2ModernPressure.financingProxyValidation.countryCount} 国 · 2000—2020</span><em>方向一致 {(c2ModernPressure.financingProxyValidation.directionAgreement * 100).toFixed(1)}%</em></div>
                                <div><small>当前结构压力 · {c2CurrentPressure.asOfYear}</small><strong>{c2CurrentPressure.label}</strong><span>历史分位 {(c2CurrentPressure.historicalPercentile * 100).toFixed(1)}%</span><em>3年斜率 {c2CurrentPressure.slope3Y >= 0 ? '+' : ''}{c2CurrentPressure.slope3Y.toFixed(3)}</em></div>
                                <div><small>融资条件覆盖</small><strong>{c2CurrentPressure.financingCoverage.latestDataCountryCount}/{c2CurrentPressure.financingCoverage.minimumCountryCount} 国</strong><span>口径验证相关 {c2ModernPressure.financingProxyValidation.correlation.toFixed(3)}</span><em>全球覆盖最近通过于 {c2CurrentPressure.financingCoverage.latestSupportedYear}</em></div>
                              </div>
                              <p>{c2CurrentPressure.interpretation} {c2ModernPressure.caveat}</p>
                            </div>
                          )}
                          <p>{c2BondRiskChannel.interpretation} {c2BondRiskChannel.caveat}</p>
                        </div>
                      )}
                      <p>{c2AssetClassValidation?.interpretation} 12个独立资产—期限通道均未取得稳定C2增量；旧联合模型和旧国债通道也未通过。</p>
                    </div>
                  )}
                  {c2Geography && <div className="c2-geographic-panel"><div className="family-ablation-heading"><span>全球—区域—本国错位</span><b className="is-failed">资产预测未通过</b></div><div className="c2-geographic-summary"><div><small>国家相位同全球</small><strong>{(c2Geography.summary.countryPhaseAgreementWithGlobal * 100).toFixed(0)}%</strong><span>{c2Geography.summary.countryCount} 国</span></div><div><small>国家动量同全球</small><strong>{(c2Geography.summary.countrySlopeAgreementWithGlobal * 100).toFixed(0)}%</strong><span>允许国家错位</span></div><div><small>本国时钟长历史</small><strong>{c2JointAsset.countryClockMapping.summary.countryCount} 国</strong><span>{c2JointAsset.countryClockMapping.summary.directAssetCount} 条直接资产</span></div></div><div className="c2-focus-country-grid">{c2Geography.focusCountries.map((country: any) => { const clock = c2JointAsset.countryClockMapping.focusCountries.find((item: any) => item.iso === country.iso); return <div key={country.iso}><strong>{country.name}</strong><span>{phaseNames[country.phase]}</span><em>{country.asOfPeriod} · {country.activity.toFixed(2)}σ</em><small>持续 {country.phaseDurationYears.toFixed(1)} 年 · 相对同业 {country.deviationFromPeers >= 0 ? '+' : ''}{country.deviationFromPeers.toFixed(2)}σ</small><small>{clock?.status === 'direct_long_history' ? `${clock.history.startYear}—${clock.history.endYear} · ${clock.directAssetCount} 条本国长历史资产` : clock?.reason}</small></div> })}</div><p>{c2Geography.method} 历史资产改按各国自身峰谷的事件时间对齐；中国因2012年后短样本继续阻断，日本使用JST本国股票、国债和短票直接历史，不用ETF上市地代理。{c2Geography.caveat}</p></div>}
                  <p>方向概率预测的是住房—按揭核心自身，不代表地产股或其他资产涨跌。当前资产映射只保留历史条件统计；多数资产的绝对样本外R²仍为负。</p>
                </div>
              ) : cycle.id === 'C3' && c3Regime ? (
                <div className="long-panel-card c2-direct-regime-card">
                  <span>C3 投资—信用双核心重构</span>
                  <strong>当前为{phaseNames[c3Regime.state.current.phase]}期：双核心仍在低位，但斜率已转正。100个月只作弱先验，三组搜索范围均识别约 {c3Regime.state.current.periodYears.toFixed(1)} 年。</strong>
                  <div className="long-panel-probabilities three-columns">
                    <div><small>未来1年双核心上行</small><b>{(oneYearForecast.probabilityUp * 100).toFixed(0)}%</b><em>相对惯性 ΔAUC {(c3Regime.architectureComparison.architectures.find((item: any) => item.architectureId === 'dual_core').horizons['1y'].aucImprovement * 100).toFixed(1)}pct</em></div>
                    <div><small>未来2年双核心上行</small><b>{(twoYearForecast.probabilityUp * 100).toFixed(0)}%</b><em>相对惯性 ΔAUC {(c3Regime.architectureComparison.architectures.find((item: any) => item.architectureId === 'dual_core').horizons['2y'].aucImprovement * 100).toFixed(1)}pct</em></div>
                    <div><small>未来3年双核心上行</small><b>{(threeYearForecast.probabilityUp * 100).toFixed(0)}%</b><em>相对惯性 ΔAUC {(c3Regime.architectureComparison.architectures.find((item: any) => item.architectureId === 'dual_core').horizons['3y'].aucImprovement * 100).toFixed(1)}pct</em></div>
                  </div>
                  <div className="c2-architecture-grid">
                    <div><span>周期核心</span><strong>{c3Regime.factorArchitecture.cycleCore.join(' + ')}</strong><small>直接定义C3</small></div>
                    <div><span>确认层</span><strong>{c3Regime.factorArchitecture.confirmation.join(' + ')}</strong><small>未稳定升级</small></div>
                    <div><span>结构位置</span><strong>{c3Regime.factorArchitecture.structuralPosition.join(' + ')}</strong><small>不参与周期长度</small></div>
                    <div><span>禁止输入</span><strong>股票 / 债券 / 商品收益</strong><small>避免资产价格泄漏</small></div>
                  </div>
                  <div className="architecture-comparison-panel">
                    <div className="family-ablation-heading"><span>固定共同目标架构比较</span><b className="is-failed">0/4 架构全期限通过</b></div>
                    <div className="architecture-comparison-grid">
                      {c3Regime.architectureComparison.architectures.map((item: any) => (
                        <div className={item.architectureId === c3Regime.architectureComparison.selectedArchitecture ? 'is-selected' : ''} key={item.architectureId}>
                          <strong>{item.label}</strong>
                          <span>1年 ΔAUC {(item.horizons['1y'].aucImprovement * 100).toFixed(1)}pct</span>
                          <span>3年 ΔAUC {(item.horizons['3y'].aucImprovement * 100).toFixed(1)}pct</span>
                          <em>{item.passedHorizons}/{item.horizonCount} 期限通过</em>
                        </div>
                      ))}
                    </div>
                    <p>{c3Regime.architectureComparison.conclusion}</p>
                  </div>
                  <dl>
                    <div><dt>当前动态周期</dt><dd>{c3Regime.state.current.periodYears.toFixed(1)}年</dd></div>
                    <div><dt>多规格相位一致</dt><dd>{(c3Regime.state.parameterRobustness.phaseAgreement * 100).toFixed(0)}%</dd></div>
                    <div><dt>搜索边界占比</dt><dd>{(c3Regime.state.current.periodBoundaryShare * 100).toFixed(0)}%</dd></div>
                    <div><dt>当前覆盖</dt><dd>{c3Regime.state.current.countryCount} 国</dd></div>
                    <div><dt>资产增量通道</dt><dd>{c3Regime.assetValidation.passedTargets}/{c3Regime.assetValidation.targetCount}</dd></div>
                    <div><dt>直接商品验证</dt><dd>历史不足</dd></div>
                  </dl>
                  <div className="asset-forward-validation-grid c2-cycle-validation-grid">
                    {c3Regime.assetValidation.cells.map((cell: any) => (
                      <div key={`${cell.category}-${cell.horizonYears}-${cell.target}`}>
                        <small>{cell.category.replace('跨国', '')} · {cell.horizonYears}年{cell.target === 'return' ? '收益' : '风险'}</small>
                        <strong>{cell.passed ? '通过' : '未通过'}</strong>
                        <span>AUC {cell.auc.toFixed(2)} · ΔAUC {(cell.aucImprovement * 100).toFixed(1)}pct</span>
                        <em>ΔBrier {cell.brierImprovement >= 0 ? '+' : ''}{cell.brierImprovement.toFixed(3)}</em>
                      </div>
                    ))}
                  </div>
                  <p>{c3Regime.assetValidation.method} 当前仅股票1年最大回撤风险通过；不足以形成资产概率或配置建议。</p>
                </div>
              ) : longPanel ? (
                <div className="long-panel-card">
                  <span>长历史方向验证</span>
                  <strong>{longPanel.publishableClaim}</strong>
                  <div className="long-panel-probabilities three-columns">
                    <div><small>未来1年因子上行</small><b>{(oneYearForecast.probabilityUp * 100).toFixed(0)}%</b><em>样本外准确率 {(longPanel.validation['1y'].accuracy * 100).toFixed(0)}%</em></div>
                    {twoYearForecast && <div><small>未来2年因子上行</small><b>{(twoYearForecast.probabilityUp * 100).toFixed(0)}%</b><em>样本外准确率 {(longPanel.validation['2y'].accuracy * 100).toFixed(0)}%</em></div>}
                    <div><small>未来3年因子上行</small><b>{(threeYearForecast.probabilityUp * 100).toFixed(0)}%</b><em>样本外准确率 {(longPanel.validation['3y'].accuracy * 100).toFixed(0)}%</em></div>
                  </div>
                  <dl>
                    <div><dt>当前信息时点</dt><dd>{oneYearForecast.asOfPeriod ?? oneYearForecast.asOfYear}</dd></div>
                    <div><dt>最新时点国家</dt><dd>{oneYearForecast.latestYearCountryCount}/{oneYearForecast.countryCount}</dd></div>
                    <div><dt>国家留一·1年</dt><dd>{(longPanel.validation['1y'].leaveCountryOut2000Plus.accuracy * 100).toFixed(0)}%</dd></div>
                    <div><dt>国家留一·3年</dt><dd>{(longPanel.validation['3y'].leaveCountryOut2000Plus.accuracy * 100).toFixed(0)}%</dd></div>
                    <div><dt>峰值中位数</dt><dd>{longPanel.spectral.medianPeakYears.toFixed(1)}年</dd></div>
                    <div><dt>红噪声通过率</dt><dd>{(longPanel.spectral.redNoisePassShare10pct * 100).toFixed(0)}%</dd></div>
                  </dl>
                  {cycle.id === 'C2' && architectureComparison && (
                    <div className="architecture-comparison-panel">
                      <div className="family-ablation-heading">
                        <span>固定目标因子架构比较</span>
                        <b>选择 住房—信用核心综合</b>
                      </div>
                      <div className="architecture-comparison-grid">
                        {architectureComparison.architectures.map((item: any) => (
                          <div className={item.architectureId === architectureComparison.selectedArchitecture ? 'is-selected' : ''} key={item.architectureId}>
                            <strong>{item.label}</strong>
                            <span>递归准确率 {(item.summary.accuracyMean * 100).toFixed(1)}%</span>
                            <span>国家留一 {(item.summary.countryHoldoutAccuracyMean * 100).toFixed(1)}%</span>
                            <em>Brier {item.summary.brierMean.toFixed(3)}</em>
                          </div>
                        ))}
                      </div>
                      <p>{architectureComparison.recommendation.cycleDefinition} {architectureComparison.recommendation.confirmationLayer} {architectureComparison.recommendation.propagationLayer}</p>
                    </div>
                  )}
                  {familyAblation && (
                    <div className="family-ablation-panel">
                      <div className="family-ablation-heading">
                        <span>指标族剔除验证</span>
                        <b>{familyAblation.passedGroups}/{familyAblation.groupCount} 组通过</b>
                      </div>
                      <div className="family-ablation-grid">
                        {familyAblation.groups.map((item: any) => (
                          <div className="family-ablation-row" key={item.groupId}>
                            <strong>{item.label}</strong>
                            <span>1年 {(item.horizons['1y'].accuracy * 100).toFixed(0)}%</span>
                            <span>3年 {(item.horizons['3y'].accuracy * 100).toFixed(0)}%</span>
                            <em>标签一致 {(
                              Math.min(
                                item.horizons['1y'].targetAgreement.agreement,
                                item.horizons['3y'].targetAgreement.agreement,
                              ) * 100
                            ).toFixed(0)}%</em>
                            <i className={item.maximumAbsoluteCurrentProbabilityShift >= 0.1 ? 'is-sensitive' : ''}>
                              {item.activeInDefaultModel === false
                                ? '确认层未进入默认概率模型'
                                : `概率漂移 ${(item.maximumAbsoluteCurrentProbabilityShift * 100).toFixed(1)}pct`}
                            </i>
                          </div>
                        ))}
                      </div>
                      <p>
                        {familyAblation.passedGroups}/{familyAblation.groupCount} 组剔除测试通过；最大敏感项为{mostSensitiveFamily?.label}，当前概率最多变化
                        {mostSensitiveFamily ? (mostSensitiveFamily.maximumAbsoluteCurrentProbabilityShift * 100).toFixed(1) : '—'}个百分点。核心通道必要性较强，概率幅度仍有明显模型敏感性。
                      </p>
                    </div>
                  )}
                  {independentOutcomes && (
                    <div className="independent-outcome-panel">
                      <div className="family-ablation-heading">
                        <span>外部经济结果验证</span>
                        <b className={independentOutcomes.status === 'passed_limited' ? '' : 'is-failed'}>
                          {independentOutcomes.passedCells}/{independentOutcomes.cellCount} 单元通过
                        </b>
                      </div>
                      <div className="independent-outcome-grid">
                        {independentOutcomes.cells.map((item: any) => (
                          <div className={item.passed ? 'is-passed' : 'is-failed'} key={`${item.outcomeId}-${item.horizonYears}`}>
                            <strong>{item.label}</strong>
                            <span>{item.horizonYears}年</span>
                            <em>AUC {item.auc.toFixed(2)}</em>
                            <i>ΔAUC {item.aucImprovement >= 0 ? '+' : ''}{item.aucImprovement.toFixed(2)}</i>
                            <em>ΔBrier {item.brierImprovement >= 0 ? '+' : ''}{item.brierImprovement.toFixed(3)}</em>
                            <i>秩相关 {item.spearman.toFixed(2)}</i>
                            <b>{item.passed ? '通过' : '未通过'}</b>
                          </div>
                        ))}
                      </div>
                      <p>{independentOutcomes.caveat}</p>
                    </div>
                  )}
                  {cycle.id === 'C2' && geographicState && (
                    <div className="c2-geographic-panel">
                      <div className="family-ablation-heading">
                        <span>全球—区域—本国错位诊断</span>
                        <b className="is-failed">仅研究，不发布资产结论</b>
                      </div>
                      <div className="c2-geographic-summary">
                        <div><small>国家四相位同全球</small><strong>{(geographicState.summary.countryPhaseAgreementWithGlobal * 100).toFixed(0)}%</strong><span>{geographicState.summary.countryCount} 国</span></div>
                        <div><small>国家斜率同全球</small><strong>{(geographicState.summary.countrySlopeAgreementWithGlobal * 100).toFixed(0)}%</strong><span>{geographicState.summary.countriesUpdatedInCurrentYear} 国更新至当年</span></div>
                        <div><small>区域四相位同全球</small><strong>{(geographicState.summary.regionPhaseAgreementWithGlobal * 100).toFixed(0)}%</strong><span>{geographicState.summary.regionCount} 个区域</span></div>
                      </div>
                      <div className="c2-region-state-grid">
                        {geographicState.currentRegions.map((region: any) => (
                          <div key={region.regionId}>
                            <strong>{region.label}</strong>
                            <span>{phaseNames[region.phase]}</span>
                            <em>{region.asOfYear} · {region.countryCount} 国</em>
                            <small>候选周期 {region.periodYears.toFixed(1)} 年</small>
                          </div>
                        ))}
                      </div>
                      <p>{geographicState.caveat}</p>
                    </div>
                  )}
                  <p>因子未来方向概率通过，不等于当前动量、四相位、精确周期长度或资产收益预测通过。C2 当前只确认低位，转折尚未确认。</p>
                </div>
              ) : liquidityState ? (
                <div className="long-panel-card">
                  <span>三层流动性状态验证</span>
                  <strong>当前 {liquidityState.current.regime}；直接期限模型显示状态{liquidityPathLabel}。</strong>
                  <div className="long-panel-probabilities three-columns">
                    <div><small>未来3个月状态{(liquidityForecast3?.probabilityUp ?? 0) >= 0.5 ? '上行' : '下行'}</small><b>{(Math.max(liquidityForecast3?.probabilityUp ?? 0, liquidityForecast3?.probabilityDown ?? 0) * 100).toFixed(0)}%</b><em>样本外准确率 {(liquidityState.validation['3m'].accuracy * 100).toFixed(0)}%</em></div>
                    <div><small>未来6个月状态{(liquidityForecast6?.probabilityUp ?? 0) >= 0.5 ? '上行' : '下行'}</small><b>{(Math.max(liquidityForecast6?.probabilityUp ?? 0, liquidityForecast6?.probabilityDown ?? 0) * 100).toFixed(0)}%</b><em>样本外准确率 {(liquidityState.validation['6m'].accuracy * 100).toFixed(0)}%</em></div>
                    <div><small>未来12个月状态{(liquidityForecast12?.probabilityUp ?? 0) >= 0.5 ? '上行' : '下行'}</small><b>{(Math.max(liquidityForecast12?.probabilityUp ?? 0, liquidityForecast12?.probabilityDown ?? 0) * 100).toFixed(0)}%</b><em>样本外准确率 {(liquidityState.validation['12m'].accuracy * 100).toFixed(0)}%</em></div>
                  </div>
                  <dl>
                    <div><dt>3个月 AUC</dt><dd>{liquidityState.validation['3m'].auc.toFixed(2)}</dd></div>
                    <div><dt>6个月 AUC</dt><dd>{liquidityState.validation['6m'].auc.toFixed(2)}</dd></div>
                    <div><dt>12个月 AUC</dt><dd>{liquidityState.validation['12m'].auc.toFixed(2)}</dd></div>
                    <div><dt>当前状态值</dt><dd>{liquidityState.current.level.toFixed(2)}σ</dd></div>
                    <div><dt>资产增量通道</dt><dd>{liquidityState.assetValidation.summary.passedChannels}/{liquidityState.assetValidation.summary.totalChannels}</dd></div>
                  </dl>
                  <div className="family-ablation-panel">
                    <div className="family-ablation-heading"><span>当前三层贡献</span><b className={liquidityState.confirmation.current.status === '同向确认' ? '' : 'is-failed'}>NFCI {liquidityState.confirmation.current.status}</b></div>
                    <div className="family-ablation-grid">
                      {liquidityState.current.families.map((family: any) => (
                        <div className="family-ablation-row" key={family.family}>
                          <strong>{family.family}</strong><span>{family.value.toFixed(2)}σ</span><span>{family.compositeContribution >= 0 ? '+' : ''}{family.compositeContribution.toFixed(2)}σ</span>
                          <em>{family.signalCount}/{family.signalTotal} 个信号可用</em><i>等权合成贡献</i>
                        </div>
                      ))}
                    </div>
                    <p>{liquidityState.ablationValidation.status === 'mixed_redundancy' ? '删去国内政策层后6个月AUC略有改善，说明三层间仍有部分冗余；信用传导与全球美元层提供了更稳定的新增信息。' : '删去任一核心层均未改善验证表现，三层结构保持稳定。'}</p>
                  </div>
                  <p>{liquidityState.caveat}</p>
                </div>
              ) : riskAppetiteState ? (
                <div className="long-panel-card">
                  <span>风险偏好状态验证</span>
                  <strong>当前 {riskAppetiteState.current.regime}；1至5个月风险区间概率通过，6个月不发布。</strong>
                  <div className="long-panel-probabilities">
                    <div><small>1个月仍在正区间</small><b>{((riskAppetiteState.forecastPath.find((row: any) => row.horizonMonths === 1)?.probabilityRiskOn ?? 0) * 100).toFixed(0)}%</b><em>样本外准确率 {(riskAppetiteState.validation['1m'].accuracy * 100).toFixed(0)}%</em></div>
                    <div><small>3个月仍在正区间</small><b>{((riskAppetiteState.forecastPath.find((row: any) => row.horizonMonths === 3)?.probabilityRiskOn ?? 0) * 100).toFixed(0)}%</b><em>样本外准确率 {(riskAppetiteState.validation['3m'].accuracy * 100).toFixed(0)}%</em></div>
                    <div><small>5个月仍在正区间</small><b>{((riskAppetiteState.forecastPath.find((row: any) => row.horizonMonths === 5)?.probabilityRiskOn ?? 0) * 100).toFixed(0)}%</b><em>样本外准确率 {(riskAppetiteState.pathValidation['5m'].accuracy * 100).toFixed(0)}%</em></div>
                  </div>
                  <dl>
                    <div><dt>1个月 AUC</dt><dd>{riskAppetiteState.validation['1m'].auc.toFixed(2)}</dd></div>
                    <div><dt>3个月 AUC</dt><dd>{riskAppetiteState.validation['3m'].auc.toFixed(2)}</dd></div>
                    <div><dt>5个月 AUC</dt><dd>{riskAppetiteState.pathValidation['5m'].auc.toFixed(2)}</dd></div>
                    <div><dt>当前状态值</dt><dd>{riskAppetiteState.current.level.toFixed(2)}σ</dd></div>
                    <div><dt>资产增量通道</dt><dd>{riskAppetiteState.assetValidation.summary.passedChannels}/{riskAppetiteState.assetValidation.summary.totalChannels}</dd></div>
                  </dl>
                  <p>{riskAppetiteState.caveat}</p>
                </div>
              ) : (
                <div className="diagnostic-current-card">
                  <span>当前方向性提示</span>
                  <strong>{diagnostic.current.direction}</strong>
                  <dl><div><dt>状态水平</dt><dd>{diagnostic.current.level.toFixed(2)}σ</dd></div><div><dt>变化斜率</dt><dd>{diagnostic.current.slope.toFixed(2)}σ</dd></div><div><dt>家族分歧</dt><dd>{diagnostic.current.familyDisagreement.toFixed(2)}</dd></div><div><dt>数据时点</dt><dd>{diagnostic.current.date}</dd></div></dl>
                </div>
              )}
              {!['C2', 'C3', 'C5', 'C7'].includes(cycle.id) && phaseCandidate && (
                <div className="phase-candidate-card">
                  <span>{currentPhaseCandidate ? '当前地产周期研究状态' : '历史相位研究候选'}</span>
                  <strong>{currentPhaseCandidate ? `${currentPhaseCandidate.asOfPeriod}：${governedBroadState?.label ?? phaseNames[currentPhaseCandidate.current.phase]}` : `${latestHistoricalPhase.year} 年：${phaseNames[latestHistoricalPhase.phase]}`}</strong>
                  {factorArchitecture && (
                    <div className="c2-architecture-grid">
                      <div><span>核心层</span><strong>{factorArchitecture.cycleCore.join(' + ')}</strong><small>定义 C2 自身状态</small></div>
                      <div><span>确认层</span><strong>{factorArchitecture.confirmation.join(' + ')}</strong><small>只确认方向，不改变周期水平</small></div>
                      {factorArchitecture.propagation && <div><span>传播层</span><strong>{factorArchitecture.propagation.join(' + ')}</strong><small>验证外溢，不反向定义周期</small></div>}
                      <div><span>结构位置层</span><strong>{factorArchitecture.structuralPosition.join(' + ')}</strong><small>不参与周期长度识别</small></div>
                    </div>
                  )}
                  {phaseProbability?.status === 'passed_limited' && exactPhasePublishable && (
                    <div className="phase-probability-grid">
                      {Object.entries(phaseProbability.probabilities).map(([phase, probability]) => (
                        <div className={phase === phaseProbability.primaryPhase ? 'is-primary' : ''} key={phase}>
                          <span><b>{phaseNames[phase]}</b><em>{((probability as number) * 100).toFixed(1)}%</em></span>
                          <i><u style={{ width: `${Math.max(2, (probability as number) * 100)}%` }} /></i>
                        </div>
                      ))}
                    </div>
                  )}
                  <dl>
                    {currentPhaseCandidate ? <>
                      <div><dt>跨源相位一致率</dt><dd>{(currentPhaseCandidate.validation.phaseAgreement * 100).toFixed(1)}%</dd></div>
                      <div><dt>方向一致率</dt><dd>{(currentPhaseCandidate.validation.directionAgreement * 100).toFixed(1)}%</dd></div>
                    {mixedFrequencyPhase?.status === 'passed_limited' && <div><dt>Q1四相位准确率</dt><dd>{(mixedFrequencyPhase.phaseAccuracy * 100).toFixed(1)}% · 90%区间 {(mixedFrequencyPhase.phaseAccuracyInterval90[0] * 100).toFixed(0)}—{(mixedFrequencyPhase.phaseAccuracyInterval90[1] * 100).toFixed(0)}%</dd></div>}
                    {mixedFrequencyPhase?.status === 'passed_limited' && <div><dt>Q1高低位准确率</dt><dd>{(mixedFrequencyPhase.levelDirectionAccuracy * 100).toFixed(1)}% · 下界 {(mixedFrequencyPhase.levelDirectionAccuracyInterval90[0] * 100).toFixed(0)}%</dd></div>}
                    {mixedFrequencyPhase?.status === 'passed_limited' && <div><dt>Q1斜率方向准确率</dt><dd>{(mixedFrequencyPhase.slopeDirectionAccuracy * 100).toFixed(1)}% · 下界 {(mixedFrequencyPhase.slopeDirectionAccuracyInterval90[0] * 100).toFixed(0)}%</dd></div>}
                    {mixedFrequencyPhase?.status === 'passed_limited' && <div><dt>转相年份准确率</dt><dd>{(mixedFrequencyPhase.transitionPhaseAccuracy * 100).toFixed(1)}%（{mixedFrequencyPhase.transitionObservations}次）· 90%区间 {(mixedFrequencyPhase.transitionPhaseAccuracyInterval90[0] * 100).toFixed(0)}—{(mixedFrequencyPhase.transitionPhaseAccuracyInterval90[1] * 100).toFixed(0)}%</dd></div>}
                    {phaseProbability?.status === 'passed_limited' && exactPhasePublishable && <div><dt>相邻备选相位</dt><dd>{phaseNames[phaseProbability.alternativePhase]} {(phaseProbability.alternativeProbability * 100).toFixed(1)}%</dd></div>}
                    {phaseProbability?.status === 'passed_limited' && exactPhasePublishable && <div><dt>概率校准改善</dt><dd>Brier {(phaseProbability.validation.relativeBrierImprovement * 100).toFixed(1)}%</dd></div>}
                    <div><dt>重叠期相关性</dt><dd>{currentPhaseCandidate.validation.correlation.toFixed(2)}</dd></div>
                    {familyConfirmation && <div><dt>当前家族相位同向</dt><dd>{(familyConfirmation.aggregatePhaseAgreement * 100).toFixed(0)}%（{familyConfirmation.currentFamilyCount}组）</dd></div>}
                    {familyConfirmation && <div><dt>当前家族斜率同向</dt><dd>{(familyConfirmation.aggregateSlopeAgreement * 100).toFixed(0)}%</dd></div>}
                    {familyConfirmation && <div><dt>家族周期中位</dt><dd>{familyConfirmation.periodMedianYears.toFixed(1)}年（{familyConfirmation.periodIqrYears[0].toFixed(1)}—{familyConfirmation.periodIqrYears[1].toFixed(1)}年）</dd></div>}
                    {familyAblationPhase && <div><dt>逐家族剔除·相位稳定</dt><dd>{(familyAblationPhase.phaseAgreement * 100).toFixed(0)}%</dd></div>}
                    {familyAblationPhase && <div><dt>逐家族剔除·斜率稳定</dt><dd>{(familyAblationPhase.slopeAgreement * 100).toFixed(0)}%</dd></div>}
                    {governedBroadState && <div><dt>稳健宽状态</dt><dd>{governedBroadState.label}</dd></div>}
                    {governedBroadState && <div><dt>高低位稳定率</dt><dd>{(governedBroadState.levelAgreement * 100).toFixed(0)}%</dd></div>}
                    {governedBroadState && <div><dt>动量稳定率</dt><dd>{(governedBroadState.momentumAgreement * 100).toFixed(0)}%</dd></div>}
                    <div><dt>候选置信度</dt><dd>{(currentPhaseCandidate.current.confidence * 100).toFixed(0)}%</dd></div>
                    <div><dt>单一规格候选</dt><dd>{currentAdaptivePeriod.toFixed(1)}年 · 不发布为精确值</dd></div>
                    <div><dt>多规格稳健范围</dt><dd>{currentAdaptivePeriodRange?.[0].toFixed(1)}—{currentAdaptivePeriodRange?.[1].toFixed(1)}年</dd></div>
                    {periodRobustness && <div><dt>规格斜率同向</dt><dd>{(periodRobustness.slopeDirectionAgreement * 100).toFixed(0)}%</dd></div>}
                    {periodRobustness && <div><dt>未触边规格</dt><dd>{(periodRobustness.boundaryFreeShare * 100).toFixed(0)}%</dd></div>}
                    <div><dt>参数相位一致率</dt><dd>{(currentPhaseCandidate.current.phaseAgreement * 100).toFixed(0)}%</dd></div>
                    <div><dt>搜索边界占比</dt><dd>{(currentPhaseCandidate.current.periodBoundaryShare * 100).toFixed(0)}%</dd></div>
                    {expandedPeriodDiagnostic && <div><dt>扩围周期诊断</dt><dd>{expandedPeriodDiagnostic.candidateYears.toFixed(1)}年（{expandedPeriodDiagnostic.candidateRangeYears[0].toFixed(1)}—{expandedPeriodDiagnostic.candidateRangeYears[1].toFixed(1)}年）</dd></div>}
                    <div><dt>周期发布结论</dt><dd>{currentPhaseCandidate.periodIdentification.conclusion}</dd></div>
                    {structuralPosition?.channels?.map((channel: any) => <div key={channel.channelId}><dt>{channel.label} · {structuralPosition.asOfYear}</dt><dd>{channel.value >= 0 ? '+' : ''}{channel.value.toFixed(2)}σ · {channel.state}</dd></div>)}
                  </> : <>
                    <div><dt>因果追加稳定率</dt><dd>{(phaseCandidate.validation.meanHistoryAgreement * 100).toFixed(1)}%</dd></div>
                    <div><dt>峰谷间隔中位数</dt><dd>{phaseCandidate.validation.turnIntervalMedianYears.toFixed(1)}年</dd></div>
                    <div><dt>动态周期中位数</dt><dd>{phaseCandidate.validation.dynamicPeriodMedianYears.toFixed(1)}年</dd></div>
                    <div><dt>动态周期四分位</dt><dd>{phaseCandidate.validation.dynamicPeriodIqrYears[0].toFixed(1)}—{phaseCandidate.validation.dynamicPeriodIqrYears[1].toFixed(1)}年</dd></div>
                    <div><dt>相位持续中位数</dt><dd>{phaseCandidate.validation.medianPhaseRunYears.toFixed(1)}年</dd></div>
                      <div><dt>是否使用未来数据</dt><dd>{phaseCandidate.validation.lookAhead ? '是' : '否'}</dd></div>
                    </>}
                  </dl>
                  <p>{currentPhaseCandidate?.caveat ?? phaseCandidate.caveat}</p>
                </div>
              )}
              <div className="model-rebuild-card">
                <span>{['C2', 'C3', 'C5', 'C7'].includes(cycle.id) ? '当前已采用模型' : '建议重构模型'}</span>
                <strong>{diagnostic.modelRebuild.recommended}</strong>
                <p>{diagnostic.modelRebuild.why}</p>
                <div><b>状态定义</b>{diagnostic.modelRebuild.state}</div>
                <div><b>验证方法</b>{diagnostic.modelRebuild.validation}</div>
              </div>
              <div className="unlock-list">
                <span>解锁正式发布的条件</span>
                {diagnostic.unlockConditions.map((item: string) => <div key={item}>{item}</div>)}
              </div>
            </>
          )}
        </aside>
      </section>
      {!['C1', 'C2'].includes(cycle.id) && (
        <details className="cycle-secondary-research">
          <summary><span>指标贡献与稳健性</span><small>展开查看滤波贡献、实时稳定性和方法诊断</small><ChevronDown size={16} /></summary>
          <IndicatorContributionStudy cycleId={cycle.id} study={data.indicatorContributionStudy} />
        </details>
      )}
      {cycle.id === 'C4' && <CycleForecastExtension />}
    </div>
  )
}
