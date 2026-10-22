import { useCallback, useEffect, useId, useRef, useState } from "react";

/** HTML dialogs work inside Desk's sandbox without allowing native JS modals. */
export function useIndustryConfirm() {
  const [message, setMessage] = useState<string | null>(null);
  const element = useRef<HTMLDialogElement>(null);
  const resolve = useRef<((accepted: boolean) => void) | null>(null);
  const id = useId();
  const confirm = useCallback((text: string) => new Promise<boolean>((done) => {
    resolve.current?.(false);
    resolve.current = done;
    setMessage(text);
  }), []);
  const finish = useCallback((accepted: boolean) => {
    const done = resolve.current;
    resolve.current = null;
    element.current?.close();
    setMessage(null);
    done?.(accepted);
  }, []);
  const cancelConfirmation = useCallback(() => finish(false), [finish]);
  useEffect(() => { if (message && !element.current?.open) element.current?.showModal(); }, [message]);
  useEffect(() => () => { resolve.current?.(false); resolve.current = null; }, []);
  const confirmation = <dialog ref={element} aria-labelledby={id} onCancel={(event) => { event.preventDefault(); finish(false); }} onClose={() => { if (resolve.current) finish(false); }}
    className="m-auto w-[calc(100%_-_2rem)] max-w-md rounded-xl border border-border bg-background p-5 text-foreground shadow-xl backdrop:bg-black/50">
    <h2 id={id} className="text-base font-semibold">确认图谱操作</h2>
    <p className="my-4 text-sm leading-7">{message}</p>
    <div className="flex justify-end gap-3"><button type="button" autoFocus className="rounded border border-border px-4 py-2 text-sm" onClick={() => finish(false)}>取消</button><button type="button" className="rounded bg-primary/20 px-4 py-2 text-sm text-primary" onClick={() => finish(true)}>确认继续</button></div>
  </dialog>;
  return { confirm, confirmation, cancelConfirmation };
}
