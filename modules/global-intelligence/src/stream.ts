import type { GatewayFetch } from "@newma-desk/mod-sdk";

const FAILURE_MESSAGES = {
  world_stream_idle_timeout: "情报引擎长时间未返回数据，连接已结束；已收到的数据保留，可手动刷新",
  world_connection_failed: "无法连接情报引擎，请检查本地引擎是否运行",
  world_http_rejected: "情报引擎拒绝了数据请求，请检查引擎配置",
  world_invalid_stream: "情报引擎返回的不是实时数据流，请检查服务地址",
  world_stream_disconnected: "情报引擎连接中断；已收到的数据保留，可手动刷新",
  domain_stream_disconnected: "独立全球情报服务连接中断；已收到的数据保留，可手动刷新",
  scope_denied: "页面授权已失效或变更，请重新加载页面获取授权",
  scope_unavailable: "授权校验服务暂不可用，实时流已停止；未回退到匿名访问",
  stream_closed: "实时流已结束；已收到的数据保留，可手动刷新",
  stream_invalid_payload: "实时流数据格式无效，读取已停止",
  stream_unavailable: "全球情报实时流不可用；已收到的数据保留，可手动刷新",
} as const;

export interface GlobalStreamFailure { code: string; message: string }

export function globalStreamFailure(value: unknown): GlobalStreamFailure {
  const code = typeof value === "string" && Object.hasOwn(FAILURE_MESSAGES, value)
    ? value as keyof typeof FAILURE_MESSAGES : "stream_unavailable";
  return { code, message: FAILURE_MESSAGES[code] };
}

class StreamFailure extends Error {
  constructor(readonly code: unknown) { super("Global stream failed"); }
}

/** Fetch-based SSE keeps scoped authorization in headers, never in the URL. */
export function subscribeGlobalStream(
  fetcher: GatewayFetch,
  url: string,
  onPayload: (payload: Record<string, unknown>) => void,
  onStatus: (status: "connecting" | "live" | "degraded") => void,
  onFailure?: (failure: GlobalStreamFailure) => void,
): () => void {
  const controller = new AbortController();
  let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
  onStatus("connecting");
  void (async () => {
    try {
      const response = await fetcher(url, {
        headers: { Accept: "text/event-stream" }, signal: controller.signal,
        redirect: "error", credentials: "omit", cache: "no-store",
      });
      if (controller.signal.aborted) {
        await response.body?.cancel();
        return;
      }
      if (!response.ok || !response.headers.get("content-type")?.startsWith("text/event-stream") || !response.body) {
        throw new StreamFailure([401, 403].includes(response.status) ? "scope_denied" : "stream_unavailable");
      }
      reader = response.body.getReader();
      onStatus("live");
      const decoder = new TextDecoder();
      let buffer = "";
      while (!controller.signal.aborted) {
        const { value, done } = await reader.read();
        if (controller.signal.aborted) return;
        if (done) throw new StreamFailure("stream_closed");
        buffer += decoder.decode(value, { stream: true });
        let boundary: RegExpExecArray | null;
        while ((boundary = /\r?\n\r?\n/.exec(buffer))) {
          const frame = buffer.slice(0, boundary.index);
          buffer = buffer.slice(boundary.index + boundary[0].length);
          let event = "message";
          const data: string[] = [];
          for (const line of frame.split(/\r?\n/)) {
            if (line.startsWith("event:")) event = line.slice(6).trim();
            if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
          }
          if (event === "error") {
            let failure: { code?: unknown; status?: unknown } = {};
            try { failure = JSON.parse(data.join("\n")) ?? {}; } catch { /* Older sources may omit the error body. */ }
            throw new StreamFailure(failure.code ?? (failure.status === "unauthorized" ? "scope_denied" : "stream_unavailable"));
          }
          if (event !== "message" || !data.length) continue;
          let payload: unknown;
          try { payload = JSON.parse(data.join("\n")); } catch { throw new StreamFailure("stream_invalid_payload"); }
          if (!payload || typeof payload !== "object" || Array.isArray(payload)) throw new StreamFailure("stream_invalid_payload");
          onPayload(payload as Record<string, unknown>);
        }
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        onFailure?.(globalStreamFailure(error instanceof StreamFailure ? error.code : undefined));
        onStatus("degraded");
      }
    } finally {
      if (reader) await reader.cancel().catch(() => undefined);
    }
  })();
  return () => {
    controller.abort();
    void reader?.cancel().catch(() => undefined);
  };
}
