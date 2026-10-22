import { describe, expect, it, vi } from "vitest";
import { createGlobalIntelDataSource } from "./data";

const encoder = new TextEncoder();
const session = { accessToken: "synthetic-token", instanceId: "frame-one", canRead: true };

function setup() {
  let writer!: ReadableStreamDefaultController<Uint8Array>;
  const cancel = vi.fn();
  const body = new ReadableStream<Uint8Array>({ start(controller) { writer = controller; }, cancel });
  const fetcher = vi.fn().mockResolvedValue(new Response(body, { headers: { "content-type": "text/event-stream" } }));
  const source = createGlobalIntelDataSource({ baseUrl: "https://desk.example", fetch: fetcher, session, requireSession: true });
  const payload = vi.fn(), status = vi.fn();
  const close = source.subscribe(payload, status);
  return { writer, cancel, fetcher, payload, status, close };
}

describe("authenticated global SSE", () => {
  it("preserves incremental, multiline and UTF-8 events with scoped headers", async () => {
    const test = setup();
    await vi.waitFor(() => expect(test.status).toHaveBeenLastCalledWith("live"));
    const [url, options] = test.fetcher.mock.calls[0]!;
    expect(url).toBe("https://desk.example/api/global-intel/stream");
    expect(options).toMatchObject({ credentials: "omit", redirect: "error", cache: "no-store" });
    expect(options.headers.get("Authorization")).toBe("Bearer synthetic-token");
    expect(options.headers.get("X-Newma-Desk-Instance-Id")).toBe("frame-one");
    const bytes = encoder.encode(': heartbeat\r\n\r\ndata: {"name":"中国",\r\ndata: "step":1}\r\n\r\ndata: {"step":2}\n\n');
    for (const value of bytes) test.writer.enqueue(new Uint8Array([value]));
    await vi.waitFor(() => expect(test.payload).toHaveBeenCalledTimes(2));
    expect(test.payload.mock.calls.map(([value]) => value)).toEqual([{ name: "中国", step: 1 }, { step: 2 }]);
    test.writer.enqueue(encoder.encode('data: {"late":true}\n\n'));
    test.close();
    await vi.waitFor(() => expect(test.cancel).toHaveBeenCalledOnce());
    expect(test.payload).toHaveBeenCalledTimes(2);
    expect(test.fetcher).toHaveBeenCalledOnce();
  });

  it.each(['event: error\ndata: {"status":"unauthorized"}\n\n', 'data: not-json\n\n'])("terminates failures without retry or fake data: %s", async (frame) => {
    const test = setup();
    test.writer.enqueue(encoder.encode(frame));
    await vi.waitFor(() => expect(test.status).toHaveBeenLastCalledWith("degraded"));
    expect(test.payload).not.toHaveBeenCalled();
    expect(test.cancel).toHaveBeenCalledOnce();
    expect(test.fetcher).toHaveBeenCalledOnce();
    test.close();
  });

  it("treats EOF as disconnected and never reconnects automatically", async () => {
    const test = setup();
    test.writer.close();
    await vi.waitFor(() => expect(test.status).toHaveBeenLastCalledWith("degraded"));
    expect(test.fetcher).toHaveBeenCalledOnce();
  });

  it("rejects missing grants before fetch, and HTTP denial without a stream", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response("denied", { status: 403 }));
    const denied = createGlobalIntelDataSource({ baseUrl: "https://desk.example", fetch: fetcher, requireSession: true });
    await expect(denied.staticSnapshot()).rejects.toThrow("授权");
    const status = vi.fn(), payload = vi.fn();
    const stop = denied.subscribe(payload, status);
    await vi.waitFor(() => expect(status).toHaveBeenLastCalledWith("degraded"));
    expect(fetcher).not.toHaveBeenCalled();
    stop();
    const expired = createGlobalIntelDataSource({ baseUrl: "https://desk.example", fetch: fetcher, session, requireSession: true });
    expired.subscribe(payload, status);
    await vi.waitFor(() => expect(fetcher).toHaveBeenCalledOnce());
    expect(payload).not.toHaveBeenCalled();
  });
});
