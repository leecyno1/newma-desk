import { rm } from "node:fs/promises";

import { databaseFiles } from "./runtime-config";

export default async function globalTeardown(): Promise<void> {
  for (const databaseFile of databaseFiles) {
    await rm(databaseFile, { force: true });
  }
}
