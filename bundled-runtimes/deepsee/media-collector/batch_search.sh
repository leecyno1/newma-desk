#!/bin/bash
# 批量关键词搜索 — 从配置文件读取关键词，逐词搜索各平台
# 用法: bash batch_search.sh [--pretty]

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG_FILE="$SCRIPT_DIR/keywords.json"
OUTPUT_BASE="${OUTPUT_BASE:-$PROJECT_ROOT/data/search}"
PRETTY=""

# 解析参数
for arg in "$@"; do
    case "$arg" in
        --config|-c) CONFIG_FILE="$2"; shift 2 ;;
        --pretty) PRETTY="--pretty" ;;
    esac
done

if [ ! -f "$CONFIG_FILE" ]; then
    echo "❌ 配置文件不存在: $CONFIG_FILE"
    exit 1
fi

echo "📋 读取关键词配置: $CONFIG_FILE"
KEYWORDS=$(python3 -c "import json; print('\n'.join(json.load(open('$CONFIG_FILE'))['keywords']))")
TOTAL=$(echo "$KEYWORDS" | wc -l | tr -d ' ')
echo "  共 $TOTAL 个关键词"
echo ""

KW_N=0
KW_OK=0
TOTAL_ITEMS=0

while IFS= read -r kw; do
    [ -z "$kw" ] && continue
    KW_N=$((KW_N + 1))
    echo "━━━ [$KW_N/$TOTAL] \"$kw\" ━━━"
    
    # 调用统一搜索
    if bash "$SCRIPT_DIR/search.sh" "$kw" $PRETTY > /dev/null 2>&1; then
        # 统计条数
        latest=$(find "$OUTPUT_BASE" -name "_summary.json" -newer "$CONFIG_FILE" 2>/dev/null | sort -r | head -1)
        if [ -n "$latest" ]; then
            cnt=$(python3 -c "import json; print(json.load(open('$latest')).get('total_items',0))" 2>/dev/null || echo 0)
            echo "  ✅ $cnt 条"
            TOTAL_ITEMS=$((TOTAL_ITEMS + cnt))
            KW_OK=$((KW_OK + 1))
        else
            echo "  ✅ 完成"
            KW_OK=$((KW_OK + 1))
        fi
    else
        echo "  ❌ 失败"
    fi
    echo ""
    
    # 避免请求过快
    sleep 1
done <<< "$KEYWORDS"

echo "═══════════════════════════════════"
echo "📊 批量搜索完成"
echo "  关键词: $KW_OK/$TOTAL 成功"
echo "  总条目: $TOTAL_ITEMS"
echo "  输出目录: $OUTPUT_BASE/"
