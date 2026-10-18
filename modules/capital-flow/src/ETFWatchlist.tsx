import { useEffect, useMemo, useRef, useState } from "react";
import type { DeskInit } from "@newma-desk/contracts";
import { createModStorageClientFromDesk, GatewayError } from "@newma-desk/mod-sdk";

export const ETF_GROUPS = ["宽基", "行业", "债券", "商品", "跨境", "货币", "未分类"] as const;
export interface ETFWatchItem { code: string; name: string; category: string }
const CSI300_ETFS: ETFWatchItem[] = [
  { code: "510300.SH", name: "华泰柏瑞沪深300ETF", category: "宽基" },
  { code: "510310.SH", name: "易方达沪深300ETF", category: "宽基" },
  { code: "510330.SH", name: "华夏沪深300ETF", category: "宽基" },
  { code: "159919.SZ", name: "嘉实沪深300ETF", category: "宽基" },
];
export const DEFAULT_ETFS: ETFWatchItem[] = ([
  ["510300.SH", "沪深300ETF", "宽基"], ["510500.SH", "中证500ETF", "宽基"], ["159915.SZ", "创业板ETF", "宽基"],
  ["512480.SH", "半导体ETF", "行业"], ["512880.SH", "证券ETF", "行业"], ["511010.SH", "国债ETF", "债券"],
  ["518880.SH", "黄金ETF", "商品"], ["513100.SH", "纳指ETF", "跨境"],
] as const).map(([code, name, category]) => ({ code, name, category }));
export const poolKey = (items: ETFWatchItem[]) => JSON.stringify(items.map(({ code, category }) => ({ code, category })));
function validPool(value: unknown): value is ETFWatchItem[] {
  return Array.isArray(value) && value.length > 0 && value.length <= 12 && new Set(value.map(row => row?.code)).size === value.length
    && value.every(row => row && /^\d{6}\.(SH|SZ)$/.test(row.code) && typeof row.name === "string" && ETF_GROUPS.includes(row.category));
}

export function useETFWatchlist(config: DeskInit | undefined, embedded: boolean, active: boolean) {
  const granted = !!config?.grants.permissions.includes("storage.read") && !!config?.grants.permissions.includes("storage.write");
  const client = useMemo(() => config?.session && config.gateways.storage && granted ? createModStorageClientFromDesk(config) : null,
    [config?.session?.accessToken, config?.instanceId, config?.modId, config?.gateways.storage, granted]);
  const scope = embedded ? config ? `${config.user.id}:${config.workspace.id}:${config.modId}` : null : "standalone";
  const [items, setItems] = useState<ETFWatchItem[]>(DEFAULT_ETFS);
  const [loadedScope, setLoadedScope] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const loaded = scope !== null && loadedScope === scope;
  useEffect(() => {
    if (!active || !scope) return;
    let live = true;
    setLoadedScope(null); setError(""); setNotice("");
    void (async () => {
      try {
        let value = DEFAULT_ETFS, rev = 0;
        if (client) {
          try { const record = await client.get<{ items: ETFWatchItem[] }>("etf-watchlist", "default"); value = record.value.items; rev = record.revision; }
          catch (reason) { if (!(reason instanceof GatewayError && reason.status === 404)) throw reason; }
        } else {
          const raw = localStorage.getItem(`newma-desk:etf-watchlist:${scope}`);
          if (raw) value = JSON.parse(raw);
        }
        if (!validPool(value)) throw new Error("已保存观察池格式异常，未覆盖原记录");
        if (live) { setItems(value); setRevision(rev); setLoadedScope(scope); if (reloadKey) setNotice("已读取最新观察池；未保存草稿仍保留，请核对后保存或撤销草稿修改。"); }
      } catch (reason) { if (live) setError(reason instanceof Error ? reason.message : "观察池读取失败"); }
    })();
    return () => { live = false; };
  }, [active, scope, !!client, reloadKey]);
  async function save(next: ETFWatchItem[]) {
    if (!loaded || busy || !validPool(next)) return false;
    setBusy(true); setError(""); setNotice("");
    try {
      if (client) {
        const record = await client.put("etf-watchlist", "default", { items: next }, revision);
        setRevision(record.revision);
      } else localStorage.setItem(`newma-desk:etf-watchlist:${scope}`, JSON.stringify(next));
      setItems(next); setNotice(client ? "已保存到当前用户工作区" : "已保存到本浏览器"); return true;
    } catch (reason) {
      setError(reason instanceof GatewayError && reason.status === 409 ? "观察池已被其他页面修改，草稿保留；请重新载入后合并，不覆盖他人修改。" : reason instanceof Error ? reason.message : "保存失败");
      return false;
    } finally { setBusy(false); }
  }
  return { items, loaded, busy, error, notice, save, scope, retry: () => setReloadKey(value => value + 1), storage: client ? "当前用户工作区" : embedded ? "本浏览器当前工作区" : "独立页本浏览器" };
}

export function ETFWatchlist({ state }: { state: ReturnType<typeof useETFWatchlist> }) {
  const [draft, setDraft] = useState(state.items), [query, setQuery] = useState("");
  const [results, setResults] = useState<Array<{ code: string; name: string; indexName?: string }>>([]);
  const [searching, setSearching] = useState(false), [searchError, setSearchError] = useState("");
  const [source, setSource] = useState("");
  const previousItems = useRef(state.items);
  useEffect(() => {
    const previous = previousItems.current;
    setDraft(current => JSON.stringify(current) === JSON.stringify(previous) ? state.items : current);
    previousItems.current = state.items;
  }, [state.items]);
  useEffect(() => {
    setResults([]); setSearchError(""); setSource("");
    const term = query.trim();
    if (!term) { setSearching(false); return; }
    const controller = new AbortController(); setSearching(true);
    const timer = window.setTimeout(() => {
      void fetch(`/api/capital-flow/etf-search?query=${encodeURIComponent(term)}`, { signal: controller.signal })
        .then(async response => { if (!response.ok) throw new Error(`ETF搜索失败（${response.status}）`); return response.json(); })
        .then(data => {
          if (controller.signal.aborted) return;
          if (data.status !== "ready") { setSearchError(data.reason || "目录未确认，不能新增标的"); return; }
          setResults(data.items); setSource(`${data.source} · 目录 ${data.total} 只 · 匹配 ${data.matched} 只（最多显示20只）`);
        }).catch(reason => { if (!controller.signal.aborted) setSearchError(reason instanceof Error ? reason.message : "ETF搜索失败"); })
        .finally(() => { if (!controller.signal.aborted) setSearching(false); });
    }, 250);
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [query]);
  const dirty = JSON.stringify(draft) !== JSON.stringify(state.items);
  const missingCSI300 = CSI300_ETFS.filter(item => !draft.some(row => row.code === item.code));
  return <section className="etf-watchlist" aria-label="ETF观察池管理">
    <details><summary>管理ETF观察池 · {state.items.length}只 · {state.storage}</summary>
      <p>研究观察池不是持仓，分组由你指定，并非官方分类。保留1—12只；保存后重新读取研究数据。</p>
      <fieldset disabled={!state.loaded || state.busy}>
        <button type="button" disabled={!missingCSI300.length || draft.length + missingCSI300.length > 12} onClick={() => setDraft([...draft, ...missingCSI300])}>补入四只沪深300ETF（草稿）</button>
        <label>搜索ETF<input aria-label="搜索ETF名称或代码" value={query} maxLength={48} onChange={event => setQuery(event.target.value)} placeholder="名称、代码或跟踪指数" /></label>
        <small>{searching ? "搜索中…" : source}</small>
        {searchError && <p role="alert">{searchError}</p>}
        <div className="etf-search-results">{results.map(item => <button type="button" key={item.code} disabled={draft.length >= 12 || draft.some(row => row.code === item.code)} onClick={() => setDraft([...draft, { code: item.code, name: item.name, category: "未分类" }])}>
          {item.name} · {item.code} · {item.indexName || "跟踪指数未披露"} · {draft.some(row => row.code === item.code) ? "已添加" : "添加"}</button>)}</div>
        <div className="etf-pool-list">{draft.map(item => <div key={item.code}><span>{item.name}<small>{item.code}</small></span><select aria-label={`${item.code}研究分组`} value={item.category} onChange={event => setDraft(draft.map(row => row.code === item.code ? { ...row, category: event.target.value } : row))}>{ETF_GROUPS.map(group => <option key={group}>{group}</option>)}</select><button type="button" aria-label={`移除${item.code}`} disabled={draft.length === 1} onClick={() => setDraft(draft.filter(row => row.code !== item.code))}>移除</button></div>)}</div>
        <div className="etf-pool-actions"><button type="button" disabled={!dirty} onClick={() => void state.save(draft)}>保存并应用观察池</button><button type="button" onClick={() => setDraft(DEFAULT_ETFS)}>恢复默认草稿</button><button type="button" disabled={!dirty} onClick={() => setDraft(state.items)}>撤销草稿修改</button></div>
      </fieldset>
      <p>{state.busy ? "保存中…" : state.notice || (state.loaded ? dirty ? "草稿未保存，研究仍使用已保存观察池" : "观察池已载入" : "正在连接并读取观察池…")}</p>
      {state.error && <p role="alert">{state.error} <button type="button" onClick={state.retry}>重新读取观察池</button></p>}
    </details>
  </section>;
}
