#!/usr/bin/env node

import { checkFinanceProjectIntake } from "./lib/finance-project-intake.mjs";

const report = await checkFinanceProjectIntake(process.argv[2]);
process.stdout.write(`Finance project intake: ${report.projectCount} repositories\n`);
for (const warning of report.warnings) process.stdout.write(`WARN ${warning}\n`);
for (const error of report.errors) process.stdout.write(`ERROR ${error}\n`);
process.stdout.write(report.ok ? "PASS finance project intake policy\n" : "FAIL finance project intake policy\n");
if (!report.ok) process.exitCode = 1;
