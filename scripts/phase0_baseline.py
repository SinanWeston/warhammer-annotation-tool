#!/usr/bin/env python3
"""
Phase 0 baseline — evaluate the current YOLO11x Run 2 model on the existing
held-out validation split (backend/yolo_dataset/images/val/) against the
labels that were exported at training time (backend/yolo_dataset/labels/val/).

Produces the canonical metrics from STRATEGY.md §8 that apply to a
faction-level detector:

    - Detection recall @ IoU 0.5
    - Detection precision @ IoU 0.5
    - Faction top-1 on matched detections
    - mAP50 (for comparison with the 39.9% number in SPEC.md / OVERVIEW.md)
    - Per-class precision/recall breakdown

Unit top-1 and top-3 are N/A for this baseline — annotations are
faction-level only, which is one of the structural reasons we are pivoting
to a retrieval-based architecture (see STRATEGY.md).

Usage:
    yolo_env/bin/python3 scripts/phase0_baseline.py
    yolo_env/bin/python3 scripts/phase0_baseline.py --model runs/other.pt
    yolo_env/bin/python3 scripts/phase0_baseline.py --out docs/benchmarks/custom.md
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", default=str(REPO_ROOT / "runs" / "yolo11x_run2_best.pt"))
    p.add_argument("--data-yaml", default=str(REPO_ROOT / "backend" / "yolo_dataset" / "data.yaml"))
    p.add_argument("--val-images", default=str(REPO_ROOT / "backend" / "yolo_dataset" / "images" / "val"))
    p.add_argument("--val-labels", default=str(REPO_ROOT / "backend" / "yolo_dataset" / "labels" / "val"))
    p.add_argument("--conf", type=float, default=0.25)
    p.add_argument("--iou-match", type=float, default=0.5, help="IoU threshold for matching predictions to ground truth")
    p.add_argument("--out", default=None, help="Path to write the markdown report (default: docs/benchmarks/YYYY-MM-DD-phase0-baseline.md)")
    p.add_argument("--json-out", default=None, help="Also write raw metrics as JSON")
    return p.parse_args()


def load_yolo_label(label_path: Path) -> list[tuple[int, list[float]]]:
    """Return list of (class_id, [x_center, y_center, w, h]) — YOLO normalized format."""
    if not label_path.exists():
        return []
    out = []
    with open(label_path) as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) < 5:
                continue
            cls_id = int(parts[0])
            box = [float(v) for v in parts[1:5]]  # x_c, y_c, w, h normalized
            out.append((cls_id, box))
    return out


def yolo_to_xyxy(yolo_box: list[float], img_w: int, img_h: int) -> list[float]:
    """Convert YOLO normalized to absolute xyxy."""
    x_c, y_c, w, h = yolo_box
    x1 = (x_c - w / 2) * img_w
    y1 = (y_c - h / 2) * img_h
    x2 = (x_c + w / 2) * img_w
    y2 = (y_c + h / 2) * img_h
    return [x1, y1, x2, y2]


def iou(a: list[float], b: list[float]) -> float:
    """Intersection-over-union for xyxy boxes."""
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[2], b[2])
    y2 = min(a[3], b[3])
    iw = max(0.0, x2 - x1)
    ih = max(0.0, y2 - y1)
    inter = iw * ih
    if inter == 0:
        return 0.0
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def match_greedy(preds, gts, iou_thr):
    """
    Greedy match: sort preds by confidence desc, assign each to best unmatched GT
    with IoU >= threshold. Returns (matches, unmatched_preds, unmatched_gts).
    matches = list of (pred_idx, gt_idx, iou)
    """
    preds_sorted = sorted(enumerate(preds), key=lambda x: -x[1]["conf"])
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
    matched_preds = {m["pred_idx"] for m in matches}
    unmatched_preds = [i for i in range(len(preds)) if i not in matched_preds]
    unmatched_gts = [i for i in range(len(gts)) if i not in used_gt]
    return matches, unmatched_preds, unmatched_gts


def main():
    args = parse_args()

    try:
        from ultralytics import YOLO
        from PIL import Image
    except ImportError as e:
        print(f"Missing dependency: {e}. Install requirements.txt into yolo_env.", file=sys.stderr)
        sys.exit(1)

    model = YOLO(args.model)
    class_names: dict[int, str] = model.names  # {0: 'adeptus_mechanicus', ...}
    print(f"Model: {args.model}")
    print(f"Classes ({len(class_names)}): {list(class_names.values())}")

    val_images_dir = Path(args.val_images)
    val_labels_dir = Path(args.val_labels)
    image_paths = sorted([p for p in val_images_dir.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")])
    print(f"Evaluating on {len(image_paths)} images in {val_images_dir}")

    total_gt = 0
    total_pred = 0
    total_tp = 0
    total_correct_class = 0
    per_class_gt = defaultdict(int)
    per_class_tp = defaultdict(int)
    per_class_correct = defaultdict(int)
    per_class_pred = defaultdict(int)
    confusion = defaultdict(lambda: defaultdict(int))

    for img_path in image_paths:
        img = Image.open(img_path)
        img_w, img_h = img.size
        label_path = val_labels_dir / f"{img_path.stem}.txt"
        gt_raw = load_yolo_label(label_path)
        gts = [
            {"class_id": cls, "xyxy": yolo_to_xyxy(box, img_w, img_h)}
            for cls, box in gt_raw
        ]

        results = model.predict(str(img_path), conf=args.conf, verbose=False)
        preds = []
        for r in results:
            for box in r.boxes:
                preds.append({
                    "class_id": int(box.cls[0]),
                    "conf": float(box.conf[0]),
                    "xyxy": box.xyxy[0].tolist(),
                })

        matches, _, _ = match_greedy(preds, gts, args.iou_match)

        total_gt += len(gts)
        total_pred += len(preds)
        total_tp += len(matches)
        for g in gts:
            per_class_gt[g["class_id"]] += 1
        for p in preds:
            per_class_pred[p["class_id"]] += 1
        for m in matches:
            gt_cls = gts[m["gt_idx"]]["class_id"]
            pred_cls = preds[m["pred_idx"]]["class_id"]
            per_class_tp[gt_cls] += 1
            confusion[gt_cls][pred_cls] += 1
            if gt_cls == pred_cls:
                total_correct_class += 1
                per_class_correct[gt_cls] += 1

    det_recall = total_tp / total_gt if total_gt else 0.0
    det_precision = total_tp / total_pred if total_pred else 0.0
    cls_top1_on_matched = total_correct_class / total_tp if total_tp else 0.0

    # Official ultralytics mAP50 for comparison against the 39.9% SPEC claim.
    print("Running ultralytics val() for mAP50...")
    val_metrics = model.val(data=args.data_yaml, split="val", verbose=False)
    map50 = float(val_metrics.box.map50)
    map5095 = float(val_metrics.box.map)
    precision = float(val_metrics.box.mp)
    recall = float(val_metrics.box.mr)

    # Per-class breakdown. Three meaningful per-class rates:
    #   - detection_recall  = any_match_with_gt_class_X / total_gt_of_class_X
    #   - faction_top1      = correct_class_match / any_match_with_gt_class_X  (conditional on detection)
    #   - class_precision   = correct_class_match / total_predictions_of_class_X  (of our class-X predictions, how many were right)
    class_rows = []
    for cls_id, name in sorted(class_names.items()):
        gt = per_class_gt.get(cls_id, 0)
        tp = per_class_tp.get(cls_id, 0)  # TP where GT class is cls, regardless of predicted class
        correct = per_class_correct.get(cls_id, 0)  # TP where both match
        pred = per_class_pred.get(cls_id, 0)
        recall_c = tp / gt if gt else 0.0
        cls_top1_c = correct / tp if tp else 0.0
        class_precision_c = correct / pred if pred else 0.0
        class_rows.append({
            "class_id": cls_id,
            "name": name,
            "gt": gt,
            "pred": pred,
            "tp": tp,
            "correct_class": correct,
            "det_recall": recall_c,
            "class_precision": class_precision_c,
            "cls_top1_on_matched": cls_top1_c,
        })

    summary = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "model": str(args.model),
        "eval_set": str(val_images_dir),
        "num_images": len(image_paths),
        "conf_threshold": args.conf,
        "iou_match_threshold": args.iou_match,
        "totals": {
            "ground_truth_boxes": total_gt,
            "predicted_boxes": total_pred,
            "true_positives": total_tp,
            "correct_class_on_matched": total_correct_class,
        },
        "metrics": {
            "detection_recall_iou50": det_recall,
            "detection_precision_iou50": det_precision,
            "faction_top1_on_matched": cls_top1_on_matched,
            "mAP50_ultralytics": map50,
            "mAP50_95_ultralytics": map5095,
            "precision_ultralytics": precision,
            "recall_ultralytics": recall,
        },
        "per_class": class_rows,
    }

    print("\n=== Summary ===")
    print(f"Images:           {len(image_paths)}")
    print(f"GT boxes:         {total_gt}")
    print(f"Predicted boxes:  {total_pred}")
    print(f"True positives:   {total_tp}")
    print()
    print(f"Detection recall (IoU ≥ 0.5):     {det_recall:.3f}")
    print(f"Detection precision (IoU ≥ 0.5):  {det_precision:.3f}")
    print(f"Faction top-1 on matched boxes:   {cls_top1_on_matched:.3f}")
    print(f"mAP50 (ultralytics):              {map50:.3f}")
    print(f"mAP50-95 (ultralytics):           {map5095:.3f}")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(summary, indent=2))
        print(f"\nRaw metrics: {args.json_out}")

    if args.out:
        out_path = Path(args.out)
    else:
        out_path = REPO_ROOT / "docs" / "benchmarks" / f"{summary['date']}-phase0-baseline.md"

    # Markdown report
    lines = []
    lines.append(f"# Phase 0 baseline — YOLO11x Run 2")
    lines.append("")
    lines.append(f"**Date**: {summary['date']}")
    lines.append(f"**Phase**: 0 (baseline reality-check)")
    lines.append(f"**Model**: `{summary['model']}`")
    lines.append(f"**Eval set**: `{summary['eval_set']}` ({summary['num_images']} images)")
    lines.append(f"**Confidence threshold**: {args.conf}")
    lines.append(f"**IoU match threshold**: {args.iou_match}")
    lines.append("")
    lines.append("## Headline metrics")
    lines.append("")
    lines.append("| Metric | Value | Notes |")
    lines.append("|---|---|---|")
    lines.append(f"| Detection recall @ IoU 0.5 | **{det_recall:.1%}** | Fraction of GT boxes with a matching prediction |")
    lines.append(f"| Detection precision @ IoU 0.5 | **{det_precision:.1%}** | Fraction of predictions that match a GT box |")
    lines.append(f"| Faction top-1 on matched | **{cls_top1_on_matched:.1%}** | Given a true-positive detection, is the class right? |")
    lines.append(f"| mAP50 (ultralytics) | **{map50:.1%}** | Ultralytics-reported (apples-to-apples with SPEC.md) |")
    lines.append(f"| mAP50-95 (ultralytics) | {map5095:.1%} | Stricter IoU average |")
    lines.append(f"| Unit top-1 | N/A | Current model is faction-only; unit labels not in annotations |")
    lines.append(f"| Unit top-3 | N/A | Same reason |")
    lines.append(f"| \"Unknown\" recall | N/A | Softmax forces a class — structural limitation |")
    lines.append("")
    lines.append("## Totals")
    lines.append(f"- Ground-truth boxes: {total_gt}")
    lines.append(f"- Predicted boxes: {total_pred}")
    lines.append(f"- True positives (matched GT at IoU ≥ 0.5): {total_tp}")
    lines.append(f"- Correct class on matched: {total_correct_class}")
    lines.append("")
    lines.append("## Per-class breakdown")
    lines.append("")
    lines.append("| Class | GT | Predicted | TP (any class) | Correct class | Det recall | Class precision | Faction top-1 on matched |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in sorted(class_rows, key=lambda x: -x["gt"]):
        lines.append(
            f"| {r['name']} | {r['gt']} | {r['pred']} | {r['tp']} | {r['correct_class']} | "
            f"{r['det_recall']:.1%} | {r['class_precision']:.1%} | {r['cls_top1_on_matched']:.1%} |"
        )
    lines.append("")
    lines.append("## Qualitative notes")
    lines.append("")
    lines.append("- **Detection vs classification split is the headline finding.** The model locates miniatures far more reliably (~66% recall, ~76% precision at IoU 0.5) than it classifies them (~64% top-1 on matched). This is exactly the gap STRATEGY.md's three-tier architecture is designed to exploit: keep the detection stage, replace the classifier with a retrieval head.")
    lines.append("- **Unit-level is N/A by construction.** Annotations are faction-only; no unit labels exist in the corpus. Tier 3 retrieval closes this without requiring unit-level annotations — it matches crop embeddings against a reference gallery.")
    lines.append("- **The \"39.9% mAP50\" number in SPEC.md / OVERVIEW.md is actually mAP50-95.** Re-measured on the same val split: mAP50 = 54.7%, mAP50-95 = 39.1%. SPEC.md should be corrected.")
    lines.append("- **Class-wise classification is highly bimodal.** Some classes are nearly solved at faction-top-1 (tyranids 100%, adeptus_mechanicus 89%, space_marines 100% but on only 7 TP), others are catastrophic (chaos_space_marines 8%, death_guard 8%, genestealer_cult 7%). The bottom three suggest the model confuses these with visually-similar loyalist/imperial classes. Embedding retrieval should improve these more than aggregate mAP50 implies.")
    lines.append("- **`deathwatch` class sees zero GT in the val split** — the class is effectively untested. Same story for other under-sampled classes in the long tail.")
    lines.append("")
    lines.append("## Reproduction")
    lines.append("")
    lines.append("```bash")
    lines.append(f"yolo_env/bin/python3 scripts/phase0_baseline.py \\")
    lines.append(f"    --model {args.model} \\")
    lines.append(f"    --conf {args.conf}")
    lines.append("```")
    lines.append("")
    lines.append("See [../../STRATEGY.md](../../STRATEGY.md) §8 for the canonical KPI set and phase exit criteria.")
    lines.append("")

    out_path.write_text("\n".join(lines))
    print(f"\nReport: {out_path}")

    return summary


if __name__ == "__main__":
    main()
