#!/usr/bin/env node

import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { loadLocalEnvironment } from "./lib/local-env.mjs";

import {
  createRuntimeProfilePlan,
  resolveRuntimeProfile,
} from "./lib/dev-stack-profile.mjs";
import { registerDefaultMods } from "./lib/mod-store.mjs";
import {
  loadExternalModRuntimes,
  runtimeEnvironment,
} from "./lib/external-mod-runtimes.mjs";
import { createRuntimeServiceGroups } from "./lib/runtime-descriptor-services.mjs";
import { sevenCycleLaunch, sevenCyclePreparation } from "./lib/seven-cycle-runtime.mjs";
import {
  createCompositeProbe,
  createHttpProbe,
  RuntimeSupervisor,
  SERVICE_CRITICALITY,
  SERVICE_STATE,
} from "./lib/runtime-supervisor.mjs";
import {
  collectRuntimeStatus,
  createRuntimeStatusReport,
  formatRuntimeStatusLine,
} from "./lib/runtime-status.mjs";
import {
  claimProcessLock,
  ProcessLockError,
  releaseProcessLock,
} from "./lib/process-lock.mjs";
import {
  runRuntimeBuildTasks,
  runtimeBuildDecision,
} from "./lib/runtime-build.mjs";
import {
  createRuntimeProcessLedger,
  recoverRuntimeProcesses,
} from "./lib/runtime-process-ledger.mjs";

const repoRoot = fileURLToPath(new URL("../", import.meta.url));
loadLocalEnvironment(repoRoot);
const rawArgs = process.argv.slice(2);
const args = new Set(rawArgs);
const checkOnly = args.has("--check");
const strictStatus = args.has("--strict");
const jsonStatus = checkOnly && args.has("--json");
const forceRebuild = args.has("--rebuild");
const runtimeProfile = resolveRuntimeProfile(rawArgs, process.env);

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
const repairSevenCycleCatalogOnStart = configuredBoolean(
  "SEVEN_CYCLE_REPAIR_CATALOG_ON_START",
  false,
);
const runtimeBuildConcurrency = Number(
  configuredEnv("RUNTIME_BUILD_CONCURRENCY") || 2,
);
const pidFile = configuredEnv("STACK_PID_FILE")
  || path.join(repoRoot, "runtime", "newma-desk-stack.pid");
const processLedgerFile = configuredEnv("STACK_PROCESS_LEDGER_FILE")
  || path.join(repoRoot, "runtime", "newma-desk-managed-processes.json");
let shuttingDown = false;
let processLedger = null;

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
        // API 繁忙（快照生成/SQLite 写/恢复任务）时短暂无响应属正常，
        // 1.5s 会误判 UNAVAILABLE 并叠加成核心重启/停机，放宽到 5s。
        signal: AbortSignal.timeout(5_000),
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
        NEWMA_DESK_POLICY_RSSHUB_BASE_URL: "http://127.0.0.1:1200",
        NEWMA_DESK_ENABLE_DOMAIN_SUITES: "true",
        NEWMA_DESK_INTEGRATED_DOMAIN_RUNTIME: "1",
        VIBEDESK_INTEGRATED_DOMAIN_RUNTIME: "1",
        // Local compatibility only. Production installs one pinned dependency
        // set into the API image and never mixes nested virtual environments.
        NEWMA_DESK_DOMAIN_SUITE_WORKSPACE_VENVS: "true",
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
  const signature = JSON.stringify({
    integrated: true,
    basePath,
    apiBase,
  });
  const signatureFile = path.join(frontend, "dist", ".newma-build-signature");
  const decision = await runtimeBuildDecision({
    output: path.join(frontend, "dist", "index.html"),
    inputs: [
      path.join(frontend, "src"),
      path.join(frontend, "index.html"),
      path.join(frontend, "package.json"),
      path.join(frontend, "package-lock.json"),
      path.join(frontend, "tsconfig.json"),
      path.join(frontend, "vite.config.ts"),
    ],
    force: forceRebuild,
    signature,
    signatureFile,
  });
  if (!decision.build) {
    console.log(`跳过内置 ${label} Mod 构建（产物已是最新）`);
    return;
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
  await writeFile(signatureFile, `${signature}\n`, "utf8");
}

async function buildFirstPartyModule(label, workspaceName, workspacePath) {
  const workspace = path.join(repoRoot, workspacePath);
  const decision = await runtimeBuildDecision({
    output: path.join(workspace, "dist", "index.html"),
    inputs: [
      path.join(workspace, "src"),
      path.join(workspace, "index.html"),
      path.join(workspace, "package.json"),
      path.join(workspace, "tsconfig.json"),
      path.join(workspace, "vite.config.ts"),
      path.join(repoRoot, "packages", "contracts", "src"),
      path.join(repoRoot, "packages", "module-sdk", "src"),
      path.join(repoRoot, "package-lock.json"),
    ],
    force: forceRebuild,
  });
  if (!decision.build) {
    console.log(`跳过内置 ${label} Mod 构建（产物已是最新）`);
    return;
  }
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

async function ensureSevenCycleRuntime(runtime) {
  const workspace = runtime?.workspaces.source.path;
  if (!workspace) {
    throw new Error("未找到 Seven Cycle 源码目录。");
  }
  const preparation = sevenCyclePreparation({ workspace });
  if (!preparation) return;
  await runSetupCommand(
    "校验 Seven Cycle 本地数据索引",
    preparation.command,
    preparation.commandArgs,
    workspace,
  );
}

function openChatCutLaunch({ endpoint }) {
  const configuredNode = configuredEnv("OPENCHATCUT_NODE_BIN");
  const configuredNpmCli = configuredEnv("OPENCHATCUT_NPM_CLI");
  const node24 = configuredNode || "/opt/homebrew/opt/node@24/bin/node";
  const npmCli = configuredNpmCli
    || "/opt/homebrew/opt/node@24/lib/node_modules/npm/bin/npm-cli.js";
  const pinnedNodeRuntime = existsSync(node24) && existsSync(npmCli);
  return {
    command: pinnedNodeRuntime ? node24 : "npm",
    commandArgs: [
      ...(pinnedNodeRuntime ? [npmCli] : []),
      "run", "dev:shared", "--",
      "--host", "127.0.0.1",
      "--port", String(endpoint.port),
      "--strictPort",
    ],
  };
}

async function claimPidFile() {
  claimProcessLock(pidFile, { label: "Newma-Desk 统一启动器" });
  const recovery = await recoverRuntimeProcesses(processLedgerFile);
  if (recovery.status === "active-owner") {
    releaseProcessLock(pidFile);
    throw new ProcessLockError(
      `Newma-Desk 统一启动器已运行（PID ${recovery.ownerPid}）。`,
    );
  }
  if (recovery.recoveredServiceIds.length > 0) {
    console.log(
      `已清理上次异常退出遗留的 Mod：${recovery.recoveredServiceIds.join(", ")}`,
    );
  }
  if (recovery.skippedServiceIds.length > 0) {
    console.warn(
      `跳过身份不匹配的旧进程：${recovery.skippedServiceIds.join(", ")}`,
    );
  }
  processLedger = createRuntimeProcessLedger(processLedgerFile);
}

async function shutdown(exitCode = 0) {
  if (shuttingDown) return;
  shuttingDown = true;
  await supervisor.stopAll();
  processLedger?.clear();
  releaseProcessLock(pidFile);
  process.exit(exitCode);
}

const researchWorkspace = workspaceFrom(
  "NEWMA_DESK_INVESTMENT_WORKSPACE",
  ["bundled-runtimes/vibe-research", "mod-projects/vibe-research"],
);
const tradingWorkspace = workspaceFrom(
  "NEWMA_DESK_TRADING_WORKSPACE",
  ["bundled-runtimes/vibe-trading", "mod-projects/vibe-trading"],
);
const externalRuntimes = await loadExternalModRuntimes({ repoRoot });
const externalRuntimeEnv = runtimeEnvironment(externalRuntimes);
const core = coreServices(externalRuntimeEnv);
const runtimeServiceGroups = createRuntimeServiceGroups(externalRuntimes, {
  env: process.env,
  launchAdapters: {
    openchatcut: openChatCutLaunch,
    "seven-cycle": (options) => sevenCycleLaunch({
      ...options, repairCatalogOnStart: repairSevenCycleCatalogOnStart,
    }),
  },
  prepareAdapters: {
    "world-intel": ({ runtime }) => ensureWorldIntelRuntime(runtime),
    "seven-cycle": ({ runtime }) => ensureSevenCycleRuntime(runtime),
  },
});
const runtimePlan = createRuntimeProfilePlan(runtimeProfile, {
  core,
  ...runtimeServiceGroups,
}, externalRuntimes.profiles);
const supervisor = new RuntimeSupervisor({
  coreTimeoutMs: startupTimeoutMs,
  optionalTimeoutMs: optionalStartupTimeoutMs,
  monitorIntervalMs: runtimeHealthIntervalMs,
  monitorFailureThreshold: runtimeHealthFailureThreshold,
  restartGraceMs: runtimeRestartGraceMs,
  portReleaseTimeoutMs: runtimePortReleaseTimeoutMs,
  onCoreFailure: () => void shutdown(1),
  onProcessStarted: ({ service, child }) => {
    if (!processLedger?.track(service, child)) {
      throw new Error(`无法记录 ${service.label} 的运行时所有权。`);
    }
  },
  onProcessStopped: ({ child }) => {
    processLedger?.untrack(child);
  },
});

if (!jsonStatus) {
  if (!researchWorkspace) {
    console.warn("未找到 Vibe Research；请设置 NEWMA_DESK_INVESTMENT_WORKSPACE。相关 Mods 将不可用。");
  }
  if (!tradingWorkspace) {
    console.warn("未找到 Vibe Trading；请设置 NEWMA_DESK_TRADING_WORKSPACE。量化 Mods 将不可用。");
  }
  for (const runtime of externalRuntimes.runtimes.filter(({ id }) =>
    runtimePlan.externalRuntimeIds.includes(id)
  )) {
    for (const [name, workspace] of Object.entries(runtime.workspaces)) {
      if (!workspace.path) {
        console.warn(
          `未找到 ${runtime.label} ${name} 工作区；可设置 ${workspace.env}。运行入口将保持降级状态。`,
        );
      }
    }
  }
}

if (checkOnly) {
  const results = await collectRuntimeStatus(runtimePlan.allServices);
  const report = createRuntimeStatusReport({
    profile: runtimeProfile,
    results,
  });
  process.exitCode = (
    strictStatus ? report.summary.allReady : report.summary.coreReady
  ) ? 0 : 1;

  if (jsonStatus) {
    console.log(JSON.stringify(report, null, 2));
  } else {
    console.log(`Runtime Profile: ${runtimeProfile}`);
    for (const result of results) {
      console.log(formatRuntimeStatusLine(result));
    }
  }
  if (!jsonStatus && report.summary.coreReady && !report.summary.allReady) {
    console.log("\nNewma-Desk 核心可用；部分可选或外部 Mod 当前处于降级状态。");
    console.log("如需把所有可选 Mod 也作为失败条件，请运行 npm run dev:status -- --strict。");
  }
} else {
  process.once("exit", () => {
    supervisor.stopAllSync();
    releaseProcessLock(pidFile);
  });
  process.once("SIGINT", () => void shutdown(0));
  process.once("SIGTERM", () => void shutdown(0));
  process.once("SIGHUP", () => void shutdown(0));

  try {
    await claimPidFile();
    if (!researchWorkspace || !tradingWorkspace) {
      throw new Error("Newma-Desk 内置领域运行时缺少 Research 或 Trading 源码目录。");
    }
    await runRuntimeBuildTasks([
      () => buildIntegratedFrontend(
        "Research",
        researchWorkspace,
        "/mod-runtime/research/",
        "/api/research",
      ),
      () => buildIntegratedFrontend(
        "Trading",
        tradingWorkspace,
        "/mod-runtime/trading/",
        "/api/trading",
      ),
      () => buildFirstPartyModule(
        "Portfolio Center",
        "@newma-desk/portfolio-center",
        "modules/portfolio-center",
      ),
      () => buildFirstPartyModule(
        "Creator Studio",
        "@newma-desk/creator-studio",
        "modules/creator-studio",
      ),
      () => buildFirstPartyModule(
        "Workflow Center",
        "@newma-desk/workflow-center",
        "modules/workflow-center",
      ),
      () => buildFirstPartyModule(
        "Policy Analysis",
        "@newma-desk/policy-analysis",
        "modules/policy-analysis",
      ),
      () => buildFirstPartyModule(
        "Capital Flow",
        "@newma-desk/capital-flow",
        "modules/capital-flow",
      ),
      () => buildFirstPartyModule(
        "Industry Research",
        "@newma-desk/industry-research",
        "modules/industry-research",
      ),
    ], { concurrency: runtimeBuildConcurrency });
    await Promise.all(
      runtimePlan.preCoreServices.map((service) => supervisor.start(service)),
    );
    await supervisor.start(runtimePlan.coreServices[0]);
    // A fresh Desk starts with the core Global, Policy, Capital and Market projects.
    // Existing published Mods are left untouched,
    // so upgrades preserve each user's installed projects and ordering.
    await registerDefaultMods({
      apiUrl: "http://127.0.0.1:8911",
      env: {
        ...process.env,
        ...externalRuntimeEnv,
        NEWMA_DESK_INVESTMENT_WEB_URL: "http://127.0.0.1:8911",
        NEWMA_DESK_TRADING_WEB_URL: "http://127.0.0.1:8911",
        NEWMA_DESK_CONTROL_PLANE_URL: "http://127.0.0.1:8911",
      },
    });
    for (const service of runtimePlan.coreServices.slice(1)) {
      await supervisor.start(service);
    }
    console.log("\nNewma-Desk 核心已就绪：http://127.0.0.1:5888/?mod=global-situation");
    console.log(`Runtime Profile: ${runtimeProfile}`);
    console.log("Research / Trading 与已选情报运行时已由 Newma-Desk 统一加载。");
    const optionalResults = await supervisor.startOptional(
      runtimePlan.optionalServices,
    );
    const degradedCount = optionalResults
      .filter(({ state }) => state !== SERVICE_STATE.READY)
      .length;
    if (degradedCount > 0) {
      console.log(`可选 Mod 状态：${degradedCount} 个未完全就绪；Desk 核心继续运行。`);
    } else {
      console.log("可选 Mod 状态：全部就绪。");
    }
    console.log("按 Ctrl+C 可停止本次启动的服务。");
    await new Promise(() => {
      // Node 25 exits with code 13 for an unsettled top-level await when no
      // child process or other active handle exists. This interval keeps the
      // supervisor alive even when every service was reused.
      setInterval(() => {}, 60_000);
    });
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    // A launch agent may race with an already running stack. Treat the
    // duplicate as a clean no-op; otherwise KeepAlive repeatedly respawns the
    // loser and floods the runtime log every few seconds.
    await shutdown(error instanceof ProcessLockError ? 0 : 1);
  }
}
