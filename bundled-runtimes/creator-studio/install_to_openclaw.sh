#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC_DIR="${BASE_DIR}/skills"

# Parse arguments
SKIP_CONFIRM=""
SKILLS_DIR=""
WORKSPACE_DIR=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-confirm)
            SKIP_CONFIRM="yes"
            shift
            ;;
        -*)
            echo "Unknown option: $1"
            exit 1
            ;;
        *)
            if [[ -z "$SKILLS_DIR" ]]; then
                SKILLS_DIR="$1"
            elif [[ -z "$WORKSPACE_DIR" ]]; then
                WORKSPACE_DIR="$1"
            fi
            shift
            ;;
    esac
done

# Default paths if not provided
SKILLS_DIR="${SKILLS_DIR:-$HOME/.openclaw/skills}"
WORKSPACE_DIR="${WORKSPACE_DIR:-$HOME/.openclaw/workspace}"

mkdir -p -- "${SKILLS_DIR}"
mkdir -p -- "${WORKSPACE_DIR}"
mkdir -p -- "${WORKSPACE_DIR}/scripts"
mkdir -p -- "${WORKSPACE_DIR}/configs"

cp -R "${SRC_DIR}/." "${SKILLS_DIR}/"

# Copy workspace files
cp "${BASE_DIR}/scripts/run_mainline_stage.py" "${WORKSPACE_DIR}/scripts/"
cp "${BASE_DIR}/ENV_TEMPLATE.env" "${WORKSPACE_DIR}/"
cp -r "${BASE_DIR}/configs"/* "${WORKSPACE_DIR}/configs/" 2>/dev/null || true

echo "Installed skills to: ${SKILLS_DIR}"
echo "Installed workspace to: ${WORKSPACE_DIR}"
echo "Verify entry skill: dasheng-media-sop"
echo "Next: copy env template -> ~/.openclaw/dasheng.env"
echo "Template file: ${BASE_DIR}/ENV_TEMPLATE.env"
echo "Smoke prompts: ${BASE_DIR}/SMOKE_PROMPTS.md"
