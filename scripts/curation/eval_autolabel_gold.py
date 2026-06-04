"""Baseline auto-label eval: Grounding-DINO 'miniature' vs the gold set (Plan D2).

CPU stand-in for SAM 3 (which needs a GPU/Colab). Runs the open text-prompt detector
Grounding-DINO with the concept 'miniature' on the 35 frozen gold images and scores its
boxes against the 124 hand-labeled boxes — CLASS-AGNOSTIC (every gold box, any faction,
counts as a detection target, exactly like Tier 1).

Metrics (the §D2 numbers): detection precision / recall @ IoU>=0.5, and per-image count error.

Usage:
  fiftyone_env/bin/python scripts/curation/eval_autolabel_gold.py [--prompt "miniature."] [--box-thresh 0.3]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from PIL import Image
from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor

REPO = Path(__file__).resolve().parents[2]
GOLD = REPO / "data" / "gold" / "gold_v1.json"
MODEL_ID = "IDEA-Research/grounding-dino-tiny"


def iou_xywh(a, b):
    ax, ay, aw, ah = a; bx, by, bw, bh = b
    ix1, iy1 = max(ax, bx), max(ay, by)
    ix2, iy2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", default="miniature.")
    ap.add_argument("--box-thresh", type=float, default=0.3)
    ap.add_argument("--text-thresh", type=float, default=0.25)
    ap.add_argument("--iou", type=float, default=0.5)
    args = ap.parse_args()

    gold = json.loads(GOLD.read_text())["images"]
    proc = AutoProcessor.from_pretrained(MODEL_ID)
    model = AutoModelForZeroShotObjectDetection.from_pretrained(MODEL_ID).eval()

    TP = FP = FN = 0
    count_err = []
    print(f"running Grounding-DINO '{args.prompt}' on {len(gold)} gold images (CPU)...")
    for i, rec in enumerate(gold, 1):
        im = Image.open(rec["filepath"]).convert("RGB")
        W, H = im.size
        inputs = proc(images=im, text=args.prompt, return_tensors="pt")
        with torch.no_grad():
            out = model(**inputs)
        res = proc.post_process_grounded_object_detection(
            out, inputs.input_ids, box_threshold=args.box_thresh,
            text_threshold=args.text_thresh, target_sizes=[(H, W)])[0]
        # predicted boxes -> normalized xywh
        preds = []
        for (x1, y1, x2, y2) in res["boxes"].tolist():
            preds.append([x1 / W, y1 / H, (x2 - x1) / W, (y2 - y1) / H])
        gts = [b["bbox_xywh_norm"] for b in rec["boxes"]]
        count_err.append(len(preds) - len(gts))
        # greedy IoU match
        matched = set()
        for p in preds:
            best, bj = args.iou, -1
            for j, g in enumerate(gts):
                if j in matched:
                    continue
                v = iou_xywh(p, g)
                if v >= best:
                    best, bj = v, j
            if bj >= 0:
                matched.add(bj); TP += 1
            else:
                FP += 1
        FN += len(gts) - len(matched)
        if i % 10 == 0:
            print(f"  {i}/{len(gold)}")

    prec = TP / (TP + FP) if TP + FP else 0.0
    rec = TP / (TP + FN) if TP + FN else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    mae = sum(abs(c) for c in count_err) / len(count_err)
    bias = sum(count_err) / len(count_err)
    print(f"\n=== AUTO-LABEL BASELINE (Grounding-DINO '{args.prompt}', IoU>={args.iou}) ===")
    print(f"  images: {len(gold)} | gold boxes: {TP+FN} | predicted: {TP+FP}")
    print(f"  precision: {prec:.3f}  recall: {rec:.3f}  F1: {f1:.3f}")
    print(f"  count MAE/img: {mae:.2f}  (bias {bias:+.2f})")
    print(f"  TP={TP} FP={FP} FN={FN}")
    print(f"\n  Plan D2 exit bar: detection recall >= ~0.90. SAM 3 (Colab) should beat this.")


if __name__ == "__main__":
    main()
