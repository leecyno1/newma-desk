#!/usr/bin/env node

const message = [
  '[dasheng-daily-postmortem] 旧入口已停用。',
  '请改用 canonical `scripts/postmortem_writeback.py --publish-manifest <publish_manifest.json>`。',
  '正式主链 skill：dasheng-media-sop。',
].join(' ');

function failLegacyEntry() {
  throw new Error(message);
}

if (require.main === module) {
  console.error(message);
  process.exit(1);
}

module.exports = {
  generatePostmortem: failLegacyEntry,
};
