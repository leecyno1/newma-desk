#!/usr/bin/env bash
set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

output="$("$BACKEND_DIR/scripts/start_backend.sh" --check)"
printf '%s\n' "$output"

grep -q "Selected Python:" <<< "$output"
grep -q "Required imports: OK" <<< "$output"
