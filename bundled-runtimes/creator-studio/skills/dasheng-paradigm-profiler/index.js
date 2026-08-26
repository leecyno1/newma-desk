#!/usr/bin/env node
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const ROOT = process.env.DASHENG_ROOT || path.join(__dirname, '../..');
const SCRIPT = path.join(ROOT, 'scripts', 'build_paradigm_profile.py');

function assertSamples(samples) {
  if (!Array.isArray(samples) || samples.length === 0) {
    throw new Error('请至少提供一个 .md/.txt 样本文件');
  }
  for (const sample of samples) {
    if (!fs.existsSync(sample)) {
      throw new Error(`样本文件不存在: ${sample}`);
    }
  }
}

function pushRepeated(args, flag, values) {
  if (!values) return;
  const list = Array.isArray(values) ? values : [values];
  for (const value of list.filter(Boolean)) {
    args.push(flag, String(value));
  }
}

function buildParadigmProfile(samples, options = {}) {
  assertSamples(samples);
  if (!options.runId && !options.run_id) {
    throw new Error('必须提供 runId / run_id');
  }

  const runId = options.runId || options.run_id;
  const args = [SCRIPT, ...samples, '--run-id', runId];

  if (options.profileName || options.profile_name) args.push('--profile-name', options.profileName || options.profile_name);
  if (options.sampleType || options.sample_type) args.push('--sample-type', options.sampleType || options.sample_type);
  if (options.bindStyleDna || options.bind_style_dna) args.push('--bind-style-dna', options.bindStyleDna || options.bind_style_dna);
  if (options.outputDir || options.output_dir) args.push('--output-dir', options.outputDir || options.output_dir);
  if (options.noAi || options.no_ai) args.push('--no-ai');
  pushRepeated(args, '--scenario', options.scenarios || options.scenario);
  pushRepeated(args, '--channel', options.channels || options.channel);

  const proc = spawnSync('python3', args, {
    cwd: ROOT,
    encoding: 'utf8',
  });

  if (proc.status !== 0) {
    throw new Error(`范式学习执行失败\nSTDOUT:\n${proc.stdout}\nSTDERR:\n${proc.stderr}`);
  }

  return JSON.parse(proc.stdout);
}

if (require.main === module) {
  const argv = process.argv.slice(2);
  const samples = [];
  const options = { scenarios: [], channels: [] };

  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    const next = argv[index + 1];
    if (token === '--run-id') {
      options.runId = next;
      index += 1;
    } else if (token === '--profile-name') {
      options.profileName = next;
      index += 1;
    } else if (token === '--sample-type') {
      options.sampleType = next;
      index += 1;
    } else if (token === '--scenario') {
      options.scenarios.push(next);
      index += 1;
    } else if (token === '--channel') {
      options.channels.push(next);
      index += 1;
    } else if (token === '--bind-style-dna') {
      options.bindStyleDna = next;
      index += 1;
    } else if (token === '--output-dir') {
      options.outputDir = next;
      index += 1;
    } else if (token === '--no-ai') {
      options.noAi = true;
    } else if (!token.startsWith('--')) {
      samples.push(token);
    }
  }

  try {
    const result = buildParadigmProfile(samples, options);
    console.log(JSON.stringify(result, null, 2));
    process.exit(0);
  } catch (error) {
    console.error(error.message);
    process.exit(1);
  }
}

module.exports = { buildParadigmProfile };
