#!/bin/bash

# 中国十五五规划视频渲染脚本
# 用途：将 Remotion 组件渲染为高质量视频

set -e

# 自动检测项目根目录
_CURRENT_SCRIPT="${BASH_SOURCE[0]}"
if [ -L "$_CURRENT_SCRIPT" ]; then
  _CURRENT_SCRIPT=$(readlink -f "$_CURRENT_SCRIPT")
fi
_ROOT=$(cd "$(dirname "$_CURRENT_SCRIPT")/.." && pwd)

# 支持环境变量覆盖
ROOT="${DASHENG_ROOT:-$_ROOT}"
export DASHENG_ROOT="$ROOT"

echo "🎬 开始渲染中国十五五规划视频..."
echo ""

# 配置
COMPOSITION_ID="ChinaPlanXhs"
OUTPUT_BASE="${DASHENG_OUTPUT_ROOT:-${HOME}/Desktop/自媒体创作}"
OUTPUT_DIR="${OUTPUT_BASE}/2026-04-05_075240_ai/05_发布/videos/motion_narrative"
OUTPUT_FILE="${OUTPUT_DIR}/china-plan-xhs-claude-purple.mp4"

# 创建输出目录
mkdir -p "${OUTPUT_DIR}"

# 进入 Remotion 项目目录（支持环境变量覆盖）
REMOTION_PROJECT="${DASHENG_REMOTION_PROJECT:-${HOME}/clawd/remotion-video-starter}"
if [ ! -d "$REMOTION_PROJECT" ]; then
  echo "⚠️  Remotion 项目目录不存在: $REMOTION_PROJECT"
  echo "请设置 DASHENG_REMOTION_PROJECT 环境变量指向 Remotion 项目"
  echo "跳过视频渲染..."
  exit 0
fi
cd "$REMOTION_PROJECT"

echo "📹 渲染配置："
echo "  - 组合：${COMPOSITION_ID}"
echo "  - 输出：${OUTPUT_FILE}"
echo "  - 分辨率：1080x1920（竖版）"
echo "  - 帧率：30fps"
echo "  - 质量：100（最高）"
echo ""

# 渲染视频
npx remotion render src/index.jsx ${COMPOSITION_ID} "${OUTPUT_FILE}" \
  --quality=100 \
  --concurrency=4

echo ""
echo "✅ 渲染完成！"
echo ""
echo "📁 视频位置："
echo "  ${OUTPUT_FILE}"
echo ""
echo "📊 视频信息："
ls -lh "${OUTPUT_FILE}"
echo ""
echo "🎥 可以使用以下命令预览："
echo "  open \"${OUTPUT_FILE}\""
