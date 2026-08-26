import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Cloud,
  CloudOff,
  FolderPlus,
  Loader2,
  Pencil,
  Plus,
  RefreshCw,
  Star,
  Trash2,
  X,
} from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { GlassCard } from "@/components/ui/GlassCard";
import { Disclaimer } from "@/components/ui/Disclaimer";
import { api, type TerminalQuote } from "@/lib/api";
import {
  connectWorkspaceWatchlist,
  createGroupId,
  loadLocalWatchGroups,
  parseCodes,
  saveLocalWatchGroups,
  type SecurityRef,
  type WatchGroup,
  type WatchlistClient,
  type WatchlistSnapshot,
} from "@/lib/watchlist";
import {
  emitVibeDeskEvent,
  publishVibeDeskContext,
  registerVibeDeskContextProvider,
  type VibeDeskPageContext,
} from "@/lib/vibedesk";
import { cn } from "@/lib/utils";

const securityKey = (security: Pick<SecurityRef, "market" | "symbol">) =>
  `${security.market}:${security.symbol}`;

const color = (value: number | null | undefined) =>
  value == null
    ? "text-muted-foreground"
    : value > 0
      ? "text-danger"
      : value < 0
        ? "text-success"
        : "text-muted-foreground";

const number = (value: number | null | undefined, digits = 2) =>
  value == null || !Number.isFinite(value) ? "—" : value.toFixed(digits);

const percent = (value: number | null | undefined) =>
  value == null || !Number.isFinite(value)
    ? "—"
    : `${value > 0 ? "+" : ""}${value.toFixed(2)}%`;

function watchlistContext(input: {
  groups: WatchGroup[];
  activeGroup?: WatchGroup;
  selected?: SecurityRef;
  selectedQuote?: TerminalQuote;
  synced: boolean;
}): VibeDeskPageContext {
  const securityCount = input.groups.reduce(
    (total, group) => total + group.symbols.length,
    0,
  );
  return {
    view: { id: "watchlist", title: "自选股" },
    visibleBlocks: [
      { id: "watchlist-groups", type: "watchlist-groups", title: "自定义分组" },
      { id: "watchlist-table", type: "watchlist", title: input.activeGroup?.name || "自选列表" },
    ],
    selection: {
      groupId: input.activeGroup?.id || "",
      groupName: input.activeGroup?.name || "",
      ...(input.selected
        ? {
            symbol: input.selected.symbol,
            name: input.selected.name,
            market: input.selected.market,
            exchange: input.selected.exchange || "",
          }
        : {}),
    },
    filters: { scope: "active-group" },
    data: {
      asOf: input.selectedQuote?.asOf || new Date().toISOString(),
      source: input.synced ? "vibedesk-watchlist-service" : "vibe-research-local-cache",
      freshness: input.selectedQuote ? "live" : input.synced ? "fresh" : "unknown",
      summary: {
        groupCount: input.groups.length,
        securityCount,
        activeGroupSecurityCount: input.activeGroup?.symbols.length || 0,
        groups: input.groups.map((group) => ({
          id: group.id,
          name: group.name,
          count: group.symbols.length,
        })),
        activeSecurities: (input.activeGroup?.symbols || []).slice(0, 100),
        ...(input.selectedQuote
          ? {
              selectedQuote: {
                symbol: input.selectedQuote.symbol,
                name: input.selectedQuote.name,
                market: input.selectedQuote.market,
                price: input.selectedQuote.price,
                changePct: input.selectedQuote.changePct,
                pe: input.selectedQuote.pe,
                pb: input.selectedQuote.pb,
                source: input.selectedQuote.source,
              },
            }
          : {}),
      },
    },
    actions: [],
    tasks: [],
  };
}

export function Watchlist() {
  const [localSnapshot] = useState(loadLocalWatchGroups);
  const [groups, setGroups] = useState<WatchGroup[]>(localSnapshot.groups);
  const [activeGroupId, setActiveGroupId] = useState(
    () => localSnapshot.groups[0]?.id || "sample",
  );
  const [selected, setSelected] = useState<SecurityRef>();
  const [quotes, setQuotes] = useState<Record<string, TerminalQuote>>({});
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [adding, setAdding] = useState(false);
  const [hint, setHint] = useState<string | null>(null);
  const [syncState, setSyncState] = useState<
    "connecting" | "synced" | "offline"
  >("connecting");
  const [client, setClient] = useState<WatchlistClient>();
  const [groupEditor, setGroupEditor] = useState<{
    mode: "create" | "rename";
    value: string;
  }>();
  const [deleteConfirmId, setDeleteConfirmId] = useState("");
  const mutationQueue = useRef<Promise<unknown>>(Promise.resolve());
  const mutationToken = useRef(0);
  const activeGroup = groups.find((group) => group.id === activeGroupId) || groups[0];
  const selectedQuote = selected ? quotes[securityKey(selected)] : undefined;
  const contextRef = useRef<VibeDeskPageContext>(
    watchlistContext({ groups, activeGroup, selected, selectedQuote, synced: false }),
  );
  contextRef.current = watchlistContext({
    groups,
    activeGroup,
    selected,
    selectedQuote,
    synced: syncState === "synced",
  });

  const applySnapshot = useCallback((snapshot: WatchlistSnapshot) => {
    setGroups(snapshot.groups);
    setActiveGroupId((current) =>
      snapshot.groups.some((group) => group.id === current)
        ? current
        : snapshot.groups[0]?.id || "sample",
    );
    saveLocalWatchGroups(snapshot.groups);
  }, []);

  useEffect(() => saveLocalWatchGroups(groups), [groups]);

  useEffect(() => {
    const unregister = registerVibeDeskContextProvider(() => contextRef.current);
    return unregister;
  }, []);

  useEffect(() => {
    void publishVibeDeskContext();
  }, [groups, activeGroupId, selected, selectedQuote, syncState]);

  useEffect(() => {
    let active = true;
    void connectWorkspaceWatchlist().then(async (connectedClient) => {
      if (!active) return;
      setClient(connectedClient);
      let remote = await connectedClient.load();
      if (remote.revision === 0 && localSnapshot.hasStoredValue) {
        try {
          remote = await connectedClient.replace(remote.revision, localSnapshot.groups);
        } catch {
          remote = await connectedClient.load();
        }
      }
      if (!active) return;
      applySnapshot(remote);
      setSyncState("synced");
    }).catch(() => {
      if (active) setSyncState("offline");
    });
    return () => {
      active = false;
    };
  }, [applySnapshot, localSnapshot]);

  const queueMutation = useCallback((
    operation: (nextClient: WatchlistClient) => Promise<WatchlistSnapshot>,
  ) => {
    if (!client) return;
    const token = ++mutationToken.current;
    setSyncState("connecting");
    mutationQueue.current = mutationQueue.current
      .catch(() => undefined)
      .then(() => operation(client))
      .then((snapshot) => {
        if (token !== mutationToken.current) return;
        applySnapshot(snapshot);
        setSyncState("synced");
      })
      .catch(async () => {
        if (token !== mutationToken.current) return;
        try {
          applySnapshot(await client.load());
        } catch {
          // Keep the optimistic local state while the Desk API is unavailable.
        }
        setSyncState("offline");
      });
  }, [applySnapshot, client]);

  const refresh = useCallback(async (securities: SecurityRef[]) => {
    if (!securities.length) {
      setQuotes({});
      return;
    }
    setLoading(true);
    try {
      const result = await api.terminalQuotes(
        securities.map((security) => securityKey(security)).join(","),
      );
      setQuotes(Object.fromEntries(
        result.items.map((quote) => [securityKey(quote), quote]),
      ));
    } catch {
      setHint("部分行情暂时不可用，自选分组仍可正常编辑");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh(activeGroup?.symbols || []);
  }, [activeGroup?.symbols, refresh]);

  const add = async () => {
    const groupId = activeGroup?.id;
    if (!groupId || adding) return;
    const existing = new Set(activeGroup.symbols.map((security) => securityKey(security)));
    const symbols = parseCodes(input).filter((symbol) => !existing.has(`CN:${symbol}`));
    if (!symbols.length) {
      setHint(input.trim() ? "没识别到新的 6 位 A 股代码（可能已在当前分组）" : null);
      setInput("");
      return;
    }
    setAdding(true);
    let quoteBySymbol = new Map<string, TerminalQuote>();
    try {
      const result = await api.terminalQuotes(
        symbols.map((symbol) => `CN:${symbol}`).join(","),
      );
      quoteBySymbol = new Map(result.items.map((quote) => [quote.symbol, quote]));
    } catch {
      // Symbol persistence does not depend on a live quote response.
    }
    const securities = symbols.map((symbol): SecurityRef => {
      const quote = quoteBySymbol.get(symbol);
      return {
        symbol,
        name: quote?.name || symbol,
        market: "CN",
        exchange: quote?.exchange || (symbol.startsWith("6") ? "SH" : "SZ"),
        currency: quote?.currency || "CNY",
      };
    });
    setGroups((current) => current.map((group) =>
      group.id === groupId
        ? { ...group, symbols: [...group.symbols, ...securities] }
        : group));
    for (const security of securities) {
      queueMutation((nextClient) => nextClient.addSecurity(groupId, security));
    }
    setInput("");
    setHint(`已添加 ${securities.length} 只到「${activeGroup.name}」`);
    setAdding(false);
  };

  const remove = (security: SecurityRef) => {
    const groupId = activeGroup?.id;
    if (!groupId) return;
    setGroups((current) => current.map((group) =>
      group.id === groupId
        ? {
            ...group,
            symbols: group.symbols.filter((item) =>
              securityKey(item) !== securityKey(security)),
          }
        : group));
    if (selected && securityKey(selected) === securityKey(security)) {
      setSelected(undefined);
    }
    queueMutation((nextClient) =>
      nextClient.removeSecurity(groupId, security));
  };

  const saveGroupEditor = () => {
    const cleanName = groupEditor?.value.trim();
    if (!groupEditor || !cleanName) return;
    if (groupEditor.mode === "create") {
      const id = createGroupId(cleanName, groups.map((group) => group.id));
      setGroups((current) => [...current, { id, name: cleanName, symbols: [] }]);
      setActiveGroupId(id);
      queueMutation((nextClient) => nextClient.createGroup({ id, name: cleanName }));
    } else if (activeGroup) {
      setGroups((current) => current.map((group) =>
        group.id === activeGroup.id ? { ...group, name: cleanName } : group));
      queueMutation((nextClient) =>
        nextClient.renameGroup(activeGroup.id, cleanName));
    }
    setGroupEditor(undefined);
  };

  const deleteGroup = () => {
    if (!activeGroup || groups.length <= 1) return;
    if (deleteConfirmId !== activeGroup.id) {
      setDeleteConfirmId(activeGroup.id);
      setHint(`再次点击删除按钮，确认删除「${activeGroup.name}」`);
      return;
    }
    const next = groups.filter((group) => group.id !== activeGroup.id);
    setGroups(next);
    setActiveGroupId(next[0]?.id || "");
    setSelected(undefined);
    setDeleteConfirmId("");
    queueMutation((nextClient) => nextClient.deleteGroup(activeGroup.id));
  };

  const selectSecurity = (security: SecurityRef) => {
    setSelected(security);
    emitVibeDeskEvent("security.selected", {
      symbol: security.symbol,
      name: security.name,
      market: security.market,
      exchange: security.exchange || "",
      groupId: activeGroup?.id || "",
      groupName: activeGroup?.name || "",
    });
  };

  const totalSecurities = useMemo(
    () => groups.reduce((total, group) => total + group.symbols.length, 0),
    [groups],
  );
  const syncLabel = syncState === "synced"
    ? "Desk 已同步"
    : syncState === "connecting"
      ? "同步中"
      : "本地可用";

  return (
    <div>
      <PageHeader
        title="自选股"
        subtitle="按你自己的方式建立分组；市场终端、研究页与 Agent 共用同一份工作区自选。"
        actions={(
          <span className={cn(
            "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs",
            syncState === "synced"
              ? "border-success/25 text-success"
              : "border-border text-muted-foreground",
          )}>
            {syncState === "synced"
              ? <Cloud className="h-3.5 w-3.5" />
              : syncState === "connecting"
                ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                : <CloudOff className="h-3.5 w-3.5" />}
            {syncLabel}
          </span>
        )}
      />

      <GlassCard className="mb-4 p-3 sm:p-4">
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex min-w-0 flex-1 gap-1 overflow-x-auto pb-1">
            {groups.map((group) => (
              <button
                key={group.id}
                type="button"
                onClick={() => {
                  setActiveGroupId(group.id);
                  setSelected(undefined);
                  setDeleteConfirmId("");
                  setGroupEditor(undefined);
                }}
                className={cn(
                  "shrink-0 rounded-lg px-3 py-2 text-xs transition-colors",
                  group.id === activeGroup?.id
                    ? "bg-primary/15 font-medium text-primary"
                    : "bg-muted/30 text-muted-foreground hover:text-foreground",
                )}
              >
                {group.name}
                <span className="ml-1.5 opacity-60">{group.symbols.length}</span>
              </button>
            ))}
          </div>
          <div className="flex shrink-0 items-center gap-1">
            <button
              type="button"
              onClick={() => setGroupEditor({ mode: "create", value: "" })}
              className="rounded-lg p-2 text-muted-foreground hover:bg-muted hover:text-primary"
              title="新建分组"
            >
              <FolderPlus className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={() => activeGroup && setGroupEditor({ mode: "rename", value: activeGroup.name })}
              className="rounded-lg p-2 text-muted-foreground hover:bg-muted hover:text-primary"
              title="重命名当前分组"
            >
              <Pencil className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={deleteGroup}
              disabled={groups.length <= 1}
              className={cn(
                "rounded-lg p-2 text-muted-foreground hover:bg-muted hover:text-destructive disabled:cursor-not-allowed disabled:opacity-30",
                deleteConfirmId === activeGroup?.id && "bg-destructive/10 text-destructive",
              )}
              title="删除当前分组"
            >
              <Trash2 className="h-4 w-4" />
            </button>
          </div>
        </div>
        {groupEditor && (
          <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-border/50 pt-3">
            <input
              autoFocus
              value={groupEditor.value}
              onChange={(event) => setGroupEditor({
                ...groupEditor,
                value: event.target.value.slice(0, 80),
              })}
              onKeyDown={(event) => {
                if (event.key === "Enter") saveGroupEditor();
                if (event.key === "Escape") setGroupEditor(undefined);
              }}
              placeholder="分组名称"
              aria-label="分组名称"
              className="min-w-[220px] flex-1 rounded-lg border border-border bg-muted/20 px-3 py-2 text-sm outline-none focus:border-primary/50"
            />
            <button
              type="button"
              onClick={saveGroupEditor}
              disabled={!groupEditor.value.trim()}
              className="rounded-lg bg-primary/15 px-3 py-2 text-xs font-medium text-primary disabled:opacity-40"
            >
              保存
            </button>
            <button
              type="button"
              onClick={() => setGroupEditor(undefined)}
              className="rounded-lg px-3 py-2 text-xs text-muted-foreground hover:bg-muted"
            >
              取消
            </button>
          </div>
        )}
        <p className="mt-2 text-[11px] text-muted-foreground/70">
          共 {groups.length} 个分组、{totalSecurities} 个标的。分类完全由你维护，不做系统强制归类。
        </p>
      </GlassCard>

      <GlassCard className="mb-4">
        <label className="mb-1.5 block text-xs text-muted-foreground">
          批量加入「{activeGroup?.name || "当前分组"}」—— 粘贴 A 股代码，支持逗号、空格和换行
        </label>
        <div className="flex flex-col gap-2 sm:flex-row">
          <textarea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
                void add();
              }
            }}
            rows={2}
            placeholder={"如：600519 000858, 002463\n300750 688981"}
            className="min-w-0 flex-1 resize-y rounded-lg border border-border bg-muted/20 px-3 py-2 text-sm outline-none focus:border-primary/50"
          />
          <button
            type="button"
            onClick={() => void add()}
            disabled={adding}
            className="inline-flex h-9 shrink-0 items-center justify-center gap-1.5 rounded-lg bg-primary/15 px-4 text-sm font-medium text-primary shadow-glow hover:bg-primary/25 disabled:opacity-50"
          >
            {adding ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
            添加
          </button>
        </div>
        {hint && <p className="mt-2 text-xs text-muted-foreground/70">{hint}</p>}
      </GlassCard>

      <GlassCard glow>
        <div className="mb-2 flex items-center justify-between gap-3">
          <h3 className="flex min-w-0 items-center gap-1.5 font-semibold">
            <Star className="h-4 w-4 shrink-0 text-primary" />
            <span className="truncate">{activeGroup?.name || "自选总览"}</span>
            <span className="text-xs font-normal text-muted-foreground">
              （{activeGroup?.symbols.length || 0}）
            </span>
          </h3>
          <button
            type="button"
            onClick={() => void refresh(activeGroup?.symbols || [])}
            disabled={loading}
            className="text-muted-foreground hover:text-primary"
            title="刷新价格"
          >
            <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
          </button>
        </div>
        {!activeGroup?.symbols.length ? (
          <p className="py-10 text-center text-sm text-muted-foreground/60">
            当前分组还是空的，用上面的输入框加入标的。
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-sm">
              <thead>
                <tr className="border-b border-border/50 text-left text-xs text-muted-foreground">
                  {["市场", "名称", "代码", "现价", "涨跌%", "PE", "PB", "换手%", ""].map((heading) => (
                    <th key={heading} className="whitespace-nowrap px-2 py-2 font-medium">
                      {heading}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {activeGroup.symbols.map((security) => {
                  const quote = quotes[securityKey(security)];
                  const isSelected = selected && securityKey(selected) === securityKey(security);
                  return (
                    <tr
                      key={securityKey(security)}
                      className={cn(
                        "border-b border-border/30 transition-colors",
                        isSelected ? "bg-primary/8" : "hover:bg-muted/20",
                      )}
                    >
                      <td className="px-2 py-2.5">
                        <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                          {security.market}
                        </span>
                      </td>
                      <td className="px-2 py-2.5">
                        <button
                          type="button"
                          onClick={() => selectSecurity(security)}
                          className="font-medium hover:text-primary"
                          title="选择并同步到其他 Mods"
                        >
                          {quote?.name || security.name}
                        </button>
                      </td>
                      <td className="px-2 py-2.5 font-mono text-xs text-muted-foreground">
                        {security.symbol}
                      </td>
                      <td className={cn("px-2 py-2.5 font-mono", color(quote?.changePct))}>
                        {number(quote?.price)}
                      </td>
                      <td className={cn("px-2 py-2.5 font-mono", color(quote?.changePct))}>
                        {percent(quote?.changePct)}
                      </td>
                      <td className="px-2 py-2.5 font-mono text-muted-foreground">{number(quote?.pe)}</td>
                      <td className="px-2 py-2.5 font-mono text-muted-foreground">{number(quote?.pb)}</td>
                      <td className="px-2 py-2.5 font-mono text-muted-foreground">{percent(quote?.turnoverPct)}</td>
                      <td className="px-2 py-2.5">
                        <button
                          type="button"
                          onClick={() => remove(security)}
                          className="text-muted-foreground/50 hover:text-destructive"
                          title="从当前分组移除"
                        >
                          <X className="h-3.5 w-3.5" />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {selected && (
          <p className="mt-3 border-t border-border/50 pt-3 text-xs text-muted-foreground">
            当前证券：<b className="text-foreground">{selected.name} {selected.symbol}</b>。右侧 Agent 与订阅该事件的研究 Mod 将使用这一上下文。
          </p>
        )}
      </GlassCard>

      <Disclaimer />
    </div>
  );
}
