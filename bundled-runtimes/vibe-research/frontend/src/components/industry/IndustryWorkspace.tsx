import { useEffect, useRef, useState } from "react";
import type { GraphArtifactInput } from "@/lib/artifacts";
import { subscribeVibeDeskConfig } from "@/lib/vibedesk";
import { evidenceCoverage, evidenceError, evidenceJudgments, evidenceLink, evidenceTiming, industryStorageAvailable, industryStructureError, industryTargets, reviseIndustryStructure, readIndustryBook, readIndustrySource, writeIndustryBook, type IndustryDocument, type IndustryEvidence, type IndustrySourceCheck, type IndustryVersion } from "@/lib/industryWorkspace";
import { IndustryStructureEditor } from "./IndustryStructureEditor";
import { useIndustryConfirm } from "./useIndustryConfirm";

export interface IndustryWorkspaceView {
  version: IndustryVersion;
  dirty: boolean;
  revision: number;
  pendingEvidence: IndustryEvidence | null;
  sourceCheck: Omit<IndustrySourceCheck, "paragraphs"> | null;
}
interface Props {
  sectorKey: string;
  sectorLabel: string;
  sourceSpec: GraphArtifactInput | null;
  sourceEvidence?: IndustryEvidence[];
  provenance: string;
  onViewChange: (view: IndustryWorkspaceView | null) => void;
}
const blankEvidence = (): IndustryEvidence => ({
  id: "", target: "", title: "", url: "", locator: "", excerpt: "", publishedAt: "", nextReview: "", judgment: "unclear", note: "", recordedAt: "",
});
const inputClass = "mt-1 w-full min-w-0 rounded-lg border border-border bg-background px-3 py-2 text-sm";

export function IndustryWorkspace({ sectorKey, sectorLabel, sourceSpec, sourceEvidence, provenance, onViewChange }: Props) {
  const { confirm, confirmation, cancelConfirmation } = useIndustryConfirm();
  const [available, setAvailable] = useState(() => industryStorageAvailable());
  const [writable, setWritable] = useState(() => industryStorageAvailable(undefined, true));
  const [document, setDocument] = useState<IndustryDocument | null>(null);
  const [draft, setDraft] = useState<IndustryVersion | null>(null);
  const [dirty, setDirty] = useState(false);
  const [form, setForm] = useState<IndustryEvidence>(blankEvidence);
  const [formDirty, setFormDirty] = useState(false);
  const [reviewConfirmed, setReviewConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [message, setMessage] = useState("");
  const [sourceCheck, setSourceCheck] = useState<IndustrySourceCheck | null>(null);
  const [sourceLoading, setSourceLoading] = useState(false);
  const [sourcePage, setSourcePage] = useState(1);
  const operation = useRef<AbortController | null>(null);
  const sourceOperation = useRef<AbortController | null>(null);
  useEffect(() => {
    const unsubscribe = subscribeVibeDeskConfig(() => {
      const readable = industryStorageAvailable();
      const canWrite = industryStorageAvailable(undefined, true);
      setAvailable(readable); setWritable(canWrite);
      if (!canWrite) cancelConfirmation();
      if (!readable) {
        operation.current?.abort(); sourceOperation.current?.abort(); setSourceCheck(null); setSourceLoading(false); setDocument(null); setDraft(null); setDirty(false); setFormDirty(false); setBusy(false);
        setMessage("工作区读取权限不可用，已撤回私人内容。");
      }
    });
    return () => { operation.current?.abort(); sourceOperation.current?.abort(); unsubscribe(); };
  }, [cancelConfirmation]);
  useEffect(() => {
    const summary = sourceCheck ? (({ paragraphs: _paragraphs, ...rest }) => rest)(sourceCheck) : null;
    onViewChange(draft && document ? { version: draft, dirty: dirty || formDirty, revision: document.revision, pendingEvidence: formDirty ? form : null, sourceCheck: summary } : null);
  }, [draft, document, dirty, formDirty, form, sourceCheck, onViewChange]);
  useEffect(() => {
    sourceOperation.current?.abort(); setSourceCheck(null); setSourceLoading(false); setSourcePage(1);
  }, [draft?.spec, draft?.evidence, draft?.number, form]);
  const checkSource = async (item: IndustryEvidence, pageStart = 1) => {
    sourceOperation.current?.abort();
    const controller = new AbortController(); sourceOperation.current = controller;
    setSourceCheck(null); setSourceLoading(true); setMessage("");
    try {
      const result = await readIndustrySource(item, controller.signal, pageStart);
      if (!controller.signal.aborted) { setSourceCheck(result); setSourcePage(pageStart); }
    } catch (error) {
      if (!controller.signal.aborted) setMessage(error instanceof Error ? error.message : "原文读取失败。");
    } finally { if (!controller.signal.aborted) setSourceLoading(false); }
  };
  const discardAllowed = async () => !(dirty || formDirty) || await confirm("放弃当前未保存修改？已保存版本不会删除。");
  const resetForm = () => { setForm(blankEvidence()); setFormDirty(false); setReviewConfirmed(false); };
  const load = async () => {
    if (busy || !await discardAllowed()) return;
    const controller = new AbortController(); operation.current?.abort(); operation.current = controller;
    setBusy(true); setMessage(""); setDraft(null); setDocument(null); setDirty(false); resetForm();
    try {
      const result = await readIndustryBook(sectorKey, controller.signal);
      if (controller.signal.aborted) return;
      setDocument(result); setDraft(result.value.versions[result.value.versions.length - 1] ?? null); setUncertain(false);
      setMessage(result.value.versions.length ? "已读取工作区版本；保存时间不是资料更新时间。" : "当前工作区没有该主题的图谱，可建立副本。");
    } catch (error) {
      if (!controller.signal.aborted) setMessage(error instanceof Error ? error.message : "工作区读取失败。");
    } finally { if (!controller.signal.aborted) setBusy(false); }
  };
  const copy = async () => {
    if (!document || busy || !await discardAllowed()) return;
    setDraft({ number: 0, basedOn: null, savedAt: "", provenance: sourceSpec ? provenance : "手工建立结构，待证据核验", spec: sourceSpec ? structuredClone(sourceSpec) : { moduleId: "industry-map", title: sectorLabel + "产业结构", nodes: [], edges: [], metadata: { sectorKey } }, evidence: structuredClone(sourceEvidence ?? []) });
    setDirty(true); resetForm(); setMessage("已建立内存草稿，尚未保存到工作区；不会继承共享库的核验结论。");
  };
  const save = async () => {
    if (!draft || !document || busy || formDirty || !dirty || uncertain) return;
    const structureError = industryStructureError(draft.spec);
    if (structureError) { setMessage(structureError); return; }
    if (document.value.versions.length >= 20) { setMessage("已达 20 个版本，请先导出并整理；不会自动删除历史。"); return; }
    const controller = new AbortController(); operation.current?.abort(); operation.current = controller;
    const version = { ...draft, number: document.value.versions.length + 1, basedOn: draft.number || draft.basedOn, savedAt: new Date().toISOString() };
    setBusy(true); setMessage("");
    try {
      const result = await writeIndustryBook(document, { ...document.value, versions: [...document.value.versions, version] }, controller.signal);
      if (controller.signal.aborted) return;
      setDocument(result); setDraft(result.value.versions[result.value.versions.length - 1]); setDirty(false);
      setMessage("已保存工作区版本 " + version.number + "；人工记录不等于系统核实。");
    } catch (error) {
      if (!controller.signal.aborted) { setUncertain(true); setMessage(error instanceof Error ? error.message : "保存未确认，请导出草稿后重新读取核对。"); }
    } finally { if (!controller.signal.aborted) setBusy(false); }
  };
  const addEvidence = () => {
    if (!draft) return;
    if (!industryTargets(draft.spec).some((target) => target.key === form.target)) { setMessage("请重新选择当前图谱中的证据对象。"); return; }
    if (form.reviewRequired && !reviewConfirmed) { setMessage("请核对新结构与原文，并明确确认重新复核。"); return; }
    const candidate = { ...form, id: form.id || "e-" + Date.now() + "-" + Math.random().toString(36).slice(2, 8), recordedAt: new Date().toISOString() };
    delete candidate.reviewRequired;
    const error = evidenceError(candidate, draft.spec);
    if (error) { setMessage(error); return; }
    if (!form.id && draft.evidence.length >= 80) { setMessage("当前版本最多 80 条证据，请整理已有记录。"); return; }
    setDraft({ ...draft, evidence: form.id ? draft.evidence.map((item) => item.id === form.id ? candidate : item) : [...draft.evidence, candidate] });
    setDirty(true); resetForm(); setMessage("证据已加入草稿，请保存新版本。");
  };
  const download = () => {
    const blob = new Blob([JSON.stringify({ schemaVersion: "newma-desk.industry-map-export.v1", sectorKey, saved: document?.value, draft, pendingEvidence: formDirty ? form : null }, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob); const anchor = window.document.createElement("a");
    anchor.href = url; anchor.download = "industry-map-" + sectorKey + ".json"; anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const updateForm = (field: keyof IndustryEvidence, value: string) => { setForm((previous) => ({ ...previous, [field]: value })); setFormDirty(true); setReviewConfirmed(false); };
  useEffect(() => {
    if (!dirty && !formDirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty, formDirty]);
  const coverage = draft ? evidenceCoverage(draft.spec, draft.evidence) : null;
  const targets = draft ? industryTargets(draft.spec) : [];
  const structureError = draft ? industryStructureError(draft.spec) : null;
  return <section aria-label="工作区图谱与证据" className="mb-5 rounded-xl border border-primary/25 bg-primary/5 p-4">
    {confirmation}
    <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
      <div><h2 className="font-semibold">工作区图谱与证据</h2><p className="mt-1 text-xs leading-6 text-muted-foreground">按 Desk 用户与工作区隔离。手动登记来源与判断，可按需核对公开原文；不代表系统核实。</p></div>
      <span className="rounded border border-border px-2 py-1 text-xs">{dirty || formDirty ? "未保存修改" : draft ? "已保存版本 " + draft.number : "未选择私人图谱"}</span>
    </div>
    {!available && <p className="mb-3 text-xs text-warning">需已授权的 Desk 会话；不会将私人研究降级保存到共享库或浏览器。</p>}
    <div className="flex flex-wrap gap-2 text-xs">
      <button type="button" className="rounded border border-border px-3 py-2 disabled:opacity-40" onClick={load} disabled={!available || busy}>{document ? "重新读取工作区" : "读取工作区图谱"}</button>
      <button type="button" className="rounded border border-border px-3 py-2 disabled:opacity-40" onClick={copy} disabled={!writable || !document || busy || uncertain}>{sourceEvidence?.length ? "复制结构与待复核引用" : sourceSpec ? "复制当前结构为草稿" : "从空白建立图谱"}</button>
      <button type="button" className="rounded bg-primary/20 px-3 py-2 text-primary disabled:opacity-40" onClick={save} disabled={!writable || !dirty || formDirty || busy || uncertain || Boolean(structureError)}>保存新版本</button>
      <button type="button" className="rounded border border-border px-3 py-2 disabled:opacity-40" onClick={download} disabled={!document && !draft}>导出版本与草稿</button>
      {draft && <button type="button" className="rounded border border-border px-3 py-2 disabled:opacity-40" disabled={busy} onClick={async () => { if (await discardAllowed()) { setDraft(null); setDirty(false); resetForm(); } }}>返回预置／共享图谱</button>}
    </div>
    {message && <p role="status" className="mt-3 text-xs leading-6">{message}</p>}
    {document && document.value.versions.length > 0 && <label className="mt-3 block text-xs">工作区版本<select aria-label="工作区版本" className={inputClass} value={draft?.number || ""} disabled={busy} onChange={async (event) => {
      const selected = Number(event.target.value);
      if (!await discardAllowed()) return;
      setDraft(document.value.versions.find((version) => version.number === selected) ?? null); setDirty(false); resetForm();
    }}><option value="">未保存草稿／未选择</option>{document.value.versions.map((version) => <option key={version.number} value={version.number}>版本 {version.number} · {version.savedAt} · {version.evidence.length} 条人工记录</option>)}</select></label>}
    {draft && coverage && <>
      <IndustryStructureEditor spec={draft.spec} confirm={confirm} disabled={!writable || busy || uncertain || formDirty} onChange={(spec) => {
        setDraft(reviseIndustryStructure(draft, spec)); setDirty(true); resetForm(); setMessage("结构已修改，尚未保存；受影响的证据保留为待复核。");
      }} />
      {formDirty && <p className="text-xs text-muted-foreground">请先加入或取消单条证据编辑，再修改结构。</p>}
      {structureError && <p role="status" className="mt-2 text-xs text-warning">{structureError} 草稿可继续编辑或导出。</p>}
      <div className="my-4 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
        {[[coverage.recordedTargets, "对象有记录"], [coverage.missingTargets, "对象缺证据"], [coverage.conflictingTargets, "对象有正反冲突"], [coverage.due, "条记录到期复核"]].map(([value, label]) => <p key={label} className="rounded-lg border border-border bg-background/50 p-3"><b className="mr-2 font-mono text-lg">{value}</b>{label}</p>)}
      </div>
      <p className="mb-3 text-xs text-muted-foreground">来源：{draft.provenance}。覆盖表示已有人工记录，不表示证据有效；无记录不等于关系不存在。</p>
      {coverage.needsReview > 0 && <p className="mb-3 text-xs text-warning">{coverage.needsReview} 条记录待复核，暂不计入覆盖与正反冲突。具体原因见各条说明，原摘录及判断仍保留。</p>}
      <fieldset disabled={!writable || busy || uncertain || Boolean(structureError)} className="space-y-3 disabled:opacity-60">
        <legend className="mb-2 text-sm font-semibold">{form.id ? "修改证据记录" : "补充逐条证据"}</legend>
        <label className="block text-xs">对应节点／关系<select aria-label="证据对象" className={inputClass} value={form.target} onChange={(event) => { updateForm("target", event.target.value); setReviewConfirmed(false); }}><option value="">请选择具体对象</option>{form.reviewRequired && !targets.some((target) => target.key === form.target) && <option value={form.target} disabled>原对象已移除／修改，请重新选择</option>}{targets.map((target) => <option key={target.key} value={target.key}>{target.label}</option>)}</select></label>
        {form.reviewRequired && <label className="block text-xs leading-6 text-warning"><p>原对象：{form.reviewRequired.targetLabel}</p><input type="checkbox" checked={reviewConfirmed} onChange={(event) => { setReviewConfirmed(event.target.checked); setFormDirty(true); }} /> 已重新核对当前对象与原文，确认本条判断</label>}
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="text-xs">来源名称<input aria-label="证据来源名称" maxLength={160} className={inputClass} value={form.title} onChange={(event) => updateForm("title", event.target.value)} /></label>
          <label className="text-xs">原文链接（可留空）<input aria-label="证据原文链接" maxLength={2000} className={inputClass} value={form.url} onChange={(event) => updateForm("url", event.target.value)} /></label>
          <label className="text-xs">页码／段落定位<input aria-label="证据原文定位" maxLength={240} className={inputClass} value={form.locator} onChange={(event) => updateForm("locator", event.target.value)} /></label>
          <label className="text-xs">人工判断<select aria-label="证据人工判断" className={inputClass} value={form.judgment} onChange={(event) => updateForm("judgment", event.target.value)}>{Object.entries(evidenceJudgments).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
          <label className="text-xs">资料发布日期（未知留空）<input aria-label="证据发布日期" type="date" className={inputClass} value={form.publishedAt} onChange={(event) => updateForm("publishedAt", event.target.value)} /></label>
          <label className="text-xs">下次复核日（可留空）<input aria-label="证据复核日期" type="date" className={inputClass} value={form.nextReview} onChange={(event) => updateForm("nextReview", event.target.value)} /></label>
        </div>
        <label className="block text-xs">原文摘录<textarea aria-label="证据原文摘录" rows={3} maxLength={4000} className={inputClass} value={form.excerpt} onChange={(event) => updateForm("excerpt", event.target.value)} /></label>
        <label className="block text-xs">判断依据／失效条件<textarea aria-label="证据判断说明" rows={2} maxLength={2000} className={inputClass} value={form.note} onChange={(event) => updateForm("note", event.target.value)} /></label>
        <div className="flex gap-3"><button type="button" className="rounded bg-primary/20 px-3 py-2 text-xs text-primary" onClick={addEvidence}>加入版本草稿</button><button type="button" className="text-xs text-muted-foreground" onClick={resetForm}>取消本条编辑</button></div>
      </fieldset>
      <div className="mt-4 space-y-3" aria-label="图谱证据记录">
        {draft.evidence.map((item) => <article key={item.id} className="rounded-lg border border-border bg-background/50 p-3 text-xs leading-6">
          <div className="flex flex-wrap justify-between gap-2"><b>{item.title}</b><span>{evidenceJudgments[item.judgment]} · {evidenceTiming(item)}</span></div>
          <p>{item.reviewRequired ? "原对象：" + item.reviewRequired.targetLabel : targets.find((target) => target.key === item.target)?.label}</p>
          {item.reviewRequired && <p className="text-warning">{item.reviewRequired.reason}</p>}
          <p className="text-muted-foreground">定位：{item.locator} · 发布：{item.publishedAt || "未知"} · 复核：{item.nextReview || "未安排"}</p>
          <blockquote className="my-2 whitespace-pre-wrap break-words border-l-2 border-primary/40 pl-3">{item.excerpt}</blockquote>
          <p className="whitespace-pre-wrap break-words">{item.note}</p>
          {evidenceLink(item.url) && <a href={evidenceLink(item.url)!} target="_blank" rel="noreferrer" className="text-primary underline">打开原文（未自动核验）</a>}
          <div className="mt-2 flex flex-wrap gap-3"><button type="button" disabled={!writable || busy || uncertain} className="text-primary disabled:opacity-40" onClick={async () => { if (!formDirty || await confirm("放弃尚未加入的单条编辑？")) { setForm(item); setFormDirty(false); setReviewConfirmed(false); } }}>编辑记录</button>
            <button type="button" className="text-primary disabled:opacity-40" disabled={!available || !evidenceLink(item.url) || formDirty || sourceLoading} onClick={() => checkSource(item)}>核对原文</button>
            <button type="button" disabled={!writable || busy || uncertain} className="text-destructive disabled:opacity-40" onClick={async () => {
              if (await confirm("从当前草稿移除此条证据？旧版本仍保留。")) { setDraft({ ...draft, evidence: draft.evidence.filter((entry) => entry.id !== item.id) }); setDirty(true); if (form.id === item.id) resetForm(); }
            }}>移出本版</button></div>
        </article>)}
        {!draft.evidence.length && <p className="text-xs text-muted-foreground">本版尚无逐条证据。预置来源线索不会自动计为证据。</p>}
      </div>
      {sourceLoading && <p role="status" className="mt-3 text-xs">正在核对公开原文…</p>}
      {sourceCheck && <section aria-label="原文核对结果" className="mt-4 rounded-lg border border-border bg-background/50 p-3 text-xs leading-6">
        <h3 className="font-semibold">原文核对 · 不等于事实核实</h3>
        <p>{sourceCheck.status === "readable" ? "已取得文本" : "未取得完整可读正文"} · 读取状态：{sourceCheck.status}</p>
        <p>{sourceCheck.quoteMatch === "found" ? "摘录出现在本次已读取文本中；不证明关系或因果成立。" : sourceCheck.quoteMatch === "not_found" ? "本次已读取部分未找到摘录；不等于主张为假。" : "未完成逐字匹配。"}</p>
        <p>原文发布日期：{sourceCheck.publishedAt || "未识别"} · 读取：{sourceCheck.checkedAt || "未知"}</p>
        <p className="break-all">实际读取地址：{sourceCheck.finalUrl || sourceCheck.sourceUrl}</p>
        {(sourceCheck.partialDocument || sourceCheck.truncated) && <p className="text-warning">只读取了部分内容，不代表已检查整份原文。</p>}
        {sourceCheck.documentType === "pdf" && <div className="my-2 flex flex-wrap items-center gap-2">
          <p>PDF 物理页：{sourceCheck.readPages?.join("、") || "未取得"}；共 {sourceCheck.pageCount ?? "未知"} 页。未做 OCR，也未还原表格语义。</p>
          <label>起始物理页<input aria-label="原文起始物理页" type="number" min={1} max={Math.min(sourceCheck.pageCount || 10000, 10000)} className="mx-2 w-20 rounded border border-border bg-background p-1" value={sourcePage} onChange={(event) => setSourcePage(Number(event.target.value))} /></label>
          <button type="button" className="text-primary" disabled={!Number.isInteger(sourcePage) || sourcePage < 1 || sourcePage > Math.min(sourceCheck.pageCount || 10000, 10000)} onClick={() => {
            const item = draft.evidence.find((entry) => entry.id === sourceCheck.evidenceId); if (item) void checkSource(item, sourcePage);
          }}>读取指定页起的 10 页</button>
        </div>}
        <details className="mt-2"><summary className="cursor-pointer">查看提取段落（最多显示 60 段）</summary><div className="max-h-80 overflow-y-auto">{sourceCheck.paragraphs?.slice(0, 60).map((part, index) => <div key={index} className="mt-3"><b>{part.locator}</b><p className="whitespace-pre-wrap break-words">{part.text}</p></div>)}</div></details>
        <p className="mt-2 text-muted-foreground">本次读取结果只保留在当前页面，不自动更新人工判断、发布日期或历史版本。</p>
      </section>}
    </>}
  </section>;
}
