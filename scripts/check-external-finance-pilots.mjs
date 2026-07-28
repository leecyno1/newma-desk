#!/usr/bin/env node

import { pathToFileURL } from "node:url";

import {
  checkConfiguredExternalFinancePilots,
  externalFinancePilotDescriptorPath,
} from "./lib/external-finance-pilots.mjs";

export async function runExternalFinancePilotCheck() {
  const result = await checkConfiguredExternalFinancePilots();
  process.stdout.write(`External finance pilot descriptor: ${externalFinancePilotDescriptorPath}\n`);
  for (const pilot of result.pilots) {
    process.stdout.write(
      `${pilot.errors.length === 0 ? "PASS" : "FAIL"} ${pilot.id} mode=${pilot.mode} decision=${pilot.decision} audit=${pilot.auditStatus}\n`,
    );
  }
  for (const warning of result.warnings) process.stdout.write(`WARN ${warning}\n`);
  for (const error of result.errors) process.stderr.write(`ERROR ${error}\n`);
  if (!result.ok) process.exitCode = 1;
  return result;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await runExternalFinancePilotCheck();
}
