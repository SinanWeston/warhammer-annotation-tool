#!/usr/bin/env python3
"""
Phase 1 — evaluate class-agnostic detection with OWLv2 visual prompts.

Runs google/owlv2-base-patch16-ensemble on every image in
backend/yolo_dataset/images/val/, with a fixed set of visual prompt crops
sampled from scripts/phase1/crops/ (reused from extract_gt_crops output).
Matches each prediction to ground-truth boxes via IoU 0.5 and reports
detection recall / precision for comparison against the YOLO baseline
recorded in Phase 0 (66.0% recall, 76.3% precision).

Helpers (iou, yolo_to_xyxy, match_greedy, load_yolo_label) are
re-implemented here so the script is standalone — their semantics mirror
scripts/phase0_baseline.py exactly.

Usage:
    yolo_env/bin/python3 scripts/phase1/eval_detection.py
    yolo_env/bin/python3 scripts/phase1/eval_detection.py --prompts-per-faction 3
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VAL_IMAGES = REPO_ROOT / "backend" / "yolo_dataset" / "images" / "val"
VAL_LABELS = REPO_ROOT / "backend" / "yolo_dataset" / "labels" / "val"
DATA_YAML = REPO_ROOT / "backend" / "yolo_dataset" / "data.yaml"
PHASE1 = REPO_ROOT / "scripts" / "phase1"
CROPS_DIR = PHASE1 / "crops"
RESULTS_DIR = PHASE1 / "results"

MODEL_ID = "google/owlv2-base-patch16-ensemble"
IOU_THRESHOLD = 0.5


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--prompts-per-faction", type=int, default=1, help="How many example crops per faction to use as visual prompts (each adds an inference pass per image)")
    p.add_argument("--score-threshold", type=float, default=0.1, help="OWLv2 score threshold to retain a detection")
    p.add_argument("--nms-iou", type=float, default=0.3, help="NMS IoU threshold when unioning predictions across prompts")
    p.add_argument("--device", default=None)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--limit", type=int, default=None, help="Evaluate only the first N images (for smoke tests)")
    return p.parse_args()


def load_class_names(yaml_path: Path) -> list[str]:
    for line in yaml_path.read_text().splitlines():
        if line.strip().startswith("names:"):
            raw = line.split(":", 1)[1].strip().strip("[]")
            names = [n.strip().strip('"').strip("'") for n in raw.split(",")]
            return [n for n in names if n]
    raise ValueError(f"Could not parse class names from {yaml_path}")


def load_yolo_label(label_path: Path) -> list[tuple[int, list[float]]]:
    if not label_path.exists():
        return []
    out = []
    for line in label_path.read_text().splitlines():
        parts = line.strip().split()
        if len(parts) < 5:
            continue
        out.append((int(parts[0]), [float(v) for v in parts[1:5]]))
    return out


def yolo_to_xyxy(yolo_box, img_w, img_h):
    x_c, y_c, w, h = yolo_box
    x1 = (x_c - w / 2) * img_w
    y1 = (y_c - h / 2) * img_h
    x2 = (x_c + w / 2) * img_w
    y2 = (y_c + h / 2) * img_h
    return [x1, y1, x2, y2]


def iou(a, b):
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    iw, ih = max(0.0, x2 - x1), max(0.0, y2 - y1)
    inter = iw * ih
    if inter == 0:
        return 0.0
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def match_greedy(preds, gts, iou_thr):
    preds_sorted = sorted(enumerate(preds), key=lambda x: -x[1]["score"])
    used_gt = set()
    matches = []
    for pi, pred in preds_sorted:
        best_iou, best_gt = 0.0, None
        for gi, gt in enumerate(gts):
            if gi in used_gt:
                continue
            i = iou(pred["xyxy"], gt["xyxy"])
            if i > best_iou:
                best_iou, best_gt = i, gi
        if best_gt is not None and best_iou >= iou_thr:
            matches.append({"pred_idx": pi, "gt_idx": best_gt, "iou": best_iou})
            used_gt.add(best_gt)
    return matches


def nms(preds: list[dict], iou_thr: float) -> list[dict]:
    """Standard greedy NMS: keep highest-score preds that don't overlap >iou_thr with already-kept."""
    kept: list[dict] = []
    for p in sorted(preds, key=lambda x: -x["score"]):
        if any(iou(p["xyxy"], k["xyxy"]) >= iou_thr for k in kept):
            continue
        kept.append(p)
    return kept


def pick_prompts(rng: random.Random, per_faction: int) -> list[Path]:
    """Collect up to `per_faction` example crops per faction for visual prompting."""
    if not CROPS_DIR.exists():
        sys.exit(f"{CROPS_DIR} not found — run extract_gt_crops.py first.")
    prompts: list[Path] = []
    for fd in sorted(p for p in CROPS_DIR.iterdir() if p.is_dir()):
        imgs = sorted(fd.glob("*.jpg"))
        rng.shuffle(imgs)
        prompts.extend(imgs[:per_faction])
    return prompts


def main():
    args = parse_args()

    try:
        import numpy as np
        import torch
        from PIL import Image
        from transformers import Owlv2ForObjectDetection, Owlv2Processor
    except ImportError as e:
        sys.exit(f"Missing dependency: {e}. Run from yolo_env.")

    class_names = load_class_names(DATA_YAML)
    device = args.device or ("cuda:0" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    rng = random.Random(args.seed)
    prompt_paths = pick_prompts(rng, args.prompts_per_faction)
    if not prompt_paths:
        sys.exit("No prompt crops found under scripts/phase1/crops/")
    print(f"Using {len(prompt_paths)} visual prompts ({args.prompts_per_faction}/faction)")

    print(f"Loading {MODEL_ID}...")
    processor = Owlv2Processor.from_pretrained(MODEL_ID)
    model = Owlv2ForObjectDetection.from_pretrained(MODEL_ID).to(device).eval()

    prompt_imgs = [Image.open(p).convert("RGB") for p in prompt_paths]

    images = sorted(p for p in VAL_IMAGES.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"))
    if args.limit:
        images = images[: args.limit]
    print(f"Evaluating {len(images)} val images × {len(prompt_imgs)} prompts = "
          f"{len(images) * len(prompt_imgs)} inference calls")
    print(f"Score threshold: {args.score_threshold}  |  NMS IoU: {args.nms_iou}  |  Match IoU: {IOU_THRESHOLD}")

    total_gt = 0
    total_pred = 0
    total_tp = 0

    # OWLv2 image_guided_detection expects one query per target — we iterate the
    # prompts and union predictions with NMS. Processing one image×prompt pair
    # per call keeps batching simple and avoids shape mismatches.
    with torch.no_grad():
        for i, img_path in enumerate(images, 1):
            img = Image.open(img_path).convert("RGB")
            img_w, img_h = img.size

            union_preds: list[dict] = []
            for prompt_img in prompt_imgs:
                inputs = processor(
                    images=img,
                    query_images=prompt_img,
                    return_tensors="pt",
                ).to(device)
                outputs = model.image_guided_detection(**inputs)
                target_sizes = torch.tensor([[img_h, img_w]], device=device)
                results = processor.post_process_image_guided_detection(
                    outputs=outputs,
                    threshold=args.score_threshold,
                    nms_threshold=args.nms_iou,
                    target_sizes=target_sizes,
                )[0]
                for box, score in zip(results["boxes"].cpu().tolist(), results["scores"].cpu().tolist()):
                    union_preds.append({"xyxy": box, "score": float(score)})

            preds = nms(union_preds, args.nms_iou)

            # Load GT.
            label_path = VAL_LABELS / f"{img_path.stem}.txt"
            gts = [
                {"class_id": cls, "xyxy": yolo_to_xyxy(yb, img_w, img_h)}
                for cls, yb in load_yolo_label(label_path)
            ]
            matches = match_greedy(preds, gts, IOU_THRESHOLD)

            total_gt += len(gts)
            total_pred += len(preds)
            total_tp += len(matches)

            if i % 10 == 0 or i == len(images):
                recall = total_tp / total_gt if total_gt else 0.0
                prec = total_tp / total_pred if total_pred else 0.0
                print(f"  [{i}/{len(images)}]  GT={total_gt}  pred={total_pred}  "
                      f"TP={total_tp}  recall={recall:.1%}  prec={prec:.1%}")

    det_recall = total_tp / total_gt if total_gt else 0.0
    det_precision = total_tp / total_pred if total_pred else 0.0

    summary = {
        "model_id": MODEL_ID,
        "num_images": len(images),
        "prompts_per_faction": args.prompts_per_faction,
        "prompt_paths": [str(p.relative_to(REPO_ROOT)) for p in prompt_paths],
        "score_threshold": args.score_threshold,
        "iou_match_threshold": IOU_THRESHOLD,
        "totals": {
            "ground_truth_boxes": total_gt,
            "predicted_boxes": total_pred,
            "true_positives": total_tp,
        },
        "metrics": {
            "detection_recall_iou50": det_recall,
            "detection_precision_iou50": det_precision,
        },
        "comparison_baseline": {
            "yolo_phase0_recall_iou50": 0.660,
            "yolo_phase0_precision_iou50": 0.763,
        },
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / "detection_summary.json"
    out_path.write_text(json.dumps(summary, indent=2))

    print()
    print("=== Detection summary ===")
    print(f"Images: {len(images)}")
    print(f"GT boxes: {total_gt}")
    print(f"Predicted boxes: {total_pred}")
    print(f"True positives (IoU ≥ 0.5): {total_tp}")
    print()
    print(f"OWLv2 detection recall:    {det_recall:.1%}  (YOLO baseline: 66.0%)")
    print(f"OWLv2 detection precision: {det_precision:.1%}  (YOLO baseline: 76.3%)")
    print(f"\nFull results: {out_path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
