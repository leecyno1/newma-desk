import { ArrowDownUp, ChevronDown, ChevronRight, ChevronsDownUp, FlaskConical, Search, X } from 'lucide-react'
import { Fragment, useMemo, useState } from 'react'
import PlotlyCanvas from './PlotlyCanvas'

const phases = ['recovery', 'expansion', 'slowdown', 'contraction'] as const
const chartColors = ['#58c9ed', '#f1aa4b', '#69ce9f', '#9b83ef', '#ef6d7c', '#7195ff']

function percent(value: number | null | undefined, digits = 1) {
  if (value == null || !Number.isFinite(value)) return '—'
  return `${(value * 100).toFixed(digits)}%`
}

function number(value: number | null | undefined, digits = 3) {
  if (value == null || !Number.isFinite(value)) return '—'
  return value.toFixed(digits)
}

function average(values: Array<number | null | undefined>) {
  const valid = values.filter((value): value is number => value != null && Number.isFinite(value))
  return valid.length ? valid.reduce((sum, value) => sum + value, 0) / valid.length : null
}

export default function ResearchAssetMapping({ cycleId, mapping, currentDirection, assetValidation, jointMapping, phaseLabels }: { cycleId: string; mapping: any; currentDirection?: any; assetValidation?: any; jointMapping?: any; phaseLabels: Record<string, string> }) {
  const isStateAssociation = mapping.kind === 'state_association'
  const stateAssetValidation = isStateAssociation ? mapping.assetValidation : null
  const legacyMappingAudit = mapping.status === 'legacy_mapping_rebuild_required'
  const display = mapping.display ?? {
    sampleLabel: '年度样本', observationUnit: '年', returnLabel: '年度实际收益', volatilityLabel: '年度波动',
    sectionTitle: '长样本资产收益—风险表现', description: '相位因子已剔除资产收益家族；JST直接历史序列与Ken French研究组合均显示数据身份。',
  }
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('全部')
  const [confidence, setConfidence] = useState('全部')
  const [sortKey, setSortKey] = useState<'spread' | 'oos' | 'name'>('oos')
  const [phase, setPhase] = useState<(typeof phases)[number]>('recovery')
  const [selected, setSelected] = useState<any | null>(null)
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(() => new Set())

  const eligibleAssets = useMemo(() => mapping.assets.filter((asset: any) => asset.eligible), [mapping])
  const categories = useMemo(() => ['全部', ...Array.from(new Set(eligibleAssets.map((asset: any) => asset.category))) as string[]], [eligibleAssets])
  const rows = useMemo(() => {
    const normalized = query.trim().toLowerCase()
    return eligibleAssets
      .filter((asset: any) => category === '全部' || asset.category === category)
      .filter((asset: any) => confidence === '全部' || asset.confidence === confidence)
      .filter((asset: any) => !normalized || `${asset.name} ${asset.category}`.toLowerCase().includes(normalized))
      .sort((left: any, right: any) => {
        if (sortKey === 'name') return left.name.localeCompare(right.name, 'zh-CN')
        if (sortKey === 'oos') return (right.oosR2 ?? -Infinity) - (left.oosR2 ?? -Infinity)
        return (right.phaseSpread ?? -Infinity) - (left.phaseSpread ?? -Infinity)
      })
  }, [category, confidence, eligibleAssets, query, sortKey])
  const groupedRows = useMemo(() => {
    const groups = new Map<string, any[]>()
    rows.forEach((asset: any) => groups.set(asset.category, [...(groups.get(asset.category) ?? []), asset]))
    return Array.from(groups, ([name, assets]) => ({ name, assets })).sort((left, right) => {
      if (sortKey === 'name') return left.name.localeCompare(right.name, 'zh-CN')
      if (sortKey === 'oos') return (average(right.assets.map((asset) => asset.oosR2)) ?? -Infinity) - (average(left.assets.map((asset) => asset.oosR2)) ?? -Infinity)
      return (average(right.assets.map((asset) => asset.phaseSpread)) ?? -Infinity) - (average(left.assets.map((asset) => asset.phaseSpread)) ?? -Infinity)
    })
  }, [rows, sortKey])

  const chart = useMemo(() => {
    const chartCategories = Array.from(new Set(rows.map((asset: any) => asset.category)))
    return {
      data: chartCategories.map((item, categoryIndex) => {
        const assets = rows.filter((asset: any) => asset.category === item && asset.phaseStats?.[phase])
        return {
          type: 'scatter', mode: 'markers', name: item,
          x: assets.map((asset: any) => asset.phaseStats[phase].annVol),
          y: assets.map((asset: any) => asset.phaseStats[phase].annReturn),
          text: assets.map((asset: any) => asset.name),
          customdata: assets.map((asset: any) => [asset.assetId]),
          marker: { size: assets.map((asset: any) => asset.confidence === 'high' ? 11 : asset.confidence === 'medium' ? 8 : 6), color: chartColors[categoryIndex % chartColors.length], opacity: .8, line: { color: '#08111f', width: 1 } },
          hovertemplate: `%{text}<br>${display.returnLabel} %{y:.1%}<br>${display.volatilityLabel} %{x:.1%}<extra></extra>`,
        }
      }),
      layout: {
        paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)', margin: { l: 58, r: 18, t: 12, b: 48 },
        font: { color: '#c9d7e5', family: 'Inter, PingFang SC, sans-serif', size: 10 },
        xaxis: { title: display.volatilityLabel, tickformat: '.0%', gridcolor: '#1d3146' },
        yaxis: { title: display.returnLabel, tickformat: '.0%', gridcolor: '#1d3146', zerolinecolor: '#657c91' },
        legend: { orientation: 'h', y: 1.13, font: { size: 9 } }, hovermode: 'closest',
      },
    }
  }, [display.returnLabel, display.volatilityLabel, phase, rows])

  const leaders = useMemo(() => rows
    .filter((asset: any) => asset.phaseStats?.[phase]?.annVol)
    .map((asset: any) => ({ asset, score: asset.phaseStats[phase].annReturn / Math.max(.01, asset.phaseStats[phase].annVol) }))
    .sort((left: any, right: any) => right.score - left.score)
    .slice(0, 5), [phase, rows])
  const searchExpanded = Boolean(query.trim())
  const allExpanded = groupedRows.length > 0 && groupedRows.every((group) => expandedCategories.has(group.name))
  const toggleCategory = (name: string) => setExpandedCategories((current) => {
    const next = new Set(current)
    if (next.has(name)) next.delete(name)
    else next.add(name)
    return next
  })
  const setAllCategories = (expanded: boolean) => setExpandedCategories(expanded ? new Set(groupedRows.map((group) => group.name)) : new Set())
  const oneYear = currentDirection?.currentForecasts?.find((item: any) => item.horizonYears === 1)
  const twoYear = currentDirection?.currentForecasts?.find((item: any) => item.horizonYears === 2)
  const threeYear = currentDirection?.currentForecasts?.find((item: any) => item.horizonYears === 3)
  const currentPhase = currentDirection?.currentPhaseCandidate?.current
  const currentBroadState = currentDirection?.currentPhaseCandidate?.governedBroadState
  const regimeState = currentDirection?.regimeState
  const exactPhasePublishable = currentDirection?.currentPhaseCandidate?.exactPhaseStatus === 'limited'
  const regimeFactor = regimeState?.activity ?? regimeState?.rawValue ?? oneYear?.currentFactor
  const regimeFactorNote = regimeState?.slopeConsensus != null
    ? `1/2/3年动量共识 ${number(regimeState.slopeConsensus, 2)}`
    : regimeState?.periodYears != null
      ? `动态周期 ${number(regimeState.periodYears, 1)}年 · 当前斜率 ${number(regimeState.slope, 2)}σ`
      : currentDirection?.partialNowcast?.coverageLabel ?? `${oneYear?.latestYearCountryCount ?? oneYear?.countryCount}/${oneYear?.countryCount} 国最新`
  const currentScenario = mapping.currentProbabilityWeightedScenario
  const forwardValidation = mapping.summary.forwardValidation
  const geographicValidation = mapping.geographicValidation
  const interactionValidation = mapping.interactionValidation
  const countryClockMapping = jointMapping?.countryClockMapping
  const hierarchicalRisk = jointMapping?.hierarchicalRiskValidation
  const assetClassValidation = hierarchicalRisk?.assetClassValidation
  const conditionalPropagation = hierarchicalRisk?.conditionalPropagationValidation
  const historicalRiskChannels = hierarchicalRisk?.historicalRiskChannels ?? []
  const countryPhaseAssetRows = countryClockMapping?.focusCountries.flatMap((country: any) =>
    country.currentPhaseAssets.map((asset: any) => ({ ...asset, country: country.name, asOfPeriod: country.asOfPeriod })),
  ) ?? []
  const scenarioAssets = useMemo(() => {
    if (!currentScenario) return []
    const visible = new Set(rows.map((asset: any) => asset.assetId))
    return currentScenario.assets.filter((asset: any) => visible.has(asset.assetId) && (currentScenario.riskForecastStatus !== 'limited' || asset.riskValidationEligible))
  }, [currentScenario, rows])
  const scenarioChart = useMemo(() => {
    if (!currentScenario) return null
    const governedRisk = currentScenario.riskForecastStatus === 'limited'
    const chartCategories = Array.from(new Set(scenarioAssets.map((asset: any) => asset.category)))
    return {
      data: chartCategories.map((item, categoryIndex) => {
        const assets = scenarioAssets.filter((asset: any) => asset.category === item)
        return {
          type: 'scatter', mode: 'markers', name: item,
          x: assets.map((asset: any) => governedRisk ? asset.governedRiskScale : asset.conditionalAnnVol),
          y: assets.map((asset: any) => asset.expectedAnnReturn),
          text: assets.map((asset: any) => asset.name),
          customdata: assets.map((asset: any) => [asset.assetId, asset.quantile20Return, asset.expectedShortfall20, asset.positiveRate, asset.riskScaleShiftVsUnconditional]),
          marker: { size: assets.map((asset: any) => asset.confidence === 'high' ? 11 : asset.confidence === 'medium' ? 8 : 6), color: chartColors[categoryIndex % chartColors.length], opacity: .82, line: { color: '#08111f', width: 1 } },
          hovertemplate: `%{text}<br>概率加权收益 %{y:.1%}<br>${governedRisk ? '治理风险尺度' : '条件历史波动'} %{x:.1%}<br>风险变化 %{customdata[4]:+.1%}<br>20%分位 %{customdata[1]:.1%}<br>尾部20%均值 %{customdata[2]:.1%}<br>正收益率 %{customdata[3]:.0%}<extra></extra>`,
        }
      }),
      layout: {
        paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)', margin: { l: 58, r: 18, t: 12, b: 48 },
        font: { color: '#c9d7e5', family: 'Inter, PingFang SC, sans-serif', size: 10 },
        xaxis: { title: governedRisk ? '治理风险尺度（平方收益）' : '概率加权历史波动', tickformat: '.0%', gridcolor: '#1d3146' },
        yaxis: { title: '概率加权历史收益', tickformat: '.0%', gridcolor: '#1d3146', zerolinecolor: '#657c91' },
        legend: { orientation: 'h', y: 1.13, font: { size: 9 } }, hovermode: 'closest',
      },
    }
  }, [currentScenario, scenarioAssets])
  const selectedScenario = currentScenario?.assets.find((asset: any) => asset.assetId === selected?.assetId)

  return (
    <>
      <section className="research-mapping-banner">
        <FlaskConical size={17} />
        <div><strong>{mapping.title ?? `${cycleId} 长样本资产映射候选`}</strong><span>{legacyMappingAudit ? mapping.caveat : `${mapping.summary.eligibleAssets} 条资产通过最低样本门槛；${mapping.summary.positiveOosR2} 条同期模型样本外 R² 为正${forwardValidation ? `，多资产 FDR 通过 ${mapping.summary.hacFdrPassed} 条。` : isStateAssociation ? `，${mapping.summary.qualifiedAssociations} 条同时满足显著性。` : '。'}`}</span></div>
        <span className={`status-badge ${legacyMappingAudit || forwardValidation?.status === 'failed' ? 'status-blocked' : 'status-research'}`}>{legacyMappingAudit ? '旧口径暂停' : forwardValidation?.status === 'failed' ? '仅历史统计' : '研究可用'}</span>
      </section>

      {mapping.currentState && (
        <section className="research-direction-strip">
          <div><span>当前状态</span><strong>{mapping.currentState.regime}</strong><small>{mapping.currentState.date} · 修订后序列</small></div>
          <div><span>状态水平</span><strong>{number(mapping.currentState.level, 2)}σ</strong><small>不是独立资产因果因子</small></div>
          <div><span>三个月斜率</span><strong>{number(mapping.currentState.slope3, 2)}σ</strong><small>方向变化速度</small></div>
          <div><span>{cycleId === 'C7' ? '状态正区间通过' : '状态方向通过'}</span><strong>{mapping.currentState.qualifiedDirectionHorizons?.join(' / ') || '无'}</strong><small>{cycleId === 'C7' ? '不是继续上行概率' : '仅状态自身方向'}</small></div>
          <div className="direction-governance"><span>资产预测状态</span><b>阻断</b><p>{mapping.caveat}</p></div>
        </section>
      )}

      {!mapping.currentState && currentDirection && oneYear && threeYear && (
        <section className="research-direction-strip research-direction-strip-three">
          <div><span>当前周期状态</span><strong>{regimeState ? phaseLabels[regimeState.phase] : currentBroadState?.label ?? (currentPhase ? phaseLabels[currentPhase.phase] : '未识别')}</strong><small>{oneYear.asOfPeriod} · {regimeState ? '直接四相位研究状态' : exactPhasePublishable ? '四相位研究可用' : '四相位阻断'}</small></div>
          <div><span>未来 1 年上行</span><strong>{percent(oneYear.probabilityUp, 0)}</strong><small>周期因子方向概率</small></div>
          <div><span>未来 2 年上行</span><strong>{percent(twoYear?.probabilityUp, 0)}</strong><small>周期因子方向概率</small></div>
          <div><span>未来 3 年上行</span><strong>{percent(threeYear.probabilityUp, 0)}</strong><small>周期因子方向概率</small></div>
          <div><span>当前周期因子</span><strong>{number(regimeFactor, 2)}σ</strong><small>{regimeFactorNote}</small></div>
          <div className="direction-governance"><span>资产预测状态</span><b>阻断</b><p>{exactPhasePublishable ? currentDirection.caveat : '当前只确认低位，动量分歧；四相位概率及当前资产收益风险图暂停。'}</p></div>
        </section>
      )}

      {forwardValidation && (
        <section className="asset-forward-validation">
          <div>
            <span>C2 前瞻资产验证</span>
            <strong>历史相位统计未转化为稳定的未来资产收益或风险预测</strong>
          </div>
          <div className="asset-forward-validation-grid">
            {([
              ['1yReturn', '未来1年收益'],
              ['3yReturn', '未来3年收益'],
              ['1yRisk', '未来1年风险'],
              ['3yRisk', '未来3年风险'],
            ] as const).map(([key, label]) => (
              <div key={key}>
                <small>{label}</small>
                <strong>{forwardValidation[key].positiveOosR2} / {forwardValidation[key].assets}</strong>
                <span>R²为正 · {percent(forwardValidation[key].positiveOosR2Share, 1)}</span>
                <em>中位R² {number(forwardValidation[key].medianOosR2)}</em>
              </div>
            ))}
          </div>
          <p>{forwardValidation.method} 当前四项均未通过，因此 C2 暂不能直接给出资产收益、波动或配置权重。</p>
        </section>
      )}

      {cycleId === 'C5' && stateAssetValidation?.cells && (
        <section className="asset-forward-validation c3-asset-validation">
          <div>
            <span>C5 大类资产增量验证</span>
            <strong>{stateAssetValidation.summary.passedChannels}/{stateAssetValidation.summary.totalChannels} 个收益风险通道通过，资产预测继续阻断</strong>
          </div>
          <div className="asset-forward-validation-grid c3-channel-grid">
            {stateAssetValidation.cells.map((cell: any) => {
              const returnValidation = cell.returnDirection
              const riskValidation = cell.volatility
              const passed = returnValidation.passed || riskValidation.passed
              return (
                <div className={passed ? 'is-passed' : 'is-failed'} key={`${cell.assetGroup}-${cell.horizonMonths}`}>
                  <small>{cell.assetGroup} · {cell.horizonMonths}个月</small>
                  <strong>{passed ? '有限通过' : '增量失败'}</strong>
                  <span>收益 AUC {number(returnValidation.augmented.auc)} · Δ {number(returnValidation.aucImprovement)}</span>
                  <em>收益 Brier 改善 {number(returnValidation.brierImprovement, 4)}</em>
                  <span>风险增量 R² {number(riskValidation.incrementalOosR2)}</span>
                  <small>风险 MAE 改善 {percent(riskValidation.maeImprovement, 1)}</small>
                </div>
              )
            })}
          </div>
          <p>{stateAssetValidation.method} 当前没有通道同时通过完整样本和近年门槛，因此不输出大类资产涨跌、风险预测或配置权重。</p>
        </section>
      )}

      {cycleId === 'C7' && stateAssetValidation?.cells && (
        <section className="asset-forward-validation c3-asset-validation">
          <div>
            <span>C7 大类资产增量验证</span>
            <strong>{stateAssetValidation.summary.passedChannels}/{stateAssetValidation.summary.totalChannels} 个收益风险通道通过，资产预测继续阻断</strong>
          </div>
          <div className="asset-forward-validation-grid c3-channel-grid">
            {stateAssetValidation.cells.map((cell: any) => {
              const returnValidation = cell.returnDirection
              const riskValidation = cell.volatility
              const passed = returnValidation.passed || riskValidation.passed
              return (
                <div className={passed ? 'is-passed' : 'is-failed'} key={`${cell.assetGroup}-${cell.horizonMonths}`}>
                  <small>{cell.assetGroup} · {cell.horizonMonths}个月</small>
                  <strong>{passed ? '有限通过' : '增量失败'}</strong>
                  <span>收益 AUC {number(returnValidation.augmented.auc)} · Δ {number(returnValidation.aucImprovement)}</span>
                  <em>收益 Brier 改善 {number(returnValidation.brierImprovement, 4)}</em>
                  <span>风险增量 R² {number(riskValidation.incrementalOosR2)}</span>
                  <small>{cell.riskTarget} · MAE 改善 {percent(riskValidation.maeImprovement, 1)}</small>
                </div>
              )
            })}
          </div>
          <p>{stateAssetValidation.method} {stateAssetValidation.caveat}</p>
        </section>
      )}

      {cycleId === 'C3' && assetValidation && (
        <section className="asset-forward-validation c3-asset-validation">
          <div>
            <span>C3 独立资产增量验证</span>
            <strong>{assetValidation.passedTargets}/{assetValidation.targetCount} 个收益风险通道通过，不能发布资产预测</strong>
          </div>
          <div className="asset-forward-validation-grid c3-channel-grid">
            {assetValidation.cells.map((cell: any) => {
              const weakestSubperiodDelta = Math.min(...cell.subperiods
                .map((period: any) => period.aucImprovement)
                .filter((value: number | null) => value != null))
              return (
                <div className={cell.passed ? 'is-passed' : 'is-failed'} key={`${cell.category}-${cell.horizonYears}-${cell.target}`}>
                  <small>{cell.category.replace('跨国', '')} · {cell.horizonYears}年 · {cell.targetLabel}</small>
                  <strong>{cell.passed ? '有限通过' : '增量失败'}</strong>
                  <span>AUC {number(cell.auc)} · 基线 {number(cell.baselineAuc)}</span>
                  <em>Δ {number(cell.aucImprovement)} · Brier改善 {number(cell.brierImprovement, 4)}</em>
                  <small>前后时期最低 AUC 增量 {number(Number.isFinite(weakestSubperiodDelta) ? weakestSubperiodDelta : null)}</small>
                </div>
              )
            })}
          </div>
          <p>{assetValidation.method} 唯一通过项是股票1年最大回撤风险；其余收益与风险通道未形成稳定增量。{assetValidation.commodityValidation.reason}</p>
        </section>
      )}

      {geographicValidation && (
        <section className="asset-forward-validation geographic-asset-validation">
          <div>
            <span>C2 全球—区域—本国对照</span>
            <strong>国家错位与固定时滞已进入验证，但绝对资产预测仍失败</strong>
          </div>
          <div className="geographic-validation-table">
            <div className="geographic-validation-head"><span>目标</span><span>全球</span><span>区域</span><span>本国</span><span>本国时滞</span><span>错位分解</span></div>
            {Object.entries(geographicValidation.cells).map(([cellId, cell]: [string, any]) => (
              <div className="geographic-validation-row" key={cellId}>
                <strong>{cell.label}</strong>
                {(['global', 'region', 'country', 'countryLagged', 'decomposition'] as const).map((modelId) => (
                  <span key={modelId}>
                    <b>{cell.models[modelId].positiveOosR2}/{cell.models[modelId].assets}</b>
                    <small>R²为正 · 中位 {number(cell.models[modelId].medianOosR2)}</small>
                  </span>
                ))}
              </div>
            ))}
          </div>
          <div className="geographic-validation-foot">
            <span>区域通过 {geographicValidation.candidates.find((item: any) => item.modelId === 'region')?.passedCells ?? 0}/4</span>
            <span>本国通过 {geographicValidation.candidates.find((item: any) => item.modelId === 'country')?.passedCells ?? 0}/4</span>
            <span>时滞通过 {geographicValidation.candidates.find((item: any) => item.modelId === 'countryLagged')?.passedCells ?? 0}/4</span>
            <span>分解通过 {geographicValidation.candidates.find((item: any) => item.modelId === 'decomposition')?.passedCells ?? 0}/4</span>
            <span>共同资产 {geographicValidation.commonEligibleAssets} 条</span>
          </div>
          <p>{geographicValidation.conclusion} {interactionValidation?.reason}</p>
        </section>
      )}

      {cycleId === 'C2' && jointMapping && (
        <section className="asset-forward-validation geographic-asset-validation">
          <div>
            <span>C2 现代资产错位验证</span>
            <strong>已区分上市地与标的市场；国家错位仍未取得正的绝对样本外表现</strong>
          </div>
          <div className="asset-forward-validation-grid">
            {Object.entries(jointMapping.cells).map(([cellId, cell]: [string, any]) => {
              const global = cell.modelComparison.globalC2
              const exposure = cell.modelComparison.exposureWeightedC2
              return (
                <div key={cellId}>
                  <small>{cell.horizonMonths}个月{cell.target === 'return' ? '收益' : '风险'}</small>
                  <strong>{cell.status === 'insufficient_non_overlapping_history' ? '历史不足' : `${exposure.assetCount} 条可验`}</strong>
                  <span>全球中位R² {number(global.medianOosR2)}</span>
                  <em>错位中位R² {number(exposure.medianOosR2)} · 相对全球 {number(exposure.medianOosR2DeltaVsGlobal)}</em>
                </div>
              )
            })}
          </div>
          <div className="geographic-validation-foot">
            <span>暴露登记 {jointMapping.exposureRegistry.assetCount} 条</span>
            <span>中国轨道 {jointMapping.exposureRegistry.trackAssetCounts.CHN} 条 · 样本不足</span>
            <span>美国轨道 {jointMapping.exposureRegistry.trackAssetCounts.USA} 条</span>
            <span>英国轨道 {jointMapping.exposureRegistry.trackAssetCounts.GBR} 条</span>
            <span>日本现代月频轨道 {jointMapping.exposureRegistry.trackAssetCounts.JPN} 条</span>
          </div>
          <p>{jointMapping.method} 当前收益、风险均未通过，36个月历史也不足，因此继续阻断资产预测和配置建议。</p>
        </section>
      )}

      {cycleId === 'C2' && countryClockMapping && (
        <section className="asset-forward-validation geographic-asset-validation country-clock-validation">
          <div>
            <span>C2 本国时钟资产映射</span>
            <strong>各国按自身峰谷对齐，不再把中美日英硬套到同一日历相位</strong>
          </div>
          <div className="country-clock-grid">
            {countryClockMapping.focusCountries.map((country: any) => {
              const stockReturn = country.headlineCells.find((cell: any) => cell.category === '跨国股票' && cell.horizonYears === 1 && cell.target === 'return')
              const stockRisk = country.headlineCells.find((cell: any) => cell.category === '跨国股票' && cell.horizonYears === 1 && cell.target === 'risk')
              return (
                <div key={country.iso}>
                  <strong>{country.name}</strong>
                  <span>{country.status === 'direct_long_history' ? `${country.history.startYear}—${country.history.endYear} · ${country.turnCount} 个本国峰谷` : '历史映射阻断'}</span>
                  <em>{country.directAssetCount} 条本国直接资产 · {country.asOfPeriod ?? '—'} 当前 {country.currentPhase ? phaseLabels[country.currentPhase] : '—'}</em>
                  {country.status === 'direct_long_history' ? (
                    <>
                      <small>股票谷后−峰后收益 {percent(stockReturn?.localClock.eventDifference)}</small>
                      <small>股票峰后−谷后风险 {percent(stockRisk?.localClock.eventDifference)}</small>
                    </>
                  ) : <small>{country.reason}</small>}
                </div>
              )
            })}
          </div>
          <div className="country-clock-summary">
            {countryClockMapping.pooled.filter((cell: any) => cell.category === '跨国股票').map((cell: any) => (
              <span key={`${cell.horizonYears}-${cell.target}`}>{cell.horizonYears}年{cell.target === 'return' ? '收益' : '风险'}：本国时钟差异更强 {percent(cell.localClockStrongerShare, 0)} · 方向一致 {percent(cell.expectedDirectionShare, 0)}</span>
            ))}
          </div>
          <div className="country-phase-asset-heading">
            <strong>当前本国相位的历史资产画像</strong>
            <span>同相位历史条件统计 · 非资产预测</span>
          </div>
          <div className="country-phase-asset-table">
            <div className="country-phase-asset-head"><span>国家 / 相位</span><span>资产</span><span>期限</span><span>历史收益</span><span>正收益率</span><span>历史下行风险</span></div>
            {countryPhaseAssetRows.map((row: any) => (
              <div className="country-phase-asset-row" key={`${row.assetId}-${row.horizonYears}`}>
                <strong>{row.country}<small>{phaseLabels[row.phase]} · {row.asOfPeriod}</small></strong>
                <span>{row.category.replace('跨国', '')}</span>
                <span>{row.horizonYears} 年<small>{row.return.count} 期</small></span>
                <span><b>{percent(row.return.mean)}</b><small>较全样本 {percent(row.return.differenceVsUnconditional)}</small></span>
                <span><b>{percent(row.return.positiveShare, 0)}</b><small>历史条件胜率</small></span>
                <span><b>{percent(row.risk.mean)}</b><small>较全样本 {percent(row.risk.differenceVsUnconditional)}</small></span>
              </div>
            ))}
          </div>
          <p>{countryClockMapping.method} {countryClockMapping.caveat}</p>
        </section>
      )}

      {cycleId === 'C2' && hierarchicalRisk && (
        <section className="asset-forward-validation geographic-asset-validation">
          <div>
            <span>C2 分资产目标验证</span>
            <strong>{assetClassValidation?.passedTargets ?? 0}/{assetClassValidation?.targetCount ?? 0} 个独立通道通过，资产预测继续阻断</strong>
          </div>
          {assetClassValidation && (
            <div className="c2-asset-class-validation">
              {assetClassValidation.classes.map((assetClass: any) => (
                <div className="c2-historical-risk-channel" key={assetClass.category}>
                  <div className="family-ablation-heading">
                    <span>{assetClass.category.replace('跨国', '')}独立目标</span>
                    <b className={assetClass.passedTargets ? '' : 'is-failed'}>{assetClass.passedTargets}/{assetClass.targetCount} 通过</b>
                  </div>
                  <div className="asset-forward-validation-grid">
                    {assetClass.targets.map((target: any) => (
                      <div key={`${target.targetId}-${target.horizonYears}`}>
                        <small>{target.horizonYears}年 · {target.label}</small>
                        <strong>{target.status === 'passed_historical_channel' ? '历史通道通过' : '增量失败'}</strong>
                        <span>C2 AUC {number(target.recursiveValidation.candidate.auc)} · 基线 {number(target.recursiveValidation.baseline.auc)}</span>
                        <em>Δ {number(target.recursiveValidation.aucDelta)} · Brier改善 {number(target.recursiveValidation.brierImprovement, 4)}</em>
                        <small>国家留一 Δ {number(target.leaveCountryOut2000Plus.aucDelta)} · 双改善 {percent(target.leaveCountryOut2000Plus.improvedCountryShare, 0)}</small>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
              <p>{assetClassValidation.interpretation} {assetClassValidation.caveat}</p>
            </div>
          )}
          {conditionalPropagation && (
            <div className="c2-conditional-propagation">
              <div className="family-ablation-heading c2-legacy-audit-heading">
                <span>预注册条件传播终局验证</span>
                <b className="is-failed">{conditionalPropagation.passedChannels}/{conditionalPropagation.channelCount} 通道通过</b>
              </div>
              <div className="asset-forward-validation-grid">
                {conditionalPropagation.scenarios.map((scenario: any) => {
                  const best = [...scenario.channels]
                    .filter((channel: any) => channel.recursiveValidation.aucDelta != null)
                    .sort((left: any, right: any) => right.recursiveValidation.aucDelta - left.recursiveValidation.aucDelta)[0]
                  return (
                    <div key={scenario.scenarioId}>
                      <small>{scenario.label}</small>
                      <strong>{scenario.passedChannels}/{scenario.channelCount} 通过</strong>
                      <span>全样本双改善 {scenario.positiveFullSampleChannels} 项 · 中位Δ {number(scenario.medianAucDelta)}</span>
                      <em>{best ? `最强：${best.category.replace('跨国', '')}${best.horizonYears}年${best.targetLabel} · Δ ${number(best.recursiveValidation.aucDelta)}` : '无可比较通道'}</em>
                      <small>{scenario.definition}</small>
                    </div>
                  )
                })}
              </div>
              <p><strong>{conditionalPropagation.conclusion}</strong> {conditionalPropagation.caveat}</p>
            </div>
          )}
          <div className="family-ablation-heading c2-legacy-audit-heading">
            <span>旧联合下行风险模型审计</span>
            <b className="is-failed">{hierarchicalRisk.passedHorizons}/{hierarchicalRisk.horizonCount} 窗口通过</b>
          </div>
          <div className="asset-forward-validation-grid">
            {Object.values(hierarchicalRisk.horizons).map((horizon: any) => {
              const persistence = horizon.architectures.asset_persistence
              const global = horizon.architectures.global_common
              const hierarchy = horizon.architectures.country_hierarchy
              return (
                <div key={horizon.horizonYears}>
                  <small>未来 {horizon.horizonYears} 年高下行风险状态</small>
                  <strong>{horizon.status === 'passed_limited' ? '有限通过' : '增量失败'}</strong>
                  <span>资产惯性 AUC {number(persistence.auc)} · 全球C2 {number(global.auc)}</span>
                  <em>国家分层 AUC {number(hierarchy.auc)} · Δ {number(horizon.incrementalVsPersistence.aucDelta)}</em>
                  <small>Brier 改善 {number(horizon.incrementalVsPersistence.brierImprovement, 4)} · 大类双改善 {horizon.incrementalVsPersistence.categorySupport}/{horizon.incrementalVsPersistence.categoryCount}</small>
                </div>
              )
            })}
          </div>
          <div className="geographic-validation-foot">
            <span>标的：{hierarchicalRisk.target}</span>
            <span>路径：全球共同项 + 本国偏离 + 按揭信用/融资交互</span>
            <span>{hierarchicalRisk.riskDefinition}</span>
          </div>
          {historicalRiskChannels.map((channel: any) => (
            <div className="c2-historical-risk-channel" key={channel.channelId}>
              <div className="family-ablation-heading">
                <span>{channel.horizonYears}年{channel.assetCategory}下行压力审计</span>
                <b>{channel.status === 'passed_historical_stress' ? '历史压力测试通过' : '风险口径修正后未通过'}</b>
              </div>
              {channel.riskDefinitionAudit && <p>{channel.riskDefinitionAudit.previousDefinition} 现改为{channel.riskDefinitionAudit.currentDefinition}{channel.riskDefinitionAudit.finding}</p>}
              <div className="asset-forward-validation-grid">
                <div><small>递归样本外 AUC</small><strong>{number(channel.recursiveValidation.candidate.auc)}</strong><span>资产惯性 {number(channel.recursiveValidation.baseline.auc)}</span><em>增量 {number(channel.recursiveValidation.aucDelta)}</em></div>
                <div><small>递归样本外 Brier</small><strong>{number(channel.recursiveValidation.candidate.brier)}</strong><span>改善 {number(channel.recursiveValidation.brierImprovement, 4)}</span><em>{channel.recursiveValidation.candidate.observations} 个观察</em></div>
                <div><small>跨时期最低 AUC</small><strong>{number(Math.min(...channel.subperiods.map((period: any) => period.candidate.auc)))}</strong><span>{channel.status === 'passed_historical_stress' ? '两个子时期均改善' : '跨时期不稳定'}</span><em>{channel.status === 'passed_historical_stress' ? '四组正则参数稳定' : '旧结论已撤销'}</em></div>
                <div><small>国家留一 · 2000年后</small><strong>{number(channel.leaveCountryOut2000Plus.candidate.auc)}</strong><span>增量 {number(channel.leaveCountryOut2000Plus.aucDelta)}</span><em>{channel.leaveCountryOut2000Plus.countryCount} 国 · {percent(channel.leaveCountryOut2000Plus.improvedCountryShare, 0)} 改善</em></div>
              </div>
              {channel.modernBridge?.currentState && (
                <div className="c2-modern-pressure-panel">
                  <div className="family-ablation-heading"><span>现代结构与融资桥接</span><b>宏观状态可观察 · 资产映射阻断</b></div>
                  <div className="asset-forward-validation-grid">
                    <div><small>结构代理一致性</small><strong>{number(channel.modernBridge.structureProxyValidation.correlation)}</strong><span>{channel.modernBridge.structureProxyValidation.countryCount} 国</span><em>方向一致 {percent(channel.modernBridge.structureProxyValidation.directionAgreement, 0)}</em></div>
                    <div><small>融资代理一致性</small><strong>{number(channel.modernBridge.financingProxyValidation.correlation)}</strong><span>{channel.modernBridge.financingProxyValidation.countryCount} 国</span><em>方向一致 {percent(channel.modernBridge.financingProxyValidation.directionAgreement, 0)}</em></div>
                    <div><small>当前结构压力 · {channel.modernBridge.currentState.asOfYear}</small><strong>{channel.modernBridge.currentState.label}</strong><span>历史分位 {percent(channel.modernBridge.currentState.historicalPercentile, 0)}</span><em>覆盖 {channel.modernBridge.currentState.countryCount} 国</em></div>
                    <div><small>当前融资确认 · {channel.modernBridge.currentState.financingState?.asOfYear}</small><strong>{channel.modernBridge.currentState.financingState?.label}</strong><span>历史分位 {percent(channel.modernBridge.currentState.financingState?.historicalPercentile, 0)}</span><em>{channel.modernBridge.currentState.financingCoverage.latestDataCountryCount} 国 · 口径相关 {number(channel.modernBridge.financingProxyValidation.correlation)}</em></div>
                  </div>
                  <p>{channel.modernBridge.currentState.interpretation} {channel.modernBridge.caveat}</p>
                </div>
              )}
              <p>{channel.interpretation} {channel.caveat}</p>
            </div>
          ))}
          <p>{hierarchicalRisk.method} 独立目标与旧联合模型均未建立可发布通道。</p>
        </section>
      )}

      {legacyMappingAudit ? (
        <section className="asset-blocked-state c3-legacy-mapping-blocked">
          <span className="status-badge status-blocked">等待双核心重算</span>
          <h2>旧 C3 历史相位资产表已停止展示</h2>
          <p>当前 C3 已改为固定投资脉冲与企业信用脉冲双核心。旧表的相位、概率情景和资产排序来自不同模型口径，继续展示会造成错误对应。</p>
          <span>当前有效结论以上方 8 个独立收益风险通道为准；下一步按双核心历史状态重新计算资产分区。</span>
        </section>
      ) : (
        <>
      <section className="asset-toolbar">
        <label className="search-control"><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索资产或类别" /></label>
        <select value={category} onChange={(event) => setCategory(event.target.value)}>{categories.map((item) => <option key={item}>{item}</option>)}</select>
        <select value={confidence} onChange={(event) => setConfidence(event.target.value)}>
          <option>全部</option><option value="high">高置信</option><option value="medium">中置信</option><option value="low">低置信</option>
        </select>
        <div className="segmented small sort-control">
          <ArrowDownUp size={14} />
          <button className={sortKey === 'spread' ? 'active' : ''} onClick={() => setSortKey('spread')}>{isStateAssociation ? '状态差异' : '相位差异'}</button>
          <button className={sortKey === 'oos' ? 'active' : ''} onClick={() => setSortKey('oos')}>样本外 R²</button>
          <button className={sortKey === 'name' ? 'active' : ''} onClick={() => setSortKey('name')}>名称</button>
        </div>
        <div className="segmented small group-control">
          <ChevronsDownUp size={14} />
          <button className={!allExpanded && !searchExpanded ? 'active' : ''} onClick={() => setAllCategories(false)}>折叠全部</button>
          <button className={allExpanded || searchExpanded ? 'active' : ''} onClick={() => setAllCategories(true)}>展开全部</button>
        </div>
        <span className="row-count">{groupedRows.length} 类 · {rows.length} 条资产</span>
      </section>

      {currentScenario?.status !== 'blocked_current_phase_disagreement' && scenarioChart && (
        <section className="historical-risk-return-section probability-weighted-asset-section">
          <div className="risk-return-heading">
            <div><span>{cycleId} 当前相位概率情景</span><h2>概率加权资产收益—风险</h2><p>{currentScenario.riskDefinition} {currentScenario.caveat}</p></div>
            <div className="scenario-status-group">
              <span className="status-badge status-blocked">收益预测阻断</span>
              <span className={`status-badge ${currentScenario.riskForecastStatus === 'limited' ? 'status-research' : 'status-blocked'}`}>{currentScenario.riskForecastStatus === 'limited' ? '风险层有限' : '风险层阻断'}</span>
            </div>
          </div>
          <div className="historical-risk-return-grid">
            <PlotlyCanvas className="historical-risk-return-chart" data={scenarioChart.data} layout={scenarioChart.layout} onClick={(point) => setSelected(rows.find((asset: any) => asset.assetId === point?.customdata?.[0]) ?? null)} />
            <aside className="phase-leader-panel scenario-validation-panel">
              <span>递归样本外边界</span>
              <p>概率化只相对硬相位更稳；未整体战胜无条件收益基准，所以不能称为资产预测。</p>
              <div><small>优于硬相位</small><strong>{currentScenario.summary.assetsBeatingHardPhase} / {currentScenario.summary.validatedAssets}</strong><b>{percent(currentScenario.validation.assetShareBeatingHardPhase, 0)}</b></div>
              <div><small>优于无条件均值</small><strong>{currentScenario.summary.assetsBeatingUnconditional} / {currentScenario.summary.validatedAssets}</strong><b>{percent(currentScenario.validation.assetShareBeatingUnconditional, 0)}</b></div>
              <div><small>样本外 R² 为正</small><strong>{currentScenario.summary.positiveOosR2} / {currentScenario.summary.validatedAssets}</strong><b>{percent(currentScenario.validation.positiveOosR2Share, 0)}</b></div>
              <div><small>相对硬相位 MAE</small><strong>{percent(currentScenario.validation.maeImprovementVsHardPhase)}</strong><b>改善</b></div>
              <span className="scenario-validation-subtitle">平方收益风险验证</span>
              <div><small>C2/C3 联合开发权重</small><strong>{percent(currentScenario.validation.risk.phaseWeight, 0)}</strong><b>截至 {currentScenario.validation.risk.weightSelection.endYear}</b></div>
              <div><small>独立留出段</small><strong>{currentScenario.validation.risk.holdout.startYear}—{currentScenario.validation.risk.holdout.endYear}</strong><b>{currentScenario.validation.risk.holdout.assets} 资产</b></div>
              <div><small>风险 MAE 改善</small><strong>{percent(currentScenario.validation.risk.maeImprovementVsUnconditional)}</strong><b>{currentScenario.riskForecastStatus === 'limited' ? '通过' : '阻断'}</b></div>
              <div><small>资产风险胜率</small><strong>{currentScenario.summary.assetsBeatingUnconditionalRisk} / {currentScenario.summary.validatedAssets}</strong><b>{percent(currentScenario.validation.risk.assetShareBeatingUnconditional, 0)}</b></div>
              <div><small>改善年份占比</small><strong>{percent(currentScenario.validation.risk.positiveYearShare, 0)}</strong><b>年份块</b></div>
              <div><small>Bootstrap 改善概率</small><strong>{percent(currentScenario.validation.risk.yearBlockBootstrapProbability, 0)}</strong><b>固定门槛 90%</b></div>
            </aside>
          </div>
        </section>
      )}

      <section className="historical-risk-return-section">
        <div className="risk-return-heading">
          <div><span>{cycleId} {isStateAssociation ? '历史状态分区' : '历史相位候选'}</span><h2>{display.sectionTitle}</h2><p>{display.description}</p></div>
          <div className="segmented small">{phases.map((item) => <button key={item} className={phase === item ? 'active' : ''} onClick={() => setPhase(item)}>{phaseLabels[item]}</button>)}</div>
        </div>
        <div className="historical-risk-return-grid">
          <PlotlyCanvas className="historical-risk-return-chart" data={chart.data} layout={chart.layout} onClick={(point) => setSelected(rows.find((asset: any) => asset.assetId === point?.customdata?.[0]) ?? null)} />
          <aside className="phase-leader-panel">
            <span>{phaseLabels[phase]} · 历史收益风险比</span>
            <p>仅描述历史条件分布，不是资产排序、因果归因或配置建议。</p>
            {leaders.map(({ asset, score }: any, index: number) => (
              <button key={asset.assetId} onClick={() => setSelected(asset)}><i>{String(index + 1).padStart(2, '0')}</i><div><strong>{asset.name}</strong><small>{asset.category}</small></div><b>{score.toFixed(2)}</b></button>
            ))}
          </aside>
        </div>
      </section>

      <section className="asset-table-wrap">
        <table className="research-table asset-table">
          <thead><tr><th>资产</th><th>{display.sampleLabel}</th>{phases.map((item) => <th key={item}>{phaseLabels[item]}<small>收益 / 波动</small></th>)}<th>{isStateAssociation ? '状态差异' : '相位差异'}</th><th>样本外 R²</th><th>{isStateAssociation ? '最小 HAC p值' : 'HAC p值'}</th><th>置信度</th></tr></thead>
          <tbody>{groupedRows.map((group) => {
            const expanded = searchExpanded || expandedCategories.has(group.name)
            const confidenceCounts = group.assets.reduce(
              (counts: Record<string, number>, asset: any) => ({ ...counts, [asset.confidence]: (counts[asset.confidence] ?? 0) + 1 }),
              {} as Record<string, number>,
            )
            const starts = group.assets.map((asset: any) => String(asset.startPeriod ?? asset.startYear)).sort()
            const ends = group.assets.map((asset: any) => String(asset.endPeriod ?? asset.endYear)).sort()
            return (
              <Fragment key={group.name}>
                <tr className="asset-group-row">
                  <td><button className="asset-group-toggle" onClick={() => toggleCategory(group.name)} aria-expanded={expanded}>{expanded ? <ChevronDown size={15} /> : <ChevronRight size={15} />}<span><strong>{group.name}</strong><small>{group.assets.length} 条资产</small></span></button></td>
                  <td>{starts[0]}—{ends.at(-1)}<small>分类覆盖区间</small></td>
                  {phases.map((item) => {
                    const annReturn = average(group.assets.map((asset: any) => asset.phaseStats[item].annReturn))
                    const annVol = average(group.assets.map((asset: any) => asset.phaseStats[item].annVol))
                    return <td key={item} className={(annReturn ?? 0) >= 0 ? 'positive' : 'negative'}>{percent(annReturn)}<small>{percent(annVol)} · 类均值</small></td>
                  })}
                  <td>{percent(average(group.assets.map((asset: any) => asset.phaseSpread)))}</td>
                  <td className={(average(group.assets.map((asset: any) => asset.oosR2)) ?? 0) > 0 ? 'positive' : 'negative'}>{number(average(group.assets.map((asset: any) => asset.oosR2)))}</td>
                  <td>{number(average(group.assets.map((asset: any) => asset.hacPValue)))}</td>
                  <td><span className="category-confidence">高 {confidenceCounts.high ?? 0} · 中 {confidenceCounts.medium ?? 0} · 低 {confidenceCounts.low ?? 0}</span></td>
                </tr>
                {expanded && group.assets.map((asset: any) => (
                  <tr className="asset-detail-row" key={asset.assetId} onClick={() => setSelected(asset)}>
                    <td><strong>{asset.name}</strong><small>{asset.category} · {asset.dataIdentity}</small></td>
                    <td>{asset.startPeriod ?? asset.startYear}—{asset.endPeriod ?? asset.endYear}<small>{asset.observations} {display.observationUnit}</small></td>
                    {phases.map((item) => <td key={item} className={(asset.phaseStats[item].annReturn ?? 0) >= 0 ? 'positive' : 'negative'}>{percent(asset.phaseStats[item].annReturn)}<small>{percent(asset.phaseStats[item].annVol)}</small></td>)}
                    <td>{percent(asset.phaseSpread)}</td><td className={(asset.oosR2 ?? 0) > 0 ? 'positive' : 'negative'}>{number(asset.oosR2)}</td><td>{number(asset.hacPValue)}</td><td><span className={`confidence confidence-${asset.confidence}`}>{asset.confidence}</span></td>
                  </tr>
                ))}
              </Fragment>
            )
          })}</tbody>
        </table>
      </section>
      <div className="table-footnote">{isStateAssociation ? mapping.caveat : forwardValidation ? '表内为历史条件统计。同期HAC经多资产FDR后无一通过，未来1/3年收益和风险样本外检验也未通过，因此不能称为稳定资产映射。' : '研究映射采用年度实际收益。相位均值样本外 R² 为负的资产仍保留展示，但不能称为稳定映射。'}</div>

      {selected && (
        <div className="asset-detail-backdrop" onClick={() => setSelected(null)}>
          <aside className="asset-detail-drawer" onClick={(event) => event.stopPropagation()}>
            <button className="drawer-close" onClick={() => setSelected(null)}><X size={17} /></button>
            <span>{selected.category} · {selected.dataIdentity}</span><h2>{selected.name}</h2><p>{display.sampleLabel} {selected.startPeriod ?? selected.startYear}—{selected.endPeriod ?? selected.endYear}，共 {selected.observations} {display.observationUnit}。</p>
            {selectedScenario && <dl className="metric-list detail-metrics"><div><dt>概率加权历史收益</dt><dd>{percent(selectedScenario.expectedAnnReturn)}</dd></div><div><dt>条件历史波动</dt><dd>{percent(selectedScenario.conditionalAnnVol)}</dd></div><div><dt>治理风险尺度</dt><dd>{percent(selectedScenario.governedRiskScale)}</dd></div><div><dt>相对无条件风险变化</dt><dd>{percent(selectedScenario.riskScaleShiftVsUnconditional)}</dd></div><div><dt>正收益率</dt><dd>{percent(selectedScenario.positiveRate, 0)}</dd></div><div><dt>20%分位收益</dt><dd>{percent(selectedScenario.quantile20Return)}</dd></div><div><dt>尾部20%平均收益</dt><dd>{percent(selectedScenario.expectedShortfall20)}</dd></div><div><dt>相对无条件收益变化</dt><dd>{percent(selectedScenario.returnShiftVsUnconditional)}</dd></div></dl>}
            <div className="phase-detail-grid">{phases.map((item) => <div key={item}><span>{phaseLabels[item]}</span><strong>{percent(selected.phaseStats[item].annReturn)}</strong><small>{display.volatilityLabel} {percent(selected.phaseStats[item].annVol)} · 正收益 {percent(selected.phaseStats[item].positiveRate, 0)} · n={selected.phaseStats[item].n}</small></div>)}</div>
            <dl className="metric-list detail-metrics"><div><dt>最佳历史{isStateAssociation ? '状态' : '相位'}</dt><dd>{phaseLabels[selected.bestPhase] ?? '—'}</dd></div><div><dt>最弱历史{isStateAssociation ? '状态' : '相位'}</dt><dd>{phaseLabels[selected.worstPhase] ?? '—'}</dd></div><div><dt>{isStateAssociation ? '状态收益差异' : '相位收益差异'}</dt><dd>{percent(selected.phaseSpread)}</dd></div><div><dt>样本外 R²</dt><dd>{number(selected.oosR2)}</dd></div><div><dt>{isStateAssociation ? '最小 HAC p值' : 'HAC 联合检验 p值'}</dt><dd>{number(selected.hacPValue)}</dd></div><div><dt>来源</dt><dd>{selected.source}</dd></div></dl>
          </aside>
        </div>
      )}
        </>
      )}
    </>
  )
}
