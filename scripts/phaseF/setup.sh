#!/usr/bin/env bash
# Install Grounding DINO + SAHI deps into yolo_env.
# Run once per machine before autolabel.py.
set -euo pipefail

if [[ ! -d yolo_env ]]; then
    echo "yolo_env not found — run from the repo root after setting up yolo_env." >&2
    exit 1
fi

PIP="yolo_env/bin/pip"

# transformers >=4.45 shipped the GroundingDINO post-processing API used by
# autolabel.py. supervision provides InferenceSlicer (SAHI) and NMS helpers.
$PIP install -U \
    "transformers>=4.45" \
    "supervision>=0.24" \
    "torchvision>=0.20" \
    "Pillow>=10" \
    "tqdm>=4.66"

# Model weights are pulled lazily from Hugging Face on first run (~700 MB for
# grounding-dino-base). Cache lands in ~/.cache/huggingface/.
echo
echo "Setup complete. First autolabel.py run will download model weights (~700 MB)."
