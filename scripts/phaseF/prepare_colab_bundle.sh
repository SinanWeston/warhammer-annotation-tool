#!/usr/bin/env bash
# Thin wrapper around prepare_colab_bundle.py — ensures the bundle is
# built with fiftyone_env's Python (which has Pillow) rather than system
# Python (which may not).
set -euo pipefail

if [[ ! -x fiftyone_env/bin/python ]]; then
    echo "fiftyone_env/bin/python not found — run from the repo root after setting up fiftyone_env." >&2
    exit 1
fi

exec fiftyone_env/bin/python scripts/phaseF/prepare_colab_bundle.py "$@"
