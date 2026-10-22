import { useEffect, useMemo, useRef, useState } from "react";
import { createModStorageClientFromDesk, GatewayError, type ModHostConnection } from "@newma-desk/mod-sdk";
import { emptyBook, readBook, trackingOverview, type TrackingBook } from "./tracking";

type Host = Extract<ModHostConnection, {embedded: true}>;
export function useIndustryTracking(host: Host | undefined, industry: string | undefined) {
  const [config, setConfig] = useState<Host["config"]>();
  useEffect(() => {if (!host) {setConfig(undefined); return;} setConfig(host.config); return host.subscribe(setConfig);}, [host]);
  const scope = config ? JSON.stringify([config.user.id, config.workspace.id, config.instanceId]) : "";
  const client = useMemo(() => config?.session && config.gateways.storage ? createModStorageClientFromDesk(config) : null, [config]);
  const [state, setState] = useState({scope: "", status: "idle", book: emptyBook(), revision: 0, error: ""});
  const [selection, setSelection] = useState({scope: "", industry: "", id: ""});
  const active = useRef({scope, sequence: 0, busy: false});
  if (active.current.scope !== scope) active.current = {scope, sequence: active.current.sequence + 1, busy: false};
  useEffect(() => () => {active.current.sequence++;}, []);
  const visible = useMemo(() => state.scope === scope ? state : {scope, status: "idle", book: emptyBook(), revision: 0, error: ""}, [state, scope]);
  async function perform(next?: TrackingBook) {
    if (!client || active.current.busy || next && visible.status !== "ready") return false;
    const sequence = ++active.current.sequence; active.current.busy = true;
    setState({...visible, status: next ? "saving" : "loading", error: ""});
    const current = () => active.current.scope === scope && active.current.sequence === sequence;
    try {
      let book: TrackingBook, revision: number;
      if (next) {
        const result = await client.put("industry-tracking", "records", readBook(next), visible.revision);
        book = readBook(result.value); revision = result.revision;
      } else {
        try {
          const result = await client.get("industry-tracking", "records");
          book = readBook(result.value); revision = result.revision;
        } catch (error) {
          if (!(error instanceof GatewayError) || error.status !== 404) throw error;
          book = emptyBook(); revision = 0;
        }
      }
      if (!current()) return false;
      setState({scope, status: "ready", book, revision, error: ""}); return true;
    } catch (error) {
      if (current()) setState({...visible, status: "failed", error: error instanceof GatewayError && error.status === 409
        ? "记录已在其他页面更新。草稿保留，请重新读取后核对再保存。"
        : error instanceof GatewayError ? "存储不可用，未确认保存；请重新读取核验。" : error instanceof Error ? error.message : "读取失败"});
      return false;
    } finally {if (current()) active.current.busy = false;}
  }
  const entries = visible.book.entries.filter(row => row.industry === industry);
  const selectedId = selection.scope === scope && selection.industry === industry ? selection.id : "";
  const context = useMemo(() => ({status: visible.status, revision: visible.revision,
    overview: visible.status === "ready" ? trackingOverview(visible.book) : null,
    selectedId: visible.status === "ready" && visible.book.entries.some(row => row.id === selectedId && row.industry === industry) ? selectedId : null,
    entries: visible.status === "ready" ? visible.book.entries.filter(row => row.industry === industry) : [],
    boundary: "用户研究判断，不是官方事实；仅含已保存记录，不自动判定证伪或交易。"}), [visible.status, visible.revision, visible.book, industry, selectedId]);
  return {...visible, entries, context, scope, selectedId, select: (id: string, targetIndustry = industry ?? "") => setSelection({scope, industry: targetIndustry, id}), available: !!client, busy: visible.status === "loading" || visible.status === "saving", load: () => perform(), save: (book: TrackingBook) => perform(book)};
}
