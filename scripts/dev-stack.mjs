#!/usr/bin/env node

import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { registerStoreMods } from "./lib/mod-store.mjs";
import {
  loadExternalModRuntimes,
  runtimeEnvironment,
} from "./lib/external-mod-runtimes.mjs";
import {
  createCompositeProbe,
  createHttpProbe,
  probeService,
  RuntimeSupervisor,
  SERVICE_CRITICALITY,
  SERVICE_STATE,
} from "./lib/runtime-supervisor.mjs";
import {
  claimProcessLock,
  releaseProcessLock,
} from "./lib/process-lock.mjs";

const repoRoot = fileURLToPath(new URL("../", import.meta.url));
const args = new Set(process.argv.slice(2));
const checkOnly = args.has("--check");
const strictStatus = args.has("--strict");

function configuredEnv(name) {
  const suffix = name.startsWith("NEWMA_DESK_")
    ? name.slice("NEWMA_DESK_".length)
    : name;
  return (
    process.env[`NEWMA_DESK_${suffix}`]?.trim() ||
    process.env[`NEWMA_DOCK_${suffix}`]?.trim() ||
    process.env[`VIBEDESK_${suffix}`]?.trim()
  );
}

function configuredBoolean(name, defaultValue = false) {
  const value = configuredEnv(name);
  if (!value) return defaultValue;
  return !["0", "false", "no", "off"].includes(value.toLowerCase());
}

const startupTimeoutMs = Number(configuredEnv("STARTUP_TIMEOUT_MS") || 120_000);
const optionalStartupTimeoutMs = Number(
  configuredEnv("OPTIONAL_STARTUP_TIMEOUT_MS") || 30_000,
);
const runtimeHealthIntervalMs = Number(
  configuredEnv("RUNTIME_HEALTH_INTERVAL_MS") || 5_000,
);
const runtimeHealthFailureThreshold = Number(
  configuredEnv("RUNTIME_HEALTH_FAILURE_THRESHOLD") || 3,
);
const runtimeRestartGraceMs = Number(
  configuredEnv("RUNTIME_RESTART_GRACE_MS") || 1_000,
);
const runtimePortReleaseTimeoutMs = Number(
  configuredEnv("RUNTIME_PORT_RELEASE_TIMEOUT_MS") || 5_000,
);
const sevenCycleHealthTimeoutMs = Number(
  configuredEnv("SEVEN_CYCLE_HEALTH_TIMEOUT_MS") || 5_000,
);
const repairSevenCycleCatalogOnStart = configuredBoolean(
  "SEVEN_CYCLE_REPAIR_CATALOG_ON_START",
  true,
);
const pidFile = configuredEnv("STACK_PID_FILE")
  || path.join(repoRoot, "runtime", "newma-desk-stack.pid");
let shuttingDown = false;

function withLocalProxyBypass(...values) {
  const entries = values
    .flatMap((value) => String(value || "").split(","))
    .map((value) => value.trim())
    .filter(Boolean);
  return [...new Set([...entries, "127.0.0.1", "localhost", "::1"])].join(",");
}

const localNoProxy = withLocalProxyBypass(
  process.env.NO_PROXY,
  process.env.no_proxy,
);
process.env.NO_PROXY = localNoProxy;
process.env.no_proxy = localNoProxy;

function workspaceFrom(name, candidates) {
  const configured = configuredEnv(name);
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

const apiHealthUrl = "http://127.0.0.1:8911/api/health";
const domainSuitesUrl = "http://127.0.0.1:8911/api/domain-suites";

function createDomainSuitesProbe() {
  return async () => {
    try {
      const response = await fetch(domainSuitesUrl, {
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
  };
}

function createApiReadinessProbe() {
  return createCompositeProbe([
    {
      label: "API health",
      probe: createHttpProbe(apiHealthUrl, {
        expectedService: "newma-desk-api",
      }),
    },
    {
      label: "Research / Trading domain suites",
      probe: createDomainSuitesProbe(),
    },
  ]);
}

function coreServices(externalRuntimeEnv = {}) {
  const apiPython = pythonAt(path.join(repoRoot, "services", "api"));
  return [
    {
      id: "newma-desk-api",
      label: "Newma-Desk API",
      cwd: repoRoot,
      command: apiPython,
      commandArgs: [
        "-m", "uvicorn", "vibe_visualization_api.main:app",
        "--app-dir", "services/api", "--host", "127.0.0.1", "--port", "8911",
      ],
      env: {
        ...externalRuntimeEnv,
        NEWMA_DESK_ENABLE_DOMAIN_SUITES: "true",
        NEWMA_DESK_INTEGRATED_DOMAIN_RUNTIME: "1",
        VIBEDESK_INTEGRATED_DOMAIN_RUNTIME: "1",
        // Local compatibility only. Production installs one pinned dependency
        // set into the API image and never mixes nested virtual environments.
        NEWMA_DESK_DOMAIN_SUITE_WORKSPACE_VENVS: "true",
        NEWMA_DESK_INVESTMENT_WORKSPACE: path.join(repoRoot, "mod-projects", "vibe-research"),
        NEWMA_DESK_TRADING_WORKSPACE: path.join(repoRoot, "mod-projects", "vibe-trading"),
        NEWMA_DESK_INVESTMENT_WEB_URL: "http://127.0.0.1:8911",
        NEWMA_DESK_TRADING_WEB_URL: "http://127.0.0.1:8911",
        NEWMA_DESK_RESEARCH_BASE_URL: "http://127.0.0.1:8911/api/research",
      },
      criticality: SERVICE_CRITICALITY.CORE,
      url: apiHealthUrl,
      probe: createApiReadinessProbe(),
    },
    {
      id: "newma-desk-web",
      label: "Newma-Desk",
      cwd: repoRoot,
      command: "npm",
      commandArgs: [
        "run", "dev:shell", "--", "--host", "127.0.0.1",
        "--port", "5888", "--strictPort",
      ],
      env: {
        VITE_API_PROXY_TARGET: "http://127.0.0.1:8911",
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
      NEWMA_DESK_INTEGRATED: "1",
      NEWMA_DOCK_INTEGRATED: "1",
      VITE_NEWMA_DESK_INTEGRATED: "1",
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

async function buildFirstPartyModule(label, workspaceName) {
  console.log(`构建内置 ${label} Mod`);
  const child = spawn("npm", ["run", "build", "-w", workspaceName], {
    cwd: repoRoot,
    env: process.env,
    stdio: "inherit",
  });
  await new Promise((resolve, reject) => {
    child.once("error", reject);
    child.once("exit", (code, signal) => {
      if (code === 0) resolve();
      else reject(new Error(`${label} 构建失败：code=${code ?? "-"} signal=${signal ?? "-"}`));
    });
  });
}

async function runSetupCommand(label, command, commandArgs, cwd) {
  console.log(label);
  const child = spawn(command, commandArgs, {
    cwd,
    env: process.env,
    stdio: "inherit",
  });
  await new Promise((resolve, reject) => {
    child.once("error", reject);
    child.once("exit", (code, signal) => {
      if (code === 0) resolve();
      else reject(new Error(`${label}失败：code=${code ?? "-"} signal=${signal ?? "-"}`));
    });
  });
}

async function ensureWorldIntelRuntime(runtime) {
  const workspace = runtime?.workspaces.source.path;
  if (!workspace) {
    throw new Error("未找到 World Intelligence MCP 源码目录。");
  }
  const venvPython = path.join(workspace, ".venv", "bin", "python");
  if (!existsSync(venvPython)) {
    const bootstrapPython = existsSync("/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12")
      ? "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12"
      : "python3";
    await runSetupCommand(
      "初始化 World Intelligence MCP Python 环境",
      bootstrapPython,
      ["-m", "venv", ".venv"],
      workspace,
    );
  }
  const importCheck = spawn(venvPython, [
    "-c",
    "import world_intel_mcp.dashboard.app",
  ], {
    cwd: workspace,
    env: process.env,
    stdio: "ignore",
  });
  const ready = await new Promise((resolve) => {
    importCheck.once("error", () => resolve(false));
    importCheck.once("exit", (code) => resolve(code === 0));
  });
  if (ready) return;
  await runSetupCommand(
    "安装 World Intelligence MCP 与 Dashboard 依赖",
    venvPython,
    ["-m", "pip", "install", "-e", ".[dashboard]"],
    workspace,
  );
}

function worldIntelServices(runtime) {
  if (!runtime) return [];
  const workspace = runtime.workspaces.source.path;
  const endpoint = runtime.endpoints.api;
  return [{
    id: "world-intel-mcp",
    label: "World Intelligence MCP",
    cwd: workspace,
    ...(workspace && endpoint.local
      ? {
          command: pythonAt(workspace),
          commandArgs: [
            "-m", "world_intel_mcp.dashboard.app",
            "--host", "127.0.0.1",
            "--port", String(endpoint.port),
          ],
        }
      : {}),
    env: {
      PYTHONUNBUFFERED: "1",
      WORLD_INTEL_DASHBOARD_HOST: "127.0.0.1",
      WORLD_INTEL_DASHBOARD_PORT: String(endpoint.port),
    },
    criticality: SERVICE_CRITICALITY.CORE,
    url: endpoint.healthUrl,
    probe: createHttpProbe(endpoint.healthUrl, {
      expectedService: "world-intel-mcp",
    }),
  }];
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
              ...(repairSevenCycleCatalogOnStart
                ? ["--repair-catalog-on-start"]
                : []),
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
        timeoutMs: sevenCycleHealthTimeoutMs,
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
        NEWMA_DESK_DATA_URL: "http://127.0.0.1:8911/api/research",
        NEWMA_DESK_PARENT_ORIGIN: "http://127.0.0.1:5888",
        NEWMA_DOCK_DATA_URL: "http://127.0.0.1:8911/api/research",
        NEWMA_DOCK_PARENT_ORIGIN: "http://127.0.0.1:5888",
        VIBEDESK_DATA_URL: "http://127.0.0.1:8911/api/research",
        VIBEDESK_PARENT_ORIGIN: "http://127.0.0.1:5888",
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
        VITE_NEWMA_DESK_PARENT_ORIGIN: "http://127.0.0.1:5888",
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
  claimProcessLock(pidFile, { label: "Newma-Desk 统一启动器" });
}

async function shutdown(exitCode = 0) {
  if (shuttingDown) return;
  shuttingDown = true;
  await supervisor.stopAll();
  releaseProcessLock(pidFile);
  process.exit(exitCode);
}

const researchWorkspace = workspaceFrom(
  "NEWMA_DESK_INVESTMENT_WORKSPACE",
  ["mod-projects/vibe-research"],
);
const tradingWorkspace = workspaceFrom(
  "NEWMA_DESK_TRADING_WORKSPACE",
  ["mod-projects/vibe-trading"],
);
const externalRuntimes = await loadExternalModRuntimes({ repoRoot });
const externalRuntimeEnv = runtimeEnvironment(externalRuntimes);
const core = coreServices(externalRuntimeEnv);
const worldIntelRuntime = externalRuntimes.byId["world-intel"];
const sevenCycleRuntime = externalRuntimes.byId["seven-cycle"];
const instockRuntime = externalRuntimes.byId.instock;
const orchestraRuntime = externalRuntimes.byId.orchestra;
const deepseeRuntime = externalRuntimes.byId.deepsee;
const worldIntel = worldIntelServices(worldIntelRuntime);
const sevenCycle = sevenCycleServices(sevenCycleRuntime);
const instock = instockServices(instockRuntime);
const orchestra = orchestraServices(orchestraRuntime);
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
  monitorIntervalMs: runtimeHealthIntervalMs,
  monitorFailureThreshold: runtimeHealthFailureThreshold,
  restartGraceMs: runtimeRestartGraceMs,
  portReleaseTimeoutMs: runtimePortReleaseTimeoutMs,
  onCoreFailure: () => void shutdown(1),
});

if (!researchWorkspace) {
  console.warn("未找到 Vibe Research；请设置 NEWMA_DESK_INVESTMENT_WORKSPACE。相关 Mods 将不可用。");
}
if (!tradingWorkspace) {
  console.warn("未找到 Vibe Trading；请设置 NEWMA_DESK_TRADING_WORKSPACE。量化 Mods 将不可用。");
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
  for (const service of [...worldIntel, ...core, ...instock, ...orchestra, ...sevenCycle, deepsee]) {
    results.push(await statusLine(service));
  }
  const coreReady = results
    .filter(({ service }) => service.criticality === SERVICE_CRITICALITY.CORE)
    .every(({ state }) => state === SERVICE_STATE.READY);
  const allReady = results.every(({ state }) => state === SERVICE_STATE.READY);
  process.exitCode = (strictStatus ? allReady : coreReady) ? 0 : 1;
  if (coreReady && !allReady) {
    console.log("\nNewma-Desk 核心可用；部分可选或外部 Mod 当前处于降级状态。");
    console.log("如需把所有可选 Mod 也作为失败条件，请运行 npm run dev:status -- --strict。");
  }
} else {
  process.once("SIGINT", () => void shutdown(0));
  process.once("SIGTERM", () => void shutdown(0));
  process.once("SIGHUP", () => void shutdown(0));

  try {
    claimPidFile();
    if (!researchWorkspace || !tradingWorkspace) {
      throw new Error("Newma-Desk 内置领域运行时缺少 Research 或 Trading 源码目录。");
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
    await buildFirstPartyModule(
      "Portfolio Center",
      "@newma-desk/portfolio-center",
    );
    await ensureWorldIntelRuntime(worldIntelRuntime);
    for (const service of worldIntel) {
      await supervisor.start(service);
    }
    await supervisor.start(core[0]);
    await registerStoreMods({
      apiUrl: "http://127.0.0.1:8911",
      env: {
        ...process.env,
        ...externalRuntimeEnv,
        NEWMA_DESK_INVESTMENT_WEB_URL: "http://127.0.0.1:8911",
        NEWMA_DESK_TRADING_WEB_URL: "http://127.0.0.1:8911",
        NEWMA_DESK_CONTROL_PLANE_URL: "http://127.0.0.1:8911",
      },
    });
    for (const service of core.slice(1)) {
      await supervisor.start(service);
    }
    console.log("\nNewma-Desk 核心已就绪：http://127.0.0.1:5888/?mod=daily-review");
    console.log("Research / Trading 与 World Intelligence 已作为 Newma-Desk 核心运行时加载。");
    const optionalServices = [
      ...instock,
      ...orchestra,
      ...sevenCycle,
    ];
    const optionalResults = await supervisor.startOptional(
      optionalServices,
    );
    const externalResult = await supervisor.start(deepsee);
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
