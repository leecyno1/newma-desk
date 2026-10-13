import { describe, expect, it, vi } from "vitest";
import {
  newmaHostIdentityFromLocation,
  parseNewmaHostContextRequest,
  parseNewmaHostVisualContextRequest,
  postNewmaHostAgentRequest,
  postNewmaHostContext,
  postNewmaHostVisualContext,
} from "./hostBridge";

describe("Newma host bridge", () => {
  it("reads only explicit validated host workspace identity", () => {
    window.history.replaceState(
      null,
      "",
      "/?host=newma&project=market-surface&workspace=newma-mod-market-123&parentOrigin=https%3A%2F%2Fnewma.example",
    );
    expect(newmaHostIdentityFromLocation()).toEqual({
      projectId: "market-surface",
      workspaceId: "newma-mod-market-123",
      parentOrigin: "https://newma.example",
      parentMessageOrigin: "https://newma.example",
      parentTargetOrigin: "https://newma.example",
    });
  });

  it("validates requests and reports structured context to the parent", () => {
    const request = parseNewmaHostContextRequest({
      type: "newma:mod-context-request",
      protocol: "newma:mod-host:v1",
      requestId: "request-1",
      projectId: "market-surface",
      modId: "market-daily",
      workspaceId: "newma-mod-market-123",
      reason: "agent",
    });
    expect(request?.reason).toBe("agent");
    expect(
      parseNewmaHostContextRequest({
        type: "newma:mod-context-request",
        protocol: "newma:mod-host:v1",
        requestId: "request-initial",
        projectId: "market-surface",
        modId: "market-daily",
        workspaceId: "newma-mod-market-123",
        reason: "initial",
      })?.reason,
    ).toBe("initial");

    const target = { postMessage: vi.fn() } as unknown as Window;
    postNewmaHostContext({
      identity: {
        projectId: "market-surface",
        workspaceId: "newma-mod-market-123",
        parentOrigin: "https://newma.example",
        parentMessageOrigin: "https://newma.example",
        parentTargetOrigin: "https://newma.example",
      },
      modId: "market-daily",
      requestId: "request-1",
      target,
      context: {
        view: { id: "kline", title: "贵州茅台 K 线" },
        visibleBlocks: [],
        selection: { symbol: "600519" },
        filters: {},
        data: {},
        actions: [],
        tasks: [],
      },
    });

    expect(target.postMessage).toHaveBeenCalledWith(
      expect.objectContaining({
        type: "newma:mod-context",
        requestId: "request-1",
        modId: "market-daily",
        context: expect.objectContaining({ selection: { symbol: "600519" } }),
      }),
      "https://newma.example",
    );
  });

  it("accepts only explicit HTTPS, localhost, or Electron file parents", () => {
    window.history.replaceState(
      null,
      "",
      "/?host=newma&project=market-surface&workspace=newma-mod-market-123&parentOrigin=file%3A%2F%2F%2F",
    );
    expect(newmaHostIdentityFromLocation()).toMatchObject({
      parentOrigin: "file://",
      parentMessageOrigin: "null",
      parentTargetOrigin: "*",
    });

    window.history.replaceState(
      null,
      "",
      "/?host=newma&project=market-surface&workspace=newma-mod-market-123&parentOrigin=http%3A%2F%2Fevil.example",
    );
    expect(newmaHostIdentityFromLocation()).toBeNull();
  });

  it("forwards visual fallback and Agent drafts to the owning Newma runtime", () => {
    const identity = {
      projectId: "market-surface",
      workspaceId: "newma-mod-market-123",
      parentOrigin: "https://newma.example",
      parentMessageOrigin: "https://newma.example",
      parentTargetOrigin: "https://newma.example",
    };
    expect(parseNewmaHostVisualContextRequest({
      type: "newma:mod-visual-context-request",
      protocol: "newma:mod-host:v1",
      requestId: "visual-1",
      projectId: identity.projectId,
      modId: "market-daily",
      workspaceId: identity.workspaceId,
      reason: "agent",
      maxBytes: 5 * 1024 * 1024,
    })).toMatchObject({ requestId: "visual-1", reason: "agent" });

    const target = { postMessage: vi.fn() } as unknown as Window;
    postNewmaHostVisualContext({
      identity,
      modId: "market-daily",
      requestId: "visual-1",
      target,
      capture: {
        dataUrl: "data:image/png;base64,iVBORw==",
        width: 1280,
        height: 720,
        capturedAt: "2026-08-29T08:00:00+08:00",
        title: "当前市场曲面",
      },
    });
    postNewmaHostAgentRequest({
      identity,
      modId: "market-daily",
      request: { mode: "ask", prompt: "分析当前页面" },
      target,
    });

    expect(target.postMessage).toHaveBeenNthCalledWith(
      1,
      expect.objectContaining({
        type: "newma:mod-visual-context",
        requestId: "visual-1",
        ok: true,
        capture: expect.objectContaining({ title: "当前市场曲面" }),
      }),
      identity.parentTargetOrigin,
    );
    expect(target.postMessage).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({
        type: "newma:agent-request",
        mode: "ask",
        prompt: "分析当前页面",
      }),
      identity.parentTargetOrigin,
    );
  });
});
