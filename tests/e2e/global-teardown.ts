import { rm } from "node:fs/promises";

import { databaseFiles, runtimeDir } from "./runtime-config";

export default async function globalTeardown(): Promise<void> {
  for (const databaseFile of databaseFiles) {
    await rm(databaseFile, { force: true });
  }
  await rm(runtimeDir, { force: true, recursive: true });
}
