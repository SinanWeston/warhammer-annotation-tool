#!/usr/bin/env bash
# Install the SAM 3 + SAM 2 + SAHI deps into fiftyone_env.
# Run once per machine before the local bundle-prep / autolabel scripts.
# (On Colab the notebook installs its own deps.)
set -euo pipefail

ENV="${ENV:-fiftyone_env}"
if [[ ! -d "$ENV" ]]; then
    echo "$ENV not found — run from the repo root after creating $ENV." >&2
    exit 1
fi

PIP="$ENV/bin/pip"

# transformers ships the SAM 3 / SAM 2 post-processing API; supervision provides
# InferenceSlicer (SAHI) + NMS helpers used by the SAM 3 pipeline.
$PIP install -U \
    "transformers>=4.49" \
    "supervision>=0.24" \
    "torchvision>=0.20" \
    "Pillow>=10" \
    "tqdm>=4.66"

# SAM 3 (facebook/sam3, gated) + SAM 2 weights pull lazily from Hugging Face on
# first run. Cache lands in ~/.cache/huggingface/. SAM 3 needs HUGGINGFACE_HUB_TOKEN.
echo
echo "Setup complete. First SAM 3 run downloads model weights."
