import { useEffect, useRef, useState } from "react";
import { Trash2, ChevronDown, ChevronRight, NotebookPen } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { GlassCard } from "@/components/ui/GlassCard";
import { Disclaimer } from "@/components/ui/Disclaimer";
import { ResearchText } from "@/components/ui/ResearchText";
import { clearNotes, deleteNote, hydrateNotes, loadNotes, type Note } from "@/lib/notes";
import { publishVibeDeskContext, registerVibeDeskContextProvider, type VibeDeskPageContext } from "@/lib/vibedesk";

const KIND_COLOR: Record<string, string> = {
  复盘: "bg-primary/15 text-primary",
  今日要点: "bg-warning/15 text-warning",
  问AI: "bg-success/15 text-success",
};

export function Notes() {
  const [notes, setNotes] = useState<Note[]>(loadNotes);
  const [openId, setOpenId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => { let active = true; void hydrateNotes().then((records) => { if (active) setNotes(records); }).finally(() => { if (active) setLoading(false); }); return () => { active = false; }; }, []);
  const activeNote = notes.find((note) => note.id === openId);
  const contextRef = useRef<VibeDeskPageContext>({ view: { id: "research-notes", title: "研究记录" }, visibleBlocks: [], selection: {}, filters: {}, data: {}, actions: [], tasks: [] });
  contextRef.current = {
    view: { id: "research-notes", title: "研究记录" },
    visibleBlocks: [{ id: "record-list", type: "research-record-list", title: "研究记录列表" }, ...(activeNote ? [{ id: "active-record", type: "research-record", title: activeNote.title }] : [])],
    selection: activeNote ? { recordId: activeNote.id, kind: activeNote.kind, title: activeNote.title } : {},
    filters: {},
    data: { asOf: new Date().toISOString(), source: "newma-desk.research-records.v1", freshness: loading ? "unknown" : "fresh", summary: { recordCount: notes.length, kinds: [...new Set(notes.map((note) => note.kind))], activeRecord: activeNote || null } },
    actions: [{ id: "records.summarize", label: "总结当前记录", available: Boolean(activeNote) }, { id: "records.find-related", label: "查找相关研究档案", available: Boolean(activeNote) }, { id: "records.prepare-followup", label: "形成后续研究清单", available: Boolean(activeNote) }],
    tasks: [],
  };
  useEffect(() => registerVibeDeskContextProvider(() => contextRef.current), []);
  useEffect(() => { void publishVibeDeskContext(); }, [activeNote, loading, notes.length]);

  const fmt = (ts: number) => new Date(ts).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });

  return (
    <div>
      <PageHeader
        title="研究记录"
        subtitle="把 AI 复盘、要点和问答沉淀到 Desk 工作区，支持旧本地记录自动迁移与离线回退。"
        actions={notes.length > 0 && (
          <button onClick={async () => { if (confirm("清空所有研究记录？")) setNotes(await clearNotes()); }}
            className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm text-muted-foreground hover:text-destructive">
            <Trash2 className="h-4 w-4" /> 清空
          </button>
        )}
      />

      {notes.length === 0 ? (
        <GlassCard>
          <div className="flex flex-col items-center gap-2 py-10 text-center text-sm text-muted-foreground">
            <NotebookPen className="h-8 w-8 text-muted-foreground/40" />
            还没有记录。在「每日复盘」「资讯雷达」或「问 AI」里点 <b className="text-foreground">「存入沉淀」</b> 保存分析结果。
          </div>
        </GlassCard>
      ) : (
        <div className="space-y-2">
          {notes.map((n) => {
            const open = openId === n.id;
            return (
              <GlassCard key={n.id} className="!p-0 overflow-hidden">
                <div className="flex items-center gap-2 px-4 py-3">
                  <button onClick={() => setOpenId(open ? null : n.id)} className="flex flex-1 items-center gap-2 text-left">
                    {open ? <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" /> : <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />}
                    <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] ${KIND_COLOR[n.kind] || "bg-muted/50 text-muted-foreground"}`}>{n.kind}</span>
                    <span className="flex-1 truncate text-sm font-medium">{n.title}</span>
                    <span className="shrink-0 font-mono text-[11px] text-muted-foreground/60">{fmt(n.ts)}</span>
                  </button>
                  <button onClick={async () => setNotes(await deleteNote(n.id))} className="shrink-0 text-muted-foreground/60 hover:text-destructive" title="删除">
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
                {open && (
                  <div className="border-t border-border/40 px-4 py-3">
                    <ResearchText content={n.content} />
                  </div>
                )}
              </GlassCard>
            );
          })}
        </div>
      )}

      <Disclaimer />
    </div>
  );
}
