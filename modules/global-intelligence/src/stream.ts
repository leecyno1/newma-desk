import type { GatewayFetch } from "@newma-desk/mod-sdk";

/** Fetch-based SSE keeps scoped authorization in headers, never in the URL. */
export function subscribeGlobalStream(
  fetcher: GatewayFetch,
  url: string,
  onPayload: (payload: Record<string, unknown>) => void,
  onStatus: (status: "connecting" | "live" | "degraded") => void,
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
        throw new Error("全球情报流不可用");
      }
      reader = response.body.getReader();
      onStatus("live");
      const decoder = new TextDecoder();
      let buffer = "";
      while (!controller.signal.aborted) {
        const { value, done } = await reader.read();
        if (controller.signal.aborted) return;
        if (done) throw new Error("全球情报流已断开");
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
          if (event === "error") throw new Error("全球情报流不可用");
          if (event !== "message" || !data.length) continue;
          const payload: unknown = JSON.parse(data.join("\n"));
          if (!payload || typeof payload !== "object" || Array.isArray(payload)) throw new Error("情报格式无效");
          onPayload(payload as Record<string, unknown>);
        }
      }
    } catch {
      if (!controller.signal.aborted) onStatus("degraded");
    } finally {
      if (reader) await reader.cancel().catch(() => undefined);
    }
  })();
  return () => {
    controller.abort();
    void reader?.cancel().catch(() => undefined);
  };
}
