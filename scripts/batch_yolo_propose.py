#!/usr/bin/env python3
"""
Batch YOLO Proposal Generator

Pre-computes bounding box proposals for all unannotated images using the trained
YOLO model and writes them to backend/training_data_proposals/ in the same JSON
format as grounding_dino_propose.py.

This is faster than Grounding DINO on CPU (~4-6s/image vs ~78s/image).

Usage:
    python scripts/batch_yolo_propose.py                     # All unannotated ebay images
    python scripts/batch_yolo_propose.py --source all        # All sources
    python scripts/batch_yolo_propose.py --faction necrons   # Single faction
    python scripts/batch_yolo_propose.py --limit 500         # Cap at N images
    python scripts/batch_yolo_propose.py --threshold 0.2     # Confidence threshold
    python scripts/batch_yolo_propose.py --dry-run           # Preview only
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image
from ultralytics import YOLO

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TRAINING_DATA_DIR = PROJECT_ROOT / "backend" / "training_data"
ANNOTATIONS_DIR   = PROJECT_ROOT / "backend" / "training_data_annotations"
PROPOSALS_DIR     = PROJECT_ROOT / "backend" / "training_data_proposals"

DEFAULT_MODEL     = PROJECT_ROOT / "runs" / "yolo11x_run2_best.pt"
FALLBACK_MODEL    = PROJECT_ROOT / "runs" / "yolo11_colab_best.pt"

IMAGE_EXTENSIONS  = {".jpg", ".jpeg", ".png", ".webp"}
SKIP_FACTIONS     = {"hormagaunts", "tyranid_ripper_swarm", "reddit", "dakkadakka"}

DEFAULT_SOURCE    = "ebay"
DEFAULT_THRESHOLD = 0.20
BATCH_SIZE        = 1   # YOLO handles its own batching; 1 is safest for memory on CPU


def collect_images(faction_filter, source_filter):
    annotated = {f.stem for f in ANNOTATIONS_DIR.iterdir() if f.suffix == ".json"} if ANNOTATIONS_DIR.exists() else set()
    proposed  = {f.stem for f in PROPOSALS_DIR.iterdir()  if f.suffix == ".json"} if PROPOSALS_DIR.exists() else set()

    images = []
    for faction_dir in sorted(TRAINING_DATA_DIR.iterdir()):
        if not faction_dir.is_dir():
            continue
        faction = faction_dir.name
        if faction in SKIP_FACTIONS:
            continue
        if faction_filter and faction != faction_filter:
            continue

        for source_dir in sorted(faction_dir.iterdir()):
            if not source_dir.is_dir():
                continue
            source = source_dir.name
            if source_filter and source != source_filter:
                continue

            for img_file in sorted(source_dir.iterdir()):
                if img_file.suffix.lower() not in IMAGE_EXTENSIONS:
                    continue

                stem     = img_file.stem
                image_id = f"{faction}_{source}_{stem}"

                if image_id in annotated or image_id in proposed:
                    continue

                images.append({
                    "imageId": image_id,
                    "path":    str(img_file),
                    "faction": faction,
                    "source":  source,
                })

    return images


def run(args):
    source_filter = None if args.source == "all" else args.source

    print(f"Scanning images (faction={args.faction or 'all'}, source={source_filter or 'all'})...", flush=True)
    images = collect_images(args.faction, source_filter)

    if args.limit:
        images = images[:args.limit]

    total = len(images)
    if total == 0:
        print("Nothing to process — all images already have proposals or annotations.")
        return

    print(f"Found {total} images to process", flush=True)

    if args.dry_run:
        for img in images[:20]:
            print(f"  {img['imageId']}")
        if total > 20:
            print(f"  ... and {total-20} more")
        return

    # Load model
    model_path = DEFAULT_MODEL if DEFAULT_MODEL.exists() else FALLBACK_MODEL
    if not model_path.exists():
        print(f"ERROR: No YOLO model found at {DEFAULT_MODEL} or {FALLBACK_MODEL}")
        sys.exit(1)

    print(f"Loading model: {model_path.name}", flush=True)
    model = YOLO(str(model_path))

    PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)

    done = 0
    skipped = 0
    t_start = time.time()

    for entry in images:
        image_id = entry["imageId"]
        img_path = Path(entry["path"])

        # Resolve symlinks for PIL
        if img_path.is_symlink():
            img_path = img_path.resolve()

        try:
            # Get image dimensions
            with Image.open(img_path) as img:
                img_w, img_h = img.size

            results = model.predict(str(img_path), verbose=False, conf=args.threshold)
            result  = results[0]

            boxes = []
            if result.boxes is not None and len(result.boxes) > 0:
                for box in result.boxes:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    conf = float(box.conf[0])
                    boxes.append({
                        "x":          round(x1, 1),
                        "y":          round(y1, 1),
                        "width":      round(x2 - x1, 1),
                        "height":     round(y2 - y1, 1),
                        "confidence": round(conf, 3),
                    })

            proposal = {
                "imageId":       image_id,
                "proposalSource": "yolo",
                "generatedAt":   datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "boxes":         boxes,
            }

            out_path = PROPOSALS_DIR / f"{image_id}.json"
            out_path.write_text(json.dumps(proposal, indent=2))
            done += 1

        except Exception as e:
            print(f"  ERROR {image_id}: {e}", flush=True)
            skipped += 1
            continue

        # Progress every 50 images
        if done % 50 == 0:
            elapsed = time.time() - t_start
            rate    = elapsed / done
            remaining = (total - done - skipped) * rate
            print(
                f"  [{done}/{total}] {rate:.1f}s/img  ETA {remaining/3600:.1f}h  "
                f"({entry['faction']})",
                flush=True,
            )

    elapsed = time.time() - t_start
    print(f"\nDone. {done} proposals written, {skipped} errors. Total time: {elapsed/3600:.1f}h", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--faction",   default=None,         help="Filter to one faction")
    parser.add_argument("--source",    default=DEFAULT_SOURCE, help="Source subdir filter (default: ebay, use 'all' for all)")
    parser.add_argument("--limit",     type=int, default=None, help="Max images to process")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD, help="YOLO confidence threshold (default: 0.20)")
    parser.add_argument("--dry-run",   action="store_true",  help="Preview without writing")
    args = parser.parse_args()
    run(args)
