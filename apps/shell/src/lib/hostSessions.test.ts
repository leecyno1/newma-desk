import { afterEach, describe, expect, it, vi } from "vitest";
import { readNewmaSessions } from "./hostSessions";

const identity = { projectId: "workflow-center-suite", workspaceId: "workspace-1", parentOrigin: "https://newma.example", parentMessageOrigin: "https://newma.example", parentTargetOrigin: "https://newma.example" };
const snapshot = { source: "newma-hermes", scope: "default", fetchedAt: "2026-10-23T10:00:00.000Z", truncated: false, sessions: [] };
afterEach(() => vi.useRealTimers());
function harness() {
  const target = { postMessage: vi.fn() } as unknown as Window;
  const reply = (data: object = {}, event: object = {}) => {
    const sent = vi.mocked(target.postMessage).mock.calls[0]?.[0];
    window.dispatchEvent(new MessageEvent("message", { source: target, origin: identity.parentOrigin,
      data: { ...sent, type: "newma:sessions-result", ok: true, snapshot, ...data }, ...event }));
  };
  return { target, reply };
}
describe("newma session metadata bridge", () => {
  it("requires an attached Web host", async () => {
    await expect(readNewmaSessions({ identity: null })).rejects.toThrow("未连接");
  });
  it("accepts only the exact parent, request and workspace", async () => {
    const { target, reply } = harness();
    const result = readNewmaSessions({ identity, target });
    reply({}, { origin: "https://wrong.example" });
    reply({}, { source: window });
    reply({ workspaceId: "another-workspace" });
    reply({ requestId: "another-request" });
    reply();
    expect(await result).toEqual(snapshot);
  });
  it("rejects cross-origin session links and drops extra payload fields", async () => {
    const { target, reply } = harness();
    const result = readNewmaSessions({ identity, target });
    reply({ snapshot: { ...snapshot, sessions: [{ id: "s1", title: "test", projectId: "p", projectName: "p", model: "", status: "idle", attention: "", pinned: false, readOnly: false, updatedAt: null, url: "https://wrong.example/session/s1" }] } });
    await expect(result).rejects.toThrow("跳转地址");
    const next = harness();
    const accepted = readNewmaSessions({ identity, target: next.target });
    next.reply({ snapshot: { ...snapshot, messages: ["should not be forwarded"] } });
    expect(await accepted).not.toHaveProperty("messages");
  });
  it("rejects late results after a module switch", async () => {
    const { target, reply } = harness();
    const result = readNewmaSessions({ identity, target, isCurrent: () => false });
    reply();
    await expect(result).rejects.toThrow("已切换");
  });
  it("times out once without retrying or starting a model", async () => {
    vi.useFakeTimers();
    const { target } = harness();
    const result = readNewmaSessions({ identity, target });
    const assertion = expect(result).rejects.toThrow("未响应");
    await vi.advanceTimersByTimeAsync(10000);
    await assertion;
    expect(target.postMessage).toHaveBeenCalledTimes(1);
  });
});
