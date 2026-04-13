#!/usr/bin/env python3
"""
Grounding DINO Batch Proposal Generator

Runs Grounding DINO over unannotated images to generate bounding box proposals.
These proposals are saved as JSON files that the annotator loads as AI suggestions,
letting annotators accept/reject/resize instead of drawing from scratch.

Usage:
    python scripts/grounding_dino_propose.py                    # Process all unannotated
    python scripts/grounding_dino_propose.py --faction necrons  # Single faction
    python scripts/grounding_dino_propose.py --limit 500        # Cap at 500 images
    python scripts/grounding_dino_propose.py --threshold 0.3    # Lower confidence threshold
    python scripts/grounding_dino_propose.py --dry-run          # Preview without writing
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import torch
from PIL import Image
from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection

# Paths relative to project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
TRAINING_DATA_DIR = PROJECT_ROOT / "backend" / "training_data"
ANNOTATIONS_DIR = PROJECT_ROOT / "backend" / "training_data_annotations"
PROPOSALS_DIR = PROJECT_ROOT / "backend" / "training_data_proposals"

# Grounding DINO model — use local path if available, otherwise HuggingFace
LOCAL_MODEL_DIR = PROJECT_ROOT / "models" / "grounding-dino-base"
MODEL_ID = str(LOCAL_MODEL_DIR) if LOCAL_MODEL_DIR.exists() and (LOCAL_MODEL_DIR / "config.json").exists() else "IDEA-Research/grounding-dino-base"

# Text prompt — period-separated classes for DINO's text grounding.
# "miniature" alone works well for Warhammer minis. Adding synonyms
# slightly improves recall on unusual poses/angles.
DEFAULT_PROMPT = "miniature . figurine"

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def get_image_id(faction: str, source: str, filename: str) -> str:
    """Build imageId matching the backend convention: faction_source_stem."""
    stem = Path(filename).stem
    return f"{faction}_{source}_{stem}"


def collect_unannotated_images(faction_filter: str | None = None, source_filter: str | None = None) -> list[dict]:
    """Walk training_data and return images without annotations or proposals."""
    # Load existing annotation IDs
    annotated_ids: set[str] = set()
    if ANNOTATIONS_DIR.exists():
        for f in ANNOTATIONS_DIR.iterdir():
            if f.suffix == ".json":
                annotated_ids.add(f.stem)

    # Load existing proposal IDs (so we can resume interrupted runs)
    proposed_ids: set[str] = set()
    if PROPOSALS_DIR.exists():
        for f in PROPOSALS_DIR.iterdir():
            if f.suffix == ".json":
                proposed_ids.add(f.stem)

    images: list[dict] = []
    if not TRAINING_DATA_DIR.exists():
        print(f"ERROR: Training data directory not found: {TRAINING_DATA_DIR}")
        sys.exit(1)

    for faction_dir in sorted(TRAINING_DATA_DIR.iterdir()):
        if not faction_dir.is_dir():
            continue
        faction = faction_dir.name

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

                image_id = get_image_id(faction, source, img_file.name)

                # Skip already annotated or already proposed
                if image_id in annotated_ids or image_id in proposed_ids:
                    continue

                images.append({
                    "imageId": image_id,
                    "path": str(img_file),
                    "faction": faction,
                    "source": source,
                })

    return images


def load_model(device: str) -> tuple:
    """Load Grounding DINO model and processor."""
    print(f"Loading Grounding DINO model ({MODEL_ID})...")
    print(f"Device: {device}")
    t0 = time.time()

    processor = AutoProcessor.from_pretrained(MODEL_ID)
    model = AutoModelForZeroShotObjectDetection.from_pretrained(MODEL_ID).to(device)

    print(f"Model loaded in {time.time() - t0:.1f}s")
    return model, processor


def run_inference(
    model,
    processor,
    image_path: str,
    prompt: str,
    threshold: float,
    device: str,
    nms_threshold: float = 0.5,
) -> list[dict]:
    """Run Grounding DINO on a single image. Returns list of box dicts."""
    image = Image.open(image_path).convert("RGB")
    w, h = image.size

    inputs = processor(images=image, text=prompt, return_tensors="pt").to(device)

    with torch.no_grad():
        outputs = model(**inputs)

    results = processor.post_process_grounded_object_detection(
        outputs,
        inputs.input_ids,
        threshold=threshold,
        text_threshold=threshold,
        target_sizes=[(h, w)],
    )[0]

    boxes = []
    for score, box in zip(results["scores"], results["boxes"]):
        x1, y1, x2, y2 = box.tolist()
        conf = score.item()

        # Skip tiny detections (< 20px in either dimension)
        bw = x2 - x1
        bh = y2 - y1
        if bw < 20 or bh < 20:
            continue

        boxes.append({
            "x": round(x1, 1),
            "y": round(y1, 1),
            "width": round(bw, 1),
            "height": round(bh, 1),
            "confidence": round(conf, 3),
        })

    return nms(boxes, iou_threshold=nms_threshold)


def box_iou(a: dict, b: dict) -> float:
    """Compute IoU between two boxes (x, y, width, height format)."""
    ax1, ay1 = a["x"], a["y"]
    ax2, ay2 = ax1 + a["width"], ay1 + a["height"]
    bx1, by1 = b["x"], b["y"]
    bx2, by2 = bx1 + b["width"], by1 + b["height"]

    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)

    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0

    inter = (ix2 - ix1) * (iy2 - iy1)
    union = a["width"] * a["height"] + b["width"] * b["height"] - inter
    return inter / union if union > 0 else 0.0


def nms(boxes: list[dict], iou_threshold: float = 0.5) -> list[dict]:
    """Non-Maximum Suppression: remove overlapping lower-confidence duplicates."""
    if not boxes:
        return boxes
    # Sort by confidence descending
    sorted_boxes = sorted(boxes, key=lambda b: b["confidence"], reverse=True)
    keep = []
    for box in sorted_boxes:
        # Keep this box if it doesn't overlap too much with any already-kept box
        if not any(box_iou(box, kept) > iou_threshold for kept in keep):
            keep.append(box)
    return keep


def save_proposal(image_id: str, boxes: list[dict]) -> None:
    """Write proposal JSON to the proposals directory."""
    PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)

    proposal = {
        "imageId": image_id,
        "proposalSource": "grounding_dino",
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "boxes": boxes,
    }

    out_path = PROPOSALS_DIR / f"{image_id}.json"
    out_path.write_text(json.dumps(proposal, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Generate DINO box proposals for annotation")
    parser.add_argument("--faction", type=str, default=None, help="Only process this faction")
    parser.add_argument("--source", type=str, default=None, help="Only process this source (e.g. isolation, reddit)")
    parser.add_argument("--limit", type=int, default=None, help="Max images to process")
    parser.add_argument("--threshold", type=float, default=0.25, help="Confidence threshold (default: 0.25)")
    parser.add_argument("--prompt", type=str, default=DEFAULT_PROMPT, help="Text prompt for DINO")
    parser.add_argument("--device", type=str, default=None, help="Device (auto-detected if omitted)")
    parser.add_argument("--nms-threshold", type=float, default=0.5, help="NMS IoU threshold to suppress duplicates (default: 0.5)")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be processed without writing")
    args = parser.parse_args()

    # Auto-detect device
    if args.device:
        device = args.device
    elif torch.cuda.is_available():
        device = "cuda"
    else:
        device = "cpu"

    # Collect images
    images = collect_unannotated_images(args.faction, args.source)
    if args.limit:
        images = images[:args.limit]

    if not images:
        print("No unannotated images to process.")
        return

    print(f"Found {len(images)} unannotated images to process")

    if args.dry_run:
        factions = {}
        for img in images:
            factions[img["faction"]] = factions.get(img["faction"], 0) + 1
        print("\nDry run — would process:")
        for faction, count in sorted(factions.items(), key=lambda x: -x[1]):
            print(f"  {faction}: {count}")
        return

    # Load model
    model, processor = load_model(device)

    # Process images
    total_boxes = 0
    images_with_boxes = 0
    start_time = time.time()

    for i, img in enumerate(images):
        try:
            boxes = run_inference(
                model, processor, img["path"], args.prompt, args.threshold, device,
                nms_threshold=args.nms_threshold,
            )

            # Always save proposal (even empty — prevents re-processing)
            save_proposal(img["imageId"], boxes)

            if boxes:
                total_boxes += len(boxes)
                images_with_boxes += 1

            # Progress logging
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            remaining = (len(images) - i - 1) / rate if rate > 0 else 0

            if (i + 1) % 10 == 0 or i == 0:
                print(
                    f"[{i+1}/{len(images)}] "
                    f"{img['imageId'][:50]}... "
                    f"{'%d boxes' % len(boxes) if boxes else 'no boxes'} | "
                    f"{rate:.1f} img/s | "
                    f"ETA {remaining/60:.0f}m"
                )

        except Exception as e:
            print(f"ERROR processing {img['imageId']}: {e}")
            continue

    elapsed = time.time() - start_time
    print(f"\nDone! Processed {len(images)} images in {elapsed/60:.1f} minutes")
    print(f"  {images_with_boxes} images with proposals ({images_with_boxes/len(images)*100:.0f}%)")
    print(f"  {total_boxes} total boxes ({total_boxes/len(images):.1f} avg per image)")
    print(f"  Proposals saved to: {PROPOSALS_DIR}")


if __name__ == "__main__":
    main()
