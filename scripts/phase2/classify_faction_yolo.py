#!/usr/bin/env python3
"""
Phase 2 — YOLO-based faction classifier (DEPRECATED for crops).

⚠ This file is kept for reference but NOT used as Tier 2.

YOLO11x Run 2 was trained on full tabletop photographs with scene
context. On tight single-miniature crops (as Phase 2 produces), its
confidence collapses — empirically 0.01–0.17 on a handful of test
crops, often with the wrong top-1 class. We pivoted Tier 2 to
`classify_faction_knn.py`, which votes with the DINOv2 gallery
neighbours. That runs in the same embedding space as Tier 3 and has
no crop/scene distribution mismatch.

This file may still be useful for classifying full images
(e.g. the unconditional consumer-scan pipeline in a future phase).
Do not import it from the Phase 2 eval path.

Usage as a CLI (for full-image classification debugging):
    yolo_env/bin/python3 scripts/phase2/classify_faction_yolo.py \
        backend/yolo_dataset/images/val/106798_0c58414bb9eb.jpg
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_MODEL = REPO_ROOT / "runs" / "yolo11x_run2_best.pt"

# Model class-name aliases — same mapping as
# backend/src/services/yoloInferenceService.ts MODEL_CLASS_ALIASES.
# Normalises the model's training labels onto the canonical faction set
# used by the rest of the pipeline.
CLASS_ALIASES = {
    "eldar": "eldar",  # already canonical in YOLO's class list
    "imperial_guard": "astra_militarum",
    "custodes": "adeptus_custodes",
    "genestealer_cult": "genestealer_cult",  # already canonical
}


def init_model(model_path: Path | str = DEFAULT_MODEL):
    """Load the YOLO model once. Reuse the same instance across calls."""
    from ultralytics import YOLO

    model = YOLO(str(model_path))
    return model


def _canonicalise(name: str) -> str:
    return CLASS_ALIASES.get(name, name)


def classify_faction(model, image, conf_threshold: float = 0.10) -> dict:
    """
    Classify a single image's faction.

    `image` can be a pathlib.Path, a str path, bytes (JPEG buffer), or
    a PIL.Image. Returns:
        {
          "faction": <canonical faction slug>,
          "confidence": <float 0-1>,
          "all_scores": {<faction>: <max-conf across boxes>, ...},
          "n_detections": <int>,
        }

    Strategy: run YOLO on the crop (conf threshold low to keep options
    open), aggregate each class's maximum confidence across detections,
    return the class with the highest max-confidence. This is a
    single-image classification, not multi-object detection.
    """
    results = model.predict(image, conf=conf_threshold, verbose=False)

    all_scores: dict[str, float] = {}
    n_detections = 0
    if results:
        r = results[0]
        names = r.names  # {class_id: "name"}
        for box in r.boxes:
            n_detections += 1
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            label = _canonicalise(names.get(cls_id, str(cls_id)))
            if conf > all_scores.get(label, 0):
                all_scores[label] = conf

    if not all_scores:
        return {
            "faction": None,
            "confidence": 0.0,
            "all_scores": {},
            "n_detections": 0,
        }

    top_label, top_conf = max(all_scores.items(), key=lambda kv: kv[1])
    return {
        "faction": top_label,
        "confidence": top_conf,
        "all_scores": all_scores,
        "n_detections": n_detections,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("image", help="Path to a crop image")
    parser.add_argument("--model", default=str(DEFAULT_MODEL))
    parser.add_argument("--conf", type=float, default=0.10)
    args = parser.parse_args()

    model = init_model(args.model)
    result = classify_faction(model, args.image, conf_threshold=args.conf)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
