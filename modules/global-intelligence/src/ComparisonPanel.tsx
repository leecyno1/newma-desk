export interface CrucixComparison {
  status: "current" | "restored" | "baseline" | "unavailable";
  timestamp: string | null;
  previous: string | null;
  freshness: { status: string };
  entries: Array<{
    key: string; label: string; from: number; to: number; change: number; pctChange: number | null;
    fromDate: string; toDate: string; unit: string; changeUnit: string; direction: string;
    currentEligible: boolean; source: string; basis: string; seriesId?: string;
    kind?: "collection-sample"; timeBasis?: "collected"; countScope?: Record<string, unknown>; note?: string;
  }>;
  gaps: Array<{ key: string; reason: string }>;
  changeCount: number | null;
  reportedChangeCount: number | null;
  reportedDirection: string | null;
  note: string;
}

export function readCrucixComparison(value: unknown): CrucixComparison | null {
  if (!value || typeof value !== "object") return null;
  const receipt = value as CrucixComparison;
  return ["current", "restored", "baseline", "unavailable"].includes(receipt.status)
    && Array.isArray(receipt.entries) && Array.isArray(receipt.gaps) ? receipt : null;
}

const unitLabel = (value: string) => ({
  "index points": "指数点", index: "指数", percent: "%", "percentage points": "百分点",
  "percentage-points": "百分点", "USD/troy-ounce": "美元/金衡盎司",
  records: "条样本", detections: "次探测", "regional-aircraft-samples": "架次区域样本",
  "reported-fatalities": "样本报告死亡人数", "source-checks": "项来源检查",
})[value] ?? value;
const numeric = (value: number) => value.toLocaleString("zh-CN", { maximumFractionDigits: 8 });
const scopeLabel = (value: string) => ({ source: "来源", feeds: "订阅源", channels: "频道", limit: "样本上限",
  selection: "筛选规则", window: "查询窗口", period: "统计窗口", days: "回看天数", regions: "区域与边界", sources: "检查来源" })[value] ?? value;

export function ComparisonPanel({ receipt }: { receipt: CrucixComparison | null }) {
  const active = receipt?.status === "current" || receipt?.status === "restored";
  const status = receipt?.status === "restored" ? "历史比较 · 非新采集"
    : receipt?.status === "current" ? receipt.freshness?.status === "fresh" ? "本批比较" : "旧批次或时效未核验"
      : receipt?.status === "baseline" ? "仅建立基线 · 暂无前批" : "比较不可用 · 不能判断无变化";
  return <section className="intel-comparison" aria-label="两批观测变化">
    <header><strong>两批观测变化</strong><span>{status}</span></header>
    {receipt?.timestamp ? <p>采集批次：{receipt.previous ?? "前批未知"} → {receipt.timestamp}</p> : null}
    <p>{receipt?.note ?? "未取得可匹配的来源比较，不能据此判断持平、安全或风险下降。"}</p>
    {active ? <>
      <p>可追溯数值变化 {receipt.entries.length} · 来源报告 {receipt.reportedChangeCount ?? "未知"} · 比较缺口 {receipt.gaps.length}</p>
      {!receipt.entries.length ? <p>暂无可核验的数值变化，不等于全部指标未变。</p> : <details>
        <summary>查看变化明细（{receipt.entries.length}）</summary>
        <div className="intel-comparison-table"><table>
          <thead><tr><th>指标 / 来源</th><th>前值 → 现值</th><th>绝对变化</th><th>相对变化</th><th>原时间 / 依据</th><th>使用范围</th></tr></thead>
          <tbody>{receipt.entries.map((row) => <tr key={row.key}>
            <td>{row.label}<small>{row.source}{row.seriesId ? ` / ${row.seriesId}` : ""}</small></td>
            <td>{numeric(row.from)} → {numeric(row.to)} {unitLabel(row.unit)}</td>
            <td>{row.change > 0 ? "+" : ""}{numeric(row.change)} {unitLabel(row.changeUnit)}</td>
            <td>{row.pctChange === null ? "不可计算（零或非正基数）" : `${row.pctChange > 0 ? "+" : ""}${numeric(row.pctChange)}%`}</td>
            <td>{row.fromDate} → {row.toDate}<small>{row.timeBasis === "collected" ? "采集时间，非发布或发生时间" : "原观测期"}</small></td>
            <td className="intel-comparison-scope">{row.kind === "collection-sample"
              ? <>{row.currentEligible ? "本批样本对照 · 非风险信号" : "历史样本对照 · 非新采集"}
                <small>{row.note}</small>
                {row.countScope ? <details><summary>查询范围</summary><dl>
                  {Object.entries(row.countScope).map(([key, value]) => <div key={key}><dt>{scopeLabel(key)}</dt>
                    <dd>{typeof value === "object" ? JSON.stringify(value) : String(value)}</dd></div>)}
                </dl></details> : null}</>
              : row.currentEligible ? "本批观测比较" : "仅历史对照，非当前信号"}</td>
          </tr>)}</tbody>
        </table></div>
      </details>}
      {receipt.gaps.length ? <details><summary>查看比较缺口（{receipt.gaps.length}）</summary>
        <ul>{receipt.gaps.map((gap, i) => <li key={`${gap.key}:${i}`}>{gap.key}：{gap.reason}</li>)}</ul>
      </details> : null}
    </> : null}
  </section>;
}
