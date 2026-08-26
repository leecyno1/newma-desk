#!/usr/bin/env node

const assert = require('assert');
const path = require('path');
const fs = require('fs');

// 自动检测项目根目录
function detectProjectRoot() {
  let current = __dirname;
  while (current !== '/') {
    if (fs.existsSync(path.join(current, 'CLAUDE.md'))) {
      return current;
    }
    current = path.dirname(current);
  }
  throw new Error('Cannot detect project root: CLAUDE.md not found');
}

const PROJECT_ROOT = detectProjectRoot();
const client = require(path.join(PROJECT_ROOT, 'skills/dasheng-daily-shared/runtime/feishu-client.js'));

function makeLargeMarkdown() {
  const section = [
    '# 主标题',
    '',
    '## 第一节',
    '',
    '| 指标 | 数值 |',
    '| --- | --- |',
    '| A | 1 |',
    '| B | 2 |',
    '',
    '这是一段用于测试的大段正文。'.repeat(400),
    '',
    '## 第二节',
    '',
    '继续补充内容。'.repeat(300)
  ].join('\n');
  return `${section}\n\n${section}`;
}

function main() {
  assert.strictEqual(typeof client.createWriteDocPlan, 'function', 'missing createWriteDocPlan');
  assert.strictEqual(typeof client.writeDocSection, 'function', 'missing writeDocSection');
  assert.strictEqual(typeof client.writeDocTable, 'function', 'missing writeDocTable');
  assert.strictEqual(typeof client.writeDocAssets, 'function', 'missing writeDocAssets');
  assert.strictEqual(typeof client.resumeDocWrite, 'function', 'missing resumeDocWrite');

  const plan = client.createWriteDocPlan(makeLargeMarkdown(), { forceMarkdown: true, maxChunkChars: 3200 });
  assert.strictEqual(plan.mode, 'markdown_document', 'plan mode should stay markdown');
  assert.ok(Array.isArray(plan.chunks), 'plan chunks must be array');
  assert.ok(plan.chunks.length > 2, 'large markdown should be chunked into multiple sections');
  assert.ok(plan.preparedMarkdown.includes('| 指标 | 数值 |'), 'markdown table should remain in markdown table format');
  assert.ok(plan.chunks.every(chunk => typeof chunk === 'string' && chunk.trim().length > 0), 'all chunks should be non-empty strings');

  const resumed = client.createWriteDocPlan(makeLargeMarkdown(), { forceMarkdown: true, maxChunkChars: 3200, startChunkIndex: 2 });
  assert.strictEqual(resumed.startChunkIndex, 2, 'plan should preserve requested resume offset');
  assert.strictEqual(resumed.remainingChunks.length, resumed.chunks.length - 2, 'remaining chunks should honor resume offset');

  console.log('test_feishu_write_pipeline: ok');
}

main();
