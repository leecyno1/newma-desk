#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd -P)"
SOURCE_DIR="${CHATLOG_SOURCE_DIR:-$ROOT_DIR/third_party/chatlog}"
OUTPUT_DIR="${CHATLOG_BUILD_DIR:-$ROOT_DIR/.local/chatlog/bin}"
VERSION="${CHATLOG_BUILD_VERSION:-vendored-bfb031f}"

find_go() {
  if command -v go >/dev/null 2>&1; then
    command -v go
    return 0
  fi
  for candidate in /opt/homebrew/bin/go /usr/local/bin/go /usr/bin/go; do
    if [[ -x "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

if [[ ! -f "$SOURCE_DIR/go.mod" || ! -f "$SOURCE_DIR/main.go" ]]; then
  echo "vendored chatlog source not found: $SOURCE_DIR" >&2
  exit 1
fi

GO_BIN="$(find_go || true)"
if [[ -z "$GO_BIN" ]]; then
  echo "Go 1.24+ is required to build the vendored chatlog source" >&2
  exit 1
fi

case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) OUTPUT_BIN="$OUTPUT_DIR/chatlog.exe" ;;
  *) OUTPUT_BIN="$OUTPUT_DIR/chatlog" ;;
esac

if [[ "${1:-}" == "--print-output" ]]; then
  printf '%s\n' "$OUTPUT_BIN"
  exit 0
fi

mkdir -p "$OUTPUT_DIR"
echo "building vendored chatlog -> $OUTPUT_BIN"
(
  cd "$SOURCE_DIR"
  CGO_ENABLED="${CGO_ENABLED:-1}" "$GO_BIN" build \
    -trimpath \
    -ldflags "-s -w -X github.com/sjzar/chatlog/pkg/version.Version=$VERSION" \
    -o "$OUTPUT_BIN" \
    ./main.go
)
chmod +x "$OUTPUT_BIN" 2>/dev/null || true
echo "built: $OUTPUT_BIN"
