import { useEffect, useMemo, useState } from "react";

export interface ArchiveRow {
  signalDate: string; capturedAt: string | null; candidateCount: number; eligibleCount: number | null;
  controlCount: number | null; controlStatus: "saved" | "missing"; baselineStart: string | null; baselineEnd: string | null;
  rules: { id: string; baselineDays: number; minAmountYi: number; minOwnRatio: number; minMarketAdjustedRatio: number } | null;
  marketMedianRatio: number | null; mode: "recorded"; verification: "not-evaluated";
  captureSource?: string;
}
export interface CollectionStatus {
  enabled: boolean; tokenReady: boolean; schedule: string; note: string;
  job: { status: string; next_run_at: string; last_success_at: string | null; last_error: string | null } | null;
  lastCheck: { status: string; checkedAt: string; reason: string; signalDate?: string; missingDates?: string[] } | null;
  missingDates: string[]; knownSessionCount: number;
}
export interface ArchiveList { rows: ArchiveRow[]; total: number; page: number; pageCount: number; note: string; collection?: CollectionStatus }
export interface ArchiveDetail extends ArchiveRow {
  candidates: Array<{ code: string; amountYi: number; baselineYi: number; ownRatio: number; marketAdjustedRatio: number; signalPct: number | null }>;
  page: number; pageCount: number; note: string;
}
interface Resource<T> { loading: boolean; error: string; data: T | null }

function useArchiveResource<T>(path: string | null, revision: number): Resource<T> {
  const key = path ? `${path}#${revision}` : null;
  const [state, setState] = useState<Resource<T> & { key: string | null }>({ key: null, loading: false, error: "", data: null });
  useEffect(() => {
    if (!path) { setState({ key: null, loading: false, error: "", data: null }); return; }
    const controller = new AbortController();
    setState({ key, loading: true, error: "", data: null });
    void fetch(path, { signal: controller.signal }).then(async response => {
      if (!response.ok) throw new Error(response.status === 404 ? "该日没有首次观察归档" : `归档读取失败（${response.status}）`);
      const data: T = await response.json();
      if (!controller.signal.aborted) setState({ key, loading: false, error: "", data });
    }).catch(error => { if (!controller.signal.aborted) setState({ key, loading: false, error: String(error.message || error), data: null }); });
    return () => controller.abort();
  }, [path, key]);
  if (!path || state.key !== key) return { loading: !!path, error: "", data: null };
  return { loading: state.loading, error: state.error, data: state.data };
}

export function useCandidateArchive(active: boolean) {
  const [open, setOpen] = useState(false), [range, setRange] = useState({ start: "", end: "" });
  const [page, setPage] = useState(1), [selected, setSelected] = useState(""), [detailPage, setDetailPage] = useState(1);
  const [revision, setRevision] = useState(0);
  const enabled = active && open;
  const params = new URLSearchParams({ page: String(page) });
  if (range.start) params.set("start", range.start);
  if (range.end) params.set("end", range.end);
  const list = useArchiveResource<ArchiveList>(enabled ? `/api/capital-flow/turnover-candidate-archive?${params}` : null, revision);
  const detail = useArchiveResource<ArchiveDetail>(enabled && selected ? `/api/capital-flow/turnover-candidate-archive/${selected}?page=${detailPage}` : null, revision);
  const state = useMemo(() => enabled ? { range, selectedDate: selected || null, list, detail } : null,
    [enabled, range, selected, list.loading, list.error, list.data, detail.loading, detail.error, detail.data]);
  return {
    state,
    toggle: () => { setOpen(value => !value); setSelected(""); setRevision(value => value + 1); },
    filter: (start: string, end: string) => { setRange({ start, end }); setPage(1); setSelected(""); },
    selectPage: (value: number) => { setPage(value); setSelected(""); },
    inspect: (day: string) => { setSelected(day); setDetailPage(1); },
    selectDetailPage: setDetailPage, closeDetail: () => setSelected(""),
    refresh: () => setRevision(value => value + 1),
  };
}
