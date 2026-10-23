import { act, render, screen, waitFor } from "@testing-library/react";
import type { ModManifest } from "@newma-desk/contracts";
import { afterEach, expect, it, vi } from "vitest";
import { ShellEventBus } from "../events/ShellEventBus";
import { readNewmaSessions } from "../lib/hostSessions";
import { ModFrame } from "./ModuleFrame";

vi.mock("../lib/hostSessions", () => ({ readNewmaSessions: vi.fn() }));
afterEach(() => vi.clearAllMocks());

const manifest: ModManifest = {
  schemaVersion: "1.1", id: "workflow-sessions", name: "会话看板", version: "0.1.0",
  category: "workflow", entry: { type: "external", url: "https://workflow.example/" },
  permissions: ["sessions.read"], dataServices: [], events: { emits: [], accepts: [] },
  compatibility: { level: 3, bridgeProtocol: "1.0", viewSpecVersion: "1.0" },
  actions: { "sessions.snapshot": { binding: { type: "local" }, execution: "request", permission: "sessions.read", confirmation: "none" } },
};

async function openBoard(permissions = ["sessions.read"], actions = ["sessions.snapshot"]) {
  const eventBus = new ShellEventBus();
  const actionInvoker = vi.fn();
  const sessionIssuer = vi.fn(async ({ instanceId }: { instanceId: string }) => ({
    sessionId: "board", instanceId, accessToken: "test-only", tokenType: "Bearer" as const,
    expiresAt: "2099-01-01T00:00:00Z", userId: "test", workspaceId: "desk",
    moduleId: manifest.id, revision: 1, grants: { permissions, actions },
  }));
  const view = render(<ModFrame manifest={manifest} eventBus={eventBus} theme="light"
    sessionIssuer={sessionIssuer} actionInvoker={actionInvoker} contextSaver={async () => undefined} />);
  const frame = screen.getByTitle("会话看板") as HTMLIFrameElement;
  const post = vi.spyOn(frame.contentWindow!, "postMessage").mockImplementation(() => undefined);
  const send = (data: object) => act(() => {
    window.dispatchEvent(new MessageEvent("message", { source: frame.contentWindow, origin: "https://workflow.example", data }));
  });
  send({ type: "vibedesk:hello", modId: manifest.id, protocolVersions: ["1.0"], capabilities: ["actions", "context"] });
  await waitFor(() => expect(post.mock.calls.some(([message]) => message.type === "vibedesk:init")).toBe(true));
  const init = post.mock.calls.find(([message]) => message.type === "vibedesk:init")![0];
  send({ type: "vibedesk:ack", modId: manifest.id, instanceId: init.instanceId, protocolVersion: "1.0" });
  return { view, post, eventBus, actionInvoker, request(input = {}) {
    send({ type: "vibedesk:action-request", requestId: "snapshot", modId: manifest.id,
      instanceId: init.instanceId, actionId: "sessions.snapshot", input });
  } };
}

it("reads through the host only with granted session permissions and invalidates on unmount", async () => {
  const snapshot = { source: "newma-hermes" as const, scope: "default", fetchedAt: new Date().toISOString(), truncated: false, sessions: [] };
  vi.mocked(readNewmaSessions).mockResolvedValue(snapshot);
  const board = await openBoard();
  board.request();
  await waitFor(() => expect(board.post).toHaveBeenCalledWith(expect.objectContaining({ type: "vibedesk:action-result", ok: true, result: snapshot }), "https://workflow.example"));
  expect(board.actionInvoker).not.toHaveBeenCalled();
  const isCurrent = vi.mocked(readNewmaSessions).mock.calls[0]![0]!.isCurrent!;
  expect(isCurrent()).toBe(true);
  board.view.unmount();
  expect(isCurrent()).toBe(false);
  board.eventBus.close();
});

it.each([
  { permissions: [], actions: ["sessions.snapshot"], input: {} },
  { permissions: ["sessions.read"], actions: [], input: {} },
  { permissions: ["sessions.read"], actions: ["sessions.snapshot"], input: { profile: "other" } },
])("rejects missing grants or caller-selected scope: %j", async ({ permissions, actions, input }) => {
  const board = await openBoard(permissions, actions);
  board.request(input);
  await waitFor(() => expect(board.post).toHaveBeenCalledWith(expect.objectContaining({ type: "vibedesk:action-result", ok: false }), "https://workflow.example"));
  expect(readNewmaSessions).not.toHaveBeenCalled();
  expect(board.actionInvoker).not.toHaveBeenCalled();
  board.view.unmount();
  board.eventBus.close();
});
