import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it, vi } from "vitest";

import type { StoredMod } from "../api/modules";
import { server } from "../test/server";
import { ModCopilot } from "./ModCopilot";

function useAvailableAgent() {
  server.use(
    http.get("/api/capabilities", () =>
      HttpResponse.json({
        adapters: [
          {
            id: "codex-cli",
            name: "Codex CLI",
            kind: "local-cli",
            available: true,
            supportsMemory: true,
            capabilities: ["chat"],
            default: true,
          },
        ],
        moduleActions: [],
      }),
    ),
    http.get("/api/agent/preferences", () =>
      HttpResponse.json({
        userId: "user-1",
        defaultAdapter: "codex-cli",
        moduleOverrides: {},
        updatedAt: null,
      }),
    ),
  );
}

const module: StoredMod = {
  moduleId: "industry-map",
  revision: 3,
  status: "published",
  manifest: {
    schemaVersion: "1.0",
    id: "industry-map",
    name: "产业链研究",
    version: "0.1.0",
    category: "研究",
    entry: { type: "external", url: "http://127.0.0.1:5899/sectors" },
    permissions: [],
    dataServices: [],
    agentCapabilities: [],
    events: { emits: [], accepts: [] },
    refresh: { mode: "manual" },
  },
  createdAt: "2026-07-23T00:00:00Z",
};

describe("ModCopilot", () => {
  it("sends current-page context with workspace identity and renders the answer", async () => {
    useAvailableAgent();
    let createBody: Record<string, unknown> | undefined;
    let userHeader: string | null = null;
    let workspaceHeader: string | null = null;
    server.use(
      http.post("/api/agent/tasks", async ({ request }) => {
        createBody = (await request.json()) as Record<string, unknown>;
        userHeader = request.headers.get("X-User-Id");
        workspaceHeader = request.headers.get("X-Workspace-Id");
        return HttpResponse.json(
          { id: "task-1", status: "queued", result: null, error: null },
          { status: 202 },
        );
      }),
      http.get("/api/agent/tasks/task-1", () =>
        HttpResponse.json({
          id: "task-1",
          status: "completed",
          result: { answer: "这是当前产业链页面的回答。" },
          error: null,
        }),
      ),
    );
    const requestContext = vi.fn(async () => ({
      view: { id: "industry-map:robotics", title: "机器人产业链" },
      visibleBlocks: [],
      selection: { sector: "robotics" },
      filters: {},
      data: { freshness: "fresh" as const },
      actions: [],
      tasks: [],
    }));
    render(
      <ModCopilot
        module={module}
        open
        userId="user-1"
        workspaceId="workspace-1"
        onClose={() => undefined}
        requestContext={requestContext}
      />,
    );

    expect(await screen.findByText(/Codex CLI/)).toBeVisible();
    await userEvent.type(
      screen.getByPlaceholderText("就当前页面提问…"),
      "梳理核心关系",
    );
    await userEvent.click(screen.getByRole("button", { name: "发送" }));

    expect(await screen.findByText("这是当前产业链页面的回答。")).toBeVisible();
    expect(requestContext).toHaveBeenCalledTimes(1);
    expect(userHeader).toBe("user-1");
    expect(workspaceHeader).toBe("workspace-1");
    expect(createBody).toMatchObject({
      moduleId: "industry-map",
      capability: "module.explain",
      memoryScope: "user-agent-mod",
      prompt: "梳理核心关系",
      context: {
        vibedesk: {
          mode: "ask",
          source: "mod-bridge",
          page: {
            view: { title: "机器人产业链" },
            selection: { sector: "robotics" },
          },
        },
      },
    });
  });

  it("uses explicit edit mode and cancels the active task", async () => {
    useAvailableAgent();
    let createBody: Record<string, unknown> | undefined;
    let cancelled = false;
    server.use(
      http.post("/api/agent/tasks", async ({ request }) => {
        createBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          { id: "task-edit", status: "queued", result: null, error: null },
          { status: 202 },
        );
      }),
      http.get("/api/agent/tasks/task-edit", () =>
        HttpResponse.json({
          id: "task-edit",
          status: "running",
          result: null,
          error: null,
        }),
      ),
      http.post("/api/agent/tasks/task-edit/cancel", () => {
        cancelled = true;
        return HttpResponse.json({
          id: "task-edit",
          status: "cancelled",
          result: null,
          error: null,
        });
      }),
    );
    render(
      <ModCopilot
        module={module}
        open
        userId="user-1"
        workspaceId="workspace-1"
        onClose={() => undefined}
        requestContext={async () => undefined}
      />,
    );

    expect(await screen.findByText(/Codex CLI/)).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "修改" }));
    await userEvent.type(
      screen.getByPlaceholderText("描述要修改的功能或问题…"),
      "修复空状态",
    );
    await userEvent.click(screen.getByRole("button", { name: "发送" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "停止" })).toBeVisible(),
    );
    expect(createBody).toMatchObject({
      capability: "module.edit",
      context: { vibedesk: { mode: "edit", source: "manifest-fallback" } },
    });

    await userEvent.click(screen.getByRole("button", { name: "停止" }));
    expect(await screen.findByText("任务已停止。")).toBeVisible();
    expect(cancelled).toBe(true);
  });

  it("applies structured Agent UI actions to the current Mod", async () => {
    useAvailableAgent();
    const invokeUiAction = vi.fn(async () => ({ timeframe: "15m" }));
    server.use(
      http.post("/api/agent/tasks", () =>
        HttpResponse.json({ id: "task-action", status: "queued", result: null, error: null }, { status: 202 }),
      ),
      http.get("/api/agent/tasks/task-action", () =>
        HttpResponse.json({
          id: "task-action",
          status: "completed",
          result: {
            answer: "已切换到 15 分钟。",
            actions: [{ actionId: "market.set-timeframe", input: { timeframe: "15m" } }],
          },
          error: null,
        }),
      ),
    );
    render(
      <ModCopilot
        module={module}
        open
        userId="user-1"
        workspaceId="workspace-1"
        onClose={() => undefined}
        requestContext={async () => undefined}
        invokeUiAction={invokeUiAction}
      />,
    );

    expect(await screen.findByText(/Codex CLI/)).toBeVisible();
    await userEvent.type(screen.getByPlaceholderText("就当前页面提问…"), "切换到15分钟");
    await userEvent.click(screen.getByRole("button", { name: "发送" }));

    expect(await screen.findByText(/已执行 market.set-timeframe/)).toBeVisible();
    expect(invokeUiAction).toHaveBeenCalledWith("market.set-timeframe", { timeframe: "15m" });
  });

  it("reloads the current Mod after an edit task completes", async () => {
    useAvailableAgent();
    const onEditCompleted = vi.fn(async () => undefined);
    server.use(
      http.post("/api/agent/tasks", () =>
        HttpResponse.json(
          { id: "task-complete", status: "queued", result: null, error: null },
          { status: 202 },
        ),
      ),
      http.get("/api/agent/tasks/task-complete", () =>
        HttpResponse.json({
          id: "task-complete",
          status: "completed",
          result: { answer: "修改和验证均已完成。" },
          error: null,
        }),
      ),
    );
    render(
      <ModCopilot
        module={module}
        open
        userId="user-1"
        workspaceId="workspace-1"
        onClose={() => undefined}
        onEditCompleted={onEditCompleted}
        requestContext={async () => undefined}
      />,
    );

    expect(await screen.findByText(/Codex CLI/)).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "修改" }));
    await userEvent.type(
      screen.getByPlaceholderText("描述要修改的功能或问题…"),
      "修复当前页面",
    );
    await userEvent.click(screen.getByRole("button", { name: "发送" }));

    expect(await screen.findByText("修改和验证均已完成。")).toBeVisible();
    await waitFor(() => expect(onEditCompleted).toHaveBeenCalledTimes(1));
    expect(
      await screen.findByText("修改任务已完成，当前 Mod 已重新加载。"),
    ).toBeVisible();
  });

  it("restores the conversation saved for the current Mod", async () => {
    useAvailableAgent();
    window.localStorage.setItem(
      "vibedesk.mod-copilot.messages.industry-map",
      JSON.stringify([
        {
          id: "saved-message",
          role: "assistant",
          content: "已保存的产业链结论",
        },
      ]),
    );
    render(
      <ModCopilot
        module={module}
        open
        userId="user-1"
        workspaceId="workspace-1"
        onClose={() => undefined}
        requestContext={async () => undefined}
      />,
    );

    expect(await screen.findByText("已保存的产业链结论")).toBeVisible();
  });

  it("offers mode-specific shortcuts", async () => {
    useAvailableAgent();
    render(
      <ModCopilot
        module={module}
        open
        userId="user-1"
        workspaceId="workspace-1"
        onClose={() => undefined}
        requestContext={async () => undefined}
      />,
    );

    expect(
      await screen.findByRole("button", { name: "总结当前页面的关键信息" }),
    ).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "修改" }));
    expect(
      screen.getByRole("button", { name: "修复当前页面的异常状态" }),
    ).toBeVisible();
    await userEvent.click(
      screen.getByRole("button", { name: "修复当前页面的异常状态" }),
    );
    expect(
      screen.getByPlaceholderText("描述要修改的功能或问题…"),
    ).toHaveValue("修复当前页面的异常状态");
  });
});
