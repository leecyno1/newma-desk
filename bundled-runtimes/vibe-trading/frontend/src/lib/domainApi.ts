import { apiUrl, request } from "@/lib/apiClient";
import { withAuthQuery } from "@/lib/apiAuth";
import type {
  AlphaBenchJob,
  AlphaBenchRequest,
  AlphaCompareJob,
  AlphaCompareRequest,
  AlphaDetailResponse,
  AlphaListParams,
  AlphaListResponse,
  CommitMandateRequest,
  CommitMandateResponse,
  DataSourceSettings,
  HaltLiveResponse,
  LiveAuthorizeResponse,
  LiveRunnerResponse,
  LiveStatus,
  PineScriptResult,
  QuickRunRequest,
  QuickRunResponse,
  QuickRunStatusResponse,
  RunData,
  RunDetailParams,
  RunListItem,
  UpdateDataSourceSettingsRequest,
} from "./api";

export {
  API_BASE,
  AUTH_REQUIRED_MESSAGE,
  ApiError,
  apiUrl,
  isAuthRequiredError,
} from "@/lib/apiClient";
export type * from "./api";

/** Domain-only Trading interface used by the Newma-Desk integrated build. */
export const domainApi = {
  listRuns: (limit?: number) =>
    request<RunListItem[]>(
      `/runs${limit ? `?limit=${encodeURIComponent(String(limit))}` : ""}`,
    ),
  createQuickRun: (body: QuickRunRequest) =>
    request<QuickRunResponse>("/runs/quick", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  getRunStatus: (id: string) =>
    request<QuickRunStatusResponse>(`/runs/${encodeURIComponent(id)}/status`),
  cancelRun: (id: string) =>
    request<{ status: string }>(`/runs/${encodeURIComponent(id)}/cancel`, {
      method: "POST",
    }),
  getRun: (id: string, params: RunDetailParams = {}) => {
    const q = new URLSearchParams();
    if (params.chart_payload) q.set("chart_payload", params.chart_payload);
    if (params.chart_symbol) q.set("chart_symbol", params.chart_symbol);
    const query = q.toString();
    return request<RunData>(`/runs/${id}${query ? `?${query}` : ""}`);
  },
  getRunCode: (id: string) => request<Record<string, string>>(`/runs/${id}/code`),
  getRunPine: (id: string) => request<PineScriptResult>(`/runs/${id}/pine`),

  getDataSourceSettings: () =>
    request<DataSourceSettings>("/settings/data-sources"),
  updateDataSourceSettings: (settings: UpdateDataSourceSettingsRequest) =>
    request<DataSourceSettings>("/settings/data-sources", {
      method: "PUT",
      body: JSON.stringify(settings),
    }),

  listAlphas: (params: AlphaListParams = {}) => {
    const q = new URLSearchParams();
    if (params.zoo) q.set("zoo", params.zoo);
    if (params.theme) q.set("theme", params.theme);
    if (params.universe) q.set("universe", params.universe);
    if (params.limit !== undefined) q.set("limit", String(params.limit));
    const query = q.toString();
    return request<AlphaListResponse>(`/alpha/list${query ? `?${query}` : ""}`);
  },
  getAlpha: (alphaId: string) =>
    request<AlphaDetailResponse>(`/alpha/${encodeURIComponent(alphaId)}`),
  createAlphaBench: (body: AlphaBenchRequest) =>
    request<{ status: string; job_id: string }>("/alpha/bench", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  getAlphaBench: (jobId: string) =>
    request<AlphaBenchJob>(`/alpha/bench/${encodeURIComponent(jobId)}`),
  alphaBenchStreamUrl: (jobId: string) =>
    withAuthQuery(apiUrl(`/alpha/bench/${encodeURIComponent(jobId)}/stream`)),
  createAlphaCompare: (body: AlphaCompareRequest) =>
    request<{ status: string; job_id: string }>("/alpha/compare", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  getAlphaCompare: (jobId: string) =>
    request<AlphaCompareJob>(`/alpha/compare/${encodeURIComponent(jobId)}`),
  alphaCompareStreamUrl: (jobId: string) =>
    withAuthQuery(apiUrl(`/alpha/compare/${encodeURIComponent(jobId)}/stream`)),

  commitMandate: (body: CommitMandateRequest) =>
    request<CommitMandateResponse>("/mandate/commit", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  haltLive: (session_id?: string, broker?: string, reason?: string) =>
    request<HaltLiveResponse>("/live/halt", {
      method: "POST",
      body: JSON.stringify({ session_id, broker, reason }),
    }),
  getLiveStatus: (signal?: AbortSignal) =>
    request<LiveStatus>("/live/status", { signal }),
  authorizeLive: (broker: string) =>
    request<LiveAuthorizeResponse>("/live/authorize", {
      method: "POST",
      body: JSON.stringify({ broker }),
    }),
  startLiveRunner: (broker: string) =>
    request<LiveRunnerResponse>("/live/runner/start", {
      method: "POST",
      body: JSON.stringify({ broker }),
    }),
  stopLiveRunner: (broker: string) =>
    request<LiveRunnerResponse>("/live/runner/stop", {
      method: "POST",
      body: JSON.stringify({ broker }),
    }),
};

export const api = domainApi;
