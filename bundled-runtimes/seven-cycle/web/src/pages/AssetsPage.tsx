import { ArrowDownUp, ChevronDown, ChevronRight, ChevronsDownUp, Search, X } from 'lucide-react'
import { Fragment, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import CurrentAssetForecast from '../components/CurrentAssetForecast'
import LoadingState from '../components/LoadingState'
import PlotlyCanvas from '../components/PlotlyCanvas'
import ResearchAssetMapping from '../components/ResearchAssetMapping'
import StatusBadge from '../components/StatusBadge'
import { useResearchData } from '../hooks/useResearchData'
import { loadAssetStatistics } from '../lib/data'
import type { AssetRow } from '../types'

const phases = ['recovery', 'expansion', 'downturn', 'contraction'] as const
const chartColors = ['#58c9ed', '#f1aa4b', '#69ce9f', '#9b83ef', '#ef6d7c', '#7195ff', '#c4d36b', '#d98bd5', '#94a9ba']

type AttributionRow = {
  component_type: string
  component_id: string
  point_contribution: number
  observed_return: number
  reconstructed_return: number
  status: string
  evidence_level: string
  period_start: string
  period_end: string
}

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

export default function AssetsPage() {
  const { data, error } = useResearchData(loadAssetStatistics)
  const [params, setParams] = useSearchParams()
  const requested = params.get('cycle')
  const [cycleId, setCycleId] = useState(requested && /^C[1-7]$/.test(requested) ? requested : 'C4')
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('全部')
  const [confidence, setConfidence] = useState('全部')
  const [sortKey, setSortKey] = useState<'impact' | 'oos' | 'name'>('impact')
  const [selected, setSelected] = useState<AssetRow | null>(null)
  const [phase, setPhase] = useState<(typeof phases)[number]>('recovery')
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(() => new Set())
  const [attributionRows, setAttributionRows] = useState<AttributionRow[]>([])
  const [attributionLoading, setAttributionLoading] = useState(false)

  useEffect(() => {
    if (requested && /^C[1-7]$/.test(requested) && requested !== cycleId) setCycleId(requested)
  }, [cycleId, requested])

  const categories = useMemo(() => data ? ['全部', ...Array.from(new Set(data.assets.map((asset) => asset.category)))] : [], [data])
  const rows = useMemo(() => {
    if (!data || cycleId !== 'C4') return []
    const normalized = query.trim().toLowerCase()
    return data.assets
      .filter((asset) => category === '全部' || asset.category === category)
      .filter((asset) => confidence === '全部' || asset.confidence === confidence)
      .filter((asset) => !normalized || `${asset.name} ${asset.category}`.toLowerCase().includes(normalized))
      .sort((a, b) => {
        if (sortKey === 'name') return a.name.localeCompare(b.name, 'zh-CN')
        if (sortKey === 'oos') return (b.oos_r2 ?? -Infinity) - (a.oos_r2 ?? -Infinity)
        const rightImpact = b.impact_bps_per_1sigma == null ? -Infinity : Math.abs(b.impact_bps_per_1sigma)
        const leftImpact = a.impact_bps_per_1sigma == null ? -Infinity : Math.abs(a.impact_bps_per_1sigma)
        return rightImpact - leftImpact
      })
  }, [category, confidence, cycleId, data, query, sortKey])
  const groupedRows = useMemo(() => {
    const groups = new Map<string, AssetRow[]>()
    rows.forEach((asset) => groups.set(asset.category, [...(groups.get(asset.category) ?? []), asset]))
    return Array.from(groups, ([name, assets]) => ({ name, assets })).sort((left, right) => {
      if (sortKey === 'name') return left.name.localeCompare(right.name, 'zh-CN')
      if (sortKey === 'oos') return (average(right.assets.map((asset) => asset.oos_r2)) ?? -Infinity) - (average(left.assets.map((asset) => asset.oos_r2)) ?? -Infinity)
      return (average(right.assets.map((asset) => Math.abs(asset.impact_bps_per_1sigma ?? 0))) ?? -Infinity)
        - (average(left.assets.map((asset) => Math.abs(asset.impact_bps_per_1sigma ?? 0))) ?? -Infinity)
    })
  }, [rows, sortKey])
  const riskReturnChart = useMemo(() => {
    if (!data || cycleId !== 'C4') return null
    const categories = Array.from(new Set(rows.map((asset) => asset.category)))
    return {
      data: categories.map((item, categoryIndex) => {
        const assets = rows.filter((asset) => asset.category === item && asset.phase_stats?.[phase])
        return {
          type: 'scatter', mode: 'markers', name: item,
          x: assets.map((asset) => asset.phase_stats?.[phase].ann_vol),
          y: assets.map((asset) => asset.phase_stats?.[phase].ann_return),
          text: assets.map((asset) => asset.name),
          customdata: assets.map((asset) => [asset.asset_id]),
          marker: { size: assets.map((asset) => asset.confidence === 'high' ? 11 : asset.confidence === 'medium' ? 8 : 6), color: chartColors[categoryIndex % chartColors.length], opacity: .8, line: { color: '#08111f', width: 1 } },
          hovertemplate: '%{text}<br>年化收益 %{y:.1%}<br>年化波动 %{x:.1%}<extra></extra>',
        }
      }),
      layout: {
        paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)', margin: { l: 58, r: 18, t: 12, b: 48 },
        font: { color: '#c9d7e5', family: 'Inter, PingFang SC, sans-serif', size: 10 },
        xaxis: { title: '历史年化波动', tickformat: '.0%', gridcolor: '#1d3146' },
        yaxis: { title: '历史年化收益', tickformat: '.0%', gridcolor: '#1d3146', zerolinecolor: '#657c91' },
        legend: { orientation: 'h', y: 1.13, font: { size: 9 } }, hovermode: 'closest',
      },
    }
  }, [cycleId, data, phase, rows])
  const phaseLeaders = useMemo(() => rows
    .filter((asset) => asset.phase_stats?.[phase])
    .map((asset) => ({ asset, score: (asset.phase_stats?.[phase].ann_return ?? 0) / Math.max(.01, asset.phase_stats?.[phase].ann_vol ?? .01) }))
    .sort((a, b) => b.score - a.score)
    .slice(0, 5), [phase, rows])

  useEffect(() => {
    if (!selected || cycleId !== 'C4') {
      setAttributionRows([])
      setAttributionLoading(false)
      return
    }
    const controller = new AbortController()
    setAttributionLoading(true)
    const assetId = `${selected.category}::${selected.name}`
    fetch(`/v1/assets/${encodeURIComponent(assetId)}/attribution?horizon=12`, {
      cache: 'no-store', signal: controller.signal,
    })
      .then((response) => {
        if (!response.ok) throw new Error('attribution unavailable')
        return response.json()
      })
      .then((payload) => setAttributionRows(payload.data ?? []))
      .catch((error) => {
        if (error.name !== 'AbortError') setAttributionRows([])
      })
      .finally(() => setAttributionLoading(false))
    return () => controller.abort()
  }, [cycleId, selected])

  if (!data) return <LoadingState error={error} />
  const publication = data.publication[cycleId]
  const researchCycle = data.researchMappings?.[cycleId]
  const researchMapping = researchCycle?.assetMapping
  const stateMapping = data.stateMappings?.[cycleId]
  const stateDiagnostic = data.stateDiagnostics?.[cycleId]
  const c5AssetValidation = cycleId === 'C5' ? stateDiagnostic?.assetValidation : null
  const c7AssetValidation = cycleId === 'C7' ? stateDiagnostic?.assetValidation : null
  const searchExpanded = Boolean(query.trim())
  const allExpanded = groupedRows.length > 0 && groupedRows.every((group) => expandedCategories.has(group.name))
  const toggleCategory = (name: string) => setExpandedCategories((current) => {
    const next = new Set(current)
    if (next.has(name)) next.delete(name)
    else next.add(name)
    return next
  })
  const setAllCategories = (expanded: boolean) => setExpandedCategories(expanded ? new Set(groupedRows.map((group) => group.name)) : new Set())

  return (
    <div className="page assets-page">
      <section className="page-heading">
        <div>
          <h1>资产统计与客观归因</h1>
          <p>按周期逐表统计真实资产收益、风险与样本外关联。不按行业叙事指定受益或受损资产。</p>
        </div>
        <div className="heading-meta">
          <span>页面构建 {data.meta.generated}</span>
          <span>历史统计截至 {data.meta.historicalStatisticsAsOf ?? '—'}</span>
          <span>联合状态 {data.meta.forecastAsOf ?? '—'}</span>
          <span>预测资产截至 {data.meta.forecastAssetDataThrough ?? '—'}</span>
        </div>
      </section>

      {data.currentCycleForecast && <CurrentAssetForecast data={data.currentCycleForecast} />}

      <section className="asset-layer-heading">
        <div>
          <span>单周期历史映射层</span>
          <h2>按 C1—C7 查看资产统计与阻断结果</h2>
          <p>这里只回答单个周期与资产历史收益风险的关系；不会把上方 C4+C5+C7 联合预测冒充为某个周期的独立贡献。</p>
        </div>
        <div className="asset-layer-counts">
          <span>{data.summary.observed_assets} 条正式统计资产</span>
          <span>C2/C3 各 {data.researchMappings?.C2?.assetMapping?.summary?.eligibleAssets ?? 0} 条研究候选</span>
        </div>
      </section>

      <section className="asset-cycle-tabs">
        {Object.entries(data.publication).map(([id, status]) => (
          <button key={id} className={cycleId === id ? 'active' : ''} onClick={() => { setCycleId(id); setParams({ cycle: id }) }}>
            <strong>{id}</strong>{data.researchMappings?.[id]?.assetMapping ? <span className="status-badge status-research">研究映射</span> : data.stateMappings?.[id] ? <span className="status-badge status-research">历史关联</span> : <StatusBadge status={status} />}
          </button>
        ))}
      </section>

      {researchMapping || stateMapping ? (
        <ResearchAssetMapping cycleId={cycleId} mapping={researchMapping ?? stateMapping} currentDirection={researchCycle?.currentDirection} assetValidation={researchCycle?.assetValidation} jointMapping={researchCycle?.regimeRefactor?.jointAssetMapping} phaseLabels={stateMapping?.phaseLabels ?? data.researchPhaseLabels ?? { recovery: '复苏', expansion: '扩张', slowdown: '放缓', contraction: '收缩' }} />
      ) : cycleId !== 'C4' ? (
        <section className="asset-blocked-state">
          <StatusBadge status={publication} />
          <h2>{stateDiagnostic ? `${cycleId} ${cycleId === 'C7' ? '状态概率' : '状态方向'}可用，资产映射未通过` : `${cycleId} 资产统计未发布`}</h2>
          <p>{c5AssetValidation ? `流动性状态自身的3至12个月方向通过，但分股票、债券、商品和外汇的收益风险增量仅 ${c5AssetValidation.summary.passedChannels}/${c5AssetValidation.summary.totalChannels} 个通道通过，因此禁止转换为资产涨跌或风险预测。` : c7AssetValidation ? `风险偏好状态自身的3个月准确率为 ${(stateDiagnostic.validation['3m'].accuracy * 100).toFixed(1)}%、AUC ${stateDiagnostic.validation['3m'].auc.toFixed(2)}；但五类资产1/3/6个月收益与风险增量仅 ${c7AssetValidation.summary.passedChannels}/${c7AssetValidation.summary.totalChannels} 个通道通过，因此资产预测继续阻断。` : '该周期尚未通过历史识别与发布门槛。系统不会复制 C4 结果，也不会用主观行业映射填充空表。'}</p>
          <span>{cycleId === 'C5' ? '可在七周期研究页查看三层流动性状态和3–12个月非线性路径；资产页继续保持阻断。' : cycleId === 'C7' ? '可在七周期研究页查看1–5个月风险区间条件路径；它不是继续上涨判断，6个月及资产预测继续保持阻断。' : '可继续查看中心先验和阻断原因；补齐数据并通过红噪声、截点与样本外验证后再开放。'}</span>
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
              <button className={sortKey === 'impact' ? 'active' : ''} onClick={() => setSortKey('impact')}>影响幅度</button>
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

          {riskReturnChart && (
            <section className="historical-risk-return-section">
              <div className="risk-return-heading">
                <div><span>C4 历史相位</span><h2>资产收益—风险表现</h2><p>点大小代表统计置信等级；点击资产可查看系数、样本外 R² 和 2019 年边界检查。</p></div>
                <div className="segmented small">{phases.map((item) => <button key={item} className={phase === item ? 'active' : ''} onClick={() => setPhase(item)}>{data.phase_labels[item]}</button>)}</div>
              </div>
              <div className="historical-risk-return-grid">
                <PlotlyCanvas
                  className="historical-risk-return-chart"
                  data={riskReturnChart.data}
                  layout={riskReturnChart.layout}
                  onClick={(point) => setSelected(data.assets.find((asset) => asset.asset_id === point?.customdata?.[0]) ?? null)}
                />
                <aside className="phase-leader-panel">
                  <span>{data.phase_labels[phase]} · 收益风险比</span>
                  <p>仅用于描述该相位下的历史统计分布，不代表投资排序或配置建议。</p>
                  {phaseLeaders.map(({ asset, score }, index) => (
                    <button key={asset.asset_id} onClick={() => setSelected(asset)}>
                      <i>{String(index + 1).padStart(2, '0')}</i><div><strong>{asset.name}</strong><small>{asset.category}</small></div><b>{score.toFixed(2)}</b>
                    </button>
                  ))}
                </aside>
              </div>
            </section>
          )}

          <section className="asset-table-wrap">
            <table className="research-table asset-table">
              <thead>
                <tr>
                  <th>资产</th><th>真实样本</th>
                  {phases.map((phase) => <th key={phase}>{data.phase_labels[phase]}<small>收益 / 波动</small></th>)}
                  <th>1σ 影响</th><th>样本外 R²</th><th>置信度</th>
                </tr>
              </thead>
              <tbody>
                {groupedRows.map((group) => {
                  const expanded = searchExpanded || expandedCategories.has(group.name)
                  const starts = group.assets.map((asset) => asset.start).filter(Boolean) as string[]
                  const ends = group.assets.map((asset) => asset.end).filter(Boolean) as string[]
                  const confidenceCounts = group.assets.reduce((counts, asset) => ({ ...counts, [asset.confidence]: (counts[asset.confidence] ?? 0) + 1 }), {} as Record<string, number>)
                  return (
                    <Fragment key={group.name}>
                      <tr className="asset-group-row">
                        <td>
                          <button className="asset-group-toggle" onClick={() => toggleCategory(group.name)} aria-expanded={expanded}>
                            {expanded ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
                            <span><strong>{group.name}</strong><small>{group.assets.length} 条资产</small></span>
                          </button>
                        </td>
                        <td>{starts.sort()[0] ?? '—'}—{ends.sort().at(-1) ?? '—'}<small>分类覆盖区间</small></td>
                        {phases.map((phase) => {
                          const annReturn = average(group.assets.map((asset) => asset.phase_stats?.[phase]?.ann_return))
                          const annVol = average(group.assets.map((asset) => asset.phase_stats?.[phase]?.ann_vol))
                          return <td key={phase} className={(annReturn ?? 0) >= 0 ? 'positive' : 'negative'}>{percent(annReturn)}<small>{percent(annVol)} · 类均值</small></td>
                        })}
                        <td>{number(average(group.assets.map((asset) => Math.abs(asset.impact_bps_per_1sigma ?? 0))), 1)} bp<small>平均绝对值</small></td>
                        <td className={(average(group.assets.map((asset) => asset.oos_r2)) ?? 0) > 0 ? 'positive' : 'negative'}>{number(average(group.assets.map((asset) => asset.oos_r2)))}</td>
                        <td><span className="category-confidence">高 {confidenceCounts.high ?? 0} · 中 {confidenceCounts.medium ?? 0} · 低 {confidenceCounts.low ?? 0}</span></td>
                      </tr>
                      {expanded && group.assets.map((asset) => (
                        <tr className="asset-detail-row" key={asset.asset_id} onClick={() => setSelected(asset)}>
                          <td><strong>{asset.name}</strong><small>{asset.category}</small></td>
                          <td>{asset.start}—{asset.end}<small>{asset.n_months} 个月</small></td>
                          {phases.map((phase) => (
                            <td key={phase} className={(asset.phase_stats?.[phase]?.ann_return ?? 0) >= 0 ? 'positive' : 'negative'}>
                              {percent(asset.phase_stats?.[phase]?.ann_return)}<small>{percent(asset.phase_stats?.[phase]?.ann_vol)}</small>
                            </td>
                          ))}
                          <td>{asset.impact_bps_per_1sigma == null ? '—' : `${asset.impact_bps_per_1sigma.toFixed(1)} bp`}</td>
                          <td className={(asset.oos_r2 ?? 0) > 0 ? 'positive' : 'negative'}>{number(asset.oos_r2)}</td>
                          <td><span className={`confidence confidence-${asset.confidence}`}>{asset.confidence}</span></td>
                        </tr>
                      ))}
                    </Fragment>
                  )
                })}
              </tbody>
            </table>
          </section>
          <div className="table-footnote">C4 关联分量不是因果归因；HAC 90% 区间、扩展窗口样本外 R² 与数据身份共同决定置信等级。</div>
        </>
      )}

      {selected && (
        <div className="asset-detail-backdrop" onClick={() => setSelected(null)}>
          <aside className="asset-detail-drawer" onClick={(event) => event.stopPropagation()}>
            <button className="drawer-close" onClick={() => setSelected(null)}><X size={17} /></button>
            <span>{selected.category}</span>
            <h2>{selected.name}</h2>
            <p>真实样本 {selected.start}—{selected.end}，共 {selected.n_months} 个月。</p>
            <div className="phase-detail-grid">
              {phases.map((phase) => (
                <div key={phase}>
                  <span>{data.phase_labels[phase]}</span>
                  <strong>{percent(selected.phase_stats?.[phase]?.ann_return)}</strong>
                  <small>年化波动 {percent(selected.phase_stats?.[phase]?.ann_vol)} · 上涨月 {percent(selected.phase_stats?.[phase]?.positive_rate, 0)}</small>
                </div>
              ))}
            </div>
            <dl className="metric-list detail-metrics">
              <div><dt>C4 水平系数</dt><dd>{number(selected.beta_level, 5)}</dd></div>
              <div><dt>C4 三月斜率系数</dt><dd>{number(selected.beta_slope3, 5)}</dd></div>
              <div><dt>一标准差影响</dt><dd>{selected.impact_bps_per_1sigma?.toFixed(1) ?? '—'} bp</dd></div>
              <div><dt>样本外 R²</dt><dd>{number(selected.oos_r2)}</dd></div>
            </dl>
            <div className="attribution-example">
              <strong>2019 年统计关联守恒检查</strong>
              {attributionLoading ? <p>正在读取已发布归因产品…</p> : attributionRows.length ? (
                <>
                  <div><span>资产实际收益</span><b>{percent(attributionRows[0].observed_return)}</b></div>
                  <div><span>C4 统计关联分量</span><b>{percent(attributionRows.find((row) => row.component_type === 'cycle')?.point_contribution)}</b></div>
                  <div><span>未解释残差</span><b>{percent(attributionRows.find((row) => row.component_type === 'asset_residual')?.point_contribution)}</b></div>
                  <div><span>重构收益</span><b>{percent(attributionRows[0].reconstructed_return)}</b></div>
                  <p>API产品状态 {attributionRows[0].status} · 证据 {attributionRows[0].evidence_level}。两项严格守恒，但C4分量仍是统计关联而非因果归因。</p>
                </>
              ) : (
                <>
                  <div><span>资产实际收益</span><b>{percent(selected.actual_2019)}</b></div>
                  <div><span>C4 统计关联分量</span><b>{percent(selected.c4_assoc_contribution_2019)}</b></div>
                  <p>该资产没有可发布的2019归因产品；静态研究值仅作边界检查，不强行分配给其他周期。</p>
                </>
              )}
            </div>
          </aside>
        </div>
      )}
    </div>
  )
}
