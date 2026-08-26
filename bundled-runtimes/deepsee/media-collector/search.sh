#!/bin/bash
# media-collector 统一搜索
# 用法: bash search.sh "关键词" [--pretty]
# 输出: data/search/YYYY-MM-DD/{keyword_hash}/ 下各平台结果

KEYWORD="${1:-}"
if [ -z "$KEYWORD" ]; then
    echo "用法: bash search.sh \"关键词\" [--pretty]"
    echo "示例: bash search.sh \"AI agent\" --pretty"
    exit 1
fi

PRETTY="${2:-}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLATFORM_DIR="$SCRIPT_DIR/platforms"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUTPUT_BASE="${OUTPUT_BASE:-$PROJECT_ROOT/data/search}"
DATE_DIR="$(date +%Y-%m-%d)"

# 用关键词hash避免特殊字符问题
KW_HASH=$(echo -n "$KEYWORD" | python3 -c "import sys,hashlib; print(hashlib.md5(sys.stdin.read().encode()).hexdigest()[:8])")
KW_DIR=$(echo "$KEYWORD" | sed 's/[\/ ]/_/g' | head -c 30)
OUTPUT_DIR="$OUTPUT_BASE/$DATE_DIR/${KW_DIR}_${KW_HASH}"

mkdir -p "$OUTPUT_DIR"
SUMMARY_FILE="$OUTPUT_DIR/_summary.json"
TMP_RESULTS=$(mktemp)
trap "rm -f $TMP_RESULTS" EXIT

run_search() {
    local platform="$1"; local script="$2"; local extra_args="${3:-}"
    local outfile="$OUTPUT_DIR/${platform}.json"
    echo "  [${platform}] \"$KEYWORD\" ..."
    if python3 "$PLATFORM_DIR/$script" "$KEYWORD" --limit 20 $extra_args $PRETTY > "$outfile" 2>/dev/null; then
        local count
        count=$(python3 -c "import json; print(json.load(open('$outfile')).get('count',0))" 2>/dev/null || echo 0)
        echo "  [${platform}] ✅ ${count} 条"
        echo "${platform}=ok:${count}" >> "$TMP_RESULTS"
    else
        local ts; ts=$(python3 -c "from datetime import datetime,timezone,timedelta; print(datetime.now(timezone(timedelta(hours=8))).isoformat())" 2>/dev/null || echo "")
        printf '{"platform":"%s","keyword":"%s","fetched_at":"%s","count":0,"items":[],"error":"搜索失败"}\n' "$platform" "$KEYWORD" "$ts" > "$outfile"
        echo "  [${platform}] ❌ 失败"
        echo "${platform}=fail" >> "$TMP_RESULTS"
    fi
}

echo "🔍 media-collector 搜索: \"$KEYWORD\""
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "  输出目录: $OUTPUT_DIR"
echo ""

# ═══════════════════════════════════════════
# 各平台并行搜索
# ═══════════════════════════════════════════
run_search "bilibili"   "bilibili_search.py" &
run_search "weibo"      "weibo_search.py" &
run_search "reddit"     "reddit_search.py" &
run_search "newsnow"    "newsnow_filter.py" "--sources weibo,zhihu,baidu,cls,wallstreetcn,36kr,douyin" &

# 可选: X 搜索（需认证）
if xurl auth status 2>/dev/null | grep -q "oauth2"; then
    run_search "x" "x_hot.py" &
else
    echo "  [x] ⏭️ 跳过（xurl 未认证）"
    echo "x=skip:no_auth" >> "$TMP_RESULTS"
fi

wait

# ═══════════════════════════════════════════
# 汇总
# ═══════════════════════════════════════════
NOW=$(python3 -c "from datetime import datetime,timezone,timedelta; print(datetime.now(timezone(timedelta(hours=8))).isoformat())" 2>/dev/null || echo "")

python3 -c "
import json, os, glob

outdir = '$OUTPUT_DIR'
files = {}
total_items = 0
success_count = 0

for f in sorted(glob.glob(f'{outdir}/*.json')):
    name = os.path.basename(f).replace('.json', '')
    if name.startswith('_'): continue
    try:
        with open(f) as fh:
            d = json.load(fh)
        cnt = d.get('count', 0)
        err = d.get('error')
        if err:
            files[name] = f'fail: {str(err)[:40]}'
        else:
            files[name] = f'ok:{cnt}'
            success_count += 1
            total_items += cnt
    except Exception as e:
        files[name] = f'parse_err: {e}'

summary = {
    'keyword': '$KEYWORD',
    'fetched_at': '$NOW',
    'output_dir': outdir,
    'total_platforms': len(files),
    'success': success_count,
    'total_items': total_items,
    'files': files,
}
with open(f'{outdir}/_summary.json', 'w') as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)
print(json.dumps(summary, ensure_ascii=False, indent=2))
"

echo ""
echo "完成: $OUTPUT_DIR/"
ls -lh "$OUTPUT_DIR/"
