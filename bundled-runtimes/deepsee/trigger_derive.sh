#!/bin/bash
# 触发摘要派生的快速脚本

echo "=========================================="
echo "触发摘要派生"
echo "=========================================="
echo ""

# 检查服务状态
echo "1. 检查服务状态..."
if ! curl -s http://127.0.0.1:8001/api/health > /dev/null; then
    echo "❌ 服务未运行，请先启动服务："
    echo "   bash scripts/manage.sh dev"
    exit 1
fi
echo "✅ 服务正常运行"
echo ""

# 触发派生（最近1天的消息）
echo "2. 触发派生（最近1天的消息）..."
response=$(curl -s -X POST http://127.0.0.1:8001/api/messages/derive \
  -H "Content-Type: application/json" \
  -d '{"period": "1day", "force": false}')

echo "$response" | jq .
updated=$(echo "$response" | jq -r '.updated // 0')
echo ""
echo "✅ 已触发派生：$updated 条消息"
echo ""

# 说明
echo "=========================================="
echo "说明"
echo "=========================================="
echo ""
echo "派生分为两个阶段："
echo "1. fallback 摘要（立即生成，灰色）：基于本地规则"
echo "2. tool 摘要（异步生成，橘黄色）：调用小模型"
echo ""
echo "小模型处理需要一些时间，请等待 1-3 分钟后刷新前端。"
echo ""
echo "查看派生进度："
echo "  watch -n 3 'sqlite3 data/app.db \"SELECT COUNT(*) FROM messages WHERE json_extract(derived, \\\$\\\$.summary_origin) = \\\"tool\\\" AND timestamp > datetime(\\\"now\\\", \\\"-1 day\\\");\"'"
echo ""
echo "手动触发更多消息派生："
echo "  curl -X POST http://127.0.0.1:8001/api/messages/derive -H 'Content-Type: application/json' -d '{\"period\": \"3days\", \"force\": true}'"
echo ""

