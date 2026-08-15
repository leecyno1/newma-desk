#!/usr/bin/env node

import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const repoRoot = fileURLToPath(new URL("../", import.meta.url));
const shellRoot = path.join(repoRoot, "apps", "shell");
const allowedBusinessPackages = new Set([
  "@newma-desk/global-intelligence",
  "@newma-desk/market-daily",
]);
const foundationPackages = new Set([
  "@newma-desk/contracts",
  "@newma-desk/desk-ui",
  "@newma-desk/mod-sdk",
  "@newma-desk/view-renderer",
  "@newma-desk/chart-kit",
]);

function packageRoot(specifier) {
  if (!specifier.startsWith("@")) return specifier.split("/", 1)[0];
  return specifier.split("/", 2).join("/");
}

async function workspaceBusinessPackages() {
  const modulesRoot = path.join(repoRoot, "modules");
  const entries = await readdir(modulesRoot, { withFileTypes: true });
  const names = [];
  for (const entry of entries) {
    if (!entry.isDirectory()) continue;
    try {
      const packageJson = JSON.parse(
        await readFile(path.join(modulesRoot, entry.name, "package.json"), "utf8"),
      );
      if (typeof packageJson.name === "string") names.push(packageJson.name);
    } catch (error) {
      if (error?.code !== "ENOENT") throw error;
    }
  }
  return new Set(names);
}

async function sourceFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const target = path.join(directory, entry.name);
    if (entry.isDirectory()) files.push(...await sourceFiles(target));
    else if (/\.[cm]?[jt]sx?$/.test(entry.name)) files.push(target);
  }
  return files;
}

export async function checkShellModDependencies() {
  const errors = [];
  const businessPackages = await workspaceBusinessPackages();
  const packageJson = JSON.parse(
    await readFile(path.join(shellRoot, "package.json"), "utf8"),
  );
  const declared = {
    ...packageJson.dependencies,
    ...packageJson.devDependencies,
  };

  for (const dependency of Object.keys(declared)) {
    if (
      businessPackages.has(dependency)
      && !allowedBusinessPackages.has(dependency)
    ) {
      errors.push(
        `apps/shell/package.json directly depends on business Mod ${dependency}`,
      );
    }
  }

  const importPattern = /(?:\bfrom\s*|\bimport\s*(?:\(\s*)?)(["'])([^"']+)\1/g;
  for (const file of await sourceFiles(path.join(shellRoot, "src"))) {
    const source = await readFile(file, "utf8");
    for (const match of source.matchAll(importPattern)) {
      const specifier = match[2];
      const root = packageRoot(specifier);
      if (
        businessPackages.has(root)
        && !allowedBusinessPackages.has(root)
      ) {
        errors.push(
          `${path.relative(repoRoot, file)} directly imports business Mod ${specifier}`,
        );
      }
      if (
        specifier.startsWith("@newma-desk/")
        && !foundationPackages.has(root)
        && !allowedBusinessPackages.has(root)
        && !businessPackages.has(root)
      ) {
        errors.push(
          `${path.relative(repoRoot, file)} imports unclassified workspace package ${specifier}`,
        );
      }
      const normalized = specifier.replaceAll("\\", "/");
      if (
        /(?:^|\/)modules\//.test(normalized)
        && !["market-daily", "global-intelligence"].some((id) =>
          normalized.includes(`/modules/${id}/`),
        )
      ) {
        errors.push(
          `${path.relative(repoRoot, file)} directly imports business source ${specifier}`,
        );
      }
    }
  }

  return errors;
}

async function main() {
  const errors = await checkShellModDependencies();
  if (errors.length === 0) {
    process.stdout.write("PASS Shell business Mod dependency guard\n");
    return;
  }
  for (const error of errors) process.stderr.write(`ERROR ${error}\n`);
  process.stderr.write(
    "New business Mods must enter through Manifest + Bridge; update the allowlist only for an intentional first-party embedded exception.\n",
  );
  process.exitCode = 1;
}

if (
  process.argv[1]
  && import.meta.url === pathToFileURL(process.argv[1]).href
) {
  await main();
}
