import { Archive, Check, ExternalLink, FileClock, ShieldAlert } from 'lucide-react'
import LoadingState from '../components/LoadingState'
import StatusBadge from '../components/StatusBadge'
import { useResearchData } from '../hooks/useResearchData'
import { loadAudit } from '../lib/data'

export default function AuditPage() {
  const { data, error } = useResearchData(loadAudit)
  if (!data) return <LoadingState error={error} />

  return (
    <div className="page audit-page">
      <section className="page-heading">
        <div>
          <h1>数据身份、校准与研究版本</h1>
          <p>每条结论都保留来源、时点、代理、模型版本、发布资格和修改原因，方便复盘而不是走审批流程。</p>
        </div>
        <div className="heading-meta"><span>审计基线 {data.meta.asOf}</span><span>生成 {data.meta.generated}</span></div>
      </section>

      <section className="audit-grid">
        <div className="audit-panel source-panel">
          <div className="panel-title"><div><span>数据身份</span><h2>研究结论来源</h2></div><FileClock size={19} /></div>
          <table className="research-table">
            <thead><tr><th>研究实体</th><th>来源</th><th>数据时点</th><th>身份状态</th></tr></thead>
            <tbody>{data.sources.map((source) => (
              <tr key={source.entity}><td><strong>{source.entity}</strong></td><td>{source.source}</td><td>{source.asOf}<small>{source.vintage}</small></td><td><code>{source.status}</code></td></tr>
            ))}</tbody>
          </table>
        </div>

        <div className="audit-panel rule-panel">
          <div className="panel-title"><div><span>不可突破</span><h2>发布规则</h2></div><ShieldAlert size={19} /></div>
          <ul className="audit-rule-list">
            <li><Check size={15} /><span>周期长度是中心先验，不是固定正弦波。</span></li>
            <li><Check size={15} /><span>代理、修订后数据与真实 vintage 使用不同身份。</span></li>
            <li><Check size={15} /><span>阻断周期不能进入资产统计或预测合成。</span></li>
            <li><Check size={15} /><span>未通过样本外基准的模型不画预测虚线。</span></li>
            <li><Check size={15} /><span>缺失数据保持不可用，不生成合成历史冒充真实数据。</span></li>
            <li><Check size={15} /><span>系统不输出组合权重、组合回测或交易指令。</span></li>
          </ul>
        </div>
      </section>

      {(data.c2C3Sources ?? []).length > 0 && (
        <section className="proxy-audit-panel">
          <div className="panel-title">
            <div><span>C2/C3 长历史</span><h2>原始数据覆盖与缓存时点</h2></div>
            <FileClock size={19} />
          </div>
          <p className="proxy-audit-note">覆盖期是数据内容范围；缓存时间只表示本地拉取时间，不冒充官方发布 vintage。</p>
          <div className="proxy-audit-table-wrap">
            <table className="research-table">
              <thead><tr><th>数据源</th><th>覆盖范围</th><th>研究用途</th><th>本地缓存</th></tr></thead>
              <tbody>{(data.c2C3Sources ?? []).map((source) => (
                <tr key={source.name}>
                  <td><strong>{source.name}</strong><small>{source.cache}</small></td>
                  <td>{source.coverage}</td>
                  <td>{source.role}</td>
                  <td>{new Date(source.cacheUpdated).toLocaleString('zh-CN')}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        </section>
      )}

      {(data.proxyColumns ?? []).length > 0 && (
        <section className="proxy-audit-panel">
          <div className="panel-title">
            <div><span>显式代理</span><h2>PMI 分项尾部延伸审计</h2></div>
            <FileClock size={19} />
          </div>
          <p className="proxy-audit-note">仅延伸真实分项停止后的缺失月份；不覆盖真实值，不与直接数据使用同一身份等级。</p>
          <div className="proxy-audit-table-wrap">
            <table className="research-table">
              <thead>
                <tr><th>目标分项</th><th>解释轨道</th><th>真实截至</th><th>代理区间</th><th>拟合区间</th><th>重叠期 R²</th><th>代理月份</th></tr>
              </thead>
              <tbody>{(data.proxyColumns ?? []).map((proxy) => (
                <tr key={proxy.column}>
                  <td><strong>{proxy.column}</strong><small>{proxy.identity}</small></td>
                  <td>{proxy.proxyFor}</td>
                  <td>{proxy.directThrough}</td>
                  <td>{proxy.proxyStart} — {proxy.proxyEnd}</td>
                  <td>{proxy.fitStart} — {proxy.fitEnd}</td>
                  <td><strong>{proxy.r2.toFixed(3)}</strong></td>
                  <td>{proxy.proxyObservations}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        </section>
      )}

      <section className="calibration-panel">
        <div className="panel-title"><div><span>修改留痕</span><h2>周期校准记录</h2></div></div>
        <div className="calibration-timeline">
          {data.calibrations.map((item, index) => (
            <div className="calibration-item" key={`${item.subject}-${item.version}`}>
              <span className="timeline-index">{String(index + 1).padStart(2, '0')}</span>
              <div><span>{item.subject} · {item.version}</span><strong>{item.decision}</strong></div>
              <StatusBadge status={item.status as any} />
            </div>
          ))}
        </div>
      </section>

      <section className="version-archive">
        <div className="panel-title"><div><span>研究复盘</span><h2>版本归档</h2></div><Archive size={19} /></div>
        <div className="archive-grid">
          <article><span>当前版本</span><h3>2026-07-19 七周期研究系统重做</h3><p>废弃旧三段式、组合回测与主观资产映射，建立市场曲面、证据复核、资产统计和受限预测。</p><a href="/docs/2026-07-19-seven-cycle-research-system-redesign.md" target="_blank">查看规格 <ExternalLink size={13} /></a></article>
          <article className="archived"><span>历史记录</span><h3>Phase A 研究基础</h3><p>固化 C1–C7 发布资格、C4 历史相位、资产统计原型与治理 API 契约。</p><code>research-foundation-v1</code></article>
          <article className="archived"><span>废弃方向</span><h3>旧三段式与响应面</h3><p>仅保留问题复盘，不进入当前产品导航，不继续开发。</p><code>superseded</code></article>
        </div>
      </section>
    </div>
  )
}
