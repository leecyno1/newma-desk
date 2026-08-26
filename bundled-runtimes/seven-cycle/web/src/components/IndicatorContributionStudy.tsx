import { Activity, AlertTriangle, ArrowDownRight, ArrowUpRight } from 'lucide-react'
import { useState } from 'react'
import type { IndicatorContributionRow, IndicatorContributionStudy as Study } from '../types'

type RankingMode = 'influence' | 'positive' | 'negative'

function percent(value: number | null | undefined, digits = 0) {
  if (value == null || !Number.isFinite(value)) return '—'
  return `${(value * 100).toFixed(digits)}%`
}

function sigma(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return '—'
  return `${value >= 0 ? '+' : ''}${value.toFixed(3)}σ`
}

function decimal(value: number | null | undefined, digits = 2) {
  if (value == null || !Number.isFinite(value)) return '—'
  return value.toFixed(digits)
}

function familyLevelLabel(value: string | null | undefined) {
  return value === 'category' ? '同类别' : value === 'group' ? '同组别' : value === 'global' ? '全局' : '无共享池'
}

export default function IndicatorContributionStudy({ cycleId, study }: { cycleId: string; study: Study }) {
  const [mode, setMode] = useState<RankingMode>('influence')
  const usesLongHistory = ['C1', 'C2', 'C3'].includes(cycleId) && Boolean(study.longHistory)
  const source = usesLongHistory ? study.longHistory : null
  const cycle = source?.cycles[cycleId] ?? study.cycles[cycleId]
  const realtimeCycle = study.cycles[cycleId]
  const showsLongHistoryRealtimeChallenger = usesLongHistory && Boolean(realtimeCycle?.realtimeEligibleTracks)
  const gainCalibration = (source?.crossFilterGainCalibration ?? study.crossFilterGainCalibration)?.cycles[cycleId]
  const universeCount = source?.trackCount ?? 104
  const frequencyLabel = usesLongHistory ? `年频长历史 · 截至 ${source?.asOf}` : '月频市场与经济轨道'
  const slopeLabel = usesLongHistory ? '3年变化' : '3月变化'
  const stabilityLabel = '端点严格稳定'
  if (!cycle || cycle.status !== 'retrospective_diagnostic') {
    return (
      <section className="indicator-contribution-study unavailable">
        <div><AlertTriangle size={18} /><span>周期—指标频带贡献</span></div>
        <strong>{cycle?.reason ?? '当前周期没有满足历史长度要求的指标贡献结果。'}</strong>
        <p>{study.definition}。本模块拒绝用不足三轮的历史强行计算贡献。</p>
      </section>
    )
  }
  const rows: IndicatorContributionRow[] = mode === 'positive'
    ? cycle.topPositive ?? []
    : mode === 'negative'
      ? cycle.topNegative ?? []
      : cycle.topInfluence ?? []
  return (
    <section className="indicator-contribution-study">
      <div className="indicator-contribution-heading">
        <div>
          <span><Activity size={15} />{cycleId} 对周期指标的当前频带影响 · {frequencyLabel}</span>
          <h2>从“滤波分量”升级为可加总贡献</h2>
          <p>{study.definition}。影响为回溯频带分解，不是经济因果归因。</p>
        </div>
        <div className="segmented small">
          <button className={mode === 'influence' ? 'active' : ''} onClick={() => setMode('influence')}>影响最大</button>
          <button className={mode === 'positive' ? 'active' : ''} onClick={() => setMode('positive')}>正向</button>
          <button className={mode === 'negative' ? 'active' : ''} onClick={() => setMode('negative')}>负向</button>
        </div>
      </div>
      <div className="indicator-contribution-summary">
        <div><span>满足三轮历史</span><strong>{cycle.eligibleTracks}</strong><small>共{universeCount}条轨道</small></div>
        <div><span>模型质量通过</span><strong>{cycle.modelStableTracks ?? 0}</strong><small>两套Ridge同时通过</small></div>
        <div><span>历史路径通过</span><strong>{cycle.pathStableTracks}</strong><small>相关不低于0.70</small></div>
        <div><span>当前方向一致</span><strong>{cycle.directionAgreementTracks}</strong><small>两套滤波复核</small></div>
        <div><span>点幅度通过</span><strong>{cycle.pointAmplitudeStableTracks ?? 0}</strong><small>相对差不高于75%</small></div>
        <div><span>周期占比通过</span><strong>{cycle.absoluteShareStableTracks ?? 0}</strong><small>绝对占比差不高于15%</small></div>
        <div><span>解释方差通过</span><strong>{cycle.varianceShareStableTracks ?? 0}</strong><small>Shapley差不高于15%</small></div>
        <div><span>{stabilityLabel}</span><strong>{cycle.stableTracks}</strong><small>{usesLongHistory ? '含预处理复核' : '方向+幅度+模型'}</small></div>
        <div><span>当前正 / 负向</span><strong>{cycle.positiveTracks} / {cycle.negativeTracks}</strong><small>按频带点贡献</small></div>
        <div><span>近120期解释方差中位</span><strong>{percent(cycle.medianVarianceShare120)}</strong><small>Shapley分配</small></div>
        <div><span>滤波路径相关中位</span><strong>{decimal(cycle.medianFilterPathCorrelation)}</strong><small>剔除两端后</small></div>
      </div>
      {gainCalibration && (
        <div className={`gain-calibration-strip ${gainCalibration.status}`}>
          <div>
            <span>跨滤波固定增益挑战者</span>
            <strong>{gainCalibration.status === 'adopted' ? '样本外采用' : gainCalibration.status === 'rejected' ? '样本外拒绝' : '样本不足'}</strong>
          </div>
          <div><span>训练增益</span><strong>{decimal(gainCalibration.gain, 3)}</strong></div>
          <div><span>验证段误差改善</span><strong>{percent(gainCalibration.validationRelativeImprovement, 1)}</strong><small>{percent(gainCalibration.validationImprovedTrackShare)}轨道改善</small></div>
          <div><span>独立审计段改善</span><strong>{percent(gainCalibration.auditRelativeImprovement, 1)}</strong><small>{percent(gainCalibration.auditImprovedTrackShare)}轨道改善</small></div>
          <p>{gainCalibration.status === 'adopted' ? '只校准对照滤波的可比尺度；主贡献路径、方向和解释方差不变。' : gainCalibration.reason ?? '统一倍率未同时达到验证、审计与跨轨道改善门槛，正式结果保持未校准。'}</p>
        </div>
      )}
      {showsLongHistoryRealtimeChallenger && (
        <div className="long-history-realtime-challenger">
          <div className="long-history-realtime-challenger-heading">
            <div>
              <span>月频端点挑战者 · 与年频长历史分开审阅</span>
              <strong>{cycleId} 联合重构证据</strong>
            </div>
            <small>轨道级晋级不等于单周期规律成立，也不解除正式相位阻断</small>
          </div>
          <div className="long-history-realtime-challenger-grid">
            <div><span>月频端点确认</span><strong>{realtimeCycle.realtimeConfirmedTracks ?? 0} / {realtimeCycle.realtimeEligibleTracks ?? 0}</strong><small>仅使用当期及过去数据</small></div>
            <div><span>动态因子轨道级晋级</span><strong>{realtimeCycle.realtimeDynamicFactorAdoptedTracks ?? 0} / {realtimeCycle.realtimeDynamicFactorEligibleTracks ?? 0}</strong><small>留一同业指标联合因子</small></div>
            <div><span>动态因子正 R² 增益</span><strong>{realtimeCycle.realtimeDynamicFactorPositiveR2Tracks ?? 0} / {realtimeCycle.realtimeDynamicFactorEligibleTracks ?? 0}</strong><small>正增益仍可能未达晋级门槛</small></div>
            <div><span>动态因子 R² 增量中位</span><strong>{percent(realtimeCycle.medianRealtimeDynamicFactorR2Improvement, 1)}</strong><small>中位为负表示改善不具横截面普遍性</small></div>
            <div><span>因果近邻轨道级晋级</span><strong>{realtimeCycle.realtimeNearestFactorAdoptedTracks ?? 0} / {realtimeCycle.realtimeNearestFactorEligibleTracks ?? 0}</strong><small>仅选滞后相关最高的3条同业轨道</small></div>
            <div><span>因果近邻正 R² 增益</span><strong>{realtimeCycle.realtimeNearestFactorPositiveR2Tracks ?? 0} / {realtimeCycle.realtimeNearestFactorEligibleTracks ?? 0}</strong><small>仍需同时通过MAE与方向门槛</small></div>
            <div><span>因果近邻 R² 增量中位</span><strong>{percent(realtimeCycle.medianRealtimeNearestFactorR2Improvement, 1)}</strong><small>横截面稳健统计，不使用R²均值</small></div>
            <div><span>固定规格结论一致</span><strong>{realtimeCycle.realtimeNearestFactorSpecificationStableTracks ?? 0} / {realtimeCycle.realtimeNearestFactorEligibleTracks ?? 0}</strong><small>3邻居、5邻居与长窗口同意采用或拒绝</small></div>
            <div><span>早 / 晚 vintage 正增益</span><strong>{realtimeCycle.realtimeNearestFactorPositiveEarlyVintageTracks ?? 0}/{realtimeCycle.realtimeNearestFactorEligibleTracks ?? 0} · {realtimeCycle.realtimeNearestFactorPositiveLateVintageTracks ?? 0}/{realtimeCycle.realtimeNearestFactorEligibleTracks ?? 0}</strong><small>同一主规格按滚动截点前后半段复核</small></div>
            <div><span>早 / 晚 R² 增量中位</span><strong>{percent(realtimeCycle.medianRealtimeNearestFactorEarlyVintageR2Improvement, 1)} / {percent(realtimeCycle.medianRealtimeNearestFactorLateVintageR2Improvement, 1)}</strong><small>前负后正表示改善集中在近期，不能视为长期稳定</small></div>
            <div><span>低目标方差警告</span><strong>{realtimeCycle.realtimeLowTargetVarianceWarningTracks ?? 0}</strong><small>此类轨道的 R² 不用于晋级判断</small></div>
            <div><span>滚动重构 R² 中位</span><strong>{percent(realtimeCycle.medianRealtimeRollingReconstructionR2)}</strong><small>截点外重构当前观测</small></div>
          </div>
          <p>该挑战者允许同类指标共同修正月频端点状态。主规格固定使用3个近邻，5近邻和长相关窗口只做稳定性审计；规格分歧会扩大不确定性，低目标方差时禁用R²晋级。局部改善仍不能独立证明 {cycleId} 的周期相位可稳定识别或预测。</p>
        </div>
      )}
      {!usesLongHistory && (
        <div className="realtime-contribution-summary">
          <div>
            <span>因果端点确认</span>
            <strong>{cycle.realtimeConfirmedTracks ?? 0} / {cycle.realtimeEligibleTracks ?? 0}</strong>
            <small>状态空间仅使用当期及过去数据</small>
          </div>
          <div><span>实时正 / 负向</span><strong>{cycle.realtimePositiveTracks ?? 0} / {cycle.realtimeNegativeTracks ?? 0}</strong><small>不与双边端点强行合并</small></div>
          <div><span>滚动方向一致中位</span><strong>{percent(cycle.medianRealtimeRollingDirectionAgreement)}</strong><small>最多12个历史截点逐次重训</small></div>
          <div><span>滚动贡献相关中位</span><strong>{decimal(cycle.medianRealtimeRollingContributionCorrelation)}</strong><small>相对最终回溯路径</small></div>
          <div><span>滚动重构 R² 中位</span><strong>{percent(cycle.medianRealtimeRollingReconstructionR2)}</strong><small>截点外预测当前观测</small></div>
          <div><span>滚动系数同号中位</span><strong>{percent(cycle.medianRealtimeCoefficientSignAgreement)}</strong><small>确认门槛不低于60%</small></div>
          <div><span>系数漂移误差占比</span><strong>{percent(cycle.medianRealtimeCoefficientUncertaintyShare)}</strong><small>系数漂移 / 总不确定性</small></div>
          <div><span>状态参数集同向中位</span><strong>{percent(cycle.medianRealtimeRollingStateSpecificationDirectionAgreement)}</strong><small>灵敏 / 基准 / 平滑三档</small></div>
          <div><span>状态参数集误差占比</span><strong>{percent(cycle.medianRealtimeStateSpecificationUncertaintyShare)}</strong><small>参数集差异 / 总不确定性</small></div>
          <div><span>动态参数权重中位</span><strong>灵 {percent(cycle.medianRealtimeStateSpecificationWeights?.responsive)} / 基 {percent(cycle.medianRealtimeStateSpecificationWeights?.baseline)} / 平 {percent(cycle.medianRealtimeStateSpecificationWeights?.smooth)}</strong><small>只使用当时之前的创新误差</small></div>
          <div><span>有效参数数中位</span><strong>{decimal(cycle.medianRealtimeStateSpecificationEffectiveCount)} / 3</strong><small>越低表示权重越集中</small></div>
          <div><span>动态权重优于等权</span><strong>{cycle.realtimeDynamicWeightImprovedTracks ?? 0} / {cycle.realtimeEligibleTracks ?? 0}</strong><small>同一滚动截点比较</small></div>
          <div><span>相对等权 R² 增量中位</span><strong>{percent(cycle.medianRealtimeDynamicWeightR2Improvement, 1)}</strong><small>不达正值则不证明动态加权更优</small></div>
          <div><span>家族共享晋级</span><strong>{cycle.realtimePeerSharedAdoptedTracks ?? 0} / {cycle.realtimePeerSharedEligibleTracks ?? 0}</strong><small>类别→组别→全局留一法挑战者</small></div>
          <div><span>家族共享正增益</span><strong>{cycle.realtimePeerSharedPositiveR2Tracks ?? 0} / {cycle.realtimePeerSharedEligibleTracks ?? 0}</strong><small>正增益不等于达到晋级门槛</small></div>
          <div><span>家族共享 R² 增量中位</span><strong>{percent(cycle.medianRealtimePeerSharedR2Improvement, 1)}</strong><small>至少提升1个百分点且MAE、方向不恶化才晋级</small></div>
          <div><span>动态因子轨道级晋级</span><strong>{cycle.realtimeDynamicFactorAdoptedTracks ?? 0} / {cycle.realtimeDynamicFactorEligibleTracks ?? 0}</strong><small>留一同业指标联合因子</small></div>
          <div><span>动态因子正增益</span><strong>{cycle.realtimeDynamicFactorPositiveR2Tracks ?? 0} / {cycle.realtimeDynamicFactorEligibleTracks ?? 0}</strong><small>正增益不等于达到晋级门槛</small></div>
          <div><span>动态因子 R² 增量中位</span><strong>{percent(cycle.medianRealtimeDynamicFactorR2Improvement, 1)}</strong><small>方向和MAE不得恶化</small></div>
          <div><span>因果正交晋级</span><strong>{cycle.realtimeCausalOrthogonalAdoptedTracks ?? 0} / {cycle.realtimeEligibleTracks ?? 0}</strong><small>长周期→短周期，仅使用滞后状态</small></div>
          <div><span>正交主 / 对照 R² 增量</span><strong>{percent(cycle.medianRealtimeOrthogonalPrimaryR2Improvement, 1)} / {percent(cycle.medianRealtimeOrthogonalComparisonR2Improvement, 1)}</strong><small>60期主规格与120期复核同时改善</small></div>
          <div><span>最大状态相关</span><strong>{decimal(cycle.medianRealtimeBaseMaximumCorrelation)} → {decimal(cycle.medianRealtimeOrthogonalMaximumCorrelation)}</strong><small>减少周期之间重复解释</small></div>
          <div><span>状态条件数</span><strong>{decimal(cycle.medianRealtimeBaseConditionNumber)} → {decimal(cycle.medianRealtimeOrthogonalConditionNumber)}</strong><small>越低表示频带越易区分</small></div>
          <div><span>绝对修订中位</span><strong>{sigma(cycle.medianRealtimeAbsoluteRevision)}</strong><small>因果贡献与双边贡献差</small></div>
          <div><span>信号 / 不确定性中位</span><strong>{decimal(cycle.medianRealtimeSignalToUncertainty)}</strong><small>确认门槛不低于0.50</small></div>
        </div>
      )}
      <div className="indicator-contribution-table-wrap">
        <table className="research-table indicator-contribution-table">
          <thead><tr><th>指标</th><th>类别</th><th>双边点贡献</th><th>周期内占比</th><th>近120期解释方差</th><th>{slopeLabel}</th><th>滤波复核</th>{!usesLongHistory && <th>因果端点</th>}<th>稳定性</th></tr></thead>
          <tbody>{rows.slice(0, 12).map((row) => (
            <tr key={`${mode}-${row.trackId}`}>
              <td><strong>{row.label}</strong><small>{row.date} · {row.group === 'market' ? '市场' : '经济'}</small></td>
              <td>{row.category}</td>
              <td className={row.pointContribution >= 0 ? 'positive' : 'negative'}>{row.pointContribution >= 0 ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}{sigma(row.pointContribution)}</td>
              <td>{percent(row.absoluteShare)}</td>
              <td>{percent(row.varianceShare120)}</td>
              <td className={(row.slope3 ?? 0) >= 0 ? 'positive' : 'negative'}>{sigma(row.slope3)}</td>
              <td><strong>{decimal(row.filterPathCorrelation)}</strong><small>{row.filterDirectionAgreement ? '当前同向' : '当前分歧'}</small></td>
              {!usesLongHistory && (
                <td className="realtime-contribution-cell">
                  <strong className={(row.realtimePointContribution ?? 0) >= 0 ? 'positive' : 'negative'}>{sigma(row.realtimePointContribution)}</strong>
                  <small>{row.realtimeStatus === 'limited_confirmed' ? '可确认' : '偏弱'} · 滚动同向 {percent(row.realtimeRollingDirectionAgreement)} · 系数 / 状态集同向 {percent(row.realtimeCoefficientSignAgreement)} / {percent(row.realtimeStateSpecificationDirectionAgreement)} · S/U {decimal(row.realtimeSignalToUncertainty)}</small>
                  <small>{row.realtimeStateWeightModel === 'causal_orthogonal' ? '因果正交' : row.realtimeStateWeightModel === 'nearest_factor' ? '因果近邻因子' : row.realtimeStateWeightModel === 'dynamic_factor' ? '动态同业因子' : row.realtimeStateWeightModel === 'peer_shared' ? '家族共享权重' : '单轨道权重'} · {familyLevelLabel(row.realtimePeerSharedFamilyLevel)} {row.realtimePeerSharedPeerCount ?? 0} 条</small>
                </td>
              )}
              <td><span className={`contribution-quality ${row.quality}`}>{row.quality === 'stable' ? '较稳定' : '偏弱'}</span></td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      <div className="indicator-contribution-caveat">{source?.method ?? study.method} 当前严格稳定数可能显著低于路径相关数，因为端点方向与幅度也必须同时达标。{!usesLongHistory && ' 因果端点确认是观测分解，不是下一期预测。'}{cycle.caveat}</div>
    </section>
  )
}
