import { expect, test, type Locator } from "@playwright/test";

const shellOrigin = process.env.VIBE_E2E_DOMAIN_SUITES_ORIGIN;
const apiOrigin = process.env.VIBE_E2E_DOMAIN_SUITES_API_ORIGIN;

const oldRuntimePort = /:(?:5899|5901|8900|8899)(?:\/|$)/;

async function expectFrameRoute(frameElement: Locator, route: string) {
  if (!apiOrigin) throw new Error("Domain suite API origin is required");
  await expect(frameElement).toHaveAttribute("src", /.+/);
  const src = await frameElement.getAttribute("src");
  if (!src) throw new Error("Mod iframe has no src");
  const actual = new URL(src);
  const expected = new URL(route, apiOrigin);
  expect(actual.origin).toBe(expected.origin);
  expect(actual.pathname).toBe(expected.pathname);
  for (const [name, value] of expected.searchParams) {
    expect(actual.searchParams.get(name)).toBe(value);
  }
}

const embeddedMods = [
  {
    id: "macro-monitor",
    name: "宏观观察",
    route: "/mod-runtime/research/macro-monitor",
    content: /增长、价格与流动性|核心宏观指标/,
  },
  {
    id: "industry-map",
    name: "产业图谱",
    route: "/mod-runtime/research/sectors",
    content: /共 \d+ 个板块/,
  },
  {
    id: "idea-funnel",
    name: "研究机会池",
    route: "/mod-runtime/research/idea-funnel",
    content: /双向研究假设|研究优先级评分/,
  },
  {
    id: "earnings-workbench",
    name: "财报研究",
    route: "/mod-runtime/research/earnings-workbench",
    content: /实际与预期差|报告期与来源核验/,
  },
  {
    id: "peer-comparison",
    name: "同业比较",
    route: "/mod-runtime/research/peer-comparison",
    content: /可比公司集合|经营质量与估值指标/,
  },
  {
    id: "valuation-workbench",
    name: "预测与估值",
    route: "/mod-runtime/research/valuation-workbench",
    content: /自由现金流预测|WACC × 终值增长敏感性/,
  },
  {
    id: "research-memo",
    name: "研究备忘录",
    route: "/mod-runtime/research/research-memo",
    content: /研究边界与执行结论|关联研究档案/,
  },
  {
    id: "thesis-tracker",
    name: "投资逻辑",
    route: "/mod-runtime/research/thesis-tracker",
    content: /可证伪|核心论点/,
  },
  {
    id: "etf-research",
    name: "ETF 研究",
    route: "/mod-runtime/research/etf-research",
    content: /风险收益对比/,
  },
  {
    id: "quant-overview",
    name: "量化总览",
    route: "/mod-runtime/trading/",
    content: /AI 驱动的量化策略研究|AI-Powered Quant Strategy Research/i,
  },
  {
    id: "alpha-lab",
    name: "因子实验室",
    route: "/mod-runtime/trading/alpha-zoo",
    content: /Alpha/,
  },
  {
    id: "backtest-lab",
    name: "回测实验室",
    route: "/mod-runtime/trading/reports",
    content: /回测报告库|Backtest Reports/i,
  },
] as const;

test.describe("Newma-Desk integrated Research and Trading runtimes", () => {
  test.skip(
    !shellOrigin || !apiOrigin,
    "Run with playwright.domain-suites.config.ts against the unified Newma-Desk stack",
  );

  test("serves both domain APIs from the Newma-Desk API process", async ({
    request,
  }) => {
    const suites = await request.get(`${apiOrigin}/api/domain-suites`);
    expect(suites.status()).toBe(200);
    await expect(suites.json()).resolves.toEqual({
      ok: true,
      suites: { research: true, trading: true },
    });

    const research = await request.get(`${apiOrigin}/api/research/health`);
    expect(research.status()).toBe(200);
    await expect(research.json()).resolves.toMatchObject({
      ok: true,
      service: "vibe-research-api",
    });

    const trading = await request.get(`${apiOrigin}/api/trading/health`);
    expect(trading.status()).toBe(200);
    await expect(trading.json()).resolves.toMatchObject({
      status: "healthy",
      service: "Vibe-Trading API",
    });

    const globalStock = await request.get(
      `${apiOrigin}/api/research/global/stock?symbol=AAPL`,
      { timeout: 30_000 },
    );
    expect(globalStock.status()).toBe(200);
    await expect(globalStock.json()).resolves.toMatchObject({
      data: {
        code: "AAPL",
        market: "US",
      },
    });
  });

  test("embeds first-party Mods without reaching any retired service port", async ({
    page,
  }) => {
    const retiredRequests: string[] = [];
    page.on("request", (request) => {
      if (oldRuntimePort.test(request.url())) retiredRequests.push(request.url());
    });

    await page.route("https://fonts.googleapis.com/**", (route) =>
      route.fulfill({ status: 200, contentType: "text/css", body: "" }),
    );
    await page.route("https://fonts.gstatic.com/**", (route) =>
      route.fulfill({ status: 204, body: "" }),
    );

    for (const mod of embeddedMods) {
      await page.goto(`${shellOrigin}/?mod=${mod.id}`, {
        waitUntil: "domcontentloaded",
      });

      const frameElement = page.locator(`iframe[title="${mod.name}"]`);
      await expectFrameRoute(frameElement, mod.route);

      const frame = page.frameLocator(`iframe[title="${mod.name}"]`);
      await expect(frame.locator("body")).toContainText(mod.content);

      if (mod.id === "industry-map") {
        await page.screenshot({
          path: "/tmp/vibedesk-industry-map-integrated.png",
          fullPage: true,
        });
      }
    }

    expect(retiredRequests).toEqual([]);
  });

  test("serves and embeds the shared catalyst calendar with Desk storage", async ({
    page,
    request,
  }) => {
    const feedResponse = await request.get(
      `${apiOrigin}/api/research/catalysts?symbols=600519,300308&days=180&include_cycles=true`,
      { timeout: 30_000 },
    );
    expect(feedResponse.status()).toBe(200);
    const feed = await feedResponse.json() as {
      data: {
        schemaVersion: string;
        items: Array<{ type: string; title: string }>;
        sources: Array<{ id: string; label: string; status: string; count: number }>;
        gaps: Array<{ capability: string; reason: string }>;
      };
    };
    expect(feed.data.schemaVersion).toBe("newma-desk.catalyst-calendar.v1");
    expect(feed.data.items).toEqual(expect.arrayContaining([
      expect.objectContaining({ type: "earnings" }),
    ]));
    const macroEvent = feed.data.items.find((item) => item.type === "macro");
    const cycleSource = feed.data.sources.find((source) => source.id === "seven-cycle");
    expect(cycleSource).toBeDefined();
    if (!cycleSource) throw new Error("Seven Cycle catalyst source status is missing");
    if (macroEvent) {
      expect(cycleSource.status).toBe("ok");
    } else {
      expect(["empty", "unavailable"]).toContain(cycleSource.status);
      if (cycleSource.status === "unavailable") {
        expect(feed.data.gaps).toContainEqual({
          capability: "seven-cycle",
          reason: "unavailable",
        });
      }
    }

    const workspaceId = `e2e-catalyst-${Date.now()}`;
    const storageWrites: number[] = [];
    page.on("response", (response) => {
      if (
        response.request().method() === "PUT" &&
        response.url().includes("/storage/catalyst-calendar/tracker")
      ) storageWrites.push(response.status());
    });
    await page.addInitScript(({ workspace }) => {
      localStorage.setItem("vibedesk.userId.v1", "e2e-catalyst-user");
      localStorage.setItem("vibedesk.workspaceId.v1", workspace);
      localStorage.setItem("vibedesk.research.watch-groups.v1", JSON.stringify([{
        id: "catalyst-e2e",
        name: "催化剂验收",
        symbols: [
          { market: "CN", symbol: "600519", name: "贵州茅台" },
          { market: "CN", symbol: "300308", name: "中际旭创" },
        ],
      }]));
    }, { workspace: workspaceId });

    await page.goto(`${shellOrigin}/?mod=catalyst-calendar`, { waitUntil: "domcontentloaded" });
    const frameElement = page.locator('iframe[title="催化剂日历"]');
    await expectFrameRoute(frameElement, "/mod-runtime/research/catalyst-calendar");
    const frame = page.frameLocator('iframe[title="催化剂日历"]');
    await expect(frame.getByRole("combobox", { name: /研究分组/ })).toBeVisible();
    await expect(frame.getByText(/半年报披露/).first()).toBeVisible({ timeout: 30_000 });
    if (macroEvent) {
      await expect(frame.getByText(macroEvent.title).first()).toBeVisible();
    } else {
      await expect(frame.getByText(
        `${cycleSource.label} · ${cycleSource.status} · ${cycleSource.count}`,
      )).toBeVisible();
      if (cycleSource.status === "unavailable") {
        await expect(frame.getByText("seven-cycle：unavailable")).toBeVisible();
      }
    }

    await frame.getByRole("button", { name: "添加事件" }).click();
    await frame.getByPlaceholder("事件标题").fill("E2E 自定义催化剂");
    await frame.locator('input[type="date"]').fill("2026-09-01");
    await frame.getByPlaceholder("确认条件").fill("公开来源确认");
    await frame.getByPlaceholder("失效条件").fill("事件取消");
    await frame.getByRole("button", { name: "保存并跟踪" }).click();
    await expect(frame.getByText("E2E 自定义催化剂").first()).toBeVisible();
    await expect.poll(() => storageWrites.includes(200)).toBe(true);
  });

  test("persists a falsifiable investment thesis through Desk storage", async ({
    page,
  }) => {
    const workspaceId = `e2e-thesis-${Date.now()}`;
    const storageWrites: number[] = [];
    page.on("response", (response) => {
      if (
        response.request().method() === "PUT" &&
        response.url().includes("/storage/thesis-tracker/portfolio")
      ) storageWrites.push(response.status());
    });
    await page.addInitScript(({ workspace }) => {
      localStorage.setItem("vibedesk.userId.v1", "e2e-thesis-user");
      localStorage.setItem("vibedesk.workspaceId.v1", workspace);
    }, { workspace: workspaceId });

    await page.goto(`${shellOrigin}/?mod=thesis-tracker`, { waitUntil: "domcontentloaded" });
    const frameElement = page.locator('iframe[title="投资逻辑"]');
    await expectFrameRoute(frameElement, "/mod-runtime/research/thesis-tracker");
    const frame = page.frameLocator('iframe[title="投资逻辑"]');
    await expect(frame.getByLabel("证券代码")).toBeVisible();
    await frame.getByLabel("证券代码").fill("600519");
    await frame.getByLabel("公司名称").fill("贵州茅台");
    await frame.getByLabel("逻辑标题").fill("E2E 品牌与渠道韧性研究");
    await frame.getByLabel("可证伪的核心论点").fill("品牌势能和渠道质量应能支持收入质量；若核心经营指标连续恶化则逻辑被削弱。");
    for (let index = 0; index < 3; index += 1) {
      await frame.getByPlaceholder("支柱名称").nth(index).fill(`支柱 ${index + 1}`);
      await frame.getByPlaceholder("原始预期 / 可跟踪指标").nth(index).fill(`指标 ${index + 1} 持续改善`);
      await frame.getByPlaceholder(`风险 ${index + 1}`).fill(`风险 ${index + 1}`);
      await frame.getByPlaceholder("什么可观察事实会证伪逻辑").nth(index).fill(`证伪条件 ${index + 1}`);
    }
    await frame.getByRole("button", { name: "保存" }).click();
    await expect(frame.getByText("已保存到 Desk 工作区")).toBeVisible();
    await expect(frame.getByText("E2E 品牌与渠道韧性研究")).toBeVisible();
    await expect.poll(() => storageWrites.includes(200)).toBe(true);
  });

  test("persists a two-sided research candidate through Desk storage", async ({ page }) => {
    const workspaceId = `e2e-idea-funnel-${Date.now()}`;
    const storageWrites: number[] = [];
    page.on("response", (response) => {
      if (
        response.request().method() === "PUT" &&
        response.url().includes("/storage/idea-funnel/pipeline")
      ) storageWrites.push(response.status());
    });
    await page.addInitScript(({ workspace }) => {
      localStorage.setItem("vibedesk.userId.v1", "e2e-idea-funnel-user");
      localStorage.setItem("vibedesk.workspaceId.v1", workspace);
    }, { workspace: workspaceId });

    await page.goto(`${shellOrigin}/?mod=idea-funnel`, { waitUntil: "domcontentloaded" });
    const frameElement = page.locator('iframe[title="研究机会池"]');
    await expectFrameRoute(frameElement, "/mod-runtime/research/idea-funnel");
    const frame = page.frameLocator('iframe[title="研究机会池"]');
    await expect(frame.getByLabel("候选标题")).toBeVisible();
    await frame.getByLabel("候选标题").fill("E2E 光模块需求研究线索");
    await frame.getByLabel("证券代码").fill("300308");
    await frame.getByLabel("公司名称").fill("中际旭创");
    await frame.getByLabel("研究问题").fill("需求、产品迭代和份额能否支持增长质量？");
    await frame.getByLabel("初始假设").fill("客户资本开支与产品迭代可能支持收入增长。");
    await frame.getByLabel("反方假设").fill("供给扩张和客户集中可能压缩增长与利润率。");
    await frame.getByLabel("为何现在").fill("1.6T 导入和下一次财报构成验证窗口。");
    await frame.getByLabel("市场可能遗漏").fill("市场可能低估迭代速度，也可能高估利润率持续性。");
    await frame.getByRole("button", { name: "保存" }).click();
    await expect(frame.getByText("已保存到 Desk 工作区")).toBeVisible();
    await expect(frame.getByText("E2E 光模块需求研究线索")).toBeVisible();
    await expect.poll(() => storageWrites.includes(200)).toBe(true);
  });

  test("derives a lightweight research coverage view from existing Mod caches", async ({ page }) => {
    const workspaceId = `e2e-research-coverage-${Date.now()}`;
    await page.addInitScript(({ workspace }) => {
      localStorage.setItem("vibedesk.userId.v1", "e2e-research-coverage-user");
      localStorage.setItem("vibedesk.workspaceId.v1", workspace);
      localStorage.setItem("newma-desk.thesis-tracker.v1", JSON.stringify({
        schemaVersion: "newma-desk.investment-thesis.v1",
        updatedAt: "2026-08-01T08:00:00Z",
        theses: [{
          id: "thesis:e2e-coverage",
          title: "品牌与渠道韧性",
          security: { market: "CN", symbol: "600519", name: "贵州茅台" },
          nextReviewAt: "2000-01-01",
          evidence: [{ id: "evidence:1", freshness: { status: "stale" } }],
          gaps: ["补充最新渠道数据"],
          updatedAt: "2026-08-01T08:00:00Z",
        }],
      }));
      localStorage.setItem("newma-desk.research-memo.v1", JSON.stringify({
        schemaVersion: "newma-desk.research-memo.v1",
        updatedAt: "2026-08-02T08:00:00Z",
        memos: [{
          id: "memo:e2e-coverage",
          title: "贵州茅台研究备忘录",
          status: "current",
          security: { market: "CN", symbol: "600519", name: "贵州茅台" },
          nextReviewAt: "2099-01-01",
          sources: [{ id: "source:1", status: "verified" }],
          gaps: [],
          updatedAt: "2026-08-02T08:00:00Z",
        }],
      }));
    }, { workspace: workspaceId });

    await page.goto(`${shellOrigin}/?mod=idea-funnel`, { waitUntil: "domcontentloaded" });
    const frame = page.frameLocator('iframe[title="研究机会池"]');
    await frame.getByRole("tab", { name: "流程总览" }).click();
    await expect(frame.getByText("研究流程调度")).toBeVisible();
    await expect(frame.getByRole("heading", { name: "贵州茅台" })).toBeVisible();
    await expect(frame.getByRole("button", { name: "投资逻辑 · 到期" })).toBeVisible();
    await expect(frame.getByRole("button", { name: "机会池 · 未覆盖" })).toBeVisible();
    await expect(frame.getByText("1 个陈旧来源")).toBeVisible();
    await expect(frame.getByText(/尚未回链研究机会池/)).toBeVisible();
  });

  test("migrates research records to Desk storage and exposes the active record to Agent", async ({ page, request }) => {
    const workspaceId = `e2e-research-records-${Date.now()}`;
    const storageWrites: Array<{ status: number; records: Array<{ id: string }> }> = [];
    let agentPayload: Record<string, unknown> | undefined;

    page.on("response", async (response) => {
      if (
        response.request().method() === "PUT" &&
        response.url().includes("/storage/research-notes/records")
      ) {
        const body = response.request().postDataJSON() as {
          value?: { records?: Array<{ id: string }> };
        };
        storageWrites.push({
          status: response.status(),
          records: body.value?.records ?? [],
        });
      }
    });
    await page.route("**/api/agent/tasks**", async (route) => {
      const requestUrl = new URL(route.request().url());
      if (route.request().method() === "POST" && requestUrl.pathname === "/api/agent/tasks") {
        agentPayload = route.request().postDataJSON() as Record<string, unknown>;
        await route.fulfill({
          status: 202,
          contentType: "application/json",
          body: JSON.stringify({ id: "research-records-e2e-task", status: "queued" }),
        });
        return;
      }
      if (
        route.request().method() === "GET" &&
        requestUrl.pathname === "/api/agent/tasks/research-records-e2e-task"
      ) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            id: "research-records-e2e-task",
            status: "completed",
            result: { answer: "RESEARCH_RECORD_CONTEXT_OK" },
          }),
        });
        return;
      }
      await route.continue();
    });
    await page.addInitScript(({ workspace }) => {
      localStorage.setItem("vibedesk.userId.v1", "e2e-research-records-user");
      localStorage.setItem("vibedesk.workspaceId.v1", workspace);
      if (sessionStorage.getItem("e2e-research-records-seeded")) return;
      localStorage.removeItem("newma-desk.research-records.v1");
      localStorage.setItem("vr-notes", JSON.stringify([
        {
          id: "note:e2e-research-text",
          kind: "问AI",
          title: "E2E 轻量渲染",
          ts: 1785859200000,
          content: [
            "# ResearchText 标题",
            "",
            "这是 **加粗结论** 与 [公开来源](https://example.com/source)。",
            "",
            "- 第一项证据",
            "- 第二项证据",
            "",
            "| 指标 | 数值 |",
            "| --- | --- |",
            "| 收入 | 100 |",
            "",
            "```text",
            "evidence-id: 1",
            "```",
          ].join("\n"),
        },
        {
          id: "note:e2e-secondary",
          kind: "复盘",
          title: "E2E 第二条记录",
          ts: 1785859100000,
          content: "用于验证删除和清空同步。",
        },
      ]));
      sessionStorage.setItem("e2e-research-records-seeded", "1");
    }, { workspace: workspaceId });

    await page.goto(`${shellOrigin}/?mod=research-notes`, { waitUntil: "domcontentloaded" });
    let frame = page.frameLocator('iframe[title="研究记录"]');
    await expect(frame.getByRole("button", { name: /E2E 轻量渲染/ })).toBeVisible();
    await expect.poll(() => storageWrites.some((write) =>
      write.status === 200 && write.records.length === 2
    )).toBe(true);
    const migratedArchive = await request.get(`${apiOrigin}/api/research-archive`, {
      headers: {
        "X-User-Id": "e2e-research-records-user",
        "X-Workspace-Id": workspaceId,
      },
    });
    expect(migratedArchive.status()).toBe(200);
    await expect(migratedArchive.json()).resolves.toMatchObject({
      entries: expect.arrayContaining([
        expect.objectContaining({
          kind: "research-record",
          sourceModId: "research-notes",
          artifactId: "note:e2e-research-text",
          title: "E2E 轻量渲染",
        }),
      ]),
    });

    const frameElement = await page.locator('iframe[title="研究记录"]').elementHandle();
    const contentFrame = await frameElement?.contentFrame();
    expect(contentFrame).toBeTruthy();
    await contentFrame!.evaluate(() => {
      localStorage.removeItem("newma-desk.research-records.v1");
      localStorage.removeItem("vr-notes");
    });
    await page.reload({ waitUntil: "domcontentloaded" });
    frame = page.frameLocator('iframe[title="研究记录"]');
    await expect(frame.getByRole("button", { name: /E2E 轻量渲染/ })).toBeVisible();
    await frame.getByRole("button", { name: /E2E 轻量渲染/ }).click();
    await expect(frame.getByRole("heading", { name: "ResearchText 标题" })).toBeVisible();
    await expect(frame.getByText("第一项证据")).toBeVisible();
    await expect(frame.getByRole("cell", { name: "收入" })).toBeVisible();
    await expect(frame.getByRole("link", { name: "公开来源" })).toHaveAttribute("href", "https://example.com/source");
    await expect(frame.getByText("evidence-id: 1")).toBeVisible();

    await page.getByRole("button", { name: "问当前 Mod" }).click();
    const drawer = page.getByRole("complementary", { name: "研究记录 Agent" });
    await drawer.getByPlaceholder("就当前页面提问…").fill("总结当前展开的研究记录");
    await drawer.getByRole("button", { name: "发送" }).click();
    await expect(drawer).toContainText("RESEARCH_RECORD_CONTEXT_OK");
    expect(agentPayload).toMatchObject({
      moduleId: "research-notes",
      context: {
        vibedesk: {
          source: "mod-bridge",
          page: {
            selection: {
              recordId: "note:e2e-research-text",
              title: "E2E 轻量渲染",
            },
            data: {
              source: "newma-desk.research-records.v1",
              summary: {
                recordCount: 2,
                activeRecord: {
                  id: "note:e2e-research-text",
                  content: expect.stringContaining("ResearchText 标题"),
                },
              },
            },
          },
        },
      },
    });

    await drawer.getByRole("button", { name: "关闭 Agent 侧栏" }).click();
    await frame.getByRole("button", { name: "删除" }).first().click();
    await expect(frame.getByRole("button", { name: /E2E 轻量渲染/ })).toHaveCount(0);
    await expect.poll(() => storageWrites.some((write) =>
      write.status === 200 &&
      write.records.length === 1 &&
      write.records[0]?.id === "note:e2e-secondary"
    )).toBe(true);

    const activeFrameElement = await page.locator('iframe[title="研究记录"]').elementHandle();
    const activeContentFrame = await activeFrameElement?.contentFrame();
    expect(activeContentFrame).toBeTruthy();
    await activeContentFrame!.evaluate(() => {
      window.confirm = () => true;
    });
    await frame.getByRole("button", { name: "清空" }).click();
    await expect(frame.getByText("还没有记录")).toBeVisible();
    await expect.poll(() => storageWrites.some((write) =>
      write.status === 200 && write.records.length === 0
    )).toBe(true);
    await expect.poll(async () => {
      const response = await request.get(`${apiOrigin}/api/research-archive`, {
        headers: {
          "X-User-Id": "e2e-research-records-user",
          "X-Workspace-Id": workspaceId,
        },
      });
      const payload = await response.json() as { entries: Array<{ artifactId: string }> };
      return payload.entries.some((entry) => entry.artifactId === "note:e2e-research-text");
    }).toBe(false);
  });

  test("builds a reference-only research archive across Mod storage documents", async ({ page, request }) => {
    const userId = "e2e-research-archive-user";
    const workspaceId = `e2e-research-archive-${Date.now()}`;
    let agentPayload: Record<string, unknown> | undefined;

    const putStorage = async (
      moduleId: string,
      namespace: string,
      key: string,
      value: Record<string, unknown>,
    ) => {
      const instanceId = `${moduleId}-${Date.now()}`;
      const sessionResponse = await request.post(`${apiOrigin}/api/mods/${moduleId}/sessions`, {
        headers: { "X-User-Id": userId },
        data: { instanceId, workspaceId },
      });
      expect(sessionResponse.status()).toBe(201);
      const session = await sessionResponse.json() as { accessToken: string };
      const storageResponse = await request.put(
        `${apiOrigin}/api/mods/${moduleId}/storage/${namespace}/${key}`,
        {
          headers: {
            Authorization: `Bearer ${session.accessToken}`,
            "X-Newma-Desk-Instance-Id": instanceId,
          },
          data: { expectedRevision: 0, value },
        },
      );
      expect(storageResponse.status()).toBe(200);
    };

    await putStorage("research-notes", "research-notes", "records", {
      schemaVersion: "newma-desk.research-records.v1",
      updatedAt: "2026-08-05T07:00:00Z",
      records: [{
        id: "note:e2e-archive",
        kind: "复盘",
        title: "E2E 档案索引研究记录",
        content: "这段正文不应出现在统一索引响应。",
        ts: 1785913200000,
      }],
    });
    await putStorage("thesis-tracker", "thesis-tracker", "portfolio", {
      schemaVersion: "newma-desk.investment-thesis.v1",
      updatedAt: "2026-08-05T08:00:00Z",
      theses: [{
        id: "thesis:e2e-archive",
        title: "E2E 光模块产品迭代逻辑",
        status: "active",
        conviction: "medium",
        security: { market: "CN", symbol: "300308", name: "中际旭创" },
        statement: "这段逻辑正文不应出现在统一索引响应。",
        nextReviewAt: "2026-09-01",
        updatedAt: "2026-08-05T08:00:00Z",
      }],
    });

    const archiveResponse = await request.get(`${apiOrigin}/api/research-archive`, {
      headers: { "X-User-Id": userId, "X-Workspace-Id": workspaceId },
    });
    expect(archiveResponse.status()).toBe(200);
    const archiveText = await archiveResponse.text();
    expect(archiveText).toContain("E2E 光模块产品迭代逻辑");
    expect(archiveText).toContain("E2E 档案索引研究记录");
    expect(archiveText).not.toContain("这段正文不应出现在统一索引响应");
    expect(archiveText).not.toContain("这段逻辑正文不应出现在统一索引响应");

    await page.route("**/api/agent/tasks**", async (route) => {
      const requestUrl = new URL(route.request().url());
      if (route.request().method() === "POST" && requestUrl.pathname === "/api/agent/tasks") {
        agentPayload = route.request().postDataJSON() as Record<string, unknown>;
        await route.fulfill({
          status: 202,
          contentType: "application/json",
          body: JSON.stringify({ id: "research-archive-e2e-task", status: "queued" }),
        });
        return;
      }
      if (
        route.request().method() === "GET" &&
        requestUrl.pathname === "/api/agent/tasks/research-archive-e2e-task"
      ) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            id: "research-archive-e2e-task",
            status: "completed",
            result: { answer: "RESEARCH_ARCHIVE_CONTEXT_OK" },
          }),
        });
        return;
      }
      await route.continue();
    });
    await page.addInitScript(({ user, workspace }) => {
      localStorage.setItem("vibedesk.userId.v1", user);
      localStorage.setItem("vibedesk.workspaceId.v1", workspace);
    }, { user: userId, workspace: workspaceId });

    await page.goto(`${shellOrigin}/?mod=research-library`, { waitUntil: "domcontentloaded" });
    const frameElement = page.locator('iframe[title="研究档案"]');
    await expectFrameRoute(frameElement, "/mod-runtime/research/my-reports");
    const frame = page.frameLocator('iframe[title="研究档案"]');
    await expect(frame.getByText("E2E 光模块产品迭代逻辑")).toBeVisible();
    await expect(frame.getByText("E2E 光模块产品迭代逻辑")).toBeVisible();
    await expect(frame.getByText("E2E 档案索引研究记录")).toBeVisible();
    await expect(frame.getByText("中际旭创 · CN:300308")).toBeVisible();
    await expect(frame.getByRole("link", { name: "打开来源" }).first()).toHaveAttribute(
      "href",
      /mod=thesis-tracker.*artifact=thesis%3Ae2e-archive/,
    );

    await frame.getByText("E2E 光模块产品迭代逻辑").click();
    await page.getByRole("button", { name: "问当前 Mod" }).click();
    const drawer = page.getByRole("complementary", { name: "研究档案 Agent" });
    await drawer.getByPlaceholder("就当前页面提问…").fill("检查当前研究档案覆盖与缺口");
    await drawer.getByRole("button", { name: "发送" }).click();
    await expect(drawer).toContainText("RESEARCH_ARCHIVE_CONTEXT_OK");
    expect(agentPayload).toMatchObject({
      moduleId: "research-library",
      context: {
        vibedesk: {
          source: "mod-bridge",
          page: {
            selection: {
              kind: "thesis",
              sourceModId: "thesis-tracker",
              artifactId: "thesis:e2e-archive",
              title: "E2E 光模块产品迭代逻辑",
            },
            data: {
              source: "newma-desk.research-archive.v1",
              summary: {
                selectedReference: {
                  id: "archive:thesis-tracker:thesis:e2e-archive",
                  sourceRevision: 1,
                },
              },
            },
          },
        },
      },
    });
  });

  test("generates strategic allocation from cycle data and exposes it to Desk Agent", async ({ page }) => {
    const userId = "e2e-allocation-user";
    const workspaceId = `e2e-allocation-${Date.now()}`;
    let agentPayload: Record<string, unknown> | undefined;
    await page.route("**/api/agent/tasks**", async (route) => {
      const requestUrl = new URL(route.request().url());
      if (route.request().method() === "POST" && requestUrl.pathname === "/api/agent/tasks") {
        agentPayload = route.request().postDataJSON() as Record<string, unknown>;
        await route.fulfill({
          status: 202,
          contentType: "application/json",
          body: JSON.stringify({ id: "allocation-e2e-task", status: "queued" }),
        });
        return;
      }
      if (
        route.request().method() === "GET" &&
        requestUrl.pathname === "/api/agent/tasks/allocation-e2e-task"
      ) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            id: "allocation-e2e-task",
            status: "completed",
            result: { answer: "ALLOCATION_CONTEXT_OK" },
          }),
        });
        return;
      }
      await route.continue();
    });
    await page.addInitScript(({ user, workspace }) => {
      localStorage.setItem("vibedesk.userId.v1", user);
      localStorage.setItem("vibedesk.workspaceId.v1", workspace);
    }, { user: userId, workspace: workspaceId });

    await page.goto(`${shellOrigin}/?mod=portfolio-brief`, { waitUntil: "domcontentloaded" });
    const frameElement = page.locator('iframe[title="配置总览"]');
    await expectFrameRoute(frameElement, "/mod-runtime/portfolio-center/?workspace=portfolio-brief");
    const frame = page.frameLocator('iframe[title="配置总览"]');
    await expect(frame.getByText("组合预期收益")).toBeVisible();
    await expect(frame.getByRole("heading", { name: "目标资产配置" })).toBeVisible();
    await expect(frame.getByRole("columnheader", { name: "目标权重" })).toBeVisible();
    await expect(frame.getByRole("columnheader", { name: "预期收益" })).toBeVisible();
    await expect(frame.getByRole("columnheader", { name: "预期波动" })).toBeVisible();
    await expect(frame.getByText("周期数据").first()).toBeVisible();
    await expect(frame.getByText("Black-Litterman").first()).toBeVisible();

    await page.getByRole("button", { name: "问当前 Mod" }).click();
    const drawer = page.getByRole("complementary", { name: /配置总览 Agent/ });
    await expect(drawer).toBeVisible();
    await drawer.getByPlaceholder("就当前页面提问…").fill("解释当前目标资产配置");
    await drawer.getByRole("button", { name: "发送" }).click();
    await expect(drawer).toContainText("ALLOCATION_CONTEXT_OK");
    expect(agentPayload).toMatchObject({
      moduleId: "portfolio-brief",
      capability: "module.explain",
      context: {
        vibedesk: {
          source: "mod-bridge",
          page: {
            data: {
              source: "newma-seven-cycle + strategic-allocation",
              summary: {
                model: "black-litterman",
                assets: expect.arrayContaining([
                  expect.objectContaining({
                    targetWeightPct: expect.any(Number),
                    expectedReturnPct: expect.any(Number),
                    volatilityPct: expect.any(Number),
                  }),
                ]),
              },
            },
          },
        },
      },
    });
  });

  test("persists an earnings preview and comparison workbook through Desk storage", async ({
    page,
  }) => {
    const workspaceId = `e2e-earnings-${Date.now()}`;
    const storageWrites: number[] = [];
    page.on("response", (response) => {
      if (
        response.request().method() === "PUT" &&
        response.url().includes("/storage/earnings-workbench/workbooks")
      ) storageWrites.push(response.status());
    });
    await page.addInitScript(({ workspace }) => {
      localStorage.setItem("vibedesk.userId.v1", "e2e-earnings-user");
      localStorage.setItem("vibedesk.workspaceId.v1", workspace);
    }, { workspace: workspaceId });

    await page.goto(`${shellOrigin}/?mod=earnings-workbench`, { waitUntil: "domcontentloaded" });
    const frameElement = page.locator('iframe[title="财报研究"]');
    await expectFrameRoute(frameElement, "/mod-runtime/research/earnings-workbench");
    const frame = page.frameLocator('iframe[title="财报研究"]');
    await expect(frame.getByLabel("证券代码")).toBeVisible();
    await frame.getByLabel("证券代码").fill("600519");
    await frame.getByLabel("公司名称").fill("贵州茅台");
    await frame.getByLabel("报告期").fill("2026 半年报");
    await frame.getByLabel("营业收入 内部预期").fill("900");
    await frame.getByLabel("营业收入 一致预期").fill("905");
    await frame.getByRole("button", { name: "保存" }).click();
    await expect(frame.getByText("已保存到 Desk 工作区")).toBeVisible();
    await expect(frame.getByText("2026 半年报")).toBeVisible();
    await expect.poll(() => storageWrites.includes(200)).toBe(true);
  });

  test("persists an audited peer set through Desk storage", async ({ page }) => {
    const workspaceId = `e2e-peer-${Date.now()}`;
    const storageWrites: number[] = [];
    page.on("response", (response) => {
      if (
        response.request().method() === "PUT" &&
        response.url().includes("/storage/peer-comparison/cases")
      ) storageWrites.push(response.status());
    });
    await page.addInitScript(({ workspace }) => {
      localStorage.setItem("vibedesk.userId.v1", "e2e-peer-user");
      localStorage.setItem("vibedesk.workspaceId.v1", workspace);
    }, { workspace: workspaceId });

    await page.goto(`${shellOrigin}/?mod=peer-comparison`, { waitUntil: "domcontentloaded" });
    const frameElement = page.locator('iframe[title="同业比较"]');
    await expectFrameRoute(frameElement, "/mod-runtime/research/peer-comparison");
    const frame = page.frameLocator('iframe[title="同业比较"]');
    await expect(frame.getByLabel("比较名称")).toBeVisible();
    await frame.getByLabel("比较名称").fill("E2E 光模块同业比较");
    const symbols = ["300308", "300394", "002281"];
    const names = ["中际旭创", "天孚通信", "光迅科技"];
    for (let index = 0; index < symbols.length; index += 1) {
      await frame.getByPlaceholder("证券代码").nth(index).fill(symbols[index]!);
      await frame.getByPlaceholder("公司名称").nth(index).fill(names[index]!);
    }
    await frame.getByRole("button", { name: "保存" }).click();
    await expect(frame.getByText("已保存到 Desk 工作区")).toBeVisible();
    await expect(frame.getByText("E2E 光模块同业比较")).toBeVisible();
    await expect.poll(() => storageWrites.includes(200)).toBe(true);
  });

  test("persists a driver-based valuation model through Desk storage", async ({ page }) => {
    const workspaceId = `e2e-valuation-${Date.now()}`;
    const storageWrites: number[] = [];
    page.on("response", (response) => {
      if (
        response.request().method() === "PUT" &&
        response.url().includes("/storage/valuation-workbench/models")
      ) storageWrites.push(response.status());
    });
    await page.addInitScript(({ workspace }) => {
      localStorage.setItem("vibedesk.userId.v1", "e2e-valuation-user");
      localStorage.setItem("vibedesk.workspaceId.v1", workspace);
    }, { workspace: workspaceId });

    await page.goto(`${shellOrigin}/?mod=valuation-workbench`, { waitUntil: "domcontentloaded" });
    const frameElement = page.locator('iframe[title="预测与估值"]');
    await expectFrameRoute(frameElement, "/mod-runtime/research/valuation-workbench");
    const frame = page.frameLocator('iframe[title="预测与估值"]');
    await expect(frame.getByLabel("模型名称")).toBeVisible();
    await frame.getByLabel("模型名称").fill("E2E 光模块五年驱动式 DCF");
    await frame.getByLabel("证券代码").fill("300308");
    await frame.getByLabel("公司名称").fill("中际旭创");
    await frame.getByLabel("历史收入").fill("42000");
    await frame.getByLabel("当前股价").fill("180");
    await frame.getByLabel("稀释股数（百万股）").fill("1120");
    await frame.getByLabel("总债务").fill("3000");
    await frame.getByLabel("现金及等价物").fill("6000");
    await frame.getByRole("button", { name: "保存" }).click();
    await expect(frame.getByText("已保存到 Desk 工作区")).toBeVisible();
    await expect(frame.getByText("E2E 光模块五年驱动式 DCF")).toBeVisible();
    await expect.poll(() => storageWrites.includes(200)).toBe(true);
  });

  test("persists a versioned research memo through Desk storage", async ({ page }) => {
    const workspaceId = `e2e-research-memo-${Date.now()}`;
    const storageWrites: number[] = [];
    page.on("response", (response) => {
      if (
        response.request().method() === "PUT" &&
        response.url().includes("/storage/research-memo/memos")
      ) storageWrites.push(response.status());
    });
    await page.addInitScript(({ workspace }) => {
      localStorage.setItem("vibedesk.userId.v1", "e2e-research-memo-user");
      localStorage.setItem("vibedesk.workspaceId.v1", workspace);
    }, { workspace: workspaceId });

    await page.goto(`${shellOrigin}/?mod=research-memo`, { waitUntil: "domcontentloaded" });
    const frameElement = page.locator('iframe[title="研究备忘录"]');
    await expectFrameRoute(frameElement, "/mod-runtime/research/research-memo");
    const frame = page.frameLocator('iframe[title="研究备忘录"]');
    await expect(frame.getByLabel("备忘录标题")).toBeVisible();
    await frame.getByLabel("备忘录标题").fill("E2E 光模块研究备忘录");
    await frame.getByLabel("证券代码").fill("300308");
    await frame.getByLabel("公司名称").fill("中际旭创");
    await frame.getByLabel("研究结论").fill("需求保持韧性，但估值与供给扩张需要同步核验。");
    await frame.getByLabel("核心论点").fill("高速光模块需求、产品迭代和份额变化是主要价值驱动。");
    await frame.getByLabel("关键争议").fill("需求持续性是否足以覆盖供给扩张和利润率压力。");
    await frame.getByLabel("差异认知").fill("市场对产品迭代速度与利润率持续性的判断仍有分歧。");
    await frame.getByLabel("市场可能遗漏").fill("客户资本开支结构与 1.6T 放量节奏。");
    await frame.getByLabel("逻辑断点").fill("核心需求、份额和利润率同时连续恶化。");
    await frame.getByRole("button", { name: "保存" }).click();
    await expect(frame.getByText("已保存到 Desk 工作区")).toBeVisible();
    await expect(frame.getByText("E2E 光模块研究备忘录")).toBeVisible();
    await expect.poll(() => storageWrites.includes(200)).toBe(true);
  });

  test("shares watchlist groups, securities, events, and Agent context across the workspace", async ({
    page,
    request,
  }) => {
    test.slow();
    const userId = "e2e-watchlist-user";
    const workspaceId = `e2e-watchlist-workspace-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    const groupName = `E2E 半导体组合 ${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    let agentPayload: Record<string, unknown> | undefined;

    const quoteNames: Record<string, string> = {
      "600519": "贵州茅台",
      "688981": "中芯国际",
    };
    await page.route("**/api/research/market-terminal/quotes**", async (route) => {
      const symbols = new URL(route.request().url()).searchParams
        .get("symbols")
        ?.split(",")
        .filter(Boolean) ?? [];
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          data: {
            items: symbols.map((identity) => {
              const [market, symbol] = identity.split(":");
              return {
                symbol,
                name: quoteNames[symbol] ?? symbol,
                market,
                exchange: market === "CN" ? "SH" : undefined,
                currency: market === "CN" ? "CNY" : "USD",
                price: 100,
                change: 0,
                changePct: 0,
                source: "e2e-fixture",
                asOf: "2026-07-27T08:00:00Z",
              };
            }),
            asOf: "2026-07-27T08:00:00Z",
          },
        }),
      });
    });

    await page.addInitScript(({ user, workspace }) => {
      localStorage.setItem("vibedesk.userId.v1", user);
      localStorage.setItem("vibedesk.workspaceId.v1", workspace);
    }, { user: userId, workspace: workspaceId });
    await page.route("**/api/agent/tasks**", async (route) => {
      const requestUrl = new URL(route.request().url());
      if (
        route.request().method() === "POST" &&
        requestUrl.pathname === "/api/agent/tasks"
      ) {
        agentPayload = route.request().postDataJSON() as Record<string, unknown>;
        await route.fulfill({
          status: 202,
          contentType: "application/json",
          body: JSON.stringify({ id: "watchlist-e2e-task", status: "queued" }),
        });
        return;
      }
      if (
        route.request().method() === "GET" &&
        requestUrl.pathname === "/api/agent/tasks/watchlist-e2e-task"
      ) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            id: "watchlist-e2e-task",
            status: "completed",
            result: { answer: "WATCHLIST_CONTEXT_OK" },
          }),
        });
        return;
      }
      await route.continue();
    });

    await page.goto(`${shellOrigin}/?mod=watchlist`, {
      waitUntil: "domcontentloaded",
    });
    const frame = page.frameLocator('iframe[title="自选股"]');
    await expect(frame.getByText("Desk 已同步")).toBeVisible();

    await frame.getByRole("button", { name: "新建分组" }).click();
    await frame.getByRole("textbox", { name: "分组名称" }).fill(groupName);
    await frame.getByRole("button", { name: "保存", exact: true }).click();
    await expect(frame.getByRole("button", { name: new RegExp(groupName) })).toBeVisible();
    await frame.getByPlaceholder(/600519/).fill("600519 688981");
    await frame.getByRole("button", { name: "添加", exact: true }).click();
    await expect(frame.getByRole("button", { name: "贵州茅台" })).toBeVisible();
    await expect(frame.getByRole("button", { name: "中芯国际" })).toBeVisible();
    await expect(frame.getByText("Desk 已同步")).toBeVisible();

    const remoteResponse = await request.get(`${apiOrigin}/api/watchlists`, {
      headers: {
        "X-User-Id": userId,
        "X-Workspace-Id": workspaceId,
      },
    });
    expect(remoteResponse.status()).toBe(200);
    const remote = await remoteResponse.json() as {
      groups: Array<{
        name: string;
        symbols: Array<{ market: string; symbol: string }>;
      }>;
    };
    expect(remote.groups).toEqual(expect.arrayContaining([
      expect.objectContaining({
        name: groupName,
        symbols: expect.arrayContaining([
          expect.objectContaining({ market: "CN", symbol: "600519" }),
          expect.objectContaining({ market: "CN", symbol: "688981" }),
        ]),
      }),
    ]));

    await page.reload({ waitUntil: "domcontentloaded" });
    const restoredGroup = frame.getByRole("button", { name: new RegExp(groupName) });
    await expect(restoredGroup).toBeVisible();
    await restoredGroup.click();
    await frame.getByRole("button", { name: "贵州茅台" }).click();
    await expect(page.getByLabel("Mod 事件日志")).toContainText(
      "security.selected · 600519",
    );

    await page.getByRole("button", { name: "问当前 Mod" }).click();
    const drawer = page.getByRole("complementary", { name: "自选股 Agent" });
    await drawer.getByPlaceholder("就当前页面提问…").fill("概括当前自选组合");
    await drawer.getByRole("button", { name: "发送" }).click();
    await expect(drawer).toContainText("WATCHLIST_CONTEXT_OK");
    expect(agentPayload).toMatchObject({
      moduleId: "watchlist",
      context: {
        vibedesk: {
          source: "mod-bridge",
          page: {
            selection: {
              symbol: "600519",
              groupName,
            },
            data: {
              source: "vibedesk-watchlist-service",
              summary: {
                activeGroupSecurityCount: 2,
              },
            },
          },
        },
      },
    });

    await page.screenshot({
      path: "/tmp/vibedesk-watchlist-shared.png",
      fullPage: true,
    });

    await page.getByRole("button", { name: "公司 项目", exact: true }).click();
    await page.getByRole("button", { name: "公司档案", exact: true }).click();
    const researchFrame = page.frameLocator('iframe[title="公司档案"]');
    await expect(researchFrame.locator("#dossier-symbol")).toBeVisible();

    await page.getByRole("button", { name: "配置 项目", exact: true }).click();
    const portfolioNavigation = page.getByRole("complementary", {
      name: "配置 二级导航",
    });
    await portfolioNavigation.getByRole("button", { name: "总览", exact: true }).click();
    const portfolioFrame = page.frameLocator('iframe[title="配置总览"]');
    await expect(portfolioFrame.getByRole("heading", { name: "目标资产配置" })).toBeVisible();
  });

  test("uses the shared Desk Agent drawer with live Research and Trading page context", async ({
    page,
  }) => {
    const consoleErrors: string[] = [];
    page.on("console", (message) => {
      if (message.type() === "error") consoleErrors.push(message.text());
    });
    await page.route("https://fonts.googleapis.com/**", (route) =>
      route.fulfill({ status: 200, contentType: "text/css", body: "" }),
    );
    await page.route("https://fonts.gstatic.com/**", (route) =>
      route.fulfill({ status: 204, body: "" }),
    );

    const scenarios = [
      {
        id: "industry-map",
        name: "产业图谱",
        marker: "RESEARCH_SIDE_PANEL_OK",
        contextSource: "vibe-research-rendered-page",
      },
      {
        id: "alpha-lab",
        name: "因子实验室",
        marker: "TRADING_SIDE_PANEL_OK",
        contextSource: "vibe-trading-rendered-page",
      },
    ] as const;

    for (const scenario of scenarios) {
      await page.goto(`${shellOrigin}/?mod=${scenario.id}`, {
        waitUntil: "domcontentloaded",
      });
      await expect(page).toHaveTitle(/Newma-Desk/);
      await expect(page.locator(`iframe[title="${scenario.name}"]`)).toBeVisible();
      await page.getByRole("button", { name: "问当前 Mod" }).click();
      const drawer = page.getByRole("complementary", {
        name: `${scenario.name} Agent`,
      });
      await expect(drawer).toBeVisible();
      await expect(drawer).toContainText("Codex CLI");

      const prompt = `只回复 ${scenario.marker}`;
      await drawer.getByPlaceholder("就当前页面提问…").fill(prompt);
      const createResponsePromise = page.waitForResponse(
        (response) =>
          response.request().method() === "POST" &&
          new URL(response.url()).pathname === "/api/agent/tasks",
        { timeout: 20_000 },
      );
      await drawer.getByRole("button", { name: "发送" }).click();
      const createResponse = await createResponsePromise;
      expect(createResponse.status()).toBe(202);
      const body = createResponse.request().postDataJSON();
      expect(body).toMatchObject({
        moduleId: scenario.id,
        capability: "module.explain",
        context: {
          vibedesk: {
            mode: "ask",
            source: "mod-bridge",
            page: { data: { source: scenario.contextSource } },
          },
        },
      });
      await expect(drawer).toContainText(scenario.marker, { timeout: 90_000 });
    }

    expect(consoleErrors).toEqual([]);
  });

  test("opens company archive and company events with current terminology", async ({ page }) => {
    await page.goto(`${shellOrigin}/?mod=instock-stock-research`, {
      waitUntil: "domcontentloaded",
    });
    const frameElement = page.locator('iframe[title="公司档案"]');
    const src = await frameElement.getAttribute("src");
    expect(src).toBeTruthy();
    expect(new URL(src!).pathname).toBe("/mods/stock-research");
    const frame = page.frameLocator('iframe[title="公司档案"]');
    const input = frame.locator("#dossier-symbol");
    await expect(input).toBeVisible();
    await input.fill("600519");
    await frame.getByRole("button", { name: "生成档案", exact: true }).click();
    await expect(frame.locator("#dossier-name")).toContainText("600519", {
      timeout: 40_000,
    });
    await expect(frame.getByRole("heading", { name: /综合判断/ })).toBeVisible();
    await expect(frame.getByRole("heading", { name: /财务与估值/ })).toBeVisible();
    await expect(frame.getByRole("heading", { name: /K 线结构/ })).toBeVisible();
    await expect(frame.locator("#dossier-state")).toHaveText("完整");

    await page.getByRole("button", { name: "公司事件", exact: true }).click();
    const eventFrame = page.locator('iframe[title="公司事件"]');
    const eventSrc = await eventFrame.getAttribute("src");
    expect(eventSrc).toBeTruthy();
    expect(new URL(eventSrc!).pathname).toBe("/mods/event-flow");
    await expect(eventFrame).toBeVisible();
  });
});
