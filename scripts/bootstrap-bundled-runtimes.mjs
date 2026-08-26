#!/usr/bin/env node

import { spawn, spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = fileURLToPath(new URL("../", import.meta.url));
const bundledRoot = path.join(repoRoot, "bundled-runtimes");
const coreOnly = process.argv.includes("--core");

function run(label, command, commandArgs, cwd = repoRoot) {
  console.log(`\n${label}`);
  const child = spawn(command, commandArgs, {
    cwd,
    env: process.env,
    stdio: "inherit",
  });
  return new Promise((resolve, reject) => {
    child.once("error", reject);
    child.once("exit", (code, signal) => {
      if (code === 0) resolve();
      else reject(new Error(`${label}失败：code=${code ?? "-"} signal=${signal ?? "-"}`));
    });
  });
}

function commandWorks(command, commandArgs = ["--version"]) {
  return spawnSync(command, commandArgs, { stdio: "ignore" }).status === 0;
}

function selectPython() {
  const candidates = [
    process.env.NEWMA_DESK_PYTHON_BIN,
    "python3.12",
    "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12",
    "/opt/homebrew/bin/python3.12",
  ].filter(Boolean);
  const selected = candidates.find((candidate) => commandWorks(candidate));
  if (!selected) {
    throw new Error("未找到 Python 3.12；请安装后重试，或设置 NEWMA_DESK_PYTHON_BIN。");
  }
  return selected;
}

async function installPythonRuntime(python, label, workspace, installArgs) {
  const venvPython = path.join(workspace, ".venv", "bin", "python");
  if (!existsSync(venvPython)) {
    await run(`创建 ${label} Python 环境`, python, ["-m", "venv", ".venv"], workspace);
  }
  await run(
    `安装 ${label} Python 依赖`,
    venvPython,
    ["-m", "pip", "install", "--disable-pip-version-check", ...installArgs],
    workspace,
  );
}

async function installOpenChatCut() {
  const workspace = path.join(bundledRoot, "openchatcut");
  const node = process.env.NEWMA_DESK_OPENCHATCUT_NODE_BIN
    || "/opt/homebrew/opt/node@24/bin/node";
  const npmCli = process.env.NEWMA_DESK_OPENCHATCUT_NPM_CLI
    || "/opt/homebrew/opt/node@24/lib/node_modules/npm/bin/npm-cli.js";
  if (existsSync(node) && existsSync(npmCli)) {
    await run("安装 OpenChatCut 依赖（Node 24）", node, [npmCli, "ci"], workspace);
    return;
  }
  console.warn("未发现独立 Node 24，使用当前 npm 安装 OpenChatCut；运行时仍要求 Node 24。");
  await run("安装 OpenChatCut 依赖", "npm", ["ci"], workspace);
}

async function installRssHub() {
  const workspace = path.join(bundledRoot, "rsshub-policy");
  if (commandWorks("pnpm")) {
    await run("安装 Policy RSSHub 依赖", "pnpm", ["install", "--frozen-lockfile"], workspace);
    await run("生成 Policy RSSHub 路由索引", "pnpm", ["run", "build:routes"], workspace);
    return;
  }
  const pnpmArgs = ["--yes", "pnpm@10.15.1"];
  await run("安装 Policy RSSHub 依赖", "npx", [...pnpmArgs, "install", "--frozen-lockfile"], workspace);
  await run("生成 Policy RSSHub 路由索引", "npx", [...pnpmArgs, "run", "build:routes"], workspace);
}

async function main() {
  const python = selectPython();

  await run("安装 Newma-Desk Node 依赖", "npm", ["ci"]);
  await installPythonRuntime(
    python,
    "Newma-Desk API",
    path.join(repoRoot, "services", "api"),
    ["-e", ".[test]"],
  );

  await run(
    "安装 Research 前端依赖",
    "npm",
    ["ci"],
    path.join(bundledRoot, "vibe-research", "frontend"),
  );
  await installPythonRuntime(
    python,
    "Research",
    path.join(bundledRoot, "vibe-research", "backend"),
    ["-r", "requirements.txt"],
  );

  await run(
    "安装 Trading 前端依赖",
    "npm",
    ["ci"],
    path.join(bundledRoot, "vibe-trading", "frontend"),
  );
  await installPythonRuntime(
    python,
    "Trading",
    path.join(bundledRoot, "vibe-trading"),
    ["-e", "."],
  );

  await installPythonRuntime(
    python,
    "World Intelligence",
    path.join(bundledRoot, "world-intel-mcp"),
    ["-e", ".[dashboard]"],
  );
  await installRssHub();

  if (coreOnly) {
    console.log("\n核心运行时依赖已完成。运行 npm run dev:stack 启动 Desk。");
    return;
  }

  await installOpenChatCut();
  await installPythonRuntime(
    python,
    "Deepsee",
    path.join(bundledRoot, "deepsee"),
    ["-r", "requirements.txt"],
  );
  const sevenCycleWorkspace = path.join(bundledRoot, "seven-cycle");
  await installPythonRuntime(
    python,
    "Seven Cycle",
    sevenCycleWorkspace,
    ["-e", "."],
  );
  await run(
    "安装 Seven Cycle 前端依赖",
    "npm",
    ["ci"],
    path.join(bundledRoot, "seven-cycle", "web"),
  );
  await run(
    "构建 Seven Cycle 前端",
    "npm",
    ["run", "build"],
    path.join(sevenCycleWorkspace, "web"),
  );
  await run(
    "构建 Seven Cycle 本地数据目录",
    path.join(sevenCycleWorkspace, ".venv", "bin", "python"),
    ["scripts/build_seed_catalog.py"],
    sevenCycleWorkspace,
  );
  await installPythonRuntime(
    python,
    "InStock",
    path.join(bundledRoot, "instock-analysis"),
    [
      "-r", "requirements-attached.txt",
      "-c", "requirements-attached.constraints.txt",
    ],
  );
  await run(
    "安装 Fund Analysis 前端依赖",
    "npm",
    ["ci"],
    path.join(bundledRoot, "fund-analysis"),
  );
  await run(
    "生成 Fund Analysis Prisma 客户端",
    "npm",
    ["exec", "prisma", "generate"],
    path.join(bundledRoot, "fund-analysis"),
  );
  await installPythonRuntime(
    python,
    "Fund Analysis",
    path.join(bundledRoot, "fund-analysis"),
    ["-r", "backend/requirements.txt"],
  );
  await run(
    "安装 Orchestra 前端依赖",
    "npm",
    ["ci"],
    path.join(bundledRoot, "orchestra-prisma"),
  );
  await installPythonRuntime(
    python,
    "Orchestra",
    path.join(bundledRoot, "orchestra-agentscope"),
    ["-e", ".[orchestra]"],
  );
  await installPythonRuntime(
    python,
    "Creator Studio 源工程",
    path.join(bundledRoot, "creator-studio"),
    ["-r", "requirements.txt"],
  );

  console.log("\n全部 Desk 运行时依赖已完成。运行 npm run dev:stack 启动。");
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
});
