import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import type { WorkspaceIdentity } from "../lib/workspaceIdentity";
import "./website-auth.css";

type Session = WorkspaceIdentity & { mode: "website"; expiresAt: string };
type State = { mode: "checking" | "login" | "error" | "local" } | Session;

function readSession(value: unknown): Session {
  const data = value as Partial<Session> | null;
  if (data?.mode !== "website" || typeof data.userId !== "string" || !data.userId
    || data.workspaceId !== `newma-${data.userId}-c10375`
    || typeof data.expiresAt !== "string" || !(Date.parse(data.expiresAt) > Date.now())) {
    throw new Error("Invalid Website session");
  }
  return data as Session;
}

/** No business component mounts until the API has supplied an authoritative identity. */
export function WebsiteAuthGate({ children }: {
  children: (identity?: WorkspaceIdentity) => ReactNode;
}) {
  const [state, setState] = useState<State>({ mode: "checking" });
  const pending = useRef<AbortController | null>(null);
  const loggingOut = useRef(false);
  const check = useCallback(async () => {
    if (loggingOut.current || pending.current) return;
    const controller = new AbortController();
    pending.current = controller;
    const timeout = window.setTimeout(() => controller.abort(), 8000);
    try {
      const response = await fetch("/api/auth/session", {
        credentials: "same-origin", cache: "no-store", signal: controller.signal,
      });
      if (pending.current !== controller) return;
      if (response.status === 401 || response.status === 403) {
        setState({ mode: "login" });
        return;
      }
      if (!response.ok) throw new Error("Session unavailable");
      const value = await response.json();
      if (pending.current !== controller) return;
      // Only the server may explicitly select the standalone/local identity path.
      setState(value?.mode === "local" ? { mode: "local" } : readSession(value));
    } catch {
      if (pending.current === controller) setState({ mode: "error" });
    } finally {
      window.clearTimeout(timeout);
      if (pending.current === controller) pending.current = null;
    }
  }, []);

  useEffect(() => {
    void check();
    const onFocus = () => { void check(); };
    window.addEventListener("focus", onFocus);
    const timer = window.setInterval(onFocus, 30000);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", onFocus);
      pending.current?.abort();
      pending.current = null;
    };
  }, [check]);

  const expiresAt = state.mode === "website" ? state.expiresAt : undefined;
  useEffect(() => {
    if (!expiresAt) return;
    const timer = window.setTimeout(() => {
      pending.current?.abort();
      pending.current = null;
      setState({ mode: "login" });
    }, Math.max(0, Date.parse(expiresAt) - Date.now()));
    return () => window.clearTimeout(timer);
  }, [expiresAt]);

  const logout = async () => {
    loggingOut.current = true;
    pending.current?.abort();
    pending.current = null;
    setState({ mode: "checking" });
    try {
      const response = await fetch("/api/auth/logout", {
        method: "POST", credentials: "same-origin", signal: AbortSignal.timeout(8000),
      });
      if (!response.ok) throw new Error("Logout unavailable");
      setState({ mode: "login" });
    } catch {
      setState({ mode: "error" });
    } finally {
      loggingOut.current = false;
    }
  };

  if (state.mode === "local") return children();
  if (state.mode === "website") return (
    <div className="website-session">
      <div className="website-session-bar">
        <span>Newma 已连接 · {state.userId}</span>
        <button type="button" onClick={() => void logout()}>退出 Desk</button>
      </div>
      <div className="website-session-content" key={`${state.userId}:${state.workspaceId}`}>
        {children({ userId: state.userId, workspaceId: state.workspaceId })}
      </div>
    </div>
  );
  const returnTo = window.location.pathname + window.location.search + window.location.hash;
  return (
    <main className="website-auth-state" aria-label="Newma 身份验证">
      <h1>{state.mode === "checking" ? "正在确认 Newma 身份…" : state.mode === "login" ? "请连接 Newma" : "暂时无法确认登录状态"}</h1>
      <p role="status">{state.mode === "checking" ? "身份确认后加载工作区。" : state.mode === "login"
        ? "使用已有 Newma 账号登录，Desk 将载入对应工作区。"
        : "已暂停加载工作区，请检查连接后重试。不会切换到匿名身份。"}</p>
      {state.mode !== "checking" && <div className="website-auth-actions">
        <a href={`/api/auth/website/start?returnTo=${encodeURIComponent(returnTo)}`}
          target={window.self !== window.top ? "_blank" : undefined} rel="noopener noreferrer">前往 Newma 登录</a>
        <button type="button" onClick={() => void check()}>重新检查</button>
      </div>}
    </main>
  );
}
