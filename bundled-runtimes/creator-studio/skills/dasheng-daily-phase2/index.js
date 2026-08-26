#!/usr/bin/env node

const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');

const WORKSPACE = process.env.DASHENG_ROOT || path.join(__dirname, '../..');
const OUTPUT_ROOT = process.env.DASHENG_OUTPUT_ROOT || path.join(os.homedir(), 'Desktop', '自媒体创作');
const PHASE2_SCRIPT = path.join(WORKSPACE, 'scripts', 'phase2_rebuilder.py');
const INTAKE_ROOT = path.join(OUTPUT_ROOT, '01_内容采集');
const BRIEF_ROOT = path.join(OUTPUT_ROOT, '02_内容聚合及选题分析');

function fileExists(file) {
  return !!file && fs.existsSync(file);
}

function resolveCanonicalIntake(runId) {
  if (!runId) return null;
  const manifestPath = path.join(INTAKE_ROOT, runId, 'intake_manifest.json');
  const intakeFile = path.join(INTAKE_ROOT, runId, 'raw', 'intake_records.json');
  if (!fileExists(manifestPath) || !fileExists(intakeFile)) return null;
  try {
    const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
    if (manifest.stage !== 'intake') return null;
    return { runId, intakeFile, manifestPath, manifest };
  } catch (_) {
    return null;
  }
}

function inferRunId(inputFile) {
  const normalized = path.resolve(inputFile);
  const segments = normalized.split(path.sep);
  const rawIndex = segments.lastIndexOf('raw');
  if (rawIndex >= 1) return segments[rawIndex - 1];
  return null;
}

function runPhase2(inputFile, runId, manualTopics = []) {
  const outputDir = path.join(BRIEF_ROOT, runId);
  fs.mkdirSync(outputDir, { recursive: true });

  const args = [PHASE2_SCRIPT, inputFile, outputDir, '--run-id', runId];
  for (const topic of manualTopics) {
    args.push('--manual-topic', topic);
  }

  const proc = spawnSync('python3', args, {
    cwd: WORKSPACE,
    encoding: 'utf8',
  });

  if (proc.status !== 0) {
    throw new Error(`phase2 执行失败\nSTDOUT:\n${proc.stdout}\nSTDERR:\n${proc.stderr}`);
  }

  return {
    output_dir: outputDir,
    brief_file: path.join(outputDir, '02_编辑Brief库.md'),
    report_file: path.join(outputDir, '02_编辑Brief_报告.md'),
    research_file: path.join(outputDir, '02_研究Brief库.md'),
    topic_cards_file: path.join(outputDir, 'topic_cards.json'),
    selected_topics_file: path.join(outputDir, 'selected_topics.json'),
    manifest_file: path.join(outputDir, 'brief_manifest.json'),
  };
}

function phase2(intakeFileArg, options = {}) {
  let intakeFile = intakeFileArg || options.intake_records_file || options.input_file;
  let runId = options.run_id || null;

  if (!intakeFile) {
    const canonical = resolveCanonicalIntake(runId);
    if (!canonical) {
      throw new Error('Stage 2 不再允许猜最新 intake；请显式传 intake_records.json 或 --run-id');
    }
    intakeFile = canonical.intakeFile;
    runId = canonical.runId;
  }

  if (!fileExists(intakeFile)) {
    throw new Error(`intake 文件不存在: ${intakeFile}`);
  }

  runId = runId || inferRunId(intakeFile);
  if (!runId) {
    throw new Error(`无法从 intake 文件推断 run_id: ${intakeFile}`);
  }

  const manualTopics = Array.isArray(options.manual_topics) ? options.manual_topics.filter(Boolean) : [];
  const result = runPhase2(intakeFile, runId, manualTopics);

  return {
    success: true,
    run_id: runId,
    intake_file: intakeFile,
    ...result,
    next_step: 'draft',
  };
}

if (require.main === module) {
  const argv = process.argv.slice(2);
  let intakeFile = null;
  let runId = null;
  const manualTopics = [];

  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (token === '--run-id') {
      const value = argv[index + 1];
      if (value) {
        runId = value;
        index += 1;
      }
      continue;
    }
    if (token === '--manual-topic') {
      const value = argv[index + 1];
      if (value) {
        manualTopics.push(value);
        index += 1;
      }
      continue;
    }
    if (!token.startsWith('--') && !intakeFile) {
      intakeFile = token;
    }
  }

  try {
    const result = phase2(intakeFile, { manual_topics: manualTopics, run_id: runId });
    console.log(JSON.stringify(result, null, 2));
    process.exit(0);
  } catch (error) {
    console.error(error.message);
    process.exit(1);
  }
}

module.exports = { phase2, resolveCanonicalIntake };
