import { useState } from "react";
import { Check, BookmarkPlus } from "lucide-react";
import { addNote } from "@/lib/notes";

// 把一段 AI 结果存入「研究记录」；优先同步 Desk Storage，离线时回退到本地缓存。
export function SaveNoteButton({ kind, title, content }: { kind: string; title: string; content: string }) {
  const [status, setStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  if (!content.trim()) return null;
  return (
    <button
      onClick={async () => { setStatus("saving"); try { await addNote(kind, title, content); setStatus("saved"); } catch { setStatus("error"); } }}
      disabled={status === "saving" || status === "saved"}
      className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:text-primary disabled:opacity-60"
    >
      {status === "saved" ? (<><Check className="h-3.5 w-3.5" /> 已存入沉淀</>) : (<><BookmarkPlus className="h-3.5 w-3.5" /> {status === "saving" ? "保存中…" : status === "error" ? "重试保存" : "存入沉淀"}</>)}
    </button>
  );
}
