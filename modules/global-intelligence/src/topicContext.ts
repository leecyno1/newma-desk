import type { ModPageContext } from "@newma-desk/contracts";
import type { MaritimeView } from "./TopicMaritime";

export const GLOBAL_TOPICS = {
  "fed-rates": { id: "fed-rates", title: "联储加息" },
  hormuz: { id: "hormuz-conflict", title: "美伊战争" },
  "us-china-trade": { id: "us-china-trade", title: "中美贸易" },
} as const;

export type GlobalTopicId = keyof typeof GLOBAL_TOPICS;

export const TOPIC_BASELINE_WARNING = "指标、曲线和事件为内置示例，未经实时来源核验；来源链接仅为核验入口，不构成对应事件的证据。";

export function buildGlobalTopicContext(topicId: GlobalTopicId, state: Record<string, unknown>): ModPageContext {
  const view = GLOBAL_TOPICS[topicId];
  const summary = state.topicId === topicId ? state : { topicId, loadState: "loading" };
  const maritimeView = summary.maritimeView as MaritimeView | undefined;
  return {
    view,
    visibleBlocks: summary.metrics ? [
      { id: "topic-metrics", type: "metrics", title: "来源观测" },
      { id: "topic-chart", type: "chart", title: "核心变量" },
      { id: "topic-forecast", type: "scenario-model", title: "情景推演" },
      { id: "topic-transmission", type: "transmission-chain", title: "影响传导链" },
      { id: "topic-events", type: "event-stream", title: "来源事件与文件" },
      { id: "topic-sources", type: "source-health", title: "数据接入" },
      ...(summary.maritime ? [{ id: "topic-maritime", type: "source-records", title: "霍尔木兹与周边航行警告" }] : []),
      ...(maritimeView?.selectedWarning ? [{ id: "topic-maritime-detail", type: "document", title: maritimeView.selectedWarning.reference }] : []),
    ] : [],
    selection: { topicId, ...(maritimeView ? { warningId: maritimeView.selectedWarning?.id ?? null } : {}) },
    filters: {
      factors: summary.factors ?? {}, timeRange: summary.timeRange ?? null,
      ...(maritimeView ? { maritime: { scope: maritimeView.scope, query: maritimeView.query, sort: maritimeView.sort, coverage: maritimeView.filterCoverage } } : {}),
    },
    data: {
      source: "global-topics",
      freshness: summary.displayingPreviousData ? "stale" : summary.dataMode !== "reference-baseline" && (summary.freshness === "fresh" || summary.freshness === "stale") ? summary.freshness : "unknown",
      summary: {
        ...summary,
        title: view.title,
        dataWarning: summary.dataWarning ?? TOPIC_BASELINE_WARNING,
        timeSemantics: "generatedAt 是响应生成时间，不是数据采集时间。每项 metric.date 按 dateBasis 分为数据期或检索时间；月度YYYY-MM不是月初发布时间。GSCPI.vintage是来源修订列标识，不是已核发布日期或点时版本；basisVerified只核口径，不保证实时，缺月/不同修订列/未核验点不能视为连续变化。missing/rejected保留原缺失回执，未知不补零；metric.collectedAt保留该指标原采集时间，不借整批时间。sourceStatus.collectedAt、event.collectedAt 为成功读取时间，event.publishedAt 为原始发布时间或仅日期。event.evidenceKey 是同一来源 URL 的跨页引用键，不等于多源事件已核实或合并。eventCoverage.count 为已载入的来源事件数，0 不代表没有事件发生。事件公布日期不代表生效日期；不同频率、不同来源不能用一个全局日期代替。",
        forecastSemantics: "factors 是当前编辑参数，forecastFactors 是当前结果实际使用的参数；forecastPending=true 时结果尚未按当前参数重算。撤销未提交修改只恢复当前结果的参数，不发请求或撤销服务端操作。factorDefinitions.direction是模型设定系数；scenarioOrder来自专题模型配置，正系数上调偏向末项、负系数偏向首项，不是来源观测、统计估计或因果证据；缺少配置时不推断方向。transmission仅机制示意，不证明因果已经发生。forecastOrigin=saved 表示从当前作用域已保存记录恢复或本次保存成功，forecastSavedAt 是该次推演记录时间，不是来源观测时间；刷新不会按新观测自动重算。forecastRecovery 是本浏览器待核验提交的参数、时间及本地编号，编号不是服务端任务ID；readbackReady只代表本次提交后已成功读取快照，不证明原操作成功或取消。unconfirmed不自动重发，用户核对后仅手动解除本地保护；不是持久幂等或跨设备锁。情景权重和模型指标未经过统计校准，不代表真实发生概率或证据可信度。",
        ...(summary.maritime ? { maritimeSemantics: "maritime 与页面使用同一份警告证据。publishedAt 是公告发布时刻，collectedAt 是源快照成功采集时间；status=stale 时必须标明旧快照。scannedCount/matchedCount/counts 只描述此快照筛选结果，不能证明无警告、航道中断或风险高低。区域性公告、附近坐标与明确提及霍尔木兹必须区分；源记录未取消不代表当前有效。maritimeView.visibleWarningIds 是筛选后显示集合，selectedWarning 是当前展开的公告；用户说“这条”时优先针对该记录，未选中则不能擅自指定。筛选只覆盖已载入记录，不代表全部来源。" } : {}),
      },
    },
    actions: [
      { id: "global-intel.refresh", label: "刷新专题", available: summary.loadState !== "loading" && summary.forecastStatus !== "running", inputSchema: { type: "object", additionalProperties: false } },
      { id: "workspace.save-layout", label: "保存当前视图", available: Boolean(summary.metrics), inputSchema: { type: "object", properties: { name: { type: "string", maxLength: 80 } }, additionalProperties: false } },
    ],
    tasks: [],
  };
}
