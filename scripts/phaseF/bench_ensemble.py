"""Phase C frozen-eval benchmark for the Phase F1 detector ensemble.

Runs configured detectors (individually + the ensemble) on the 200
images in `data/scene_benchmark/eval_200.json` and scores each against
ground truth from `backend/training_data_annotations/`.

Metrics reported per detector:
    - recall @ IoU in {0.3, 0.5, 0.7}
    - precision @ IoU 0.5
    - mean detections per image
    - per-density-bucket breakdown (single / sparse / medium / crowded)
    - mAP@50 via standard PR-curve integration

Usage:
    fiftyone_env/bin/python scripts/phaseF/bench_ensemble.py \\
        --detectors sam3 sam3_refined \\
        --out docs/benchmarks/<date>-phaseF1.md

Detectors: sam3, sam3_refined (SAM 3 + SAM 2 mask refinement). NOTE: this benches
against the legacy Phase C eval_200 GT; the trusted eval is gold_v2 via
scripts/phaseF/score_gold.py.
"""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

EVAL_MANIFEST = Path("data/scene_benchmark/eval_200.json")
ANN_DIR = Path("backend/training_data_annotations")


# --- IoU-based metric helpers ----------------------------------------


def _xywh_to_xyxy(b: tuple[float, float, float, float]) -> np.ndarray:
    x, y, w, h = b
    return np.array([x, y, x + w, y + h], dtype=np.float32)


def _iou(a: np.ndarray, b: np.ndarray) -> float:
    x0 = max(a[0], b[0]); y0 = max(a[1], b[1])
    x1 = min(a[2], b[2]); y1 = min(a[3], b[3])
    inter = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    union = area_a + area_b - inter
    return float(inter / union) if union > 0 else 0.0


def greedy_match(gt: list[np.ndarray], pred: list[tuple[np.ndarray, float]],
                 iou_threshold: float) -> tuple[int, int, int]:
    """Return (true_positives, false_positives, false_negatives) @ IoU."""
    used_gt = [False] * len(gt)
    pred_sorted = sorted(pred, key=lambda p: -p[1])  # high confidence first
    tp = fp = 0
    for p_box, _ in pred_sorted:
        best = -1
        best_iou = iou_threshold
        for i, g in enumerate(gt):
            if used_gt[i]:
                continue
            v = _iou(p_box, g)
            if v >= best_iou:
                best = i
                best_iou = v
        if best >= 0:
            used_gt[best] = True
            tp += 1
        else:
            fp += 1
    fn = len(gt) - tp
    return tp, fp, fn


def ap50_voc(gt_by_image: dict[str, list[np.ndarray]],
             pred_by_image: dict[str, list[tuple[np.ndarray, float]]]) -> float:
    """VOC-style mAP@50 for the single 'miniature' class.

    Accumulates per-prediction TP/FP across all images (sorted by
    confidence), then integrates the precision-recall curve."""
    total_gt = sum(len(g) for g in gt_by_image.values())
    if total_gt == 0:
        return 0.0
    entries: list[tuple[float, int]] = []  # (score, is_tp)
    for img_id, preds in pred_by_image.items():
        gt = gt_by_image.get(img_id, [])
        used = [False] * len(gt)
        for p_box, p_score in sorted(preds, key=lambda x: -x[1]):
            best = -1; best_iou = 0.5
            for i, g in enumerate(gt):
                if used[i]:
                    continue
                v = _iou(p_box, g)
                if v >= best_iou:
                    best = i; best_iou = v
            if best >= 0:
                used[best] = True
                entries.append((p_score, 1))
            else:
                entries.append((p_score, 0))
    entries.sort(key=lambda e: -e[0])
    tp_running = fp_running = 0
    precisions: list[float] = []; recalls: list[float] = []
    for _, is_tp in entries:
        if is_tp: tp_running += 1
        else:     fp_running += 1
        precisions.append(tp_running / max(1, tp_running + fp_running))
        recalls.append(tp_running / total_gt)
    if not precisions:
        return 0.0
    # VOC 11-point interpolation.
    ap = 0.0
    for r in np.linspace(0.0, 1.0, 11):
        valid = [p for p, rr in zip(precisions, recalls) if rr >= r]
        ap += (max(valid) if valid else 0.0) / 11
    return ap


# --- Manifest / ground-truth loaders ---------------------------------


@dataclass(frozen=True)
class EvalEntry:
    image_id: str
    image_path: Path
    bucket: str
    gt_boxes: list[np.ndarray]  # xyxy


def _resolve_image_path(rec: dict) -> Path | None:
    """Return an existing local path for the evaluation image, whether
    the manifest stores the recorded absolute path (local run) or we
    need to reconstruct a repo-relative path (Colab bundle run where
    the absolute prefix doesn't match)."""
    p = Path(rec["imagePath"])
    if p.exists():
        return p
    # Preferred: rebuild from the explicit faction/source fields the
    # manifest records.
    faction, source = rec.get("faction"), rec.get("source")
    if faction and source:
        rel = Path("backend") / "training_data" / faction / source / p.name
        if rel.exists():
            return rel
    # Last-ditch: take the trailing 5 path components — that's
    # `backend/training_data/<faction>/<source>/<filename>` for
    # canonical paths.
    parts = p.parts
    if len(parts) >= 5:
        rel = Path(*parts[-5:])
        if rel.exists():
            return rel
    return None


def load_eval() -> list[EvalEntry]:
    data = json.loads(EVAL_MANIFEST.read_text())
    out: list[EvalEntry] = []
    for rec in data.get("images", []):
        img_id = rec["imageId"]
        ann_path = ANN_DIR / f"{img_id}.json"
        if not ann_path.exists():
            continue
        try:
            ann = json.loads(ann_path.read_text())
        except Exception:
            continue
        if ann.get("pseudoLabelled"):
            # Shouldn't happen for Phase C entries — they were selected
            # from the gold corpus — but guard anyway.
            continue
        img_path = _resolve_image_path(rec)
        if img_path is None:
            # Image file genuinely missing — skip with warning.
            print(f"  WARN: {img_id} image not found; skipping")
            continue
        gt = []
        for a in ann.get("annotations", []):
            b = a.get("modelBbox") or {}
            x, y, w, h = b.get("x"), b.get("y"), b.get("width"), b.get("height")
            if not all(isinstance(v, (int, float)) for v in (x, y, w, h)):
                continue
            gt.append(_xywh_to_xyxy((x, y, w, h)))
        out.append(EvalEntry(
            image_id=img_id,
            image_path=img_path,
            bucket=rec["bucket"],
            gt_boxes=gt,
        ))
    return out


# --- Detector factories ---------------------------------------------


def build_detector(name: str):
    """Return a (predict_fn, tag) pair. predict_fn: path → list[(xyxy, score)].

    The pipeline is SAM 3 only (locked 2026-04-25); the historical DINO-X /
    OWLv2 / ensemble-voting factories were removed 2026-06-05."""
    if name == "sam3":
        from photoanalyzer.detect.ensemble.sam3 import Sam3Detector
        det = Sam3Detector()
        def _pred(p):
            dd = det.predict(p)
            return [(_xywh_to_xyxy(d.bbox), d.confidence) for d in dd]
        return _pred, name

    if name == "sam3_refined":
        # SAM 3 detection + SAM 2 mask-to-bbox refinement.
        from photoanalyzer.detect.ensemble.sam3 import Sam3Detector
        from photoanalyzer.detect.ensemble.sam2_refine import SAM2Refiner
        det = Sam3Detector()
        refiner = SAM2Refiner()
        def _pred(p):
            raw = det.predict(p)
            if not raw:
                return []
            refined = refiner.refine(p, raw)
            return [(_xywh_to_xyxy(rd.refined_bbox), rd.original.confidence) for rd in refined]
        return _pred, name

    raise ValueError(f"Unknown detector: {name!r} (options: sam3, sam3_refined)")


# --- Scoring & report --------------------------------------------------


def score_detector(det_name: str, eval_set: list[EvalEntry]) -> dict:
    pred_fn, _ = build_detector(det_name)
    gt_by_img: dict[str, list[np.ndarray]] = {}
    pred_by_img: dict[str, list[tuple[np.ndarray, float]]] = {}
    per_bucket: dict[str, dict[str, int]] = {}

    t0 = time.monotonic()
    for entry in eval_set:
        gt_by_img[entry.image_id] = entry.gt_boxes
        try:
            preds = pred_fn(entry.image_path)
        except Exception as e:
            print(f"  [{det_name}] {entry.image_id}: {e}")
            preds = []
        pred_by_img[entry.image_id] = preds
        # Per-bucket TP/FP/FN @ IoU 0.5 for recall/precision breakdown.
        b = per_bucket.setdefault(entry.bucket, {"tp": 0, "fp": 0, "fn": 0, "n_img": 0, "n_pred": 0, "n_gt": 0})
        tp, fp, fn = greedy_match(entry.gt_boxes, preds, 0.5)
        b["tp"] += tp; b["fp"] += fp; b["fn"] += fn
        b["n_img"] += 1
        b["n_pred"] += len(preds)
        b["n_gt"] += len(entry.gt_boxes)

    elapsed = time.monotonic() - t0

    # Aggregate metrics at IoU 0.5.
    agg = {"tp": 0, "fp": 0, "fn": 0}
    for b in per_bucket.values():
        for k in agg:
            agg[k] += b[k]
    prec = agg["tp"] / max(1, agg["tp"] + agg["fp"])
    recall = agg["tp"] / max(1, agg["tp"] + agg["fn"])

    # Recall at multiple IoUs.
    recalls: dict[float, float] = {}
    for thr in (0.3, 0.5, 0.7):
        tp_total = fn_total = 0
        for entry in eval_set:
            preds = pred_by_img.get(entry.image_id, [])
            tp, fp, fn = greedy_match(entry.gt_boxes, preds, thr)
            tp_total += tp; fn_total += fn
        recalls[thr] = tp_total / max(1, tp_total + fn_total)

    # mAP@50
    map50 = ap50_voc(gt_by_img, pred_by_img)

    return {
        "detector": det_name,
        "elapsed_sec": round(elapsed, 1),
        "recall_iou0.3": round(recalls[0.3], 4),
        "recall_iou0.5": round(recalls[0.5], 4),
        "recall_iou0.7": round(recalls[0.7], 4),
        "precision_iou0.5": round(prec, 4),
        "mAP50": round(map50, 4),
        "n_images": len(eval_set),
        "n_gt_boxes": sum(b["n_gt"] for b in per_bucket.values()),
        "n_pred_boxes": sum(b["n_pred"] for b in per_bucket.values()),
        "per_bucket": {
            name: {
                "recall_iou0.5": round(b["tp"] / max(1, b["tp"] + b["fn"]), 4),
                "precision_iou0.5": round(b["tp"] / max(1, b["tp"] + b["fp"]), 4),
                "n_images": b["n_img"],
                "n_gt": b["n_gt"],
                "n_pred": b["n_pred"],
            }
            for name, b in per_bucket.items()
        },
    }


def render_report(results: list[dict], out_path: Path) -> None:
    lines: list[str] = []
    lines.append(f"# Phase F1 ensemble benchmark — {time.strftime('%Y-%m-%d')}")
    lines.append("")
    lines.append(f"Eval set: `data/scene_benchmark/eval_200.json` "
                 f"({results[0]['n_images']} images, "
                 f"{results[0]['n_gt_boxes']} GT boxes).")
    lines.append("")
    lines.append("## Aggregate (IoU 0.5)")
    lines.append("")
    lines.append("| Detector | mAP@50 | Recall (0.3/0.5/0.7) | Precision | Pred / GT | Time (s) |")
    lines.append("|---|---|---|---|---|---|")
    for r in results:
        lines.append(
            f"| {r['detector']} | {r['mAP50']:.3f} | "
            f"{r['recall_iou0.3']:.2f}/{r['recall_iou0.5']:.2f}/{r['recall_iou0.7']:.2f} | "
            f"{r['precision_iou0.5']:.2f} | "
            f"{r['n_pred_boxes']} / {r['n_gt_boxes']} | "
            f"{r['elapsed_sec']} |"
        )
    lines.append("")
    lines.append("## Per-density bucket (IoU 0.5)")
    lines.append("")
    buckets = ["single", "sparse", "medium", "crowded"]
    lines.append("| Detector | " + " | ".join(f"{b} R/P" for b in buckets) + " |")
    lines.append("|---" * (len(buckets) + 1) + "|")
    for r in results:
        row = [r["detector"]]
        for b in buckets:
            pb = r["per_bucket"].get(b)
            if pb is None:
                row.append("—")
            else:
                row.append(f"{pb['recall_iou0.5']:.2f}/{pb['precision_iou0.5']:.2f}")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    out_path.write_text("\n".join(lines))


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--detectors", nargs="+",
        default=["sam3", "sam3_refined"],
        help="Detector names to score. Options: sam3, sam3_refined.",
    )
    ap.add_argument(
        "--out", type=Path,
        default=Path(f"docs/benchmarks/{time.strftime('%Y-%m-%d')}-phaseF1-ensemble.md"),
        help="Markdown report output path.",
    )
    ap.add_argument(
        "--json-out", type=Path, default=None,
        help="Optional raw JSON results dump.",
    )
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    print("Loading eval set…")
    eval_set = load_eval()
    print(f"  {len(eval_set)} images, "
          f"{sum(len(e.gt_boxes) for e in eval_set)} GT boxes")

    results: list[dict] = []
    for name in args.detectors:
        print(f"Running {name}…")
        try:
            r = score_detector(name, eval_set)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"  {name} failed: {e}")
            continue
        results.append(r)
        print(f"  {name}: mAP@50={r['mAP50']:.3f} "
              f"recall@0.5={r['recall_iou0.5']:.3f} "
              f"precision@0.5={r['precision_iou0.5']:.3f} "
              f"({r['elapsed_sec']:.1f}s)")

    if not results:
        print("No detectors produced results.")
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    render_report(results, args.out)
    print(f"\nReport: {args.out}")
    if args.json_out:
        args.json_out.write_text(json.dumps(results, indent=2))
        print(f"Raw JSON: {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
