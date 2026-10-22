import { useEffect, useRef, useState, type AnchorHTMLAttributes } from "react";
import { createPortal } from "react-dom";
import { reportBlob, reportScope } from "@/lib/api";
import { isVibeDeskEmbedded, subscribeVibeDeskConfig } from "@/lib/vibedesk";

// Private PDF links fetch with the current session; credentials never enter URLs.
export function ReportSourceLink({ href, children, className, ...props }: AnchorHTMLAttributes<HTMLAnchorElement>) {
  const dialog = useRef<HTMLDialogElement>(null);
  const pending = useRef<AbortController | null>(null);
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const scope = useRef(reportScope());
  const match = href?.match(/\/myreports\/file\/([^?#/]+)(?:\?[^#]*)?(?:#page=(\d+))?$/);
  useEffect(() => {
    const stop = subscribeVibeDeskConfig(() => {
      if (scope.current === reportScope()) return;
      scope.current = reportScope(); pending.current?.abort(); pending.current = null;
      setUrl(""); setError(""); setBusy(false); dialog.current?.close();
    });
    return () => { stop(); pending.current?.abort(); };
  }, []);
  useEffect(() => {
    if (url) dialog.current?.showModal();
    return () => { if (url) URL.revokeObjectURL(url); };
  }, [url]);
  if (!match) return <a href={href} className={className} {...props}>{children}</a>;
  const open = async () => {
    if (pending.current) return;
    const controller = new AbortController(); pending.current = controller;
    setBusy(true); setError("");
    try {
      const blob = await reportBlob(decodeURIComponent(match[1]), { scope: reportScope(), signal: controller.signal });
      if (!controller.signal.aborted) setUrl(URL.createObjectURL(blob));
    } catch (e) {
      if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "原文读取失败");
    } finally {
      if (pending.current === controller) { pending.current = null; setBusy(false); }
    }
  };
  return <>
    <button type="button" className={className} disabled={busy} onClick={() => void open()}>{busy ? "读取原文…" : children}</button>
    {error && <span role="alert" className="ml-2 text-destructive">{error}</span>}
    {createPortal(<dialog ref={dialog} aria-label="研报原文核对" onClose={() => setUrl("")} className={`${isVibeDeskEmbedded ? "w-[min(90vw,36rem)]" : "h-[90vh] w-[90vw] max-w-none"} rounded-lg border border-border bg-card p-4 text-foreground backdrop:bg-black/50`}>
      <div className="mb-2 flex justify-between"><span>已授权的研报原文</span><button type="button" onClick={() => dialog.current?.close()}>关闭原文</button></div>
      {url && <>
        <p className="mb-3 text-sm">{isVibeDeskEmbedded ? "Desk 隔离框架不支持浏览器 PDF 插件，请下载原文后核对；没有放宽页面隔离权限。" : "如果浏览器无法预览，请下载原文核对。"}{match[2] ? ` 请核对 PDF 物理页 ${match[2]}。` : ""}</p>
        <a className="mb-3 inline-block rounded border border-border px-3 py-2 text-primary" href={url} download={`report-${match[1]}.pdf`}>下载已授权原文</a>
        {!isVibeDeskEmbedded && <iframe title="研报 PDF 原文" className="h-[calc(100%-8rem)] w-full" src={`${url}${match[2] ? `#page=${match[2]}` : ""}`} />}
      </>}
    </dialog>, document.body)}
  </>;
}
