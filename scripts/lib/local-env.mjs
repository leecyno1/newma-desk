import { existsSync } from "node:fs";
import path from "node:path";
import { loadEnvFile } from "node:process";

export function loadLocalEnvironment(repoRoot) {
  const envFile = path.join(repoRoot, ".env");
  // Node keeps existing process variables ahead of values in the local file.
  if (existsSync(envFile)) loadEnvFile(envFile);
}
