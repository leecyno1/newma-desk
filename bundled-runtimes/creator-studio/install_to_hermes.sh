#!/usr/bin/env bash
# Newma Media Studio - Hermes 安装脚本
#
# 用法: install_to_hermes.sh [SKILLS_DIR] [WORKSPACE_DIR] [OPTIONS]
#
# 参数:
#   SKILLS_DIR       skills 安装目录（默认：$HOME/.hermes/skills）
#   WORKSPACE_DIR   工作空间目录（默认：$HOME/.hermes/workspaces/dasheng-media-workflow）
#
# 选项:
#   --help          显示此帮助信息
#   --dry-run       模拟运行，显示将执行的操作而不实际执行
#   --verbose       显示详细执行过程
#   --skip-confirm  跳过确认提示（用于自动化脚本）
#   --list-skills   仅列出将被安装的 skills，不执行安装
#
# 退出码:
#   0   安装成功
#   1   安装失败
#   2   参数错误
#   4   dry-run 或 list-skills 模式
#
# 示例:
#   install_to_hermes.sh                                    # 使用默认路径
#   install_to_hermes.sh /custom/skills                     # 自定义 skills 目录
#   install_to_hermes.sh --dry-run                          # 预览安装
#   install_to_hermes.sh --verbose --skip-confirm           # 静默安装

set -euo pipefail

# === 默认配置 ===
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET_SKILLS_DIR=""
WORKSPACE_DIR=""

# === CLI 参数解析 ===
HELP=false
DRY_RUN=false
VERBOSE=false
SKIP_CONFIRM=false
LIST_SKILLS=false

INSTALL_SKILLS=(
  dasheng-media-sop
  dasheng-daily-intake
  dasheng-daily-phase2
  dasheng-stage-draft
  dasheng-daily-material
  dasheng-stage-rewrite-v3
  dasheng-stage-publish
  dasheng-daily-postmortem
  dasheng-style-profiler
  feishu-doc-creator
  jiebang
  dasheng-daily-brief
  dasheng-daily-clustering
  dasheng-daily-draft
  dasheng-daily-outline
  dasheng-daily-final
)

# === 帮助信息 ===
usage() {
  cat <<'EOF'
用法: install_to_hermes.sh [SKILLS_DIR] [WORKSPACE_DIR] [OPTIONS]

将大圣自媒体工作流安装到 Hermes skills 目录。

参数:
  SKILLS_DIR       skills 安装目录（默认：$HOME/.hermes/skills）
  WORKSPACE_DIR   工作空间目录（默认：$HOME/.hermes/workspaces/dasheng-media-workflow）

选项:
  --help          显示此帮助信息
  --dry-run       模拟运行，显示将执行的操作而不实际执行
  --verbose       显示详细执行过程
  --skip-confirm  跳过确认提示（用于自动化脚本）
  --list-skills   仅列出将被安装的 skills，不执行安装

退出码:
  0   安装成功
  1   安装失败
  2   参数错误
  4   dry-run 或 list-skills 模式

示例:
  install_to_hermes.sh                                    # 使用默认路径
  install_to_hermes.sh /custom/skills                     # 自定义 skills 目录
  install_to_hermes.sh --dry-run                          # 预览安装
  install_to_hermes.sh --verbose --skip-confirm           # 静默安装
EOF
}

# === 解析参数 ===
while [[ $# -gt 0 ]]; do
  case "$1" in
    --help)
      HELP=true
      shift
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --verbose)
      VERBOSE=true
      shift
      ;;
    --skip-confirm)
      SKIP_CONFIRM=true
      shift
      ;;
    --list-skills)
      LIST_SKILLS=true
      shift
      ;;
    -*)
      echo "未知选项: $1" >&2
      echo "使用 --help 查看帮助" >&2
      exit 2
      ;;
    *)
      # 位置参数
      if [[ -z "$TARGET_SKILLS_DIR" ]]; then
        TARGET_SKILLS_DIR="$1"
      elif [[ -z "$WORKSPACE_DIR" ]]; then
        WORKSPACE_DIR="$1"
      else
        echo "错误：太多位置参数" >&2
        exit 2
      fi
      shift
      ;;
  esac
done

# 显示帮助
if [[ "$HELP" == true ]]; then
  usage
  exit 0
fi

# 设置默认值
TARGET_SKILLS_DIR="${TARGET_SKILLS_DIR:-$HOME/.hermes/skills}"
WORKSPACE_DIR="${WORKSPACE_DIR:-$HOME/.hermes/workspaces/dasheng-media-workflow}"

# === List-skills 模式 ===
if [[ "$LIST_SKILLS" == true ]]; then
  echo "将安装的 skills（共 ${#INSTALL_SKILLS[@]} 个）："
  for skill in "${INSTALL_SKILLS[@]}"; do
    echo "  - $skill"
  done
  exit 4
fi

# === 详细输出 ===
log() {
  if [[ "$VERBOSE" == true ]]; then
    echo "$@"
  fi
}

# === Dry-run 模式 ===
if [[ "$DRY_RUN" == true ]]; then
  cat <<EOF
[DRY-RUN] 以下操作将被执行：

1. 创建目录:
   - $TARGET_SKILLS_DIR
   - $WORKSPACE_DIR

2. 复制目录:
   - $BASE_DIR/skills/ → $WORKSPACE_DIR/skills/
   - $BASE_DIR/scripts/ → $WORKSPACE_DIR/scripts/
   - $BASE_DIR/docs/ → $WORKSPACE_DIR/docs/
   - $BASE_DIR/tests/ → $WORKSPACE_DIR/tests/

3. 复制文件:
   - README.md, requirements.txt, ENV_TEMPLATE.env

4. 创建 symlink:
EOF
  for skill in "${INSTALL_SKILLS[@]}"; do
    echo "   - $TARGET_SKILLS_DIR/$skill → $WORKSPACE_DIR/skills/$skill"
  done
  cat <<'EOF'

5. 设置环境变量:
   - HERMES_WORKSPACE=$WORKSPACE_DIR
   - DASHENG_PROJECT_ROOT=$WORKSPACE_DIR

EOF
  exit 4
fi

# === 确认提示 ===
if [[ "$SKIP_CONFIRM" != true ]]; then
  echo "即将安装到:"
  echo "  Skills 目录: $TARGET_SKILLS_DIR"
  echo "  Workspace: $WORKSPACE_DIR"
  echo ""
  read -rp "确认安装? [y/N] " confirm
  if [[ "${confirm,,}" != y ]]; then
    echo "已取消安装"
    exit 1
  fi
fi

# === 辅助函数 ===
copy_dir() {
  local src="$1"
  local dst="$2"
  log "复制: $src → $dst"
  if [[ "$DRY_RUN" == true ]]; then
    return 0
  fi
  if [[ -d "$src" ]]; then
    mkdir -p "$(dirname "$dst")"
    rsync -a --delete \
      --exclude '__pycache__' \
      --exclude '*.pyc' \
      --exclude '*.pyo' \
      --exclude '*.backup.*' \
      "$src/" "$dst/"
  fi
}

# === 执行安装 ===
log "开始安装..."

# 创建目录
if [[ "$VERBOSE" == true ]]; then
  echo "创建目录: $TARGET_SKILLS_DIR, $WORKSPACE_DIR"
fi
mkdir -p "$TARGET_SKILLS_DIR" "$WORKSPACE_DIR"

# 复制目录
copy_dir "$BASE_DIR/skills" "$WORKSPACE_DIR/skills"
copy_dir "$BASE_DIR/scripts" "$WORKSPACE_DIR/scripts"
copy_dir "$BASE_DIR/docs" "$WORKSPACE_DIR/docs"
copy_dir "$BASE_DIR/tests" "$WORKSPACE_DIR/tests"

# 复制文件
for file in README.md requirements.txt ENV_TEMPLATE.env; do
  if [[ -f "$BASE_DIR/$file" ]]; then
    log "复制文件: $file"
    cp "$BASE_DIR/$file" "$WORKSPACE_DIR/$file"
  fi
done

# 创建 symlink
for skill in "${INSTALL_SKILLS[@]}"; do
  if [[ ! -d "$WORKSPACE_DIR/skills/$skill" ]]; then
    log "跳过（不存在）: $skill"
    continue
  fi
  log "创建 symlink: $skill"
  if [[ "$DRY_RUN" == true ]]; then
    continue
  fi
  rm -rf "$TARGET_SKILLS_DIR/$skill"
  if ! ln -s "$WORKSPACE_DIR/skills/$skill" "$TARGET_SKILLS_DIR/$skill" 2>/dev/null; then
    cp -R "$WORKSPACE_DIR/skills/$skill" "$TARGET_SKILLS_DIR/$skill"
  fi
done

# === 完成 ===
cat <<EOF
✅ Hermes 安装完成

skills 目录: $TARGET_SKILLS_DIR
workspace 目录: $WORKSPACE_DIR

后续建议：
  export HERMES_WORKSPACE="$WORKSPACE_DIR"
  export DASHENG_PROJECT_ROOT="$WORKSPACE_DIR"
  cp "$WORKSPACE_DIR/ENV_TEMPLATE.env" "$WORKSPACE_DIR/.env"
EOF

exit 0
