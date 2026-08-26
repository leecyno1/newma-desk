#!/usr/bin/env node

const message = [
  '[legacy-entry] 旧入口已停用。',
  '请改用 dasheng-media-sop 正式主链。',
].join(' ');

if (require.main === module) {
  console.error(message);
  process.exit(1);
}

module.exports = {
  message,
};
