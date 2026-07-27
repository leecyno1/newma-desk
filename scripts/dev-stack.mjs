#!/usr/bin/env node

import { spawn } from "node:child_process";
import { existsSync, readFileSync, unlinkSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { registerStoreMods } from "./lib/mod-store.mjs";
import {
  loadExternalModRuntimes,
  runtimeEnvironment,
} from "./lib/external-mod-runtimes.mjs";
import {
  createHttpProbe,
  probeService,
  RuntimeSupervisor,
  SERVICE_CRITICALITY,
  SERVICE_STATE,
} from "./lib/runtime-supervisor.mjs";

const repoRoot = fileURLToPath(new URL("../", import.meta.url));
const args = new Set(process.argv.slice(2));
const checkOnly = args.has("--check");
const strictStatus = args.has("--strict");
const startupTimeoutMs = Number(process.env.NEWMA_DOCK_STARTUP_TIMEOUT_MS || 120_000);
const optionalStartupTimeoutMs = Number(
  process.env.NEWMA_DOCK_OPTIONAL_STARTUP_TIMEOUT_MS || 30_000,
);
const pidFile = process.env.NEWMA_DOCK_STACK_PID_FILE?.trim();
let shuttingDown = false;

function workspaceFrom(name, candidates) {
  const configured = process.env[name]?.trim();
  const paths = configured ? [configured] : candidates;
  for (const candidate of paths) {
    const resolved = path.resolve(repoRoot, candidate);
    if (existsSync(resolved)) return resolved;
  }
  return null;
}

function pythonAt(workspace) {
  const local = path.join(workspace, ".venv", "bin", "python");
  return existsSync(local) ? local : "python3";
}

function coreServices(externalRuntimeEnv = {}) {
  const apiPython = pythonAt(path.join(repoRoot, "services", "api"));
  return [
    {
      id: "newma-dock-api",
      label: "Newma-Dock API",
      cwd: repoRoot,
      command: apiPython,
      commandArgs: [
        "-m", "uvicorn", "vibe_visualization_api.main:app",
        "--app-dir", "services/api", "--host", "127.0.0.1", "--port", "8911",
      ],
      env: {
        ...externalRuntimeEnv,
        NEWMA_DOCK_ENABLE_DOMAIN_SUITES: "true",
        NEWMA_DOCK_INTEGRATED_DOMAIN_RUNTIME: "1",
        VIBEDESK_INTEGRATED_DOMAIN_RUNTIME: "1",
        NEWMA_DOCK_INVESTMENT_WORKSPACE: path.join(repoRoot, "mod-projects", "vibe-research"),
        NEWMA_DOCK_TRADING_WORKSPACE: path.join(repoRoot, "mod-projects", "vibe-trading"),
        NEWMA_DOCK_INVESTMENT_WEB_URL: "http://127.0.0.1:8911",
        NEWMA_DOCK_TRADING_WEB_URL: "http://127.0.0.1:8911",
        NEWMA_DOCK_RESEARCH_BASE_URL: "http://127.0.0.1:8911/api/research",
      },
      criticality: SERVICE_CRITICALITY.CORE,
      url: "http://127.0.0.1:8911/api/health",
      probe: createHttpProbe("http://127.0.0.1:8911/api/health", {
        expectedService: "newma-dock-api",
      }),
    },
    {
      id: "market-pulse",
      label: "Market Pulse",
      cwd: repoRoot,
      command: "npm",
      commandArgs: [
        "run", "dev", "-w", "@newma-dock/market-pulse", "--",
        "--host", "127.0.0.1", "--port", "5891", "--strictPort",
      ],
      env: {
        VITE_API_PROXY_TARGET: "http://127.0.0.1:8911",
        VITE_GATEWAY_BASE_URL: "http://127.0.0.1:8911",
        VITE_PARENT_ORIGIN: "http://127.0.0.1:5888",
      },
      criticality: SERVICE_CRITICALITY.CORE,
      url: "http://127.0.0.1:5891/",
      probe: createHttpProbe("http://127.0.0.1:5891/"),
    },
    {
      id: "newma-dock-web",
      label: "Newma-Dock",
      cwd: repoRoot,
      command: "npm",
      commandArgs: [
        "run", "dev:shell", "--", "--host", "127.0.0.1",
        "--port", "5888", "--strictPort",
      ],
      env: {
        VITE_API_PROXY_TARGET: "http://127.0.0.1:8911",
        VITE_MOD_ORIGIN: "http://127.0.0.1:5891",
      },
      criticality: SERVICE_CRITICALITY.CORE,
      url: "http://127.0.0.1:5888/",
      probe: createHttpProbe("http://127.0.0.1:5888/"),
    },
  ];
}

async function buildIntegratedFrontend(label, workspace, basePath, apiBase) {
  const frontend = path.join(workspace, "frontend");
  if (!existsSync(path.join(frontend, "package.json"))) {
    throw new Error(`${label} 前端源码不存在：${frontend}`);
  }
  console.log(`构建内置 ${label} Mod 运行时 -> ${basePath}`);
  const child = spawn("npm", ["run", "build"], {
    cwd: frontend,
    env: {
      ...process.env,
      NEWMA_DOCK_INTEGRATED: "1",
      VITE_BASE_PATH: basePath,
      VITE_API_BASE: apiBase,
    },
    stdio: "inherit",
  });
  await new Promise((resolve, reject) => {
    child.once("error", reject);
    child.once("exit", (code, signal) => {
      if (code === 0) resolve();
      else reject(new Error(`${label} 前端构建失败：code=${code ?? "-"} signal=${signal ?? "-"}`));
    });
  });
}

function sevenCycleServices(runtime) {
  if (!runtime) return [];
  const workspace = runtime.workspaces.source.path;
  const endpoint = runtime.endpoints.web;
  const localCommand = workspace
    ? path.join(workspace, ".venv", "bin", "seven-cycle")
    : undefined;
  const usesLocalCommand = localCommand ? existsSync(localCommand) : false;
  return [
    {
      id: "seven-cycle-research",
      label: "Seven Cycle Research",
      cwd: workspace,
      ...(workspace && endpoint.local
        ? {
            command: usesLocalCommand ? localCommand : "uv",
            commandArgs: [
              ...(usesLocalCommand ? [] : ["run", "seven-cycle"]),
              "serve", "--host", "127.0.0.1", "--port", String(endpoint.port),
            ],
          }
        : {}),
      criticality: endpoint.local
        ? SERVICE_CRITICALITY.OPTIONAL
        : SERVICE_CRITICALITY.EXTERNAL,
      url: endpoint.healthUrl,
      probe: createHttpProbe(endpoint.healthUrl, {
        expectedService: "seven-cycle-platform",
        degradedStatuses: [409],
      }),
    },
  ];
}

function instockServices(runtime) {
  if (!runtime) return [];
  const workspace = runtime.workspaces.source.path;
  const endpoint = runtime.endpoints.web;
  return [
    {
      id: "instock-analysis",
      label: "InStock Analysis",
      cwd: workspace,
      ...(workspace && endpoint.local
        ? {
            command: pythonAt(workspace),
            commandArgs: ["instock/web/web_service.py"],
          }
        : {}),
      env: {
        PYTHONUNBUFFERED: "1",
        INSTOCK_SKIP_DB: "1",
        INSTOCK_MARKET_DATA_PROVIDER: "vibedesk",
        NEWMA_DOCK_DATA_URL: "http://127.0.0.1:8911/api/research",
        NEWMA_DOCK_PARENT_ORIGIN: "http://127.0.0.1:5888",
        INSTOCK_EMBED_ORIGINS: "http://127.0.0.1:5888",
        INSTOCK_CORS_ORIGINS: "http://127.0.0.1:5888",
        INSTOCK_WEB_HOST: "127.0.0.1",
        INSTOCK_WEB_PORT: String(endpoint.port),
      },
      criticality: endpoint.local
        ? SERVICE_CRITICALITY.OPTIONAL
        : SERVICE_CRITICALITY.EXTERNAL,
      url: endpoint.healthUrl,
      probe: createHttpProbe(endpoint.healthUrl, {
        expectedService: "instock-analysis",
      }),
    },
  ];
}

function orchestraServices(runtime) {
  if (!runtime) return [];
  const frontendWorkspace = runtime.workspaces.frontend.path;
  const backendWorkspace = runtime.workspaces.backend.path;
  const webEndpoint = runtime.endpoints.web;
  const apiEndpoint = runtime.endpoints.api;
  return [
    {
      id: "orchestra-api",
      label: "Orchestra API",
      cwd: backendWorkspace,
      ...(backendWorkspace && apiEndpoint.local
        ? {
            command: pythonAt(backendWorkspace),
            commandArgs: ["-m", "orchestra_app.main"],
          }
        : {}),
      env: {
        PYTHONUNBUFFERED: "1",
        ORCHESTRA_API_HOST: "127.0.0.1",
        ORCHESTRA_API_PORT: String(apiEndpoint.port),
        ...(frontendWorkspace
          ? { ORCHESTRA_PROJECT_ROOT: path.dirname(frontendWorkspace) }
          : {}),
      },
      criticality: apiEndpoint.local
        ? SERVICE_CRITICALITY.OPTIONAL
        : SERVICE_CRITICALITY.EXTERNAL,
      url: apiEndpoint.healthUrl,
      probe: createHttpProbe(apiEndpoint.healthUrl, {
        expectedService: "orchestra",
      }),
    },
    {
      id: "orchestra-web",
      label: "Orchestra Web",
      cwd: frontendWorkspace,
      ...(frontendWorkspace && webEndpoint.local
        ? {
            command: "npm",
            commandArgs: [
              "run", "dev", "--", "--host", "127.0.0.1",
              "--port", String(webEndpoint.port), "--strictPort",
            ],
          }
        : {}),
      env: {
        ORCHESTRA_API_TARGET: apiEndpoint.origin,
        VITE_NEWMA_DOCK_PARENT_ORIGIN: "http://127.0.0.1:5888",
      },
      criticality: webEndpoint.local
        ? SERVICE_CRITICALITY.OPTIONAL
        : SERVICE_CRITICALITY.EXTERNAL,
      url: webEndpoint.healthUrl,
      probe: createHttpProbe(webEndpoint.healthUrl),
    },
  ];
}

async function statusLine(service) {
  const result = await probeService(service);
  const prefix = {
    [SERVICE_STATE.READY]: "OK  ",
    [SERVICE_STATE.DEGRADED]: "WARN",
    [SERVICE_STATE.UNAVAILABLE]: "MISS",
  }[result.state];
  const suffix = result.reason ? ` · ${result.reason}` : "";
  console.log(`${prefix} ${service.label.padEnd(28)} ${service.url}${suffix}`);
  return { service, ...result };
}

function claimPidFile() {
  if (!pidFile) return;
  if (existsSync(pidFile)) {
    const existingPid = Number(readFileSync(pidFile, "utf8").trim());
    let alive = false;
    if (Number.isInteger(existingPid) && existingPid > 0) {
      try {
        process.kill(existingPid, 0);
        alive = true;
      } catch {
        alive = false;
      }
    }
    if (alive && existingPid !== process.pid) {
      throw new Error(`Newma-Dock 统一启动器已运行（PID ${existingPid}）。`);
    }
    unlinkSync(pidFile);
  }
  writeFileSync(pidFile, `${process.pid}\n`, "utf8");
}

async function shutdown(exitCode = 0) {
  if (shuttingDown) return;
  shuttingDown = true;
  await supervisor.stopAll();
  if (pidFile && existsSync(pidFile)) unlinkSync(pidFile);
  process.exit(exitCode);
}

const researchWorkspace = workspaceFrom(
  "NEWMA_DOCK_INVESTMENT_WORKSPACE",
  ["mod-projects/vibe-research"],
);
const tradingWorkspace = workspaceFrom(
  "NEWMA_DOCK_TRADING_WORKSPACE",
  ["mod-projects/vibe-trading"],
);
const externalRuntimes = await loadExternalModRuntimes({ repoRoot });
const externalRuntimeEnv = runtimeEnvironment(externalRuntimes);
const core = coreServices(externalRuntimeEnv);
const sevenCycleRuntime = externalRuntimes.byId["seven-cycle"];
const instockRuntime = externalRuntimes.byId.instock;
const orchestraRuntime = externalRuntimes.byId.orchestra;
const deepseeRuntime = externalRuntimes.byId.deepsee;
const sevenCycle = sevenCycleServices(sevenCycleRuntime);
const instock = instockServices(instockRuntime);
const orchestra = orchestraServices(orchestraRuntime);
const domainSuites = {
  id: "domain-suites",
  label: "Research / Trading 内置领域运行时",
  criticality: SERVICE_CRITICALITY.CORE,
  url: "http://127.0.0.1:8911/api/domain-suites",
  probe: async () => {
    try {
      const response = await fetch("http://127.0.0.1:8911/api/domain-suites", {
        signal: AbortSignal.timeout(1_500),
        headers: { Accept: "application/json" },
      });
      if (!response.ok) {
        return { state: SERVICE_STATE.UNAVAILABLE, reason: `HTTP ${response.status}` };
      }
      const body = await response.json();
      const ready = body?.ok === true
        && body?.suites?.research === true
        && body?.suites?.trading === true;
      return ready
        ? { state: SERVICE_STATE.READY }
        : {
            state: SERVICE_STATE.UNAVAILABLE,
            reason: "Research / Trading domain suites are incomplete",
          };
    } catch (error) {
      return {
        state: SERVICE_STATE.UNAVAILABLE,
        reason: error instanceof Error ? error.message : String(error),
      };
    }
  },
};
const deepsee = {
  id: "deepsee",
  label: "Deepsee（独立服务）",
  criticality: SERVICE_CRITICALITY.EXTERNAL,
  url: deepseeRuntime.endpoints.web.healthUrl,
  probe: createHttpProbe(deepseeRuntime.endpoints.web.healthUrl, {
    expectedService: "deepsee",
  }),
};
const supervisor = new RuntimeSupervisor({
  coreTimeoutMs: startupTimeoutMs,
  optionalTimeoutMs: optionalStartupTimeoutMs,
  onCoreFailure: () => void shutdown(1),
});

if (!researchWorkspace) {
  console.warn("未找到 Vibe Research；请设置 NEWMA_DOCK_INVESTMENT_WORKSPACE。相关 Mods 将不可用。");
}
if (!tradingWorkspace) {
  console.warn("未找到 Vibe Trading；请设置 NEWMA_DOCK_TRADING_WORKSPACE。量化 Mods 将不可用。");
}
for (const runtime of externalRuntimes.runtimes) {
  for (const [name, workspace] of Object.entries(runtime.workspaces)) {
    if (!workspace.path) {
      console.warn(
        `未找到 ${runtime.label} ${name} 工作区；可设置 ${workspace.env}。运行入口将保持降级状态。`,
      );
    }
  }
}

if (checkOnly) {
  const results = [];
  for (const service of [...core, domainSuites, ...instock, ...orchestra, ...sevenCycle, deepsee]) {
    results.push(await statusLine(service));
  }
  const coreReady = results
    .filter(({ service }) => service.criticality === SERVICE_CRITICALITY.CORE)
    .every(({ state }) => state === SERVICE_STATE.READY);
  const allReady = results.every(({ state }) => state === SERVICE_STATE.READY);
  process.exitCode = (strictStatus ? allReady : coreReady) ? 0 : 1;
  if (coreReady && !allReady) {
    console.log("\nNewma-Dock 核心可用；部分可选或外部 Mod 当前处于降级状态。");
    console.log("如需把所有可选 Mod 也作为失败条件，请运行 npm run dev:status -- --strict。");
  }
} else {
  process.once("SIGINT", () => void shutdown(0));
  process.once("SIGTERM", () => void shutdown(0));
  process.once("SIGHUP", () => void shutdown(0));

  try {
    claimPidFile();
    if (!researchWorkspace || !tradingWorkspace) {
      throw new Error("Newma-Dock 内置领域运行时缺少 Research 或 Trading 源码目录。");
    }
    await buildIntegratedFrontend(
      "Research",
      researchWorkspace,
      "/mod-runtime/research/",
      "/api/research",
    );
    await buildIntegratedFrontend(
      "Trading",
      tradingWorkspace,
      "/mod-runtime/trading/",
      "/api/trading",
    );
    await supervisor.start(core[0]);
    const domainStatus = await statusLine(domainSuites);
    if (domainStatus.state !== SERVICE_STATE.READY) {
      throw new Error(
        `Research / Trading 内置领域运行时未就绪：${domainStatus.reason || domainSuites.url}`,
      );
    }
    await registerStoreMods({
      apiUrl: "http://127.0.0.1:8911",
      env: {
        ...process.env,
        ...externalRuntimeEnv,
        NEWMA_DOCK_INVESTMENT_WEB_URL: "http://127.0.0.1:8911",
        NEWMA_DOCK_TRADING_WEB_URL: "http://127.0.0.1:8911",
        NEWMA_DOCK_CONTROL_PLANE_URL: "http://127.0.0.1:8911",
      },
    });
    await supervisor.start(core[1]);
    await supervisor.start(core[2]);
    console.log("\nNewma-Dock 核心已就绪：http://127.0.0.1:5888/?mod=daily-review");
    console.log("Research / Trading 已作为 Newma-Dock 内置领域运行时加载，不再占用独立端口。");
    const optionalServices = [
      ...instock,
      ...orchestra,
      ...sevenCycle,
    ];
    const optionalResults = await supervisor.startOptional(
      optionalServices.filter((service) => service.command),
    );
    for (const service of optionalServices.filter((item) => !item.command)) {
      optionalResults.push(await statusLine(service));
    }
    const externalResult = await statusLine(deepsee);
    const degradedCount = [...optionalResults, externalResult]
      .filter(({ state }) => state !== SERVICE_STATE.READY)
      .length;
    if (degradedCount > 0) {
      console.log(`可选 Mod 状态：${degradedCount} 个未完全就绪；Desk 核心继续运行。`);
    } else {
      console.log("可选 Mod 状态：全部就绪。");
    }
    console.log("按 Ctrl+C 可停止本次启动的服务；Deepsee 等独立服务不会被关闭。");
    await new Promise(() => {
      // Node 25 exits with code 13 for an unsettled top-level await when no
      // child process or other active handle exists. This interval keeps the
      // supervisor alive even when every service was reused.
      setInterval(() => {}, 60_000);
    });
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    await shutdown(1);
  }
}
