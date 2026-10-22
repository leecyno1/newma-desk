import type { GatewayFetch } from "@newma-desk/mod-sdk";

export interface GlobalRequestSession {
  accessToken: string;
  instanceId: string;
  canRead: boolean;
  canWrite?: boolean;
}

export function globalRequest(input: {
  fetch?: GatewayFetch;
  session?: GlobalRequestSession;
  requireSession?: boolean;
}): GatewayFetch {
  const rawFetch = input.fetch ?? globalThis.fetch.bind(globalThis);
  return (target, init) => {
    const writing = (init?.method ?? "GET").toUpperCase() !== "GET";
    if ((input.requireSession || input.session) && (!input.session?.accessToken || !input.session.instanceId
      || !(writing ? input.session.canWrite : input.session.canRead))) {
      return Promise.reject(new Error(writing ? "当前授权不允许保存推演" : "请等待宿主授权后刷新全球情报"));
    }
    const headers = new Headers(init?.headers);
    if (input.session) {
      headers.set("Authorization", `Bearer ${input.session.accessToken}`);
      headers.set("X-Newma-Desk-Instance-Id", input.session.instanceId);
    }
    return rawFetch(target, { ...init, headers, credentials: "omit", redirect: "error", cache: "no-store" });
  };
}
