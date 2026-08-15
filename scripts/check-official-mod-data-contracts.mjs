#!/usr/bin/env node

import { pathToFileURL } from "node:url";

import {
  checkReleaseModDataContracts,
  loadReleaseDataServices,
  selectReleaseCertificationMods,
} from "./lib/official-release.mjs";
import { loadModStore } from "./lib/mod-store.mjs";

export async function checkOfficialModDataContracts() {
  const store = await loadModStore();
  const mods = selectReleaseCertificationMods(store);
  const services = await loadReleaseDataServices();
  return {
    mods,
    services,
    errors: checkReleaseModDataContracts(mods, services),
  };
}

async function main() {
  const { mods, services, errors } = await checkOfficialModDataContracts();
  if (mods.length === 0) throw new Error("No default Manifest 1.1 Mods selected");
  if (services.size === 0) throw new Error("No data service descriptors registered");
  if (errors.length === 0) {
    process.stdout.write(
      `PASS ${mods.length} official Mods use registered data capabilities\n`,
    );
    return;
  }
  for (const error of errors) process.stderr.write(`ERROR ${error}\n`);
  process.exitCode = 1;
}

if (
  process.argv[1]
  && import.meta.url === pathToFileURL(process.argv[1]).href
) {
  await main();
}
