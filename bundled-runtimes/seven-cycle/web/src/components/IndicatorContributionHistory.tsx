import { Activity, AlertTriangle } from 'lucide-react'
import { useMemo, useState } from 'react'
import type { MarketTrack } from '../types'
import PlotlyCanvas from './PlotlyCanvas'

type HistoryRange = '20y' | '50y' | 'all'

const cycleColors: Record<string, string> = {
  C1: '#7c8cff',
  C2: '#5c9dff',
  C3: '#39c5d8',
  C4: '#46d09a',
  C5: '#d5cf58',
  C6: '#f1aa4b',
  C7: '#ef6f77',
}

function inRange(date: string, range: HistoryRange, endYear: number) {
  if (range === 'all') return true
  const years = range === '20y' ? 20 : 50
  return Number(date.slice(0, 4)) >= endYear - years
}

function percent(value: number | null | undefined, digits = 0) {
  if (value == null || !Number.isFinite(value)) return '—'
  return `${(value * 100).toFixed(digits)}%`
}

function familyLevelLabel(value: string | null | undefined) {
  return value === 'category' ? '同类别' : value === 'group' ? '同组别' : value === 'global' ? '全局' : '无共享池'
}

export default function IndicatorContributionHistory({ track }: { track: MarketTrack }) {
  const [range, setRange] = useState<HistoryRange>('20y')
  const contribution = track.cycleContribution
  const chart = useMemo(() => {
    if (contribution.status !== 'retrospective_diagnostic' || !contribution.paths) return null
    const endYear = Number(track.dates.at(-1)?.slice(0, 4) ?? 0)
    const indices = track.dates
      .map((date, index) => ({ date, index }))
      .filter(({ date }) => inRange(date, range, endYear))
    const dates = indices.map(({ date }) => date)
    const topTraces = [
      {
        type: 'scatter', mode: 'lines', name: '标准化指标变化',
        x: dates, y: indices.map(({ index }) => track.standardized[index]),
        line: { color: '#dcecf7', width: 2.2 },
        hovertemplate: `${track.label}<br>%{x}<br>标准化变化 %{y:.3f}σ<extra></extra>`,
      },
      {
        type: 'scatter', mode: 'lines', name: '周期总贡献',
        x: dates, y: indices.map(({ index }) => contribution.paths?.cycleTotal[index]),
        line: { color: '#35c6e8', width: 2 },
        hovertemplate: '周期总贡献<br>%{x}<br>%{y:.3f}σ<extra></extra>',
      },
      {
        type: 'scatter', mode: 'lines', name: '未解释残差',
        x: dates, y: indices.map(({ index }) => contribution.paths?.residual[index]),
        line: { color: '#788da1', width: 1.2, dash: 'dot' },
        hovertemplate: '未解释残差<br>%{x}<br>%{y:.3f}σ<extra></extra>',
      },
      {
        type: 'scatter', mode: 'lines', name: '重构基线',
        x: dates, y: dates.map(() => contribution.paths?.baseline),
        line: { color: '#f1aa4b', width: 1, dash: 'dash' },
        hovertemplate: '重构基线<br>%{y:.3f}σ<extra></extra>',
      },
    ]
    const cycleTraces = Object.entries(contribution.paths.components).map(([cycleId, values]) => {
      const robustness = contribution.current?.components[cycleId]?.filterRobustness
      const pathStable = (robustness?.pathCorrelation ?? -1) >= 0.70
      const endpointDirectionStable = robustness?.directionAgreement === true
      return {
        type: 'scatter',
        mode: 'lines',
        name: `${cycleId} 贡献`,
        x: dates,
        y: indices.map(({ index }) => values[index]),
        xaxis: 'x2',
        yaxis: 'y2',
        line: {
          color: cycleColors[cycleId] ?? '#89a6ba',
          width: pathStable ? 2 : 1.1,
          dash: endpointDirectionStable ? 'solid' : 'dot',
        },
        opacity: pathStable ? 1 : 0.62,
        hovertemplate: `${cycleId} 频带贡献<br>%{x}<br>%{y:.3f}σ<br>路径相关 ${robustness?.pathCorrelation?.toFixed(2) ?? '—'}<extra></extra>`,
      }
    })
    return {
      data: [...topTraces, ...cycleTraces],
      layout: {
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        margin: { l: 54, r: 18, t: 18, b: 42 },
        hovermode: 'x unified',
        legend: { orientation: 'h', y: 1.03, font: { size: 9 } },
        xaxis: { domain: [0, 1], anchor: 'y', showticklabels: false, gridcolor: '#1d3146' },
        yaxis: { domain: [0.57, 1], title: '指标 / 重构（σ）', gridcolor: '#1d3146', zerolinecolor: '#668099' },
        xaxis2: { domain: [0, 1], anchor: 'y2', title: '时间', gridcolor: '#1d3146' },
        yaxis2: { domain: [0, 0.43], title: '单周期贡献（σ）', gridcolor: '#1d3146', zerolinecolor: '#668099' },
        uirevision: `indicator-contribution-${track.id}-${range}`,
      },
    }
  }, [contribution, range, track])

  if (!chart || contribution.status !== 'retrospective_diagnostic') {
    return (
      <section className="indicator-contribution-history unavailable">
        <AlertTriangle size={17} />
        <div><strong>{track.label} 暂无可复核贡献路径</strong><span>历史长度或双滤波计算未满足最低要求。</span></div>
      </section>
    )
  }

  const stableCycles = contribution.filterRobustness?.stableCycles ?? 0
  const comparableCycles = contribution.filterRobustness?.comparableCycles ?? 0
  const realtime = contribution.realtimeConfirmation
  const realtimeComponents = Object.entries(realtime?.current?.components ?? {})
  const peerStatusLabel = realtime?.training?.peerSharedStatus === 'adopted'
    ? '家族共享已晋级'
    : realtime?.training?.peerSharedStatus === 'rejected'
      ? '家族共享未晋级'
      : '家族共享不可用'
  const orthogonalStatusLabel = realtime?.training?.causalOrthogonalStatus === 'adopted'
    ? '因果正交已晋级'
    : '因果正交未晋级'
  return (
    <section className="indicator-contribution-history">
      <div className="indicator-history-heading">
        <div>
          <span><Activity size={15} />周期贡献历史路径 · {track.category}</span>
          <h2>{track.label}</h2>
          <p>上层检查逐点守恒，下层比较各周期贡献路径；粗线表示历史路径通过，点线表示最新端点方向分歧。</p>
        </div>
        <div className="segmented small">
          {(['20y', '50y', 'all'] as HistoryRange[]).map((item) => (
            <button key={item} className={range === item ? 'active' : ''} onClick={() => setRange(item)}>
              {item === '20y' ? '20年' : item === '50y' ? '50年' : '全历史'}
            </button>
          ))}
        </div>
      </div>
      <div className="indicator-history-metrics">
        <div><span>可比较周期</span><strong>{comparableCycles}</strong></div>
        <div><span>严格稳定周期</span><strong>{stableCycles}</strong></div>
        <div><span>样本内重构 R²</span><strong>{percent(contribution.diagnostics?.reconstructionR2)}</strong></div>
        <div><span>时间分块 R²</span><strong>{percent(contribution.diagnostics?.holdoutReconstructionR2)}</strong></div>
        <div><span>近120期残差方差</span><strong>{percent(contribution.diagnostics?.residualVarianceShare120)}</strong></div>
      </div>
      <PlotlyCanvas data={chart.data} layout={chart.layout} className="indicator-contribution-history-chart" />
      {realtime?.status === 'causal_realtime_confirmation' && (
        <div className="realtime-confirmation-panel">
          <div className="realtime-confirmation-heading">
            <div><span>不使用未来数据的端点确认</span><strong>{realtime.summary?.confirmedCycles ?? 0} / {realtime.summary?.comparableCycles ?? 0} 个周期通过</strong></div>
            <small>{realtime.training?.originCount ?? 0} 个滚动截点 · {realtime.training?.originStart}—{realtime.training?.originEnd} · 当前 R² {percent(realtime.training?.rollingReconstructionR2)} · 等权 R² {percent(realtime.training?.equalMedianRollingReconstructionR2)} · {orthogonalStatusLabel} · 主 / 对照增量 {percent(realtime.training?.orthogonalPrimaryRollingR2Improvement, 1)} / {percent(realtime.training?.orthogonalComparisonRollingR2Improvement, 1)} · {peerStatusLabel}</small>
          </div>
          <div className="realtime-confirmation-grid">
            {realtimeComponents.map(([cycleId, component]) => (
              <div key={cycleId} className={component.status === 'limited_confirmed' ? 'confirmed' : 'weak'}>
                <span>{cycleId}</span>
                <strong className={component.pointContribution >= 0 ? 'positive' : 'negative'}>{component.pointContribution >= 0 ? '+' : ''}{component.pointContribution.toFixed(3)}σ</strong>
                <small>滚动同向 {percent(component.rollingDirectionAgreement)} · 相关 {component.rollingContributionCorrelation?.toFixed(2) ?? '—'}</small>
                <small>系数同号 {percent(component.coefficientSignAgreement)} · 系数漂移占 {percent(component.coefficientUncertaintyShare)}</small>
                <small>状态参数集 当前 / 滚动同向 {percent(component.stateSpecificationDirectionAgreement)} / {percent(component.rollingStateSpecificationDirectionAgreement)}</small>
                <small>最新权重 灵 {percent(component.stateSpecificationWeights?.responsive)} / 基 {percent(component.stateSpecificationWeights?.baseline)} / 平 {percent(component.stateSpecificationWeights?.smooth)} · 有效数 {component.stateSpecificationEffectiveCount?.toFixed(2) ?? '—'}</small>
                <small>权重模型 {component.stateWeightModel === 'causal_orthogonal' ? '因果正交' : component.stateWeightModel === 'peer_shared' ? '家族共享' : '单轨道'} · {familyLevelLabel(component.peerSharedFamilyLevel)} {component.peerSharedFamilyKey ?? ''} · 可比轨道 {component.peerSharedPeerCount ?? 0} 条 · 收缩 {percent(component.peerSharedEvidenceWeight)}</small>
                <small>状态误差 {component.stateUncertainty?.toFixed(3) ?? '—'}σ · 系数漂移 {component.coefficientUncertainty?.toFixed(3) ?? '—'}σ · 参数集差异 {component.stateSpecificationUncertainty?.toFixed(3) ?? '—'}σ · 正交模型 / 跨度 {component.orthogonalizationUncertainty?.toFixed(3) ?? '—'} / {component.orthogonalizationSpanUncertainty?.toFixed(3) ?? '—'}σ</small>
                <small>正交跨度 当前同向 {component.orthogonalSpanEndpointDirectionAgreement ? '是' : '否'} · 滚动同向 {percent(component.orthogonalSpanRollingDirectionAgreement)} · 相关 {component.orthogonalSpanRollingCorrelation?.toFixed(2) ?? '—'}</small>
                <small>修订中位 {component.medianAbsoluteRevision?.toFixed(3) ?? '—'}σ · 合并 S/U {component.signalToUncertainty.toFixed(2)}</small>
                <small>{component.endpointDirectionAgreement ? '与双边端点同向' : '与双边端点分歧'} · 当前模型训练至 {realtime.training?.latestTrainEnd}</small>
                <em>{component.status === 'limited_confirmed' ? '可确认' : '偏弱'}</em>
              </div>
            ))}
          </div>
          <p>{realtime.caveat}</p>
        </div>
      )}
      <div className="indicator-history-caveat">{contribution.caveat} 当前端点不通过，不代表历史中段没有稳定频带，只表示不应把最新点包装成确定结论。</div>
    </section>
  )
}
