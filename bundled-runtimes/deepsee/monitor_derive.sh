#!/bin/bash
# 实时监控摘要派生进度

echo "=========================================="
echo "摘要派生进度监控"
echo "=========================================="
echo ""

# 统计最近1天的消息派生情况
echo "最近 1 天的消息派生情况："
echo ""

total=$(sqlite3 data/app.db "SELECT COUNT(*) FROM messages WHERE timestamp > datetime('now', '-1 day');")
tool_count=$(sqlite3 data/app.db "SELECT COUNT(*) FROM messages WHERE json_extract(derived, '\$.summary_origin') = 'tool' AND timestamp > datetime('now', '-1 day');")
fallback_count=$(sqlite3 data/app.db "SELECT COUNT(*) FROM messages WHERE json_extract(derived, '\$.summary_origin') = 'fallback' AND timestamp > datetime('now', '-1 day');")
null_count=$(sqlite3 data/app.db "SELECT COUNT(*) FROM messages WHERE derived IS NULL AND timestamp > datetime('now', '-1 day');")

echo "  总消息数：    $total"
echo "  ✅ 小模型派生： $tool_count (橘黄色)"
echo "  ⚪ 本地兜底：   $fallback_count (灰色)"
echo "  ⏳ 未派生：     $null_count"
echo ""

if [ "$tool_count" -eq 0 ] && [ "$fallback_count" -gt 0 ]; then
    echo "📌 状态：小模型正在处理中..."
    echo ""
    echo "预计完成时间：约 $(echo "scale=0; $fallback_count / 8 / 60" | bc) - $(echo "scale=0; $fallback_count * 2 / 8 / 60 + 1" | bc) 分钟"
    echo ""
    echo "💡 提示：小模型处理需要一些时间，请耐心等待。"
    echo "   可以使用以下命令持续监控："
    echo "   watch -n 5 bash monitor_derive.sh"
elif [ "$tool_count" -gt 0 ]; then
    progress=$(echo "scale=1; $tool_count * 100 / ($tool_count + $fallback_count)" | bc)
    echo "📊 进度：$progress% ($tool_count / $(($tool_count + $fallback_count)))"
    echo ""
    if [ "$fallback_count" -gt 0 ]; then
        echo "📌 状态：小模型正在处理中..."
        echo "   预计剩余时间：约 $(echo "scale=0; $fallback_count / 8 / 60" | bc) - $(echo "scale=0; $fallback_count * 2 / 8 / 60 + 1" | bc) 分钟"
    else
        echo "🎉 状态：所有消息已处理完成！"
        echo ""
        echo "现在刷新前端，应该能看到橘黄色的摘要了。"
    fi
fi

echo ""
echo "=========================================="
echo "最近派生的消息（橘黄色）"
echo "=========================================="
echo ""

sqlite3 data/app.db "SELECT 
    substr(content_text, 1, 40) as content,
    json_extract(derived, '\$.summary') as summary,
    datetime(timestamp) as time
FROM messages 
WHERE json_extract(derived, '\$.summary_origin') = 'tool' 
  AND timestamp > datetime('now', '-1 day')
ORDER BY timestamp DESC 
LIMIT 5;" | column -t -s '|'

echo ""
echo "=========================================="
echo "命令选项"
echo "=========================================="
echo ""
echo "持续监控（每5秒刷新）："
echo "  watch -n 5 bash monitor_derive.sh"
echo ""
echo "手动触发更多派生："
echo "  curl -X POST http://127.0.0.1:8001/api/messages/derive -H 'Content-Type: application/json' -d '{\"period\": \"3days\", \"force\": true}'"
echo ""

