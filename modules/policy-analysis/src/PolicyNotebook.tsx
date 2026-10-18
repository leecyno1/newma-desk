import { useEffect, useMemo, useState } from "react";
import type { DeskInit } from "@newma-desk/contracts";
import { createModStorageClientFromDesk, GatewayError } from "@newma-desk/mod-sdk";
import type { PolicyInterpretation } from "./types";

export interface PolicyFollowup {
  policyId: string; documentRevision?: number; sourceUrl: string; savedAt: string;
  state: "watching" | "observing" | "archived";
  note: string; observation: string; nextReview: string;
  report: PolicyInterpretation;
}
export type PolicyNotebookContext = Omit<PolicyFollowup, "report" | "sourceUrl" | "savedAt"> & {
  savedAt?: string; draftChanged: boolean; storage: string; userId?: string; workspaceId?: string;
};

export function PolicyNotebook({ config, policyId, report, documentRevision, onRestore, onContext }: {
  config?: DeskInit; policyId: string; report?: PolicyInterpretation; documentRevision?: number;
  onRestore(report: PolicyInterpretation): void;
  onContext(value: PolicyNotebookContext): void;
}) {
  const granted = Boolean(config?.grants.permissions.includes("storage.read") && config?.grants.permissions.includes("storage.write"));
  const client = useMemo(() => config?.session && config.gateways.storage
    && granted ? createModStorageClientFromDesk(config) : null,
  [config?.session?.accessToken, config?.instanceId, config?.modId, config?.gateways.storage, granted]);
  const storageAvailable = client !== null;
  const [saved, setSaved] = useState<PolicyFollowup>();
  const [revision, setRevision] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [note, setNote] = useState("");
  const [observation, setObservation] = useState("");
  const [nextReview, setNextReview] = useState("");
  const [state, setState] = useState<PolicyFollowup["state"]>("watching");

  useEffect(() => onContext({
    policyId, documentRevision: saved?.documentRevision, savedAt: saved?.savedAt,
    userId: config?.user.id, workspaceId: config?.workspace.id,
    note, observation, nextReview, state,
    draftChanged: note !== (saved?.note ?? "") || observation !== (saved?.observation ?? "")
      || nextReview !== (saved?.nextReview ?? "") || state !== (saved?.state ?? "watching"),
    storage: !client ? "unavailable" : error ? "error" : loaded ? "loaded" : "loading",
  }), [onContext, policyId, saved, note, observation, nextReview, state, client, loaded, error, config?.user.id, config?.workspace.id]);

  useEffect(() => {
    if (!client) return;
    let active = true;
    setLoaded(false); setError("");
    void client.get<PolicyFollowup>("policy-research", policyId).then((record) => {
      if (!active) return;
      setSaved(record.value); setRevision(record.revision);
      setNote(record.value.note); setObservation(record.value.observation);
      setNextReview(record.value.nextReview); setState(record.value.state); setLoaded(true);
    }).catch((reason: unknown) => {
      if (!active) return;
      if (reason instanceof GatewayError && reason.status === 404) { setRevision(0); setLoaded(true); }
      else setError(reason instanceof Error ? reason.message : "研究跟踪读取失败");
    });
    return () => { active = false; };
  // Renewed session tokens must not reload the record over an unsaved draft.
  }, [storageAvailable, policyId, config?.user.id, config?.workspace.id]);

  async function save() {
    const snapshot = report ?? saved?.report;
    if (!client || !snapshot || !loaded || busy) return;
    setBusy(true); setError(""); setNotice("");
    // Preserve the revision used for the hypothesis, not whichever body is newest now.
    const value: PolicyFollowup = {
      policyId, sourceUrl: snapshot.sourceUrl, documentRevision: snapshot.document?.revision,
      savedAt: new Date().toISOString(), state, note, observation, nextReview,
      report: { ...snapshot, document: snapshot.document ? { ...snapshot.document, text: undefined, paragraphs: undefined } : null },
    };
    try {
      const record = await client.put("policy-research", policyId, value, revision);
      setRevision(record.revision); setSaved(value); setNotice("已保存到当前用户与工作区");
    } catch (reason) {
      setError(reason instanceof GatewayError && reason.status === 409
        ? "他处已更新这份记录。本页草稿保留；请复制草稿并重新载入后合并，不会覆盖他人更新。"
        : reason instanceof Error ? reason.message : "保存失败");
    } finally { setBusy(false); }
  }

  return <section className="policy-notebook" aria-label="政策研究跟踪">
    <header><h3>研究跟踪</h3>{saved ? <span>正文 #{saved.documentRevision ?? "未知"} · 保存 {saved.savedAt.slice(0, 10)}</span> : <span>条款 → 观察 → 复核</span>}</header>
    <p className="muted-note">跟踪状态不等于投资假设已验证，不自动触发交易或风控告警。</p>
    {saved && documentRevision !== undefined && saved.documentRevision !== documentRevision ? <p className="document-error">正文版本已更新，已保存底稿需重新复核；不会自动套用新版本。</p> : null}
    {!client ? <p className="muted-note">持久跟踪需使用 Desk 的用户工作区存储；独立裸页仍可生成和导出底稿。</p> : <>
      <fieldset disabled={!loaded || busy}><div className="notebook-controls"><label>工作状态<select aria-label="研究跟踪状态" value={state} onChange={(e) => setState(e.target.value as PolicyFollowup["state"])}><option value="watching">关注中</option><option value="observing">验证观察中</option><option value="archived">已归档</option></select></label><label>下一复核<input aria-label="下一复核日期" type="date" value={nextReview} onChange={(e) => setNextReview(e.target.value)} /></label></div>
      <label>研究结论 / 仓位关联<textarea aria-label="研究跟踪结论" value={note} onChange={(e) => setNote(e.target.value)} placeholder="哪些持仓可能受影响？机制、方向与条件是什么？" /></label>
      <label>验证观察 / 反证<textarea aria-label="政策验证观察" value={observation} onChange={(e) => setObservation(e.target.value)} placeholder="记录指标日期、实际观察、来源链接及可能推翻假设的证据" /></label>
      </fieldset><div className="notebook-actions"><button type="button" disabled={!loaded || busy || !(report ?? saved?.report)} onClick={() => void save()}>{busy ? "保存中…" : "保存跟踪与底稿"}</button>{saved ? <button type="button" onClick={() => onRestore(saved.report)}>查看已保存底稿</button> : null}<span>{notice || (!loaded && !error ? "读取已保存记录…" : "")}</span></div>
    </>}
    {error ? <p role="alert" className="document-error">{error}</p> : null}
  </section>;
}
