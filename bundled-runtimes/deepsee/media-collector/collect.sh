#!/bin/bash
# media-collector 统一调度器 v2
# 策略: 直接API（丰富数据） > NewsNow聚合（多源覆盖） > 跳过

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLATFORM_DIR="$SCRIPT_DIR/platforms"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUTPUT_BASE="${OUTPUT_BASE:-$PROJECT_ROOT/data/hot}"
DATE_DIR="$(date +%Y-%m-%d)"
OUTPUT_DIR="$OUTPUT_BASE/$DATE_DIR"

mkdir -p "$OUTPUT_DIR"

LIMIT="${LIMIT:-20}"
PRETTY="${1:-}"
if [ -z "${XHS_COOKIES:-}" ]; then XHS_COOKIES="$SCRIPT_DIR/cookies.json"; fi
SUMMARY_FILE="$OUTPUT_DIR/_summary.json"
TMP_RESULTS=$(mktemp)
trap "rm -f $TMP_RESULTS" EXIT

run_one() {
    local platform="$1"; local script="$2"; local extra_args="${3:-}"
    local outfile="$OUTPUT_DIR/${platform}.json"
    echo "  [${platform}] 采集..."
    if python3 "$PLATFORM_DIR/$script" --limit "$LIMIT" $extra_args $PRETTY > "$outfile" 2>/dev/null; then
        local count
        count=$(python3 -c "import json; print(json.load(open('$outfile')).get('count',0))" 2>/dev/null || echo 0)
        echo "  [${platform}] ✅ ${count} 条"
        echo "${platform}=ok:${count}" >> "$TMP_RESULTS"
        return 0
    else
        local ts; ts=$(python3 -c "from datetime import datetime,timezone,timedelta; print(datetime.now(timezone(timedelta(hours=8))).isoformat())" 2>/dev/null || echo "")
        printf '{"platform":"%s","fetched_at":"%s","count":0,"items":[],"error":"采集失败"}\n' "$platform" "$ts" > "$outfile"
        echo "  [${platform}] ❌ 失败"
        echo "${platform}=fail" >> "$TMP_RESULTS"
        return 1
    fi
}

echo "⚡ media-collector v2 $(date '+%Y-%m-%d %H:%M:%S')"
echo "  输出目录: $OUTPUT_DIR"
echo ""

# ═══════════════════════════════════════════
# Tier 1: 直接API采集（数据最丰富）— 并行
# ═══════════════════════════════════════════
run_one "bilibili"  "bilibili_hot.py" &
run_one "weibo"     "weibo_hot.py" &      # 直接API有热度值
run_one "douyin"    "douyin_hot.py" &     # 直接API有标签等
run_one "reddit"    "reddit_hot.py" "--subreddit all" &
run_one "gtrends"   "gtrends_hot.py" "--region us" &

# ═══════════════════════════════════════════
# Tier 2: NewsNow聚合（新增金融/科技/综合源）
# ═══════════════════════════════════════════
# NewsNow 输出多源JSON数组，需要拆分为单文件
echo "  [newsnow] 多源聚合采集..."
python3 "$PLATFORM_DIR/newsnow_hot.py" --limit "$LIMIT" $PRETTY > "$OUTPUT_DIR/.newsnow_raw.json" 2>/dev/null && \
python3 -c "
import json, sys
with open('$OUTPUT_DIR/.newsnow_raw.json') as f:
    results = json.load(f)

ok_count = 0
for r in results:
    if 'error' in r:
        continue
    # 跳过已有直接采集的源（weibo, douyin）
    sid = r.get('platform','').replace('newsnow/','')
    if sid in ('weibo', 'douyin'):
        continue
    outfile = f'$OUTPUT_DIR/newsnow_{sid}.json'
    with open(outfile, 'w') as f:
        json.dump(r, f, ensure_ascii=False$([ -n "$PRETTY" ] && echo ', indent=2'))
    cnt = r.get('count', 0)
    ok_count += 1
    print(f'  [newsnow/{sid}] ✅ {cnt} 条')

# 汇总
with open('$OUTPUT_DIR/.newsnow_summary.json', 'w') as f:
    summary = {
        'total_sources': len(results),
        'success': ok_count,
        'sources': [r.get('platform','') for r in results if 'error' not in r],
    }
    json.dump(summary, f, ensure_ascii=False$([ -n "$PRETTY" ] && echo ', indent=2'))
" || echo "  [newsnow] ❌ 聚合失败"

rm -f "$OUTPUT_DIR/.newsnow_raw.json"

# ═══════════════════════════════════════════
# Tier 3: 需认证平台
# ═══════════════════════════════════════════
if xurl auth status 2>/dev/null | grep -q "oauth2"; then
    run_one "x" "x_hot.py" &
else
    echo "  [x] ⏭️ 跳过（xurl 未认证）"
    echo "x=skip:no_auth" >> "$TMP_RESULTS"
fi

if [ -f "$XHS_COOKIES" ]; then
    run_one "xhs" "xhs_hot.py" "--cookies $XHS_COOKIES" &
else
    echo "  [xhs] ⏭️ 跳过（无 Cookie）"
    echo "xhs=skip:no_cookies" >> "$TMP_RESULTS"
fi

wait

# ═══════════════════════════════════════════
# 汇总
# ═══════════════════════════════════════════
NOW=$(python3 -c "from datetime import datetime,timezone,timedelta; print(datetime.now(timezone(timedelta(hours=8))).isoformat())" 2>/dev/null || echo "")

# 统计所有输出文件
python3 -c "
import json, os, glob

outdir = '$OUTPUT_DIR'
files = {}
total_items = 0
success_count = 0

for f in sorted(glob.glob(f'{outdir}/*.json')):
    name = os.path.basename(f).replace('.json', '')
    if name.startswith('_') or name.startswith('.'): continue
    try:
        with open(f) as fh:
            d = json.load(fh)
        cnt = d.get('count', 0)
        err = d.get('error')
        if err:
            files[name] = f'fail: {err[:40]}'
        else:
            files[name] = f'ok:{cnt}'
            success_count += 1
            total_items += cnt
    except Exception as e:
        files[name] = f'parse_err: {e}'

summary = {
    'fetched_at': '$NOW',
    'date_dir': '$DATE_DIR',
    'total_files': len(files),
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
ls -lh "$OUTPUT_DIR/" | head -20
