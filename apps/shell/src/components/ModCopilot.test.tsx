import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it, vi } from "vitest";

import type { StoredMod } from "../api/modules";
import {
  buildDeskReturnUrl,
  modCopilotSessionStorageKey,
  readNumaHandoffPayload,
} from "../lib/numaHandoff";
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
            capabilities: ["chat", "module.explain", "module.analyze", "module.edit"],
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
        profileTargets: {
          quick: "openai-compatible",
          deep: "codex-cli",
          batch: "codex-cli",
          edit: "codex-cli",
        },
        moduleProfileOverrides: {},
        updatedAt: null,
      }),
    ),
    http.get("/api/model/providers", () =>
      HttpResponse.json({
        providers: [
          {
            id: "openai-compatible",
            name: "快速模型",
            available: true,
            capabilities: ["chat", "module.explain"],
            default: true,
          },
        ],
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
    navigation: {
      groupLabel: "研究",
      groupOrder: 20,
      itemOrder: 20,
      icon: "research",
      project: {
        id: "vibe-research",
        name: "Vibe Research",
        order: 20,
      },
    },
    entry: { type: "external", url: "http://127.0.0.1:5899/sectors" },
    permissions: [],
    dataServices: [],
    agentCapabilities: [],
    events: { emits: [], accepts: [] },
    refresh: { mode: "manual" },
  },
  createdAt: "2026-07-23T00:00:00Z",
  copilotPrompts: {
    ask: [
      {
        id: "understand",
        label: "提炼与核验",
        suggestions: [
          {
            id: "summary",
            intent: "summary",
            label: "总结 · 提炼核心结论与依据",
            prompt: "请基于当前「产业链研究」Mod，总结核心结论。",
          },
        ],
      },
      {
        id: "judge",
        label: "风险与推演",
        suggestions: [
          {
            id: "risk",
            intent: "risk",
            label: "风险 · 寻找反例与失效条件",
            prompt: "请基于当前「产业链研究」Mod，寻找风险。",
          },
        ],
      },
      {
        id: "advance",
        label: "延伸与行动",
        suggestions: [
          {
            id: "next-step",
            intent: "next-step",
            label: "下一步 · 形成可执行研究清单",
            prompt: "请基于当前「产业链研究」Mod，形成行动清单。",
          },
        ],
      },
    ],
    edit: [
      {
        id: "modify",
        label: "修改与优化",
        suggestions: [
          {
            id: "modify-function",
            intent: "modification",
            label: "修改 · 修复数据或交互问题",
            prompt: "请基于当前「产业链研究」Mod，复现并定位当前问题的根因。",
          },
        ],
      },
    ],
  },
};

describe("ModCopilot", () => {
  it("uses the quick model with Mod Bridge context without creating an Agent task", async () => {
    useAvailableAgent();
    let modelBody: Record<string, unknown> | undefined;
    let modelUserHeader: string | null = null;
    let agentTaskCreated = false;
    server.use(
      http.post("/api/model/responses", async ({ request }) => {
        modelBody = (await request.json()) as Record<string, unknown>;
        modelUserHeader = request.headers.get("X-User-Id");
        return HttpResponse.json({
          answer: "快速结论",
          adapter: "openai-compatible",
          model: "fast-model",
        });
      }),
      http.post("/api/agent/tasks", () => {
        agentTaskCreated = true;
        return HttpResponse.json(
          { id: "unexpected-task", status: "queued", result: null, error: null },
          { status: 202 },
        );
      }),
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

    await userEvent.click(
      await screen.findByRole("button", { name: "快速" }),
    );
    await userEvent.type(
      screen.getByPlaceholderText("快速询问当前页面…"),
      "一句话总结",
    );
    await userEvent.click(screen.getByRole("button", { name: "发送" }));

    expect(await screen.findByText("快速结论")).toBeVisible();
    expect(requestContext).toHaveBeenCalledTimes(1);
    expect(modelBody).toMatchObject({
      moduleId: "industry-map",
      capability: "module.explain",
      prompt: "一句话总结",
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
    expect(modelUserHeader).toBe("user-1");
    expect(agentTaskCreated).toBe(false);
  });

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
    expect(JSON.stringify(createBody)).not.toContain("agentOnlyCapabilities");
    expect(JSON.stringify(createBody)).not.toContain("optionalSecrets");
  });

  it("routes batch work as a stateless Agent profile", async () => {
    useAvailableAgent();
    let createBody: Record<string, unknown> | undefined;
    server.use(
      http.post("/api/agent/tasks", async ({ request }) => {
        createBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          {
            id: "task-batch",
            status: "queued",
            request: { adapter: "codex-cli", profile: "batch" },
            result: null,
            error: null,
          },
          { status: 202 },
        );
      }),
      http.get("/api/agent/tasks/task-batch", () =>
        HttpResponse.json({
          id: "task-batch",
          status: "completed",
          request: { adapter: "codex-cli", profile: "batch" },
          result: { answer: "批处理完成" },
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
      />,
    );

    await userEvent.click(await screen.findByRole("button", { name: "批量" }));
    await userEvent.type(
      screen.getByPlaceholderText("描述要批量处理的内容…"),
      "批量总结当前新闻",
    );
    await userEvent.click(screen.getByRole("button", { name: "发送" }));

    expect(await screen.findByText("批处理完成")).toBeVisible();
    expect(createBody).toMatchObject({
      moduleId: "industry-map",
      capability: "module.analyze",
      profile: "batch",
      memoryScope: "task",
      prompt: "批量总结当前新闻",
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
        HttpResponse.json(
          { id: "task-action", status: "queued", result: null, error: null },
          { status: 202 },
        ),
      ),
      http.get("/api/agent/tasks/task-action", () =>
        HttpResponse.json({
          id: "task-action",
          status: "completed",
          result: {
            answer: "已切换到 15 分钟。",
            actions: [
              { actionId: "market.set-timeframe", input: { timeframe: "15m" } },
            ],
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
    await userEvent.type(
      screen.getByPlaceholderText("就当前页面提问…"),
      "切换到15分钟",
    );
    await userEvent.click(screen.getByRole("button", { name: "发送" }));

    expect(
      await screen.findByText(/已执行 market.set-timeframe/),
    ).toBeVisible();
    expect(invokeUiAction).toHaveBeenCalledWith("market.set-timeframe", {
      timeframe: "15m",
    });
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
    expect(
      window.localStorage.getItem(
        "newma-desk.mod-copilot.messages.v1.workspace-1.industry-map",
      ),
    ).toContain("已保存的产业链结论");
    expect(
      window.localStorage.getItem("vibedesk.mod-copilot.messages.industry-map"),
    ).toBeNull();
  });

  it("isolates saved conversations by workspace and Mod", async () => {
    useAvailableAgent();
    window.localStorage.setItem(
      "newma-desk.mod-copilot.messages.v1.workspace-1.industry-map",
      JSON.stringify([
        {
          id: "workspace-1-message",
          role: "assistant",
          content: "只属于 workspace-1 的结论",
        },
      ]),
    );
    render(
      <ModCopilot
        module={module}
        open
        userId="user-1"
        workspaceId="workspace-2"
        onClose={() => undefined}
        requestContext={async () => undefined}
      />,
    );

    expect(await screen.findByText(/Codex CLI/)).toBeVisible();
    expect(
      screen.queryByText("只属于 workspace-1 的结论"),
    ).not.toBeInTheDocument();
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
      await screen.findByRole("button", { name: "总结 · 提炼核心结论与依据" }),
    ).toBeVisible();
    expect(screen.getByRole("group", { name: "风险与推演" })).toBeVisible();
    expect(screen.getByRole("group", { name: "延伸与行动" })).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "修改" }));
    expect(
      screen.getByRole("button", { name: "修改 · 修复数据或交互问题" }),
    ).toBeVisible();
    await userEvent.click(
      screen.getByRole("button", { name: "修改 · 修复数据或交互问题" }),
    );
    expect(
      (
        screen.getByPlaceholderText(
          "描述要修改的功能或问题…",
        ) as HTMLTextAreaElement
      ).value,
    ).toContain("复现并定位当前问题的根因");
  });

  it("persists upstream session metadata and exposes a configured Numa handoff", async () => {
    useAvailableAgent();
    server.use(
      http.post("/api/agent/tasks", () =>
        HttpResponse.json(
          { id: "task-handoff", status: "queued", result: null, error: null },
          { status: 202 },
        ),
      ),
      http.get("/api/agent/tasks/task-handoff", () =>
        HttpResponse.json({
          id: "task-handoff",
          status: "completed",
          result: {
            answer: "可以在 Numa 中继续。",
            agentId: "hermes-webui",
            upstreamSessionId: "hermes-session-1",
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
        numaAgentUrl="https://numa.example/chat"
        numaAllowedOrigins={["https://numa.example"]}
        onClose={() => undefined}
        requestContext={async () => undefined}
      />,
    );

    expect(await screen.findByText(/Codex CLI/)).toBeVisible();
    await userEvent.type(
      screen.getByPlaceholderText("就当前页面提问…"),
      "继续分析",
    );
    await userEvent.click(screen.getByRole("button", { name: "发送" }));

    expect(await screen.findByText("可以在 Numa 中继续。")).toBeVisible();
    const link = await screen.findByRole("link", {
      name: "转到 Numa Agent 继续当前对话",
    });
    const payload = readNumaHandoffPayload(link.getAttribute("href") || "");
    expect(payload).toMatchObject({
      moduleId: "industry-map",
      projectId: "vibe-research",
      workspaceId: "workspace-1",
      upstreamSessionId: "hermes-session-1",
    });
    expect(new URL(payload!.returnTo).searchParams.get("copilot")).toBe("1");
    expect(new URL(payload!.returnTo).searchParams.has("session")).toBe(false);

    const saved = JSON.parse(
      window.localStorage.getItem(
        modCopilotSessionStorageKey("industry-map", "workspace-1"),
      ) || "null",
    ) as Record<string, unknown>;
    expect(saved).toMatchObject({
      moduleId: "industry-map",
      projectId: "vibe-research",
      workspaceId: "workspace-1",
      taskId: "task-handoff",
      adapterId: "hermes-webui",
      upstreamSessionId: "hermes-session-1",
      status: "completed",
      lastPrompt: "继续分析",
    });
  });

  it("does not render a dead Numa handoff when no safe URL is configured", async () => {
    useAvailableAgent();
    window.localStorage.setItem(
      modCopilotSessionStorageKey("industry-map", "workspace-1"),
      JSON.stringify({
        schemaVersion: 1,
        moduleId: "industry-map",
        moduleName: "产业链研究",
        workspaceId: "workspace-1",
        projectId: "vibe-research",
        mode: "ask",
        status: "completed",
        upstreamSessionId: "hermes-session-1",
        updatedAt: "2026-07-29T00:00:00.000Z",
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
    expect(
      screen.queryByRole("link", { name: "转到 Numa Agent 继续当前对话" }),
    ).not.toBeInTheDocument();
  });

  it("restores a session when the user returns from Numa to this Mod", async () => {
    useAvailableAgent();
    window.history.replaceState(
      null,
      "",
      "/?mod=industry-map#/desk?tab=research&keep=1",
    );
    const returnTo = buildDeskReturnUrl({
      deskUrl: window.location.href,
      moduleId: "industry-map",
      projectId: "vibe-research",
      workspaceId: "workspace-1",
      upstreamSessionId: "hermes-session-returned",
    });
    const returned = new URL(returnTo!);
    window.history.replaceState(
      null,
      "",
      `${returned.pathname}${returned.search}${returned.hash}`,
    );

    render(
      <ModCopilot
        module={module}
        open
        userId="user-1"
        workspaceId="workspace-1"
        numaAgentUrl="https://numa.example/chat"
        numaAllowedOrigins={["https://numa.example"]}
        onClose={() => undefined}
        requestContext={async () => undefined}
      />,
    );

    expect(await screen.findByText(/Codex CLI/)).toBeVisible();
    expect(window.location.hash).toBe("#/desk?tab=research&keep=1");
    expect(window.location.href).not.toContain("newma-handoff=");
    expect(
      await screen.findByRole("link", {
        name: "转到 Numa Agent 继续当前对话",
      }),
    ).toBeVisible();
    const saved = JSON.parse(
      window.localStorage.getItem(
        modCopilotSessionStorageKey("industry-map", "workspace-1"),
      ) || "null",
    ) as Record<string, unknown>;
    expect(saved).toMatchObject({
      status: "handed-off",
      projectId: "vibe-research",
      upstreamSessionId: "hermes-session-returned",
    });
  });

  it("keeps long Agent answers collapsed until requested", async () => {
    useAvailableAgent();
    const longAnswer = Array.from(
      { length: 20 },
      (_, index) => "研究结论第 " + (index + 1) + " 行",
    ).join("\n");
    server.use(
      http.post("/api/agent/tasks", () =>
        HttpResponse.json(
          { id: "task-long", status: "queued", result: null, error: null },
          { status: 202 },
        ),
      ),
      http.get("/api/agent/tasks/task-long", () =>
        HttpResponse.json({
          id: "task-long",
          status: "completed",
          result: { answer: longAnswer },
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
      />,
    );

    expect(await screen.findByText(/Codex CLI/)).toBeVisible();
    await userEvent.type(
      screen.getByPlaceholderText("就当前页面提问…"),
      "生成完整研究",
    );
    await userEvent.click(screen.getByRole("button", { name: "发送" }));

    const toggle = await screen.findByRole("button", {
      name: "展开完整回答",
    });
    expect(screen.queryByText("研究结论第 20 行")).not.toBeInTheDocument();
    await userEvent.click(toggle);
    expect(screen.getByText(/研究结论第 20 行/)).toBeVisible();
  });

  it("renders report and safe graph artifacts with lazy expansion", async () => {
    useAvailableAgent();
    const artifactId = "0123456789abcdef0123456789abcdef";
    server.use(
      http.post("/api/agent/tasks", () =>
        HttpResponse.json(
          {
            id: "task-artifacts",
            status: "queued",
            result: null,
            error: null,
          },
          { status: 202 },
        ),
      ),
      http.get("/api/agent/tasks/task-artifacts", () =>
        HttpResponse.json({
          id: "task-artifacts",
          status: "completed",
          result: {
            answer: "核心结论保持简洁。",
            artifacts: [
              {
                id: "abcdef0123456789abcdef0123456789",
                kind: "report",
                title: "完整研究",
                summary: "财务、新闻与风险证据",
                content: "完整报告正文",
              },
              {
                id: artifactId,
                kind: "graph",
                title: "产业链图谱",
                viewUrl: "/api/artifacts/" + artifactId + "/view",
              },
              {
                id: "fedcba9876543210fedcba9876543210",
                kind: "graph",
                title: "不安全外链",
                viewUrl: "javascript:alert(1)",
              },
            ],
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
      />,
    );

    expect(await screen.findByText(/Codex CLI/)).toBeVisible();
    await userEvent.type(
      screen.getByPlaceholderText("就当前页面提问…"),
      "输出 Artifact",
    );
    await userEvent.click(screen.getByRole("button", { name: "发送" }));

    expect(await screen.findByText("核心结论保持简洁。")).toBeVisible();
    expect(screen.queryByText("完整报告正文")).not.toBeInTheDocument();
    expect(screen.queryByTitle("产业链图谱")).not.toBeInTheDocument();
    expect(screen.queryByText("不安全外链")).not.toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("button", { name: /完整研究/ }),
    );
    expect(screen.getByText("完整报告正文")).toBeVisible();
    await userEvent.click(
      screen.getByRole("button", { name: /产业链图谱/ }),
    );
    const frame = screen.getByTitle("产业链图谱");
    expect(frame).toHaveAttribute(
      "src",
      expect.stringContaining("/api/artifacts/" + artifactId + "/view"),
    );
    expect(
      screen.getByRole("link", { name: "独立打开" }),
    ).toHaveAttribute(
      "href",
      "/api/artifacts/" + artifactId + "/view",
    );
  });

  it("restores only validated artifacts from local storage", async () => {
    useAvailableAgent();
    window.localStorage.setItem(
      "newma-desk.mod-copilot.messages.v1.workspace-1.industry-map",
      JSON.stringify([
        {
          id: "saved-artifact-message",
          role: "assistant",
          content: "已保存报告",
          artifacts: [
            {
              id: "abcdef0123456789abcdef0123456789",
              kind: "report",
              title: "历史研究",
              content: "历史报告正文",
            },
            {
              id: "0123456789abcdef0123456789abcdef",
              kind: "graph",
              title: "恶意图谱",
              viewUrl: "https://evil.test/view",
            },
          ],
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

    expect(await screen.findByText("已保存报告")).toBeVisible();
    expect(screen.getByText("历史研究")).toBeVisible();
    expect(screen.queryByText("恶意图谱")).not.toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: "历史研究" }),
    );
    expect(screen.getByText("历史报告正文")).toBeVisible();
  });
});
