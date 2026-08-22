import {
  Activity, ArrowRight, BookOpenCheck, ExternalLink, Gauge,
  GitCompareArrows, RefreshCw, SlidersHorizontal,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

export type GlobalTopicId = "fed-rates" | "hormuz" | "us-china-trade";

interface TopicFactor {
  id: string; label: string; min: number; max: number; value: number;
}

interface TopicForecast {
  generatedAt: string;
  probabilities: Array<{ label: string; probability: number }>;
  dominantScenario: string;
  confidence: number;
  method: string;
  disclaimer: string;
}

interface TopicSnapshot {
  topicId: GlobalTopicId;
  title: string;
  subtitle: string;
  question: string;
  accent: string;
  metrics: Array<{ label: string; value: string; change: string }>;
  factors: TopicFactor[];
  series: Array<{ id: string; label: string; color: string }>;
  transmission: string[];
  sources: string[];
  observations: Array<{ seriesId: string; date: string; value: number; unit: string; source: string }>;
  events: Array<{ id: string; date: string; title: string; summary: string; source: string; sourceUrl: string; impact: string; confidence: number }>;
  forecast: TopicForecast;
  dataMode: string;
  updatedAt: string;
}

function chartPath(values: number[], width: number, height: number) {
  if (!values.length) return "";
  const min = Math.min(...values);
  const range = Math.max(...values) - min || 1;
  return values.map((value, index) => {
    const x = values.length === 1 ? 0 : (index / (values.length - 1)) * width;
    const y = height - ((value - min) / range) * height;
    return (index ? "L" : "M") + x.toFixed(1) + "," + y.toFixed(1);
  }).join(" ");
}

function TopicChart({ snapshot }: { snapshot: TopicSnapshot }) {
  const dates = [...new Set(snapshot.observations.map((item) => item.date))];
  return (
    <section className="topic-panel topic-chart-panel">
      <header><span><Activity size={15} />核心变量</span><small>标准化趋势 · 参考基线</small></header>
      <div className="topic-chart-legend">
        {snapshot.series.map((series) => <span key={series.id}><i style={{ background: series.color }} />{series.label}</span>)}
      </div>
      <svg className="topic-line-chart" viewBox="0 0 720 240" preserveAspectRatio="none" role="img" aria-label="专题核心变量趋势图">
        {[0, 1, 2, 3, 4].map((line) => <line key={line} x1="0" x2="720" y1={line * 55 + 10} y2={line * 55 + 10} />)}
        {snapshot.series.map((series) => {
          const values = snapshot.observations.filter((item) => item.seriesId === series.id).map((item) => item.value);
          return <path key={series.id} d={chartPath(values, 720, 200)} transform="translate(0 15)" style={{ stroke: series.color }} />;
        })}
      </svg>
      <div className="topic-chart-axis">{dates.map((date) => <span key={date}>{date}</span>)}</div>
    </section>
  );
}

function ForecastPanel({ snapshot, onForecast }: { snapshot: TopicSnapshot; onForecast: (forecast: TopicForecast) => void }) {
  const [factors, setFactors] = useState(() => Object.fromEntries(snapshot.factors.map((factor) => [factor.id, factor.value])));
  const [forecast, setForecast] = useState(snapshot.forecast);
  const [running, setRunning] = useState(false);

  const run = async () => {
    setRunning(true);
    try {
      const response = await fetch("/api/global-topics/" + snapshot.topicId + "/forecast", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ factors }),
      });
      if (!response.ok) throw new Error("HTTP " + response.status);
      const next = await response.json() as TopicForecast;
      setForecast(next);
      onForecast(next);
    } finally {
      setRunning(false);
    }
  };

  return (
    <section className="topic-panel topic-forecast">
      <header><span><SlidersHorizontal size={15} />情景推演</span><small>{forecast.method}</small></header>
      <p className="topic-question">{snapshot.question}</p>
      <div className="topic-factor-list">
        {snapshot.factors.map((factor) => (
          <label key={factor.id}>
            <span>{factor.label}<b>{Math.round(factors[factor.id] ?? factor.value)}</b></span>
            <input type="range" min={factor.min} max={factor.max} value={factors[factor.id] ?? factor.value} onChange={(event) => setFactors((current) => ({ ...current, [factor.id]: Number(event.target.value) }))} />
          </label>
        ))}
      </div>
      <button className="topic-run-button" type="button" onClick={run} disabled={running}><RefreshCw size={14} className={running ? "spin" : ""} />{running ? "计算中" : "重新推演"}</button>
      <div className="topic-probabilities">
        {forecast.probabilities.map((item) => (
          <div key={item.label} className={item.label === forecast.dominantScenario ? "is-dominant" : ""}>
            <span>{item.label}<b>{item.probability}%</b></span>
            <i><em style={{ width: item.probability + "%" }} /></i>
          </div>
        ))}
      </div>
      <small className="topic-disclaimer">置信度 {Math.round(forecast.confidence * 100)}% · {forecast.disclaimer}</small>
    </section>
  );
}

export function GlobalTopicDashboard({ topicId, refreshNonce, embedded = false, onContextChange }: {
  topicId: GlobalTopicId;
  refreshNonce: number;
  embedded?: boolean;
  onContextChange?: (state: Record<string, unknown>) => void;
}) {
  const [snapshot, setSnapshot] = useState<TopicSnapshot>();
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const response = await fetch("/api/global-topics/" + topicId);
      if (!response.ok) throw new Error("HTTP " + response.status);
      const next = await response.json() as TopicSnapshot;
      setSnapshot(next);
      onContextChange?.({ topicId, title: next.title, metrics: next.metrics, forecast: next.forecast, events: next.events.slice(0, 5), lastUpdate: next.updatedAt });
    } catch {
      setError("专题数据暂时不可用");
    }
  }, [onContextChange, topicId]);

  useEffect(() => { void load(); }, [load, refreshNonce]);
  if (error) return <div className="topic-state"><Gauge size={20} />{error}<button type="button" onClick={() => void load()}>重试</button></div>;
  if (!snapshot) return <div className="topic-state"><RefreshCw size={20} className="spin" />加载专题</div>;

  return (
    <div className="global-topic-root" data-accent={snapshot.accent}>
      <section className="topic-heading" data-embedded={embedded || undefined}>
        {!embedded ? <div data-mod-page-title><span>GLOBAL THEMATIC RESEARCH</span><h1>{snapshot.title}</h1><p>{snapshot.subtitle}</p></div> : null}
        <div className="topic-data-badge"><i />参考基线 <small>等待实时连接</small></div>
      </section>

      <section className="topic-metrics">
        {snapshot.metrics.map((metric) => <article key={metric.label}><span>{metric.label}</span><strong>{metric.value}</strong><small>{metric.change}</small></article>)}
      </section>

      <div className="topic-primary-grid">
        <TopicChart snapshot={snapshot} />
        <ForecastPanel snapshot={snapshot} onForecast={(forecast) => onContextChange?.({ topicId, title: snapshot.title, forecast, metrics: snapshot.metrics })} />
      </div>

      <section className="topic-panel topic-transmission">
        <header><span><GitCompareArrows size={15} />影响传导链</span><small>从事实信号到资产影响</small></header>
        <div>{snapshot.transmission.map((node, index) => <span key={node}><b>{index + 1}</b>{node}{index < snapshot.transmission.length - 1 ? <ArrowRight size={14} /> : null}</span>)}</div>
      </section>

      <div className="topic-secondary-grid">
        <section className="topic-panel topic-events">
          <header><span><BookOpenCheck size={15} />事件与证据</span><small>按可信度排序</small></header>
          {snapshot.events.map((event) => (
            <article key={event.id}>
              <time>{event.date}</time>
              <div><strong>{event.title}</strong><p>{event.summary}</p><span>{event.source} · 置信度 {Math.round(event.confidence * 100)}%</span></div>
              <a href={event.sourceUrl} target="_blank" rel="noreferrer" aria-label={"查看 " + event.title + " 来源"}><ExternalLink size={14} /></a>
            </article>
          ))}
        </section>
        <section className="topic-panel topic-sources">
          <header><span><Gauge size={15} />数据接入</span><small>专题数据库</small></header>
          {snapshot.sources.map((source, index) => <div key={source}><i className={index < 2 ? "is-reference" : ""} /><span>{source}</span><small>{index < 2 ? "已建基线" : "待实时接入"}</small></div>)}
        </section>
      </div>
    </div>
  );
}
