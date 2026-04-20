"""F1 — Auto-label the unlabelled training-data pool with Grounding DINO.

Emits one JSON per image to `data/pseudo_labels/boxes/<imageId>.json` so the
run is resumable — re-running the script skips images whose output already
exists. See `scripts/phaseF/README.md` for the full story.

Usage:
    yolo_env/bin/python scripts/phaseF/autolabel.py                    # full run
    yolo_env/bin/python scripts/phaseF/autolabel.py --limit 20         # smoke test
    yolo_env/bin/python scripts/phaseF/autolabel.py --model tiny       # lighter/faster
    yolo_env/bin/python scripts/phaseF/autolabel.py --no-sahi          # disable tiling
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
import torchvision.ops as ops
from PIL import Image
from tqdm import tqdm
from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor

# --- Config --------------------------------------------------------------

# The dot-separated multi-concept prompt is how Grounding DINO wants it.
# Lowercase and trailing period are load-bearing (documented in
# IDEA-Research/GroundingDINO README). This matches the April 2026 recipe.
PROMPT = "painted miniature . figurine . tabletop model ."
BOX_THRESHOLD = 0.25
TEXT_THRESHOLD = 0.20
NMS_IOU = 0.5
MIN_AREA_FRAC = 0.005
MAX_AREA_FRAC = 0.80
SAHI_LONG_EDGE_THRESHOLD = 1200
SAHI_SLICE_SIZE = 640
SAHI_OVERLAP = 0.2

TRAINING_DATA = Path("backend/training_data")
ANN_DIR = Path("backend/training_data_annotations")
OUT_ROOT = Path("data/pseudo_labels")
BOX_DIR = OUT_ROOT / "boxes"
MANIFEST_PATH = OUT_ROOT / "manifest.json"
ERROR_LOG = OUT_ROOT / "errors.log"

IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

MODEL_IDS = {
    "base": "IDEA-Research/grounding-dino-base",
    "tiny": "IDEA-Research/grounding-dino-tiny",
}


# --- Helpers -------------------------------------------------------------


@dataclass
class ImageJob:
    image_id: str
    path: Path
    faction: str
    source: str


def image_id_from_path(path: Path) -> str:
    """Match the scheme used in backend/training_data_annotations/ JSONs:
    `{faction}_{source}_{stem}`. Stems may contain extra underscores so we
    don't parse them back out — just reconstruct the id deterministically."""
    # path: backend/training_data/<faction>/<source>/<filename>
    parts = path.parts
    faction = parts[-3]
    source = parts[-2]
    stem = path.stem
    return f"{faction}_{source}_{stem}"


def load_annotated_ids() -> set[str]:
    ids: set[str] = set()
    for p in ANN_DIR.glob("*.json"):
        try:
            d = json.loads(p.read_text())
        except Exception:
            continue
        img_id = d.get("imageId")
        if img_id:
            ids.add(img_id)
    return ids


def iter_unlabelled(annotated: set[str]) -> list[ImageJob]:
    jobs: list[ImageJob] = []
    for ext in IMG_EXTS:
        for p in TRAINING_DATA.rglob(f"*{ext}"):
            if len(p.parts) < 3:
                continue
            img_id = image_id_from_path(p)
            if img_id in annotated:
                continue
            if (BOX_DIR / f"{img_id}.json").exists():
                continue
            jobs.append(ImageJob(
                image_id=img_id,
                path=p,
                faction=p.parts[-3],
                source=p.parts[-2],
            ))
    return jobs


# --- Detection -----------------------------------------------------------


class Detector:
    def __init__(self, model_key: str, device: str):
        model_id = MODEL_IDS[model_key]
        self.device = device
        self.processor = AutoProcessor.from_pretrained(model_id)
        self.model = AutoModelForZeroShotObjectDetection.from_pretrained(model_id).to(device)
        self.model.eval()

    @torch.inference_mode()
    def detect(self, image: Image.Image) -> tuple[np.ndarray, np.ndarray]:
        """Return (xyxy boxes, scores) in the original image's pixel coords."""
        inputs = self.processor(images=image, text=PROMPT, return_tensors="pt").to(self.device)
        outputs = self.model(**inputs)
        # target_sizes is (height, width) per the transformers convention.
        h, w = image.size[1], image.size[0]
        # transformers 5.x renamed `box_threshold` → `threshold`; older 4.x
        # versions used `box_threshold`. Prefer the 5.x name.
        results = self.processor.post_process_grounded_object_detection(
            outputs,
            inputs.input_ids,
            threshold=BOX_THRESHOLD,
            text_threshold=TEXT_THRESHOLD,
            target_sizes=[(h, w)],
        )[0]
        boxes = results["boxes"].detach().cpu().numpy() if len(results["boxes"]) else np.zeros((0, 4))
        scores = results["scores"].detach().cpu().numpy() if len(results["scores"]) else np.zeros((0,))
        return boxes.astype(np.float32), scores.astype(np.float32)


def detect_with_sahi(detector: Detector, image: Image.Image) -> tuple[np.ndarray, np.ndarray]:
    """Run tiled inference on images larger than `SAHI_LONG_EDGE_THRESHOLD`.
    Crops the image into overlapping SAHI_SLICE_SIZE tiles, runs the detector
    on each, offsets boxes back into image coordinates, then merges via
    class-agnostic NMS. Hand-rolled to keep the dependency footprint to
    just transformers + torch + Pillow — Colab's preinstalled torch is
    CUDA-12 and breaks if we let `supervision`'s wheel drag in cu13 torch."""
    w, h = image.size
    stride = max(1, int(SAHI_SLICE_SIZE * (1 - SAHI_OVERLAP)))
    # Compute anchors that cover the image even if (w - slice) isn't a
    # multiple of stride — pad the last row / column by snapping to
    # w - slice / h - slice so no pixels are missed.
    def _anchors(dim: int) -> list[int]:
        if dim <= SAHI_SLICE_SIZE:
            return [0]
        pts = list(range(0, dim - SAHI_SLICE_SIZE, stride))
        pts.append(dim - SAHI_SLICE_SIZE)
        return pts

    xs = _anchors(w)
    ys = _anchors(h)
    all_boxes: list[np.ndarray] = []
    all_scores: list[np.ndarray] = []
    for y in ys:
        for x in xs:
            tile = image.crop((x, y, x + SAHI_SLICE_SIZE, y + SAHI_SLICE_SIZE))
            tb, ts = detector.detect(tile)
            if len(tb) == 0:
                continue
            tb = tb.copy()
            tb[:, [0, 2]] += x
            tb[:, [1, 3]] += y
            all_boxes.append(tb)
            all_scores.append(ts)

    if not all_boxes:
        return np.zeros((0, 4), dtype=np.float32), np.zeros((0,), dtype=np.float32)
    boxes = np.concatenate(all_boxes, axis=0)
    scores = np.concatenate(all_scores, axis=0)
    # Class-agnostic NMS to dedupe boxes predicted on adjacent tiles.
    keep = ops.nms(torch.from_numpy(boxes), torch.from_numpy(scores), NMS_IOU).tolist()
    return boxes[keep], scores[keep]


def post_process(
    boxes: np.ndarray, scores: np.ndarray, w: int, h: int
) -> tuple[np.ndarray, np.ndarray]:
    """Class-agnostic NMS, area filters, and clip-to-image."""
    if len(boxes) == 0:
        return boxes, scores
    # Clip to image bounds.
    boxes[:, [0, 2]] = boxes[:, [0, 2]].clip(0, w)
    boxes[:, [1, 3]] = boxes[:, [1, 3]].clip(0, h)
    # Area filter.
    img_area = float(w * h)
    areas = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
    keep_mask = (
        (areas >= img_area * MIN_AREA_FRAC)
        & (areas <= img_area * MAX_AREA_FRAC)
        & (boxes[:, 2] > boxes[:, 0])
        & (boxes[:, 3] > boxes[:, 1])
    )
    boxes, scores = boxes[keep_mask], scores[keep_mask]
    if len(boxes) == 0:
        return boxes, scores
    # Final class-agnostic NMS (SAHI already did a round per-tile; this
    # deduplicates boxes that the single-image path found vs tiled runs).
    keep = ops.nms(torch.from_numpy(boxes), torch.from_numpy(scores), NMS_IOU).tolist()
    return boxes[keep], scores[keep]


# --- Main ----------------------------------------------------------------


def process_one(
    detector: Detector, job: ImageJob, use_sahi: bool
) -> dict:
    image = Image.open(job.path).convert("RGB")
    w, h = image.size
    long_edge = max(w, h)
    if use_sahi and long_edge > SAHI_LONG_EDGE_THRESHOLD:
        boxes_xyxy, scores = detect_with_sahi(detector, image)
        mode = "sahi"
    else:
        boxes_xyxy, scores = detector.detect(image)
        mode = "whole"
    boxes_xyxy, scores = post_process(boxes_xyxy, scores, w, h)
    # Persist in [x, y, w, h] (COCO-style) to simplify RF-DETR training.
    boxes_xywh = boxes_xyxy.copy()
    if len(boxes_xywh):
        boxes_xywh[:, 2] -= boxes_xywh[:, 0]
        boxes_xywh[:, 3] -= boxes_xywh[:, 1]
    return {
        "imageId": job.image_id,
        "imagePath": str(job.path),
        "faction": job.faction,
        "source": job.source,
        "width": w,
        "height": h,
        "mode": mode,
        "boxes_xywh": boxes_xywh.round(2).tolist(),
        "scores": scores.round(4).tolist(),
    }


def write_manifest(n_done: int, stats: dict) -> None:
    manifest = {
        "version": 1,
        "prompt": PROMPT,
        "box_threshold": BOX_THRESHOLD,
        "text_threshold": TEXT_THRESHOLD,
        "nms_iou": NMS_IOU,
        "min_area_frac": MIN_AREA_FRAC,
        "max_area_frac": MAX_AREA_FRAC,
        "sahi_long_edge_threshold": SAHI_LONG_EDGE_THRESHOLD,
        "sahi_slice_size": SAHI_SLICE_SIZE,
        "n_images_processed": n_done,
        **stats,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))


def compute_stats() -> dict:
    n = 0
    n_with_boxes = 0
    total_boxes = 0
    per_source: dict[str, int] = {}
    for p in BOX_DIR.glob("*.json"):
        try:
            d = json.loads(p.read_text())
        except Exception:
            continue
        n += 1
        nb = len(d.get("boxes_xywh") or [])
        if nb:
            n_with_boxes += 1
        total_boxes += nb
        per_source[d.get("source", "?")] = per_source.get(d.get("source", "?"), 0) + 1
    return {
        "n_images_with_boxes": n_with_boxes,
        "n_images_total": n,
        "mean_boxes_per_image": round(total_boxes / max(n, 1), 3),
        "coverage_frac": round(n_with_boxes / max(n, 1), 4),
        "per_source": per_source,
    }


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", choices=list(MODEL_IDS), default="base",
                    help="grounding-dino-{base,tiny} checkpoint. base ≈ 700MB, tiny ≈ 230MB.")
    ap.add_argument("--limit", type=int, default=None,
                    help="Only process the first N unlabelled images (smoke test).")
    ap.add_argument("--no-sahi", action="store_true",
                    help="Disable SAHI tiling for large images. Faster but drops recall on crowded scenes.")
    ap.add_argument("--shuffle", action="store_true",
                    help="Shuffle the job order (seeded) so early progress spans all sources and "
                         "faction dirs, not just whichever rglob hits first. Recommended for CPU "
                         "batch runs where you want quick diversity sampling.")
    ap.add_argument("--shuffle-seed", type=int, default=42,
                    help="Seed for --shuffle. Keep constant so subsequent batches continue the "
                         "same deterministic order rather than reshuffling mid-run.")
    ap.add_argument("--device", default=None,
                    help="Override auto-picked device (cuda / cpu / mps).")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    BOX_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(ERROR_LOG),
        level=logging.WARNING,
        format="%(asctime)s %(message)s",
    )
    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}  Model: {args.model}  SAHI: {not args.no_sahi}")

    print("Enumerating unlabelled images…")
    annotated = load_annotated_ids()
    print(f"  {len(annotated)} already-annotated IDs (excluded)")
    jobs = iter_unlabelled(annotated)
    print(f"  {len(jobs)} unlabelled images to process (skips those already written)")
    if args.shuffle:
        random.Random(args.shuffle_seed).shuffle(jobs)
        print(f"  --shuffle (seed={args.shuffle_seed}) → randomised job order")
    if args.limit:
        jobs = jobs[: args.limit]
        print(f"  --limit {args.limit} → processing {len(jobs)}")
    if not jobs:
        print("Nothing to do.")
        return 0

    print("Loading detector…")
    detector = Detector(args.model, device)

    t0 = time.monotonic()
    n_done = 0
    n_err = 0
    try:
        for job in tqdm(jobs, desc="autolabel"):
            out_path = BOX_DIR / f"{job.image_id}.json"
            if out_path.exists():
                continue
            try:
                result = process_one(detector, job, use_sahi=not args.no_sahi)
                out_path.write_text(json.dumps(result))
                n_done += 1
            except Exception as e:
                n_err += 1
                logging.warning(
                    "failed %s: %s\n%s",
                    job.image_id, e, traceback.format_exc(limit=3),
                )
            # Periodic manifest flush so a kill doesn't lose the stats header.
            if n_done and n_done % 200 == 0:
                write_manifest(n_done, compute_stats())
    except KeyboardInterrupt:
        print("\nInterrupted; writing final manifest.")

    stats = compute_stats()
    write_manifest(n_done, stats)
    elapsed = time.monotonic() - t0
    print(f"\nDone in {elapsed:.1f}s  ({n_done} processed, {n_err} errors)")
    print(f"Stats: {json.dumps(stats, indent=2)}")
    if n_err:
        print(f"See {ERROR_LOG} for error details.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
