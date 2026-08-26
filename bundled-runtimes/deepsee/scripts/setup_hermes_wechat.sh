#!/bin/bash
# wechatapi 机器 Hermes 微信适配器安装脚本
# 拷贝到 wechatapi 机器，chmod +x，运行

set -e

echo "=== 1. 安装 Hermes ==="
curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash

HERMES_HOME="$HOME/.hermes"

echo ""
echo "=== 2. 配置 .env ==="
cat >> "$HERMES_HOME/.env" << 'EOF'

# ── 微信 iLink Bot ──
WEIXIN_DM_POLICY=open
WEIXIN_GROUP_POLICY=disabled
EOF

echo ""
echo "=== 3. 配置 config.yaml ==="
cat >> "$HERMES_HOME/config.yaml" << 'EOF'

platforms:
  weixin:
    enabled: true
EOF

echo ""
echo "=== 4. 扫码登录 ==="
echo "下一步运行 hermes gateway setup → 选微信 → 终端扫码"
echo ""
echo "完成后运行: hermes gateway start"
echo ""
echo "群聊保持不变（wechatapi.net → 0913 → Hermes）"
echo "私聊走 iLink Bot（Hermes Gateway 微信适配器 → Hermes API Server）"
