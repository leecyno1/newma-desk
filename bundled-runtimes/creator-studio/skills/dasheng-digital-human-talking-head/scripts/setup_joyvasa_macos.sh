#!/usr/bin/env bash
set -euo pipefail

RUNTIME_ROOT="${DASHENG_DIGITAL_HUMAN_HOME:-$HOME/AI_MODELS/digital-human}"
REPO_DIR="$RUNTIME_ROOT/JoyVASA"
VENV_DIR="$RUNTIME_ROOT/.venv"
PY="$VENV_DIR/bin/python"
HF="$VENV_DIR/bin/hf"
PYTHON_VERSION="${DASHENG_DIGITAL_HUMAN_PYTHON:-3.11}"
JOYVASA_COMMIT="${DASHENG_JOYVASA_COMMIT:-916a90f8de490e8648fee460c1200bd5d9a795af}"
DOWNLOAD_WEIGHTS=1

if [[ "${1:-}" == "--skip-weights" ]]; then
  DOWNLOAD_WEIGHTS=0
elif [[ -n "${1:-}" ]]; then
  echo "usage: setup_joyvasa_macos.sh [--skip-weights]" >&2
  exit 2
fi

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "This setup targets Apple Silicon macOS." >&2
  exit 1
fi

for tool in git ffmpeg ffprobe uv; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "Missing required tool: $tool" >&2
    exit 1
  fi
done

mkdir -p "$RUNTIME_ROOT" "$RUNTIME_ROOT/out"

if [[ ! -d "$REPO_DIR/.git" ]]; then
  git clone --depth 1 https://github.com/jdh-algo/JoyVASA.git "$REPO_DIR"
else
  echo "JoyVASA checkout already exists: $REPO_DIR" >&2
fi
git -C "$REPO_DIR" fetch --depth 1 origin "$JOYVASA_COMMIT"
git -C "$REPO_DIR" checkout --detach "$JOYVASA_COMMIT"

uv venv --python "$PYTHON_VERSION" "$VENV_DIR"
uv pip install --python "$PY" \
  torch==2.8.0 torchvision==0.23.0 torchaudio==2.8.0 \
  numpy==1.26.4 scipy==1.13.1 scikit-image==0.24.0 \
  opencv-python==4.10.0.84 imageio==2.34.2 imageio-ffmpeg==0.5.1 moviepy==1.0.3 \
  librosa==0.10.2.post1 transformers==4.39.2 \
  onnx==1.16.1 onnxruntime==1.18.0 \
  omegaconf==2.3.0 pyyaml==6.0.1 tyro==0.8.5 rich==13.7.1 tqdm==4.66.4 \
  einops==0.8.0 pykalman==0.9.7 ffmpeg-python==0.2.0 matplotlib==3.9.0 pillow \
  'huggingface_hub[cli,hf_xet]'

"$PY" - "$REPO_DIR" <<'PY'
from pathlib import Path
import sys

repo = Path(sys.argv[1])
patches = {
    "src/modules/common.py": [
        ("def enc_dec_mask(T, S, frame_width=2, expansion=0, device='cuda'):",
         "def enc_dec_mask(T, S, frame_width=2, expansion=0, device=None):"),
        ("    return (mask == 1).to(device=device)",
         "    return (mask == 1) if device is None else (mask == 1).to(device=device)"),
    ],
    "src/utils/helper.py": [
        ("                               n_diff_steps=model_args.n_diff_steps,)",
         "                               n_diff_steps=model_args.n_diff_steps,\n"
         "                               device=device,)"),
    ],
}
for rel, replacements in patches.items():
    path = repo / rel
    text = path.read_text(encoding="utf-8")
    updated = text
    for old, new in replacements:
        updated = updated.replace(old, new)
    if updated != text:
        path.write_text(updated, encoding="utf-8")
        print(f"patched {rel}")
PY

if [[ "$DOWNLOAD_WEIGHTS" -eq 1 ]]; then
  export HF_HUB_ENABLE_HF_TRANSFER=0
  PW="$REPO_DIR/pretrained_weights"
  mkdir -p "$PW"
  "$HF" download jdh-algo/JoyVASA --local-dir "$PW/JoyVASA" --exclude README.md .gitattributes
  "$HF" download TencentGameMate/chinese-hubert-base \
    --local-dir "$PW/TencentGameMate:chinese-hubert-base" \
    --include config.json preprocessor_config.json pytorch_model.bin
  "$HF" download KlingTeam/LivePortrait --local-dir "$PW" \
    --include 'liveportrait/*' 'insightface/*'
fi

PYTORCH_ENABLE_MPS_FALLBACK=1 "$PY" - <<'PY'
import torch
print(f"torch={torch.__version__}")
print(f"mps_available={torch.backends.mps.is_available()}")
if not torch.backends.mps.is_available():
    raise SystemExit("MPS is unavailable in the runtime venv")
PY

echo "$PY"
