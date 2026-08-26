import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  Clock3,
  ExternalLink,
  FileText,
  Flame,
  Gauge,
  Languages,
  Loader2,
  Newspaper,
  RefreshCw,
  Rss,
  Search,
  ShieldAlert,
  Sparkles,
} from "lucide-react";

import { Disclaimer } from "@/components/ui/Disclaimer";
import { ResearchText } from "@/components/ui/ResearchText";
import { SaveNoteButton } from "@/components/ui/SaveNoteButton";
import {
  api,
  ApiError,
  type Announcement,
  type NewsItem,
  type NewsMonitorTopic,
  type NewsSentiment,
  type NewsSignal,
  type NewsVelocityState,
  type RadarData,
  type RadarItem,
} from "@/lib/api";
import {
  loadCrucixSnapshot,
  type CrucixNewsItem,
  type CrucixSnapshot,
} from "@/lib/crucix";
import { hasLlm, chatStream } from "@/lib/llm";
import { cn } from "@/lib/utils";
import {
  createVibeDeskSnapshotCache,
  publishVibeDeskContext,
  registerVibeDeskContextProvider,
  registerVibeDeskHandoffHandler,
  registerVibeDeskUiActionHandler,
  subscribeVibeDeskConfig,
  type VibeDeskPageContext,
  type VibeDeskWikiSubject,
} from "@/lib/vibedesk";
import { loadWatch } from "@/lib/watchlist";

const TABS = [
  { key: "monitor", label: "新闻监测", icon: Gauge },
  { key: "raw", label: "全部资讯", icon: Rss },
  { key: "filings", label: "A股公告", icon: FileText },
  { key: "watch-news", label: "自选新闻", icon: Newspaper },
] as const;

type TabKey = typeof TABS[number]["key"];
type SignalFilter = "all" | "rising" | "risk" | "opportunity" | "verify";
type SortMode = "attention" | "latest";
interface Digest { loading?: boolean; text?: string; err?: string; needKey?: boolean }

const SENTIMENT_LABEL: Record<NewsSentiment, string> = {
  positive: "正面",
  negative: "负面",
  neutral: "中性",
  mixed: "分化",
};

const SIGNAL_LABEL: Record<NewsSignal, string> = {
  risk: "风险",
  opportunity: "机会",
  mixed: "分化",
  watch: "观察",
};

const SIGNAL_FILTERS: Array<[SignalFilter, string]> = [
  ["all", "全部"],
  ["rising", "正在升温"],
  ["risk", "风险"],
  ["opportunity", "机会"],
  ["verify", "待核验"],
];

function hasChinese(value: string | null | undefined) {
  return Boolean(value && /[\u3400-\u9fff]/.test(value));
}

function hasLatinWords(value: string | null | undefined) {
  return Boolean(value && /[A-Za-z]{3,}/.test(value));
}

function stripHtml(value: string | null | undefined) {
  return String(value || "")
    .replace(/<[^>]+>/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, "\"")
    .replace(/&#39;|&apos;/g, "'")
    .replace(/&nbsp;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function isGeneratedCategoryTitle(value: string | null | undefined) {
  const title = stripHtml(value);
  if (!title) return false;
  if (title.startsWith("自动聚类：")) return true;
  return /^.{1,48}｜(?:风险|机会|最新|行业|观察|待核验)动态$/.test(title);
}

function chineseItemTitle(item: RadarItem) {
  const translated = stripHtml(item.zh);
  if (translated && !isGeneratedCategoryTitle(translated)) return translated;
  const original = stripHtml(item.title);
  if (original && !isGeneratedCategoryTitle(original)) return original;
  const summary = stripHtml(item.summary);
  if (summary) return summary.length > 88 ? `${summary.slice(0, 88)}…` : summary;
  const industry = item.industry_name || "全球资讯";
  const signal = item.signal === "risk" ? "风险"
    : item.signal === "opportunity" ? "机会"
      : item.verification_status && item.verification_status !== "常规报道" ? "待核验"
        : "最新";
  return `自动聚类：${industry}｜${signal}动态`;
}

function chineseTopicTitle(topic: NewsMonitorTopic) {
  const translated = topic.items
    .map((item) => stripHtml(item.zh))
    .find((title) => title && !isGeneratedCategoryTitle(title));
  if (translated) return translated;
  const headline = stripHtml(topic.headline);
  if (headline && !isGeneratedCategoryTitle(headline)) return headline;
  const original = topic.items
    .map((item) => stripHtml(item.title))
    .find((title) => title && !isGeneratedCategoryTitle(title));
  if (original) return original;
  const summary = stripHtml(topic.summary);
  if (summary) return summary.length > 88 ? `${summary.slice(0, 88)}…` : summary;
  return "";
}

function hasTopicTitle(topic: NewsMonitorTopic) {
  return Boolean(
    stripHtml(topic.headline)
    || topic.items.some((item) => stripHtml(item.zh) || stripHtml(item.title)),
  );
}

function titleKey(value: string) {
  return stripHtml(value).toLocaleLowerCase().replace(/\s+/g, " ").trim();
}

function topicOriginalTitle(topic: NewsMonitorTopic, displayTitle: string) {
  const original = stripHtml(topic.headline);
  return original && original !== displayTitle && hasLatinWords(original) ? original : "";
}

function itemOriginalTitle(item: RadarItem, displayTitle: string) {
  const original = stripHtml(item.title);
  return original && original !== displayTitle && hasLatinWords(original) ? original : "";
}

function radarItemTimestamp(item: RadarItem) {
  if (typeof item.ts === "number" && Number.isFinite(item.ts)) return item.ts > 10_000_000_000 ? item.ts : item.ts * 1000;
  const parsed = Date.parse(item.published_at || item.time || "");
  return Number.isNaN(parsed) ? 0 : parsed;
}

function sentimentTone(value: NewsSentiment) {
  if (value === "negative") return "news-tone-negative";
  if (value === "positive") return "news-tone-positive";
  if (value === "mixed") return "news-tone-mixed";
  return "news-tone-neutral";
}

function signalTone(value: NewsSignal) {
  if (value === "risk") return "news-tone-negative";
  if (value === "opportunity") return "news-tone-positive";
  if (value === "mixed") return "news-tone-mixed";
  return "news-tone-neutral";
}

function velocityLabel(value: number | null | undefined, state: NewsVelocityState) {
  if (state === "new") return "新出现";
  if (value == null || !Number.isFinite(value)) return "基线不足";
  return `${value > 0 ? "+" : ""}${Math.round(value)}%`;
}

function velocityTone(state: NewsVelocityState) {
  if (state === "rising" || state === "new") return "text-warning";
  if (state === "falling") return "text-muted-foreground";
  return "text-foreground";
}

function localTime(value: string | null | undefined) {
  if (!value) return "时间未知";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
  }).format(parsed);
}

function generatedTimestamp(data: RadarData | null) {
  if (!data?.generated_at) return null;
  const parsed = new Date(data.generated_at_iso || data.generated_at.replace(" ", "T"));
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function dataFreshness(data: RadarData | null) {
  const generated = generatedTimestamp(data);
  if (!generated) return { label: "尚未抓取", stale: true };
  const ageMinutes = Math.max(0, Math.round((Date.now() - generated.getTime()) / 60_000));
  if (ageMinutes > 24 * 60) return { label: `${Math.floor(ageMinutes / 1440)} 天前`, stale: true };
  if (ageMinutes > 90) return { label: `${Math.floor(ageMinutes / 60)} 小时前`, stale: true };
  return { label: ageMinutes < 2 ? "刚刚" : `${ageMinutes} 分钟前`, stale: false };
}

function topicSearchText(topic: NewsMonitorTopic) {
  return [
    topic.label,
    topic.headline,
    topic.summary,
    topic.industry_name,
    ...topic.sources,
    ...topic.keywords,
    ...topic.items.flatMap((item) => [item.zh, item.title, item.summary]),
  ].join(" ").toLocaleLowerCase();
}

function SummaryItem({ label, value, tone = "neutral" }: {
  label: string; value: string | number; tone?: "neutral" | "positive" | "negative" | "warning";
}) {
  return (
    <span className={cn("news-summary-item", `news-summary-${tone}`)}>
      <strong>{value}</strong><small>{label}</small>
    </span>
  );
}

function SourceHealthDetails({ data, stale }: { data: RadarData; stale: boolean }) {
  const sources = data.stats.source_health || [];
  const issues = sources.filter((source) => source.status !== "healthy");
  const healthy = data.stats.healthy_sources ?? Math.max(0, data.stats.total_sources - (data.stats.failed_sources || 0));
  const industryNames = new Map(data.industries.map((item) => [item.key, item.name]));
  const hasIssue = stale || issues.length > 0;

  return (
    <details className={cn("news-source-health", hasIssue && "has-issue")}>
      <summary>
        {hasIssue ? <AlertTriangle className="h-3.5 w-3.5" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
        来源 {healthy}/{data.stats.total_sources}
        <ChevronDown className="news-source-health-chevron h-3 w-3" />
      </summary>
      <div className="news-source-health-popover">
        <header>
          <strong>来源运行状态</strong>
          <span>{data.refresh?.refreshing ? "后台更新中" : `每 ${data.refresh?.interval_minutes || 15} 分钟自动检查`}</span>
        </header>
        {issues.length ? (
          <div className="news-source-health-list">
            {issues.map((source) => (
              <div key={source.url || source.name}>
                <span>
                  <strong>{source.name}</strong>
                  <small>{industryNames.get(source.industry_key) || source.industry_key} · {source.status === "stale" ? "沿用上次数据" : "当前不可用"}</small>
                </span>
                <em title={source.error || undefined}>{source.last_success_at ? `上次成功 ${localTime(source.last_success_at)}` : "暂无成功记录"}</em>
              </div>
            ))}
          </div>
        ) : sources.length ? (
          <p>本轮全部来源抓取正常。</p>
        ) : (
          <p>来源明细将在下一轮自动刷新后生成。</p>
        )}
      </div>
    </details>
  );
}

function CrucixNewsPanel({
  items,
  snapshot,
  loading,
  error,
}: {
  items: CrucixNewsItem[];
  snapshot: CrucixSnapshot | null;
  loading: boolean;
  error: string;
}) {
  return (
    <section className="news-crucix-panel" aria-label="Crucix 补充新闻">
      <header>
        <div>
          <span className="news-crucix-kicker"><Rss className="h-3.5 w-3.5" />Crucix 补充情报</span>
          <strong>全球公开源快讯</strong>
          <p>只展示有原始标题、且未与当前新闻池重复的事件。</p>
        </div>
        <span className="news-crucix-health">
          {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : snapshot ? <CheckCircle2 className="h-3.5 w-3.5" /> : <AlertTriangle className="h-3.5 w-3.5" />}
          {snapshot ? `来源 ${snapshot.sourceHealth.ok}/${snapshot.sourceHealth.queried}` : loading ? "读取中" : "暂未就绪"}
        </span>
      </header>
      {items.length ? (
        <div className="news-crucix-grid">
          {items.slice(0, 6).map((item) => {
            const content = (
              <>
                <span className="news-crucix-meta">
                  {item.urgent ? <em>紧急</em> : null}
                  <span>{item.source}</span>
                  <span>{item.region}</span>
                  <span>{localTime(item.publishedAt)}</span>
                </span>
                <strong>{item.title}</strong>
                {item.url ? <ExternalLink className="h-3.5 w-3.5" /> : null}
              </>
            );
            return item.url ? (
              <a key={`${item.source}:${item.publishedAt}:${item.title}`} href={item.url} target="_blank" rel="noreferrer">{content}</a>
            ) : (
              <article key={`${item.source}:${item.publishedAt}:${item.title}`}>{content}</article>
            );
          })}
        </div>
      ) : (
        <p className={cn("news-crucix-empty", error && "is-error")}>
          {loading ? "正在读取 Crucix 首轮扫描…" : error || "去重后暂无新增标题。"}
        </p>
      )}
    </section>
  );
}

function TopicRow({ topic, selected, onSelect }: {
  topic: NewsMonitorTopic; selected: boolean; onSelect: () => void;
}) {
  const displayTitle = chineseTopicTitle(topic);
  return (
    <button
      type="button"
      onClick={onSelect}
      data-sentiment={topic.sentiment}
      className={cn("news-topic-row", selected && "is-selected")}
    >
      <span className="news-topic-accent" aria-hidden="true" />
      <span className="news-topic-content">
        <span className="news-topic-primary">
          <span className="news-topic-compact-badges">
            <span className={cn("news-badge", topic.velocity_state === "new" || topic.velocity_state === "rising" ? "news-tone-warning" : "news-tone-neutral")}>
              {topic.velocity_state === "new" ? "新出现" : topic.velocity_state === "rising" ? "快速升温" : topic.velocity_state === "falling" ? "热度回落" : "持续跟踪"}
            </span>
            <span className={cn("news-badge", signalTone(topic.signal))}>{SIGNAL_LABEL[topic.signal]}</span>
            <span className={cn("news-badge", sentimentTone(topic.sentiment))}>{SENTIMENT_LABEL[topic.sentiment]}</span>
          </span>
          <strong className="news-topic-title" title={displayTitle}>{displayTitle}</strong>
        </span>
        <span className="news-topic-secondary">
          <span>{topic.industry_name}</span>
          <span>{topic.sources.slice(0, 2).join(" / ")}</span>
          <span>{localTime(topic.latest_at)}</span>
        </span>
      </span>
      <span className="news-attention-score"><strong>{topic.attention_score}</strong><small>关注度</small></span>
    </button>
  );
}

function TopicDetail({ topic }: { topic: NewsMonitorTopic | undefined }) {
  const [digest, setDigest] = useState<Digest>({});

  useEffect(() => { setDigest({}); }, [topic?.id]);

  const generateDigest = async () => {
    if (!topic) return;
    if (!hasLlm()) { setDigest({ needKey: true }); return; }
    setDigest({ loading: true });
    const evidence = topic.items.slice(0, 8).map((item) => (
      `[${item.time}] ${item.source}｜${item.zh || item.title}${item.summary ? `｜${item.summary}` : ""}`
    )).join("\n");
    const prompt = [
      "请基于以下同一新闻事件的公开报道，用中文输出三个简短部分：",
      "1. 已知事实：只写多源共同确认的内容；",
      "2. 舆情变化：说明报道语气、传播范围和热度变化；",
      "3. 待验证：列出来源分歧、传闻、否认或仍缺证据的部分。",
      "不要预测股价，不要给投资建议，不要把报道语气当成事实真伪。",
      "",
      evidence,
    ].join("\n");
    try {
      let text = "";
      await chatStream([{ role: "user", content: prompt }], `新闻事件：${chineseTopicTitle(topic)}`, {
        onDelta: (delta) => { text += delta; setDigest({ text }); },
      });
    } catch (reason) {
      setDigest({ err: reason instanceof ApiError ? reason.message : "生成失败" });
    }
  };

  if (!topic) {
    return <div className="flex min-h-72 items-center justify-center text-sm text-muted-foreground">选择一条新闻查看详细信息</div>;
  }

  const displayTitle = chineseTopicTitle(topic);
  const originalTitle = topicOriginalTitle(topic, displayTitle);
  const readableSummary = hasChinese(topic.summary) ? stripHtml(topic.summary) : "";
  const titledItems = topic.items.filter((item) => stripHtml(item.zh) || stripHtml(item.title));

  return (
    <article className="news-detail">
      <header className="news-detail-header">
        <div className="news-topic-badges">
          <span className={cn("news-badge", topic.velocity_state === "new" || topic.velocity_state === "rising" ? "news-tone-warning" : "news-tone-neutral")}>
            {topic.velocity_state === "new" ? "新出现" : topic.velocity_state === "rising" ? "快速升温" : topic.velocity_state === "falling" ? "热度回落" : "持续跟踪"}
          </span>
          <span className={cn("news-badge", signalTone(topic.signal))}>{SIGNAL_LABEL[topic.signal]}</span>
          <span className={cn("news-badge", sentimentTone(topic.sentiment))}>{SENTIMENT_LABEL[topic.sentiment]}</span>
          <span className="news-badge news-tone-info">{topic.spread_level}</span>
          {topic.verification_status !== "常规报道" ? (
            <span className="news-badge news-tone-warning">{topic.verification_label || topic.verification_status}</span>
          ) : null}
          {topic.cross_language ? <span className="news-badge news-tone-info">跨语言合并</span> : null}
        </div>
        <h2>{displayTitle}</h2>
        {originalTitle ? <details className="news-original-disclosure"><summary>查看原文标题</summary><p>{originalTitle}</p></details> : null}
        {readableSummary && readableSummary !== displayTitle ? <p className="news-detail-summary">{readableSummary}</p> : null}
        <div className="news-detail-actions">
          <SaveNoteButton
            kind="新闻事件"
            title={displayTitle}
            content={[
              readableSummary || displayTitle,
              `状态：${topic.velocity_state === "new" ? "新出现" : topic.velocity_state === "rising" ? "快速升温" : "持续跟踪"}`,
              `信号：${SIGNAL_LABEL[topic.signal]}；报道语气：${SENTIMENT_LABEL[topic.sentiment]}；传播范围：${topic.spread_level}`,
              `来源：${topic.sources.join("、")}`,
              `待核验：${topic.verification_status !== "常规报道" ? (topic.verification_label || topic.verification_status) : "暂无显式传闻或反转提示"}`,
            ].join("\n")}
          />
        </div>
      </header>

      <dl className="news-detail-metrics">
        <div><dt>关注度</dt><dd>{topic.attention_score}</dd></div>
        <div><dt>报道增速</dt><dd className={velocityTone(topic.velocity_state)}>{velocityLabel(topic.heat_velocity_pct, topic.velocity_state)}</dd></div>
        <div><dt>报道数量</dt><dd>{topic.mention_count}</dd></div>
        <div><dt>独立来源</dt><dd>{topic.source_count}</dd></div>
        <div><dt>报道热度</dt><dd>{topic.heat_score}</dd></div>
        <div><dt>传播范围</dt><dd>{topic.spread_score}</dd></div>
      </dl>

      <section className="news-detail-section news-detail-reasons">
        <h3><Flame className="h-3.5 w-3.5" />为什么值得看</h3>
        <ul>{topic.signal_reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
      </section>

      {(topic.verification_status !== "常规报道" || topic.framing_divergence) ? (
        <section className="news-detail-section news-detail-warning">
          <h3><AlertTriangle className="h-3.5 w-3.5" />核验与分歧</h3>
          <p>
            {topic.verification_status !== "常规报道" ? (topic.verification_label || topic.verification_status) : "未识别显式传闻或纠正措辞"}
            {topic.framing_divergence ? "；不同来源的报道语气存在分化。" : "。"}
          </p>
        </section>
      ) : null}

      {!!topic.source_frames.length && (
        <section className="news-detail-section">
          <h3>媒体视角</h3>
          <div className="news-frame-list">
            {topic.source_frames.map((frame) => (
              <div key={frame.group}>
                <span>{frame.label}<small>{frame.count} 条</small></span>
                <strong className={sentimentTone(frame.dominant_sentiment)}>{frame.dominant_label}</strong>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="news-detail-section">
        <div className="news-detail-section-title">
          <h3>相关报道 · {titledItems.length}</h3>
          <span>{topic.cross_language ? `已合并 ${topic.language_count} 种语言` : "单一语言"}</span>
        </div>
        <div className="news-source-list">
          {titledItems.map((item) => {
            const itemTitle = chineseItemTitle(item);
            const original = itemOriginalTitle(item, itemTitle);
            return (
              <a
                key={item.id || `${item.source}:${item.url}:${item.title}`}
                href={item.url || undefined}
                target={item.url ? "_blank" : undefined}
                rel="noreferrer"
              >
                <span><strong>{item.source}</strong><small>{item.time}</small></span>
                <p>{itemTitle}</p>
                {original ? <small className="news-source-original" title={original}>外文原文</small> : null}
              </a>
            );
          })}
        </div>
      </section>

      <section className="news-detail-section news-ai-summary">
        <div className="news-detail-section-title">
          <h3><Sparkles className="h-3.5 w-3.5" />AI 事件提炼</h3>
          {(digest.text || digest.err || digest.needKey) ? <button type="button" onClick={() => void generateDigest()}>重新提炼</button> : null}
        </div>
        {digest.loading ? (
          <p className="news-ai-state"><Loader2 className="h-3.5 w-3.5 animate-spin" />正在核对多源报道…</p>
        ) : digest.text ? (
          <><div className="mt-2 text-xs"><ResearchText content={digest.text} /></div><div className="mt-2"><SaveNoteButton kind="新闻事件" title={displayTitle} content={digest.text} /></div></>
        ) : digest.needKey ? (
          <p className="news-ai-state">还没接入 AI。<Link to="/settings" className="text-primary">先接入你的 AI</Link>。</p>
        ) : digest.err ? (
          <p className="news-ai-state text-destructive">{digest.err}</p>
        ) : (
          <button type="button" onClick={() => void generateDigest()} className="news-ai-button">
            <Sparkles className="h-3.5 w-3.5" />提炼事实、变化与待验证项
          </button>
        )}
      </section>
    </article>
  );
}

function NewsMonitorPanel({
  data,
  query,
  setQuery,
  industry,
  setIndustry,
  signal,
  setSignal,
  sort,
  setSort,
  selectedTopicId,
  setSelectedTopicId,
}: {
  data: RadarData;
  query: string; setQuery: (value: string) => void;
  industry: string; setIndustry: (value: string) => void;
  signal: SignalFilter; setSignal: (value: SignalFilter) => void;
  sort: SortMode; setSort: (value: SortMode) => void;
  selectedTopicId: string; setSelectedTopicId: (value: string) => void;
}) {
  const monitor = data.monitor;
  const initialTopics = useMemo(
    () => (monitor?.topics || []).filter(hasTopicTitle),
    [monitor?.topics],
  );
  const summary = monitor?.summary;
  const [visibleTopics, setVisibleTopics] = useState<NewsMonitorTopic[]>(initialTopics);
  const [topicTotal, setTopicTotal] = useState(summary?.topic_count || initialTopics.length);
  const [industryCounts, setIndustryCounts] = useState<Record<string, number>>({});
  const [topicsLoading, setTopicsLoading] = useState(false);
  const [topicsError, setTopicsError] = useState("");
  const requestId = useRef(0);

  useEffect(() => {
    const currentRequest = ++requestId.current;
    const timer = window.setTimeout(async () => {
      setTopicsLoading(true);
      setTopicsError("");
      try {
        const page = await api.radarTopics({ query, industry, signal, sort, offset: 0, limit: 80 });
        if (requestId.current !== currentRequest) return;
        const titledTopics = page.items.filter(hasTopicTitle);
        setVisibleTopics(titledTopics);
        setTopicTotal(page.total);
        setIndustryCounts(page.industry_counts || {});
      } catch {
        if (requestId.current !== currentRequest) return;
        const needle = query.trim().toLocaleLowerCase();
        const fallback = initialTopics.filter((topic) => {
          const matchesQuery = !needle || topicSearchText(topic).includes(needle);
          const matchesIndustry = industry === "all" || topic.industry_key === industry;
          const matchesSignal = signal === "all"
            || (signal === "rising" && ["new", "rising"].includes(topic.velocity_state))
            || (signal === "risk" && ["risk", "mixed"].includes(topic.signal))
            || (signal === "opportunity" && ["opportunity", "mixed"].includes(topic.signal))
            || (signal === "verify" && topic.verification_status !== "常规报道");
          return matchesQuery && matchesIndustry && matchesSignal;
        });
        setVisibleTopics(fallback);
        setTopicTotal(fallback.length);
        setTopicsError("完整主题查询失败，当前显示缓存结果");
      } finally {
        if (requestId.current === currentRequest) setTopicsLoading(false);
      }
    }, query.trim() ? 180 : 0);
    return () => window.clearTimeout(timer);
  }, [data.generated_at_iso, industry, initialTopics, query, signal, sort]);

  const loadMoreTopics = async () => {
    if (topicsLoading || visibleTopics.length >= topicTotal) return;
    const currentRequest = ++requestId.current;
    setTopicsLoading(true);
    setTopicsError("");
    try {
      const page = await api.radarTopics({ query, industry, signal, sort, offset: visibleTopics.length, limit: 80 });
      if (requestId.current !== currentRequest) return;
      setVisibleTopics((current) => [
        ...current,
        ...page.items.filter(hasTopicTitle).filter((topic) => !current.some((item) => item.id === topic.id)),
      ]);
      setTopicTotal(page.total);
      setIndustryCounts(page.industry_counts || {});
    } catch {
      if (requestId.current === currentRequest) setTopicsError("加载更多主题失败");
    } finally {
      if (requestId.current === currentRequest) setTopicsLoading(false);
    }
  };

  const selected = visibleTopics.find((topic) => topic.id === selectedTopicId) || visibleTopics[0];

  if (!monitor || !summary) {
    return <div className="rounded-xl border border-dashed border-border p-10 text-center text-sm text-muted-foreground">监测数据尚未生成，请刷新资讯。</div>;
  }

  return (
    <div className="news-monitor-shell">
      <div className="news-filterbar">
        <label className="news-search">
          <Search className="h-3.5 w-3.5" />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索主题、公司、行业或来源" />
        </label>
        <div className="news-signal-filters">
          {SIGNAL_FILTERS.map(([key, label]) => (
            <button key={key} type="button" onClick={() => setSignal(key)} className={cn(signal === key && "is-active")}>{label}</button>
          ))}
        </div>
        <div className="news-sort">
          <button type="button" onClick={() => setSort("attention")} className={cn(sort === "attention" && "is-active")}>变化优先</button>
          <button type="button" onClick={() => setSort("latest")} className={cn(sort === "latest" && "is-active")}>最新</button>
        </div>
      </div>

      <div className="news-workspace">
        <aside className="news-industry-rail" aria-label="赛道筛选">
          <div className="news-industry-heading"><span>赛道</span><small>已载入 {visibleTopics.length} / 共 {topicTotal}</small></div>
          <button type="button" onClick={() => setIndustry("all")} className={cn(industry === "all" && "is-active")}>
            <span><i style={{ background: "hsl(var(--primary))" }} />全部动态</span><strong>{summary.topic_count}</strong>
          </button>
          {data.industries.map((item) => (
            <button key={item.key} type="button" onClick={() => setIndustry(item.key)} className={cn(industry === item.key && "is-active")}>
              <span><i style={{ background: item.accent }} />{item.name}</span><strong>{industryCounts[item.key] || 0}</strong>
            </button>
          ))}
          {!!monitor.keywords.length && (
            <div className="news-keywords">
              <span>趋势主题</span>
              {monitor.keywords.filter((keyword) => hasChinese(keyword.keyword)).slice(0, 8).map((keyword) => (
                <button key={keyword.keyword} type="button" onClick={() => setQuery(keyword.keyword)}>{keyword.keyword}<small>{keyword.count}</small></button>
              ))}
            </div>
          )}
        </aside>

        <section className="news-topic-panel">
          <header className="news-list-heading">
            <div><strong>{industry === "all" ? "变化中的新闻" : data.industries.find((item) => item.key === industry)?.name}</strong><span>已载入 {visibleTopics.length} / 共 {topicTotal}</span></div>
            <span>{topicsLoading ? <Loader2 className="h-3 w-3 animate-spin" /> : null}中文优先 · 多源合并</span>
          </header>
          <div className="news-topic-list">
            {visibleTopics.length ? visibleTopics.map((topic) => (
              <TopicRow key={topic.id} topic={topic} selected={topic.id === selected?.id} onSelect={() => setSelectedTopicId(topic.id)} />
            )) : <div className="p-10 text-center text-sm text-muted-foreground">当前筛选没有匹配主题</div>}
            {topicsError ? <div className="news-topic-list-note is-error">{topicsError}</div> : null}
            {visibleTopics.length < topicTotal ? (
              <button type="button" className="news-load-more" onClick={() => void loadMoreTopics()} disabled={topicsLoading}>
                {topicsLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}加载更多主题
              </button>
            ) : null}
          </div>
        </section>

        <aside className="news-detail-panel"><TopicDetail topic={selected} /></aside>
      </div>
    </div>
  );
}

function RawNewsPanel({ data }: { data: RadarData }) {
  const [active, setActive] = useState("all");
  const [query, setQuery] = useState("");
  const current = active === "all" ? null : data.industries.find((industry) => industry.key === active) || null;
  const allItems = useMemo(() => {
    const seen = new Set<string>();
    return data.industries.flatMap((industry) => industry.items).filter((item) => {
      const key = item.id || item.url || `${item.source}:${item.title}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    }).sort((left, right) => radarItemTimestamp(right) - radarItemTimestamp(left));
  }, [data.industries]);
  const items = (current?.items || allItems).filter((item) => {
    if (!stripHtml(item.zh) && !stripHtml(item.title)) return false;
    const text = [item.zh, item.title, item.summary, item.source].join(" ").toLocaleLowerCase();
    return !query.trim() || text.includes(query.trim().toLocaleLowerCase());
  });
  return (
    <div className="news-raw-layout">
      <aside className="news-industry-rail">
        <div className="news-industry-heading"><span>赛道</span><small>{data.industries.length}</small></div>
        <button type="button" onClick={() => setActive("all")} className={cn(active === "all" && "is-active")}>
          <span><i style={{ background: "hsl(var(--primary))" }} />全部来源</span><strong>{allItems.length}</strong>
        </button>
        {data.industries.map((item) => (
          <button key={item.key} type="button" onClick={() => setActive(item.key)} className={cn(active === item.key && "is-active")}>
            <span><i style={{ background: item.accent }} />{item.name}</span><strong>{item.items.length}</strong>
          </button>
        ))}
      </aside>
      <section className="news-raw-panel">
        <header className="news-filterbar">
          <label className="news-search">
            <Search className="h-3.5 w-3.5" />
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={active === "all" ? "搜索全部新闻、来源或主题" : "搜索当前赛道新闻"} />
          </label>
          <span className="news-result-count">{items.length} 条资讯</span>
        </header>
        <div className="news-raw-list">
          {items.map((item) => {
            const title = chineseItemTitle(item);
            const original = itemOriginalTitle(item, title);
            return (
              <a key={item.id || `${item.source}:${item.url}:${item.title}`} href={item.url || undefined} target={item.url ? "_blank" : undefined} rel="noreferrer" data-sentiment={item.sentiment || "neutral"}>
                <span className="news-topic-accent" aria-hidden="true" />
                <span className="news-raw-time">{item.time}</span>
                <span className="news-raw-source">{item.source}</span>
                <span className="news-raw-copy"><strong>{title}</strong>{original ? <small title={original}>外文原文</small> : null}</span>
                {item.sentiment ? <span className={cn("news-badge", sentimentTone(item.sentiment))}>{SENTIMENT_LABEL[item.sentiment]}</span> : null}
                <ExternalLink className="h-3.5 w-3.5" />
              </a>
            );
          })}
          {!items.length && <p className="p-10 text-center text-sm text-muted-foreground">当前筛选暂无资讯</p>}
        </div>
      </section>
    </div>
  );
}

type FeedRelevance = "direct" | "related" | "mention";
type FeedTone = "positive" | "negative" | "warning" | "neutral";

interface FeedStock {
  code: string;
  name: string;
}

interface FeedRow {
  stocks: FeedStock[];
  when: string;
  title: string;
  meta?: string;
  source?: string;
  summary?: string;
  url?: string;
  relevance?: FeedRelevance;
}
const MAX_ROWS = 120;
const RELEVANCE_WEIGHT: Record<FeedRelevance, number> = { direct: 3, related: 2, mention: 1 };
const FILING_TONE_WEIGHT: Record<FeedTone, number> = { negative: 3, positive: 2, warning: 1, neutral: 0 };

function feedTimestamp(value: string) {
  const parsed = Date.parse((value || "").trim().replace(" ", "T"));
  return Number.isNaN(parsed) ? 0 : parsed;
}

function feedDateLabel(value: string) {
  const parsed = feedTimestamp(value);
  if (!parsed) return value.slice(0, 10) || "时间未知";
  const date = new Date(parsed);
  const today = new Date();
  const dayStart = (input: Date) => new Date(input.getFullYear(), input.getMonth(), input.getDate()).getTime();
  const days = Math.round((dayStart(today) - dayStart(date)) / 86_400_000);
  if (days === 0) return "今天";
  if (days === 1) return "昨天";
  const monthDay = new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit" }).format(date);
  const weekday = new Intl.DateTimeFormat("zh-CN", { weekday: "short" }).format(date);
  return `${monthDay} ${weekday}`;
}

function feedTimeLabel(value: string) {
  const parsed = feedTimestamp(value);
  if (!parsed) return value.slice(11, 16) || "—";
  return new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false }).format(parsed);
}

function normalizeFeedText(value: string | undefined, limit = 120) {
  const text = stripHtml(value).replace(/^（[^）]{0,18}）\s*/, "");
  return text.length > limit ? `${text.slice(0, limit)}…` : text;
}

function filingTone(value: string | undefined): FeedTone {
  const text = String(value || "");
  if (/风险|处罚|诉讼|质押|冻结|减持|终止|异常|亏损|退市|立案|担保/.test(text)) return "negative";
  if (/业绩|分配|回购|增持|中标|重组|股权激励/.test(text)) return "positive";
  if (/审计|高管|董事|注册资本|投资|融资|关联交易|股份变动/.test(text)) return "warning";
  return "neutral";
}

function newsRelevance(item: NewsItem, code: string, name: string): FeedRelevance {
  const title = stripHtml(item.新闻标题);
  const summary = stripHtml(item.新闻内容);
  if ((name && title.includes(name)) || title.includes(code)) return "direct";
  const lead = summary.slice(0, 140);
  if ((name && lead.includes(name)) || lead.includes(code)) return "related";
  return "mention";
}

function newsRelevanceLabel(value: FeedRelevance | undefined, stockCount: number) {
  if (stockCount > 1) return `提及 ${stockCount} 只自选`;
  if (value === "direct") return "直接相关";
  if (value === "related") return "正文相关";
  return "榜单提及";
}

function watchNewsSummary(value: string | undefined, relevance: FeedRelevance) {
  const summary = normalizeFeedText(value, 150);
  if (!summary) return "";
  const numericRatio = (summary.match(/[\d.%+-]/g)?.length || 0) / summary.length;
  if (relevance === "mention" && numericRatio > 0.18) return "行业、资金或榜单资讯中提及该自选股";
  return summary;
}

function compactFeedRows(rows: FeedRow[]) {
  const merged = new Map<string, FeedRow>();
  for (const row of rows) {
    const key = row.url || `${row.when.slice(0, 10)}:${row.title.replace(/\s+/g, " ").trim()}`;
    const current = merged.get(key);
    if (!current) {
      merged.set(key, { ...row, stocks: [...row.stocks] });
      continue;
    }
    for (const stock of row.stocks) {
      if (!current.stocks.some((item) => item.code === stock.code)) current.stocks.push(stock);
    }
    if ((RELEVANCE_WEIGHT[row.relevance || "mention"] || 0) > (RELEVANCE_WEIGHT[current.relevance || "mention"] || 0)) {
      current.relevance = row.relevance;
    }
    if ((row.summary?.length || 0) > (current.summary?.length || 0)) current.summary = row.summary;
  }
  return Array.from(merged.values());
}

function cachedFeedRows(rows: FeedRow[]) {
  return rows.filter((row) => Array.isArray(row.stocks) && row.stocks.length > 0);
}

function feedStockLabel(stocks: FeedStock[]) {
  if (stocks.length <= 1) return stocks[0]?.name || "未知标的";
  if (stocks.length === 2) return `${stocks[0].name} / ${stocks[1].name}`;
  return `${stocks[0].name} 等 ${stocks.length} 只`;
}

function WatchlistFeed({ kind }: { kind: "filings" | "news" }) {
  const [codes, setCodes] = useState<string[]>(loadWatch);
  const feedCache = useMemo(() => createVibeDeskSnapshotCache<FeedRow[]>(`news-watch:${kind}`, 2, 1024 * 1024), [kind]);
  const [rows, setRows] = useState<FeedRow[]>(() => cachedFeedRows(feedCache.read()?.value || []));
  const rowsRef = useRef(rows);
  rowsRef.current = rows;
  const [query, setQuery] = useState("");
  const [activeCode, setActiveCode] = useState("all");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [depNote, setDepNote] = useState<string | null>(null);

  const load = useCallback(async (symbols: string[]) => {
    if (!symbols.length) { setRows([]); return; }
    setLoading(true); setErr(null); setDepNote(null);
    try {
      const nameOf: Record<string, string> = {};
      try {
        const quotes = await api.quote(symbols.join(","));
        for (const symbol of symbols) if (quotes[symbol]?.name) nameOf[symbol] = quotes[symbol].name;
      } catch { /* Name enrichment is optional. */ }

      const output: FeedRow[] = [];
      if (kind === "filings") {
        const responses = await Promise.all(symbols.map((symbol) => api.announcements(symbol)
          .then((items) => ({ symbol, items }))
          .catch(() => ({ symbol, items: [] as Announcement[] }))));
        for (const { symbol, items } of responses) for (const item of items) output.push({
          stocks: [{ code: symbol, name: nameOf[symbol] || symbol }], when: item.date,
          title: item.title.replace(/^[^:：]*[:：]/, ""), meta: item.type, url: item.url,
        });
      } else {
        let dependency: string | null = null;
        const responses = await Promise.all(symbols.map((symbol) => api.news(symbol)
          .then((items) => ({ symbol, items }))
          .catch((reason) => {
            if (reason instanceof ApiError && reason.status === 501) dependency = reason.message;
            return { symbol, items: [] as NewsItem[] };
          })));
        for (const { symbol, items } of responses) for (const item of items) {
          const name = nameOf[symbol] || symbol;
          const relevance = newsRelevance(item, symbol, name);
          output.push({
            stocks: [{ code: symbol, name }], when: item.发布时间 || "",
            title: item.新闻标题 || "", source: item.文章来源 || "公开新闻",
            summary: watchNewsSummary(item.新闻内容, relevance), url: item.新闻链接, relevance,
          });
        }
        if (dependency && output.length === 0) setDepNote(dependency);
      }
      const nextRows = compactFeedRows(output).sort((left, right) => {
        const timeDifference = feedTimestamp(right.when) - feedTimestamp(left.when);
        if (timeDifference) return timeDifference;
        if (kind === "news") return RELEVANCE_WEIGHT[right.relevance || "mention"] - RELEVANCE_WEIGHT[left.relevance || "mention"];
        const rightTone = filingTone(`${right.meta || ""} ${right.title}`);
        const leftTone = filingTone(`${left.meta || ""} ${left.title}`);
        return FILING_TONE_WEIGHT[rightTone] - FILING_TONE_WEIGHT[leftTone];
      }).slice(0, MAX_ROWS);
      setRows(nextRows);
      feedCache.write(nextRows);
    } catch (reason) {
      setErr(rowsRef.current.length ? "更新失败，正在显示上次数据" : reason instanceof ApiError ? reason.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [feedCache, kind]);

  useEffect(() => { const symbols = loadWatch(); setCodes(symbols); void load(symbols); }, [load]);
  const refresh = () => { const symbols = loadWatch(); setCodes(symbols); void load(symbols); };

  const counts = useMemo(() => {
    const result = new Map<string, number>();
    for (const row of rows) for (const stock of row.stocks) result.set(stock.code, (result.get(stock.code) || 0) + 1);
    return result;
  }, [rows]);
  const stocks = useMemo(() => Array.from(new Map(rows.flatMap((row) => row.stocks.map((stock) => [stock.code, stock.name] as const))).entries()), [rows]);
  const visibleRows = useMemo(() => rows.filter((row) => {
    const matchesCode = activeCode === "all" || row.stocks.some((stock) => stock.code === activeCode);
    const needle = query.trim().toLocaleLowerCase();
    const matchesQuery = !needle || [...row.stocks.flatMap((stock) => [stock.name, stock.code]), row.title, row.meta, row.source, row.summary]
      .join(" ").toLocaleLowerCase().includes(needle);
    return matchesCode && matchesQuery;
  }), [activeCode, query, rows]);
  const groups = useMemo(() => {
    const output: Array<{ label: string; rows: FeedRow[] }> = [];
    for (const row of visibleRows) {
      const label = feedDateLabel(row.when);
      const current = output[output.length - 1];
      if (current?.label === label) current.rows.push(row);
      else output.push({ label, rows: [row] });
    }
    return output;
  }, [visibleRows]);

  if (!codes.length) return (
    <div className="rounded-lg border border-dashed border-border/70 p-8 text-center text-sm text-muted-foreground">
      还没有关注股票。到<Link to="/daily-review" className="text-primary">「每日复盘」</Link>添加自选，这里会汇总近期{kind === "filings" ? "公告" : "新闻"}。
    </div>
  );

  return (
    <section className={cn("news-watch-panel", `is-${kind}`)}>
      <header className="news-watch-header">
        <div>
          <strong>{kind === "filings" ? "A股公告" : "自选新闻"}</strong>
          <span>{codes.length} 只自选 · 展示 {visibleRows.length} / {rows.length} 条</span>
        </div>
        <label className="news-watch-search">
          <Search className="h-3.5 w-3.5" />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={kind === "filings" ? "搜索公司、公告或类型" : "搜索公司、新闻或来源"} />
        </label>
        <button type="button" onClick={refresh} disabled={loading}>
          {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}{loading ? "更新中" : "更新"}
        </button>
      </header>
      <nav className="news-watch-stocks" aria-label="自选股票筛选">
        <button type="button" className={cn(activeCode === "all" && "is-active")} onClick={() => setActiveCode("all")}>
          全部 <small>{rows.length}</small>
        </button>
        {stocks.map(([code, name]) => (
          <button key={code} type="button" className={cn(activeCode === code && "is-active")} onClick={() => setActiveCode(code)}>
            {name}<small>{counts.get(code) || 0}</small>
          </button>
        ))}
      </nav>
      {err && <div className="news-inline-error"><AlertCircle className="h-3.5 w-3.5" />{err}</div>}
      {loading && !rows.length ? (
        <p className="news-watch-loading"><Loader2 className="h-3.5 w-3.5 animate-spin" />正在汇总自选{kind === "filings" ? "公告" : "新闻"}…</p>
      ) : depNote ? <p className="p-8 text-center text-xs text-warning">{depNote}</p> : groups.length ? (
        <div className="news-watch-feed">
          {groups.map((group) => (
            <section key={group.label} className="news-watch-day">
              <h3>{group.label}<small>{group.rows.length} 条</small></h3>
              <div>
                {group.rows.map((row, index) => {
                  const filing = filingTone(`${row.meta || ""} ${row.title}`);
                  const stockTitle = row.stocks.map((stock) => `${stock.name} ${stock.code}`).join("、");
                  return (
                    <a
                      key={`${row.stocks.map((stock) => stock.code).join("-")}:${row.when}:${row.title}:${index}`}
                      href={row.url || undefined}
                      target={row.url ? "_blank" : undefined}
                      rel="noreferrer"
                      data-tone={kind === "filings" ? filing : undefined}
                      data-relevance={kind === "news" ? row.relevance : undefined}
                    >
                      {kind === "news" ? <span className="news-watch-time">{feedTimeLabel(row.when)}</span> : null}
                      <span className="news-watch-company" title={stockTitle}>
                        <strong>{feedStockLabel(row.stocks)}</strong>
                        <small>{row.stocks.length === 1 ? row.stocks[0].code : `${row.stocks.length} 只自选`}</small>
                      </span>
                      <span className="news-watch-copy">
                        <strong>{row.title}</strong>
                        {kind === "news" && row.summary ? <small>{row.summary}</small> : null}
                      </span>
                      <span className="news-watch-meta">
                        {kind === "filings" && row.meta ? <em className={`is-${filing}`}>{row.meta}</em> : null}
                        {kind === "news" ? <><em>{row.source || "公开新闻"}</em><small className={`is-${row.relevance || "mention"}`}>{newsRelevanceLabel(row.relevance, row.stocks.length)}</small></> : null}
                      </span>
                      {row.url && <ExternalLink className="h-3.5 w-3.5" />}
                    </a>
                  );
                })}
              </div>
            </section>
          ))}
        </div>
      ) : <p className="p-10 text-center text-sm text-muted-foreground">当前筛选暂无{kind === "filings" ? "公告" : "新闻"}</p>}
    </section>
  );
}

function newsContext(input: {
  tab: TabKey; data: RadarData | null; selectedTopicId: string;
  query: string; industry: string; signal: SignalFilter; sort: SortMode; loading: boolean;
  crucix: CrucixSnapshot | null;
  linkedSubject?: VibeDeskWikiSubject;
}): VibeDeskPageContext {
  const selected = input.data?.monitor?.topics.find((topic) => topic.id === input.selectedTopicId);
  const primarySubject = input.linkedSubject ?? (selected ? {
    type: "topic" as const,
    canonicalId: `topic:news:${encodeURIComponent(selected.id).slice(0, 200)}`,
    displayName: selected.headline || selected.label,
  } : undefined);
  return {
    view: { id: "news-radar", title: "新闻与舆情" },
    visibleBlocks: [
      { id: "news-monitor-summary", type: "monitor-metrics", title: "舆情监测摘要" },
      { id: "news-topic-clusters", type: "topic-clusters", title: "新闻主题事件簇" },
      { id: "news-topic-evidence", type: "evidence-detail", title: "事件证据与来源视角" },
      { id: "crucix-news", type: "external-intelligence", title: "Crucix 全球公开源快讯" },
      { id: "watchlist-news", type: "watchlist-feed", title: "自选股公告与新闻" },
    ],
    selection: { tab: input.tab, topicId: selected?.id || null, topic: selected || null },
    filters: { query: input.query, industry: input.industry, signal: input.signal, sort: input.sort },
    data: {
      asOf: input.data?.generated_at_iso || input.data?.generated_at || new Date().toISOString(),
      source: "newma-desk.news-monitor.v1",
      freshness: input.loading ? "unknown" : dataFreshness(input.data).stale ? "stale" : "fresh",
      summary: {
        monitor: input.data?.monitor?.summary || null,
        sourceHealth: input.data?.stats || null,
        crucix: input.crucix ? {
          asOf: input.crucix.asOf,
          newsCount: input.crucix.news.length,
          sourceHealth: input.crucix.sourceHealth,
        } : null,
        caveat: input.data?.monitor?.caveat || null,
      },
    },
    actions: [{
      id: "news.refresh",
      label: "刷新新闻与舆情",
      available: !input.loading,
      inputSchema: { type: "object", additionalProperties: false },
    }],
    ...(primarySubject ? {
      wiki: {
        primarySubject,
        relatedSubjects: [],
        conceptIds: [],
        intent: "news.monitor",
      },
    } : {}),
    tasks: input.loading ? [{ id: "news-radar-refresh", status: "running", actionId: "news.refresh" }] : [],
  };
}

export function Intel() {
  const integrated = import.meta.env.VITE_NEWMA_DESK_INTEGRATED === "1";
  const radarCache = useMemo(() => createVibeDeskSnapshotCache<RadarData>("news-radar", 1, 2 * 1024 * 1024), []);
  const [tab, setTab] = useState<TabKey>("monitor");
  const [data, setData] = useState<RadarData | null>(() => radarCache.read()?.value ?? null);
  const dataRef = useRef(data);
  dataRef.current = data;
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [industry, setIndustry] = useState("all");
  const [signal, setSignal] = useState<SignalFilter>("all");
  const [sort, setSort] = useState<SortMode>("attention");
  const [selectedTopicId, setSelectedTopicId] = useState("");
  const [linkedSubject, setLinkedSubject] = useState<VibeDeskWikiSubject>();
  const [crucix, setCrucix] = useState<CrucixSnapshot | null>(null);
  const [crucixLoading, setCrucixLoading] = useState(true);
  const [crucixError, setCrucixError] = useState("");

  const loadCrucix = useCallback(async () => {
    setCrucixLoading(true);
    setCrucixError("");
    try {
      setCrucix(await loadCrucixSnapshot());
    } catch (reason) {
      setCrucixError(reason instanceof Error ? reason.message : "Crucix 数据暂未就绪");
    } finally {
      setCrucixLoading(false);
    }
  }, []);

  const loadRadar = useCallback(async (force = false, silent = false) => {
    if (force) setRefreshing(true);
    else if (!silent) setLoading(true);
    if (!silent) setError("");
    const cached = radarCache.read()?.value;
    if (!dataRef.current && cached) setData(cached);
    try {
      const next = force ? await api.radarRefresh() : await api.radar();
      setData(next);
      dataRef.current = next;
      radarCache.write(next, next.generated_at_iso || next.generated_at || undefined);
      return next;
    } catch (reason) {
      if (!silent) {
        setError(dataRef.current || cached
          ? "更新失败，正在显示上次数据"
          : reason instanceof ApiError ? reason.message : "资讯雷达暂时不可用");
      }
      return null;
    } finally {
      if (!silent) setLoading(false);
      if (force) setRefreshing(false);
    }
  }, [radarCache]);

  useEffect(() => { void loadRadar(); }, [loadRadar]);
  useEffect(() => { void loadCrucix(); }, [loadCrucix]);
  useEffect(() => {
    const interval = window.setInterval(
      () => void loadRadar(false, true),
      data?.refresh?.refreshing ? 8_000 : 60_000,
    );
    return () => window.clearInterval(interval);
  }, [data?.refresh?.refreshing, loadRadar]);
  useEffect(() => subscribeVibeDeskConfig(() => {
    const cached = radarCache.read()?.value ?? null;
    dataRef.current = cached;
    setData(cached);
    void loadRadar();
    void loadCrucix();
  }), [loadCrucix, loadRadar, radarCache]);
  useEffect(() => {
    const topics = (data?.monitor?.topics || []).filter(hasTopicTitle);
    if (topics.length && !topics.some((topic) => topic.id === selectedTopicId)) setSelectedTopicId(topics[0].id);
  }, [data, selectedTopicId]);

  const contextRef = useRef<VibeDeskPageContext>(newsContext({ tab, data, selectedTopicId, query, industry, signal, sort, loading: loading || refreshing, crucix, linkedSubject }));
  contextRef.current = newsContext({ tab, data, selectedTopicId, query, industry, signal, sort, loading: loading || refreshing, crucix, linkedSubject });
  useEffect(() => registerVibeDeskContextProvider(() => contextRef.current), []);
  useEffect(() => registerVibeDeskHandoffHandler((handoff) => {
    if (!["security", "etf", "fund", "topic"].includes(handoff.subject.type)) {
      throw new Error("新闻模块不支持该 Wiki 对象");
    }
    setLinkedSubject(handoff.subject);
    setTab("monitor");
    setQuery(handoff.subject.displayName);
    setIndustry("all");
    setSignal("all");
    return { selected: handoff.subject.canonicalId };
  }), []);
  useEffect(() => registerVibeDeskUiActionHandler(async (actionId) => {
    if (actionId !== "news.refresh") throw new Error(`不支持页面动作：${actionId}`);
    const next = await loadRadar(true);
    if (!next) throw new Error("新闻与舆情刷新失败");
    return { refreshedAt: next.generated_at_iso || next.generated_at, summary: next.monitor?.summary || null };
  }), [loadRadar]);
  useEffect(() => { void publishVibeDeskContext(); }, [crucix, data, industry, linkedSubject, loading, query, refreshing, selectedTopicId, signal, sort, tab]);

  const freshness = dataFreshness(data);
  const summary = data?.monitor?.summary;
  const radarTab = tab === "monitor" || tab === "raw";
  const isUpdating = refreshing || Boolean(data?.refresh?.refreshing);
  const radarTitleKeys = useMemo(() => new Set(
    (data?.monitor?.topics || []).flatMap((topic) => [
      topic.headline,
      ...topic.items.flatMap((item) => [item.title, item.zh]),
    ]).map((title) => titleKey(title || "")).filter(Boolean),
  ), [data]);
  const crucixNews = useMemo(() => (crucix?.news || [])
    .filter((item) => item.title.trim() && !radarTitleKeys.has(titleKey(item.title)))
    .sort((left, right) => Number(right.urgent) - Number(left.urgent)
      || Date.parse(right.publishedAt || "") - Date.parse(left.publishedAt || "")), [crucix, radarTitleKeys]);
  return (
    <div className="news-page">
      <header className="news-page-header">
        {!integrated ? (
          <div className="news-page-title">
            <h1>新闻与舆情</h1>
            <p>先看新闻，再看热度、情绪、传播范围与来源分歧。</p>
          </div>
        ) : null}
        <nav className="news-page-tabs" aria-label="新闻与舆情栏目">
          {TABS.map(({ key, label, icon: Icon }) => (
            <button key={key} type="button" onClick={() => setTab(key)} className={cn(tab === key && "is-active")}>
              <Icon className="h-3.5 w-3.5" />{label}
            </button>
          ))}
        </nav>
        {radarTab ? <div className="news-page-actions">
          {data?.generated_at ? (
            <span className={cn("news-freshness", freshness.stale && "is-stale")}>
              <Clock3 className="h-3.5 w-3.5" />数据 {freshness.label}
            </span>
          ) : null}
          <button type="button" onClick={() => { void loadRadar(true); void loadCrucix(); }} disabled={isUpdating || crucixLoading} className="news-refresh-button">
            {isUpdating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}{isUpdating ? "更新中" : "刷新"}
          </button>
        </div> : null}
      </header>

      {summary && tab === "monitor" ? (
        <section className="news-summary-strip" aria-label="舆情监测摘要">
          <SummaryItem label="条新闻" value={summary.analyzed_items} />
          <SummaryItem label="总主题" value={summary.topic_count} />
          <SummaryItem label="风险" value={summary.risk_topic_count} tone="negative" />
          <SummaryItem label="机会" value={summary.opportunity_topic_count} tone="positive" />
          <SummaryItem label="正在升温" value={summary.rising_topic_count || 0} tone="warning" />
          <SummaryItem label="待核验" value={summary.flagged_topic_count} tone="warning" />
          <span className="news-sentiment-bar">
            <small>报道语气</small>
            <i><b style={{ width: `${summary.sentiment.positive_pct || 0}%` }} /><b style={{ width: `${summary.sentiment.neutral_pct || 0}%` }} /><b style={{ width: `${(summary.sentiment.negative_pct || 0) + (summary.sentiment.mixed_pct || 0)}%` }} /></i>
            <span><em>正面 {summary.sentiment.positive_pct || 0}%</em><em>中性 {summary.sentiment.neutral_pct || 0}%</em><em>负面 {summary.sentiment.negative_pct || 0}%</em></span>
          </span>
          {data ? <SourceHealthDetails data={data} stale={freshness.stale} /> : null}
        </section>
      ) : null}

      {error && <div className="news-inline-error"><AlertCircle className="h-4 w-4" />{error}</div>}
      {tab === "monitor" ? <CrucixNewsPanel items={crucixNews} snapshot={crucix} loading={crucixLoading} error={crucixError} /> : null}
      {loading && !data ? (
        <div className="news-loading"><Loader2 className="h-4 w-4 animate-spin" />正在载入新闻与舆情…</div>
      ) : data ? (
        tab === "monitor" ? <NewsMonitorPanel data={data} query={query} setQuery={setQuery} industry={industry} setIndustry={setIndustry} signal={signal} setSignal={setSignal} sort={sort} setSort={setSort} selectedTopicId={selectedTopicId} setSelectedTopicId={setSelectedTopicId} />
          : tab === "raw" ? <RawNewsPanel data={data} />
            : tab === "filings" ? <WatchlistFeed key="filings" kind="filings" />
              : <WatchlistFeed key="news" kind="news" />
      ) : null}

      <details className="news-method-note">
        <summary><ChevronDown className="h-3.5 w-3.5" />监测口径</summary>
        <p><Languages className="h-3 w-3" />跨语言仅在同一事件证据充分时合并。</p>
        <p><Rss className="h-3 w-3" />报道热度来自公开媒体数量，不代表社交讨论量。</p>
        <p><ShieldAlert className="h-3 w-3" />情绪表示报道语气，不代表事实真伪或资产涨跌。</p>
      </details>
      <Disclaimer compact />
    </div>
  );
}
