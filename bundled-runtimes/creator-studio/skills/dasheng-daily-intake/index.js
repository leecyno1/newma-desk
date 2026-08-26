#!/usr/bin/env node

const path = require('path');
const { spawnSync } = require('child_process');

const WORKSPACE = process.env.DASHENG_ROOT || path.join(__dirname, '../..');
const SCRIPT = path.join(WORKSPACE, 'scripts', 'run_stage1_intake.py');

function runIntake() {
  const proc = spawnSync('python3', [SCRIPT], {
    cwd: WORKSPACE,
    encoding: 'utf8',
  });

  if (proc.status !== 0) {
    throw new Error(`intake 执行失败\nSTDOUT:\n${proc.stdout}\nSTDERR:\n${proc.stderr}`);
  }

  const stdout = (proc.stdout || '').trim();
  const lines = stdout.split('\n').filter(Boolean);
  const lastJson = lines.length ? lines.slice(lines.findIndex(line => line.trim().startsWith('{'))).join('\n') : '{}';
  const payload = JSON.parse(lastJson);

  return {
    success: true,
    run_id: payload.run_id,
    out_dir: payload.out_dir,
    counts: payload.counts,
    top_event_cluster: payload.top_event_cluster,
    manifest_file: path.join(payload.out_dir, 'intake_manifest.json'),
    next_step: 'dasheng-daily-phase2',
  };
}

if (require.main === module) {
  try {
    const result = runIntake();
    console.log(JSON.stringify(result, null, 2));
    process.exit(0);
  } catch (error) {
    console.error(error.message);
    process.exit(1);
  }
}

module.exports = { runIntake };
