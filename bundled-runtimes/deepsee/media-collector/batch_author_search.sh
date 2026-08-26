#!/bin/bash
# 批量作者搜索 — 从 authors.json 读取优质财经博主，每 12 小时更新一次
# 用法: bash batch_author_search.sh [--pretty]

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PLATFORM_DIR="$SCRIPT_DIR/platforms"
CONFIG_FILE="$SCRIPT_DIR/authors.json"
PRETTY=""

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

DATE_DIR="$(date +%Y-%m-%d)"
OUTPUT_BASE="${OUTPUT_BASE:-$PROJECT_ROOT/data/authors}"
OUTPUT_DIR="$OUTPUT_BASE/$DATE_DIR"
mkdir -p "$OUTPUT_DIR"

AUTHORS=$(python3 -c "import json; print('\n'.join(json.load(open('$CONFIG_FILE'))['authors']))")
TOTAL=$(echo "$AUTHORS" | wc -l | tr -d ' ')

echo "👤 读取作者配置: $CONFIG_FILE"
echo "  共 $TOTAL 个作者"
echo "  输出目录: $OUTPUT_DIR"
echo ""

N=0
OK=0
TOTAL_ITEMS=0

while IFS= read -r author; do
    [ -z "$author" ] && continue
    N=$((N + 1))
    echo "━━━ [$N/$TOTAL] $author ━━━"
    HASH=$(echo -n "$author" | python3 -c "import sys,hashlib; print(hashlib.md5(sys.stdin.read().encode()).hexdigest()[:8])")
    SAFE=$(echo "$author" | sed 's/[\/ ]/_/g' | head -c 30)
    OUTFILE="$OUTPUT_DIR/${SAFE}_${HASH}.json"
    if python3 "$PLATFORM_DIR/bilibili_author_search.py" "$author" --limit 20 $PRETTY > "$OUTFILE" 2>/dev/null; then
        cnt=$(python3 -c "import json; print(json.load(open('$OUTFILE')).get('count',0))" 2>/dev/null || echo 0)
        echo "  ✅ $cnt 条"
        TOTAL_ITEMS=$((TOTAL_ITEMS + cnt))
        OK=$((OK + 1))
    else
        ts=$(python3 -c "from datetime import datetime,timezone,timedelta; print(datetime.now(timezone(timedelta(hours=8))).isoformat())" 2>/dev/null || echo "")
        printf '{"platform":"bilibili-author","author_query":"%s","fetched_at":"%s","count":0,"items":[],"error":"作者搜索失败"}\n' "$author" "$ts" > "$OUTFILE"
        echo "  ❌ 失败"
    fi
    echo ""
    sleep 1
done <<< "$AUTHORS"

NOW=$(python3 -c "from datetime import datetime,timezone,timedelta; print(datetime.now(timezone(timedelta(hours=8))).isoformat())" 2>/dev/null || echo "")
python3 - <<PY
import json, glob, os
outdir = "$OUTPUT_DIR"
files = {}
total = 0
success = 0
for f in sorted(glob.glob(outdir + "/*.json")):
    name = os.path.basename(f).replace('.json','')
    if name.startswith('_'): continue
    try:
        d = json.load(open(f))
        cnt = int(d.get('count') or 0)
        files[name] = 'fail: ' + str(d.get('error'))[:40] if d.get('error') else 'ok:' + str(cnt)
        if not d.get('error'):
            success += 1
            total += cnt
    except Exception as e:
        files[name] = 'parse_err:' + str(e)[:40]
summary = {
    'type': 'author_search',
    'fetched_at': "$NOW",
    'output_dir': outdir,
    'total_authors': len(files),
    'success': success,
    'total_items': total,
    'files': files,
}
json.dump(summary, open(os.path.join(outdir, '_summary.json'), 'w'), ensure_ascii=False, indent=2)
print(json.dumps(summary, ensure_ascii=False, indent=2))
PY

echo ""
echo "📊 作者搜索完成: $OK/$TOTAL 成功，$TOTAL_ITEMS 条"
