import { useEffect, useRef, useState } from "react";
import { ArrowUpRight, CircleHelp, MessageSquare, Pin, RefreshCw, Search } from "lucide-react";
import { connectModHost, type ModHostConnection } from "@newma-desk/mod-sdk";
import type { ModPageContext } from "@newma-desk/contracts";
import { SESSION_LANES, selectSessions, type SessionSnapshot } from "./session-board-model";
import "./session-board.css";

export function SessionBoard() {
  const host = useRef<Extract<ModHostConnection, { embedded: true }> | undefined>(undefined);
  const scope = useRef("");
  const pending = useRef(false);
  const live = useRef(false);
  const [snapshot, setSnapshot] = useState<SessionSnapshot>();
  const [stale, setStale] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [connected, setConnected] = useState(false);
  const [automatic, setAutomatic] = useState(false);
  const [search, setSearch] = useState("");
  const [project, setProject] = useState("");
  const [pinnedOnly, setPinnedOnly] = useState(false);
  const context = useRef<ModPageContext>({ view: { id: "workflow-sessions", title: "会话看板" }, visibleBlocks: [], selection: {}, filters: {}, data: {}, actions: [], tasks: [] });

  async function refresh() {
    if (pending.current || !host.current) return false;
    const source = host.current;
    pending.current = true;
    setBusy(true);
    try {
      const next = await source.invokeAction<SessionSnapshot>("sessions.snapshot", {});
      if (!live.current || source !== host.current) return false;
      if (scope.current !== next.scope) { setProject(""); setSearch(""); setPinnedOnly(false); }
      scope.current = next.scope;
      setSnapshot(next);
      setError("");
      return true;
    } catch (reason) {
      if (!live.current || source !== host.current) return false;
      // Do not retain private rows after a failed host/auth/scope check.
      setSnapshot(undefined);
      setAutomatic(false);
      setError(reason instanceof Error ? reason.message : "暂时无法读取会话，请手动重试。");
      return false;
    } finally {
      if (source === host.current) {
        pending.current = false;
        if (live.current) setBusy(false);
      }
    }
  }

  useEffect(() => {
    live.current = true;
    let disposed = false;
    let connection: ModHostConnection | undefined;
    void connectModHost({ modId: "workflow-sessions", parentOrigin: import.meta.env.VITE_PARENT_ORIGIN || "http://127.0.0.1:5888", requestTimeoutMs: 15000, capabilities: ["actions", "context", "theme"] }).then((next) => {
      if (disposed) { next.close(); return; }
      connection = next;
      setConnected(next.embedded);
      if (!next.embedded) { setError("未连接 newma。请从 newma 的工作流 → 会话看板打开；独立页面不会读取登录凭据。"); return; }
      host.current = next;
      next.setContextProvider(() => context.current);
      next.setUiActionHandler(async (action) => {
        if (action !== "sessions.refresh") throw new Error("不支持该看板动作");
        if (!await refresh()) throw new Error("会话刷新未成功，请检查连接后重试。");
        return { refreshed: true };
      });
    }).catch(() => { if (!disposed) setError("无法连接 Desk，请确认宿主版本并重新打开看板。"); });
    return () => { disposed = true; live.current = false; host.current = undefined; pending.current = false; connection?.close(); };
  }, []);

  useEffect(() => {
    setStale(false);
    if (!snapshot) return;
    const timer = window.setTimeout(() => setStale(true), Math.max(0, 30000 - (Date.now() - Date.parse(snapshot.fetchedAt))));
    return () => window.clearTimeout(timer);
  }, [snapshot]);

  useEffect(() => {
    if (!automatic) return;
    const timer = window.setInterval(() => { if (!document.hidden) void refresh(); }, 15000);
    return () => window.clearInterval(timer);
  }, [automatic]);

  const rows = selectSessions(snapshot?.sessions || [], search, project, pinnedOnly);
  const projects = [...new Map((snapshot?.sessions || []).map((row) => [row.projectId, row.projectName])).entries()];
  const working = snapshot?.sessions.filter((row) => row.status === "running").length;
  const attention = snapshot?.sessions.filter((row) => row.status === "attention").length;
  context.current = {
    view: { id: "workflow-sessions", title: "会话看板" },
    visibleBlocks: [{ id: "session-board", type: "kanban", title: "会话状态分栏" }],
    selection: {}, filters: { search, project, pinnedOnly },
    data: { source: "newma-hermes", freshness: snapshot ? stale ? "stale" : "fresh" : "unknown", asOf: snapshot?.fetchedAt,
      summary: { connected: Boolean(snapshot), visible: snapshot ? rows.length : null, running: working ?? null, attention: attention ?? null } },
    actions: [{ id: "sessions.refresh", label: "刷新会话", available: connected && !busy }], tasks: [],
  };
  useEffect(() => { host.current?.publishContext(context.current); }, [snapshot, stale, search, project, pinnedOnly, busy, connected]);

  return <main className="session-board-app">
    <header className="session-board-heading"><div><span className="session-board-eyebrow">NEWMA / SESSION CONTROL</span><h1 data-mod-page-title>会话看板</h1><p>先处理需要你的对话，其余交给 Agent。所有卡片连接原 session。</p></div><div className="session-board-source"><span className={snapshot && !stale ? "is-connected" : ""} />{snapshot ? stale ? "历史快照 · 请刷新" : "已读取 newma 快照" : "未读取会话"}<small>{snapshot ? `Profile：${snapshot.scope} · ${new Date(snapshot.fetchedAt).toLocaleTimeString("zh-CN")}` : "仅当前登录身份可见的云端会话"}</small></div></header>
    <section className="session-board-metrics" aria-label="会话统计">{[["会话总数", snapshot?.sessions.length], ["运行中", working], ["待你处理", attention]].map(([label, value]) => <div key={label}><span>{label}</span><strong>{value ?? "—"}</strong></div>)}<p><CircleHelp size={16} />空闲不等于任务完成。看板不发送消息，也不控制 Agent 运行。</p></section>
    <div className="session-board-toolbar"><label className="session-board-search"><Search size={16} /><input aria-label="搜索会话" placeholder="搜索会话、项目或模型" value={search} onChange={(event) => setSearch(event.target.value)} /></label><select aria-label="筛选项目" value={project} onChange={(event) => setProject(event.target.value)}><option value="">全部项目</option>{projects.map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select><label><input type="checkbox" checked={pinnedOnly} onChange={(event) => setPinnedOnly(event.target.checked)} />只看置顶</label><label><input type="checkbox" checked={automatic} disabled={!snapshot} onChange={(event) => setAutomatic(event.target.checked)} />15秒更新</label><button onClick={() => void refresh()} disabled={busy || !connected}><RefreshCw size={15} className={busy ? "is-spinning" : ""} />{busy ? "读取中…" : snapshot ? "刷新" : "连接并读取会话"}</button></div>
    {error && <div className="session-board-notice" role="alert">{error}</div>}
    {!snapshot && !error && <div className="session-board-notice">点击“连接并读取会话”，读取当前 newma 的会话标题和状态，不读取聊天正文。</div>}
    {snapshot?.truncated && <div className="session-board-notice">本次展示最近更新的 500 个可见会话；更早会话请在原会话列表查找。</div>}
    <section className="session-board-columns" id="session-board" aria-label="会话看板">{SESSION_LANES.map((lane) => {
      const cards = rows.filter((row) => row.status === lane.id);
      return <section key={lane.id} className={`session-board-lane lane-${lane.id}`} aria-label={lane.title}><header><h2><span />{lane.title}</h2><b>{snapshot ? cards.length : "—"}</b><p>{lane.hint}</p></header><div className="session-board-cards">{cards.map((card) => <article key={card.id} className="session-board-card"><div className="session-board-card-meta"><span>{card.projectName}</span>{card.pinned && <Pin size={13} aria-label="已置顶" />}</div><h3>{card.title}</h3>{card.attention && <p className="session-board-attention">{card.attention}</p>}<div className="session-board-card-details"><span>{card.model || "模型未提供"}</span><time>{card.updatedAt ? new Date(card.updatedAt).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) : "时间未知"}</time></div><a href={card.url} target="_blank" rel="noopener noreferrer">{card.readOnly ? "查看原会话（只读）" : "打开原会话"}<ArrowUpRight size={15} /></a></article>)}{cards.length === 0 && <div className="session-board-empty"><MessageSquare size={20} /><span>{snapshot ? "暂无匹配会话" : "等待连接"}</span></div>}</div></section>;
    })}</section>
    <footer className="session-board-footer">仅展示 newma / Hermes 原生云端会话 · 保留原 Profile 可见范围 · 不含 Codex / Qoder · 状态按快照更新</footer>
  </main>;
}
