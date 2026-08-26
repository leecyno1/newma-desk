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
const live = require(path.join(PROJECT_ROOT, 'skills/dasheng-daily-shared/runtime/feishu-live.js'));

function main() {
  assert.strictEqual(typeof live.buildExecutionState, 'function', 'missing buildExecutionState');

  const contractActions = [
    { key: 'folder:date', action_type: 'folder', title: 'date' },
    { key: 'doc:a', action_type: 'doc', title: 'doc a' },
    { key: 'message:a', action_type: 'message', title: 'msg a' }
  ];

  const progress = {
    actions: [
      { key: 'folder:date', status: 'completed', result: { token: 'folder-token', url: 'https://folder' } },
      { key: 'doc:a', status: 'failed', result: {}, note: 'timeout' }
    ],
    resources: {
      'folder:date': { token: 'folder-token', url: 'https://folder' }
    }
  };

  const state = live.buildExecutionState(contractActions, progress);
  assert.deepStrictEqual(state.remainingActions.map(item => item.key), ['doc:a', 'message:a'], 'should resume from first unfinished action');
  assert.deepStrictEqual(state.actions.map(item => item.key), ['folder:date'], 'completed actions should be preserved');
  assert.strictEqual(state.resources['folder:date'].token, 'folder-token', 'completed resources should be restored');

  const completedState = live.buildExecutionState(contractActions, {
    actions: contractActions.map(item => ({ key: item.key, status: 'completed', result: { ok: item.key } })),
    resources: {
      'folder:date': { ok: 'folder:date' },
      'doc:a': { ok: 'doc:a' },
      'message:a': { ok: 'message:a' }
    }
  });
  assert.strictEqual(completedState.remainingActions.length, 0, 'all completed actions should not rerun by default');
  assert.strictEqual(completedState.actions.length, 3, 'completed actions should remain in final state');

  console.log('test_feishu_live_resume: ok');
}

main();
