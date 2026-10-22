import { existsSync } from "node:fs";
import path from "node:path";

function configured(env, suffix) {
  return ["NEWMA_DESK_", "NEWMA_DOCK_", "VIBEDESK_"]
    .map((prefix) => env[`${prefix}SEVEN_CYCLE_${suffix}`]?.trim())
    .find(Boolean);
}

export function sevenCycleLaunch({
  workspace, endpoint, env = process.env, exists = existsSync, repairCatalogOnStart = false,
}) {
  const executable = configured(env, "EXECUTABLE");
  const localCommand = path.join(workspace, ".venv", "bin", "seven-cycle");
  const explicitCommand = executable ? path.resolve(workspace, executable) : null;
  if (explicitCommand && !exists(explicitCommand)) {
    throw new Error(`Seven Cycle executable does not exist: ${explicitCommand}`);
  }
  const command = explicitCommand || (exists(localCommand) ? localCommand : "uv");
  const commandArgs = [
    ...(command === "uv" ? ["run", "seven-cycle"] : []),
    "serve", "--host", "127.0.0.1", "--port", String(endpoint.port),
  ];
  const product = configured(env, "PRODUCT_ROOT");
  const catalog = configured(env, "CATALOG_ROOT");
  const web = configured(env, "WEB_ROOT");
  if (product || catalog || web) {
    const productRoot = path.resolve(workspace, product || "products/circle");
    commandArgs.push(
      "--product-root", productRoot,
      "--catalog-root", catalog ? path.resolve(workspace, catalog) : path.join(productRoot, "catalogs"),
      "--web-root", path.resolve(workspace, web || "web/dist"),
    );
  }
  if (repairCatalogOnStart) commandArgs.push("--repair-catalog-on-start");
  return { command, commandArgs };
}

export function sevenCyclePreparation({ workspace, env = process.env, exists = existsSync }) {
  // The old bundled snapshot needs its seed catalog. Built/native projects
  // validate their own deployment in serve/healthz, without rewriting this one.
  if (["EXECUTABLE", "PRODUCT_ROOT", "CATALOG_ROOT", "WEB_ROOT"].some((key) => configured(env, key))
      || !exists(path.join(workspace, "scripts", "build_seed_catalog.py"))) return null;
  const python = path.join(workspace, ".venv", "bin", "python");
  const local = exists(python) && exists(path.join(workspace, ".venv", "bin", "seven-cycle"));
  return {
    command: local ? python : "uv",
    commandArgs: [...(local ? [] : ["run", "python"]), "scripts/build_seed_catalog.py"],
  };
}
