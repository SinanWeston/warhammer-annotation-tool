#!/usr/bin/env bash
# Thin wrapper around prepare_colab_bundle.py — ensures the bundle is
# built with yolo_env's Python (which has Pillow) rather than system
# Python (which may not).
set -euo pipefail

if [[ ! -x yolo_env/bin/python ]]; then
    echo "yolo_env/bin/python not found — run from the repo root after setting up yolo_env." >&2
    exit 1
fi

exec yolo_env/bin/python scripts/phaseF/prepare_colab_bundle.py "$@"
