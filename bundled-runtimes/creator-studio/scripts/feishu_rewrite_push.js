#!/usr/bin/env node
const {
  createClient,
  createDoc,
  writeDoc,
  sendTextMessage
} = require('../skills/dasheng-daily-shared/runtime/feishu-client.js');
const fs = require('fs');
const os = require('os');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const runDate = process.argv[2] || new Date().toISOString().slice(0, 10);
const OUTPUT_ROOT = process.env.DASHENG_OUTPUT_ROOT || path.join(os.homedir(), 'Desktop', '自媒体创作');
const REWRITE_ROOT = path.join(OUTPUT_ROOT, '06_改写', `${runDate}_三篇独立改写`);
const TARGET_FOLDER = 'SpRqfe0VKlTUWzd313KczxKHngd';

const TOPICS = [
  {
    topic: 'topic10_半导体误判',
    prefix: 'topic10',
    title: '【改写稿】半导体突然很热闹，但行业最危险的误判可能才刚开始',
    message: `【改写稿】半导体突然很热闹，但行业最危险的误判可能才刚开始

4版改写已生成，请编辑审核：
• 公众号｜鲁迅｜热烈
• 公众号｜Lemon｜正常
• 小红书视频｜鲁迅｜热烈
• 小红书视频｜Lemon｜正常`,
  },
  {
    topic: 'topic11_openclaw安装',
    prefix: 'topic11',
    title: '【改写稿】一键安装OpenClaw：5分钟养上龙虾的正确姿势',
    message: `【改写稿】一键安装OpenClaw：5分钟养上龙虾的正确姿势

4版改写已生成，请编辑审核：
• 公众号｜鲁迅｜热烈
• 公众号｜Lemon｜正常
• 小红书视频｜鲁迅｜热烈
• 小红书视频｜Lemon｜正常`,
  },
  {
    topic: 'topic6_供给秩序重估',
    prefix: 'topic6',
    title: '【改写稿】表面在交易事件，真正的主线会不会其实是再通胀？',
    message: `【改写稿】表面在交易事件，真正的主线会不会其实是再通胀？

4版改写已生成，请编辑审核：
• 公众号｜鲁迅｜热烈
• 公众号｜Lemon｜正常
• 小红书视频｜鲁迅｜热烈
• 小红书视频｜Lemon｜正常`,
  },
];

async function pushTopic(client, config, topic) {
  const baseDir = path.join(REWRITE_ROOT, topic.topic);
  const bundleFile = path.join(baseDir, `${topic.prefix}__rewrite_bundle.md`);
  const metaFile = path.join(baseDir, 'meta.json');

  if (!fs.existsSync(bundleFile)) {
    console.log(`[WARN] 跳过 ${topic.topic}：未找到 ${bundleFile}`);
    return null;
  }

  const markdown = fs.readFileSync(bundleFile, 'utf-8');
  let meta = {};
  if (fs.existsSync(metaFile)) {
    try { meta = JSON.parse(fs.readFileSync(metaFile, 'utf-8')); } catch {}
  }

  console.log(`[${topic.topic}] 创建文档...`);
  const doc = await createDoc(client, topic.title, TARGET_FOLDER, config.host);
  console.log(`[${topic.topic}] 文档已创建: ${doc.url}`);

  console.log(`[${topic.topic}] 写入正文...`);
  await writeDoc(client, doc.doc_token, markdown, {});
  console.log(`[${topic.topic}] 正文写入完成`);

  let metaLines = '';
  if (Array.isArray(meta.variants)) {
    metaLines = meta.variants
      .map((item) => `  • ${String(item.variant || '').replace(`${topic.prefix}__`, '')}: ${item.char_count || 0}字`)
      .join('\n');
  } else {
    metaLines = Object.entries(meta || {})
      .filter(([, m]) => m && typeof m === 'object' && Object.prototype.hasOwnProperty.call(m, 'chars_no_newline'))
      .map(([fn, m]) => `  • ${fn.replace(`${topic.prefix}__`, '')}: ${m.chars_no_newline}字`)
      .join('\n');
  }
  if (!metaLines) {
    metaLines = '  • 字数统计文件存在，但未解析到结构化统计';
  }
  const fullMessage = `${topic.message}\n\n字数统计：\n${metaLines}\n\n文档链接：${doc.url}`;

  console.log(`[${topic.topic}] 发送群通知...`);
  const msg = await sendTextMessage(client, config.chatId, fullMessage);
  console.log(`[${topic.topic}] 群通知已发送`);

  return { topic: topic.topic, doc_url: doc.url, message_id: msg.message_id };
}

async function main() {
  const { client, config } = createClient();
  console.log('飞书配置:', { host: config.host, chatId: config.chatId });
  console.log('改写目录:', REWRITE_ROOT);

  const promises = TOPICS.map(t => pushTopic(client, config, t));
  const settled = await Promise.allSettled(promises);

  const results = [];
  for (let i = 0; i < settled.length; i++) {
    const r = settled[i];
    if (r.status === 'fulfilled' && r.value) {
      results.push(r.value);
      console.log(`✅ ${TOPICS[i].topic}: ${r.value.doc_url}`);
    } else if (r.status === 'rejected') {
      console.error(`❌ ${TOPICS[i].topic}: ${r.reason}`);
    }
  }

  console.log('\n=== 汇总 ===');
  results.forEach(r => console.log(`✅ ${r.topic}: ${r.doc_url}`));
}

main().catch(err => { console.error(err); process.exit(1); });
