"""Score a class-agnostic detector against the frozen gold set (`gold_v2.json`).

Why this module exists, beyond the generic `scene.py`:

1. **Count error is the headline, sliced by scene density.** Aggregate recall
   rewards a detector that nails singles and *merges adjacent models* — the
   product-fatal failure on a crowded table. So the primary metric is
   per-image count-MAE bucketed single / sparse / medium / crowded.
2. **Per-faction recall, class-agnostic.** The detector predicts only
   "miniature"; recall is sliced by the *ground-truth* box's faction so we get
   a provisional per-faction read. Small-n factions (e.g. Death Guard, n≈40)
   have wide CIs — treat as noisy.
3. **IoU-threshold sweep as a box-convention diagnostic.** Gold boxes are
   model + integral base (LABELING_GUIDE §1); SAM-derived boxes are mask-tight
   and clip the base. A large recall@0.3 vs recall@0.5 gap is the signature of
   a *localization/convention* mismatch, not a detection failure — see
   `boxconv.py` for the fix.

Gold boxes are stored normalized (`bbox_xywh_norm`); predictions
(`data/pseudo_labels/boxes/<id>.json`) are pixel `xywh`. Everything is
converted to pixels here so IoU is computed in true image space (IoU is *not*
invariant to the anisotropic squash of normalized coords).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from . import metrics
from .metrics import Bbox

# Density buckets — match the frozen Phase C convention (data/scene_benchmark)
# so gold and eval_200 numbers stay comparable. n = ground-truth box count.
DENSITY_ORDER = ("single", "sparse", "medium", "crowded")


def density_bucket(n: int) -> str:
    if n <= 1:
        return "single"
    if n <= 4:
        return "sparse"
    if n <= 10:
        return "medium"
    return "crowded"


# ── gold loading ───────────────────────────────────────────────────────────
@dataclass(frozen=True)
class GoldImage:
    basename: str
    filepath: str
    faction_v1: str
    source: str
    width: int
    height: int
    # boxes in PIXEL xywh, paired with their faction label
    boxes: tuple[Bbox, ...]
    labels: tuple[str, ...]

    @property
    def n_boxes(self) -> int:
        return len(self.boxes)

    @property
    def bucket(self) -> str:
        return density_bucket(self.n_boxes)


def _image_dims(filepath: str) -> tuple[int, int]:
    from PIL import Image

    with Image.open(filepath) as im:
        return int(im.width), int(im.height)


def load_gold(
    gold_path: str | Path = "data/gold/gold_v2.json",
    dims_cache: str | Path | None = "data/gold/gold_v2_dims.json",
) -> list[GoldImage]:
    """Load gold images with boxes denormalized to pixels.

    Image dimensions are read once (PIL) and cached to `dims_cache` keyed by
    basename, so repeated scoring runs don't re-open 89 files. Pass
    `dims_cache=None` to disable caching.
    """
    gold_path = Path(gold_path)
    data = json.loads(gold_path.read_text())

    cache: dict[str, list[int]] = {}
    cache_path = Path(dims_cache) if dims_cache else None
    if cache_path and cache_path.exists():
        cache = json.loads(cache_path.read_text())

    out: list[GoldImage] = []
    dirty = False
    for im in data["images"]:
        bn = im["basename"]
        if bn in cache:
            w, h = cache[bn]
        else:
            w, h = _image_dims(im["filepath"])
            cache[bn] = [w, h]
            dirty = True
        boxes, labels = [], []
        for b in im["boxes"]:
            x, y, bw, bh = b["bbox_xywh_norm"]
            boxes.append((x * w, y * h, bw * w, bh * h))
            labels.append(b["label"])
        out.append(GoldImage(
            basename=bn, filepath=im["filepath"], faction_v1=im["faction_v1"],
            source=im["source"], width=w, height=h,
            boxes=tuple(boxes), labels=tuple(labels),
        ))
    if dirty and cache_path:
        cache_path.write_text(json.dumps(cache, indent=2))
    return out


# ── prediction loading ─────────────────────────────────────────────────────
def load_predictions(
    boxes_dir: str | Path,
    score_thresh: float = 0.0,
) -> dict[str, list[Bbox]]:
    """Load per-image pseudo-label JSONs → {basename: [pixel xywh, ...]}.

    Expects the Phase F1 schema: {"boxes": [{"xywh": [x,y,w,h], "score": f}, ...]}.
    `score_thresh` drops boxes below the given detector confidence.
    """
    boxes_dir = Path(boxes_dir)
    preds: dict[str, list[Bbox]] = {}
    for jf in sorted(boxes_dir.glob("*.json")):
        rec = json.loads(jf.read_text())
        path = rec.get("imagePath") or rec.get("filepath") or jf.stem
        bn = Path(path).name
        boxes = [
            tuple(b["xywh"]) for b in rec.get("boxes", [])
            if b.get("score", 1.0) >= score_thresh
        ]
        preds[bn] = boxes
    return preds


# ── scoring ────────────────────────────────────────────────────────────────
@dataclass
class Slice:
    """A recall/precision/count tally over some subset of images."""
    n_images: int = 0
    n_gt: int = 0
    n_pred: int = 0
    tp: int = 0
    abs_count_err: int = 0          # Σ |pred_count − gt_count|
    within1: int = 0               # images where |pred − gt| ≤ 1

    @property
    def recall(self) -> float:
        return self.tp / self.n_gt if self.n_gt else 0.0

    @property
    def precision(self) -> float:
        return self.tp / self.n_pred if self.n_pred else 0.0

    @property
    def count_mae(self) -> float:
        return self.abs_count_err / self.n_images if self.n_images else 0.0

    @property
    def pct_within1(self) -> float:
        return self.within1 / self.n_images if self.n_images else 0.0

    def as_dict(self) -> dict:
        return {
            "n_images": self.n_images, "n_gt": self.n_gt, "n_pred": self.n_pred,
            "recall": round(self.recall, 4), "precision": round(self.precision, 4),
            "count_mae": round(self.count_mae, 3),
            "pct_within1": round(self.pct_within1, 4),
        }


@dataclass
class GoldReport:
    iou_threshold: float
    overall: Slice
    by_density: dict[str, Slice] = field(default_factory=dict)
    by_faction: dict[str, Slice] = field(default_factory=dict)
    recall_at_iou: dict[float, float] = field(default_factory=dict)
    missing_predictions: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "iou_threshold": self.iou_threshold,
            "overall": self.overall.as_dict(),
            "by_density": {b: self.by_density[b].as_dict()
                           for b in DENSITY_ORDER if b in self.by_density},
            "by_faction": {f: self.by_faction[f].as_dict()
                           for f in sorted(self.by_faction)},
            "recall_at_iou": {str(k): round(v, 4)
                              for k, v in sorted(self.recall_at_iou.items())},
            "missing_predictions": self.missing_predictions,
        }


def _recall_only(gold: Sequence[GoldImage],
                 preds: dict[str, list[Bbox]], thr: float) -> float:
    tp = gt = 0
    for g in gold:
        p = preds.get(g.basename, [])
        assigns = metrics.match_detections_to_gt(g.boxes, p, thr)
        tp += sum(1 for a in assigns if a is not None)
        gt += len(g.boxes)
    return tp / gt if gt else 0.0


def score_gold(
    gold: Sequence[GoldImage],
    preds: dict[str, list[Bbox]],
    iou_threshold: float = 0.5,
    iou_sweep: Sequence[float] = (0.3, 0.5, 0.7),
) -> GoldReport:
    """Score predictions against gold: count-MAE × density, per-faction recall,
    and a recall@IoU sweep for the box-convention diagnostic."""
    overall = Slice()
    by_density: dict[str, Slice] = {b: Slice() for b in DENSITY_ORDER}
    by_faction: dict[str, Slice] = {}
    missing: list[str] = []

    for g in gold:
        p = preds.get(g.basename)
        if p is None:
            missing.append(g.basename)
            p = []
        assigns = metrics.match_detections_to_gt(g.boxes, p, iou_threshold)
        img_tp = sum(1 for a in assigns if a is not None)
        count_err = abs(len(p) - g.n_boxes)

        for sl in (overall, by_density[g.bucket]):
            sl.n_images += 1
            sl.n_gt += g.n_boxes
            sl.n_pred += len(p)
            sl.tp += img_tp
            sl.abs_count_err += count_err
            sl.within1 += int(count_err <= 1)

        # per-faction recall — slice GT boxes by their own label (class-agnostic
        # detector, so "precision" per faction is undefined; recall only).
        for matched, label in zip(assigns, g.labels):
            fs = by_faction.setdefault(label, Slice())
            fs.n_gt += 1
            fs.tp += int(matched is not None)

    recall_at_iou = {thr: _recall_only(gold, preds, thr) for thr in iou_sweep}
    return GoldReport(
        iou_threshold=iou_threshold, overall=overall,
        by_density=by_density, by_faction=by_faction,
        recall_at_iou=recall_at_iou, missing_predictions=missing,
    )


def format_report(report: GoldReport) -> str:
    """Human-readable summary for the CLI / benchmark markdown."""
    o = report.overall
    lines = [
        f"Gold eval @ IoU {report.iou_threshold}  "
        f"({o.n_images} imgs, {o.n_gt} boxes)",
        f"  recall {o.recall:.3f}  precision {o.precision:.3f}  "
        f"count-MAE {o.count_mae:.2f}  within±1 {o.pct_within1:.1%}",
        "",
        "  by density        imgs   gt   recall  count-MAE  within±1",
    ]
    for b in DENSITY_ORDER:
        s = report.by_density.get(b)
        if not s or s.n_images == 0:
            continue
        flag = "  ⚠ thin" if s.n_images < 10 else ""
        lines.append(f"    {b:8}       {s.n_images:5} {s.n_gt:5}   "
                     f"{s.recall:.3f}    {s.count_mae:6.2f}    "
                     f"{s.pct_within1:5.1%}{flag}")
    lines += ["", "  by faction        gt   recall"]
    for f in sorted(report.by_faction):
        s = report.by_faction[f]
        flag = "  ⚠ wide CI" if s.n_gt < 50 else ""
        lines.append(f"    {f:16} {s.n_gt:4}   {s.recall:.3f}{flag}")
    lines += ["", "  recall@IoU sweep (box-convention diagnostic):"]
    lines.append("    " + "  ".join(f"@{thr}={r:.3f}"
                                    for thr, r in sorted(report.recall_at_iou.items())))
    if report.missing_predictions:
        lines.append(f"\n  ⚠ {len(report.missing_predictions)} gold images had "
                     f"no prediction file (counted as full miss).")
    return "\n".join(lines)
