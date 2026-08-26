const { spawnSync } = require('child_process');
const path = require('path');

const ROOT = path.join(__dirname, '../..');
const SCRIPT = path.join(ROOT, 'scripts/rewrite_execute_stage5.py');

/**
 * 执行 Rewrite Stage (Stage 5) - 改写执行
 *
 * @param {string} draftManifestFile - draft_manifest.json 文件路径
 * @param {Object} options - 可选参数
 * @param {string} options.runId - 运行ID (格式: YYYY-MM-DD_HHMMSS)
 * @param {string} options.outputDir - 输出目录
 * @param {string[]} options.versions - 版本列表 (默认: wechat_hot,wechat_normal,xiaohongshu_hot,xiaohongshu_normal)
 * @returns {Object} 执行结果
 */
function runRewrite(draftManifestFile, options = {}) {
  const args = [
    SCRIPT,
    '--draft-manifest', draftManifestFile,
    '--json-output'
  ];

  if (options.runId) {
    args.push('--run-id', options.runId);
  }

  if (options.outputDir) {
    args.push('--output-dir', options.outputDir);
  }

  if (options.versions && Array.isArray(options.versions)) {
    args.push('--versions', options.versions.join(','));
  }

  const result = spawnSync('python3', args, {
    cwd: ROOT,
    encoding: 'utf8',
    timeout: 600000, // 10分钟超时（改写需要更长时间）
    maxBuffer: 20 * 1024 * 1024, // 20MB buffer
  });

  if (result.error) {
    throw new Error(`Failed to spawn process: ${result.error.message}`);
  }

  if (result.status !== 0) {
    throw new Error(`Rewrite execution failed with exit code ${result.status}:\n${result.stderr}`);
  }

  try {
    const output = JSON.parse(result.stdout);
    return output;
  } catch (err) {
    throw new Error(`Failed to parse JSON output: ${err.message}\nStdout: ${result.stdout}`);
  }
}

module.exports = { runRewrite };
