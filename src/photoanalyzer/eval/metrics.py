"""Metric primitives for crop-level and scene-level benchmarks.

These functions are pure — no model, no I/O. `scene.py` composes them into
pipeline-level evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence


# ── bbox helpers ───────────────────────────────────────────────────────────
Bbox = tuple[float, float, float, float]  # (x, y, w, h) in image pixels


def iou(a: Bbox, b: Bbox) -> float:
    """Intersection-over-Union of two (x, y, w, h) boxes.

    Returns 0 if either box is degenerate or they do not overlap."""
    ax0, ay0, aw, ah = a
    bx0, by0, bw, bh = b
    if aw <= 0 or ah <= 0 or bw <= 0 or bh <= 0:
        return 0.0
    ax1, ay1 = ax0 + aw, ay0 + ah
    bx1, by1 = bx0 + bw, by0 + bh

    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    iw = max(0.0, ix1 - ix0)
    ih = max(0.0, iy1 - iy0)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def match_detections_to_gt(
    gt_boxes: Sequence[Bbox],
    pred_boxes: Sequence[Bbox],
    iou_threshold: float = 0.5,
) -> list[int | None]:
    """Greedy one-to-one matching: for each ground-truth box, return the
    index of the best-IoU predicted box (>= threshold), or None if no match.

    Each prediction is used at most once; if two GT boxes want the same pred,
    the one with the higher IoU wins."""
    if not gt_boxes:
        return []
    used: set[int] = set()
    assignments: list[int | None] = [None] * len(gt_boxes)

    pairs = []  # (iou, gt_idx, pred_idx)
    for gi, g in enumerate(gt_boxes):
        for pi, p in enumerate(pred_boxes):
            v = iou(g, p)
            if v >= iou_threshold:
                pairs.append((v, gi, pi))
    pairs.sort(reverse=True)
    for _, gi, pi in pairs:
        if assignments[gi] is None and pi not in used:
            assignments[gi] = pi
            used.add(pi)
    return assignments


# ── detection-level ────────────────────────────────────────────────────────
@dataclass
class DetectionTally:
    tp: int = 0         # matched GT boxes
    fp: int = 0         # predictions not matched to any GT
    fn: int = 0         # GT boxes with no matching prediction

    @property
    def recall(self) -> float:
        denom = self.tp + self.fn
        return self.tp / denom if denom else 0.0

    @property
    def precision(self) -> float:
        denom = self.tp + self.fp
        return self.tp / denom if denom else 0.0


def detection_tally(
    gt_boxes: Sequence[Bbox],
    pred_boxes: Sequence[Bbox],
    iou_threshold: float = 0.5,
) -> DetectionTally:
    """Aggregate TP / FP / FN counts for one image."""
    if not gt_boxes and not pred_boxes:
        return DetectionTally()
    assignments = match_detections_to_gt(gt_boxes, pred_boxes, iou_threshold)
    tp = sum(1 for a in assignments if a is not None)
    fn = len(gt_boxes) - tp
    used = {a for a in assignments if a is not None}
    fp = len(pred_boxes) - len(used)
    return DetectionTally(tp=tp, fp=fp, fn=fn)


# ── classification top-k ───────────────────────────────────────────────────
def top_k(ranked: Sequence[str], truth: str, k: int) -> bool:
    """True iff `truth` appears among the top-k entries of `ranked`."""
    if not truth:
        return False
    return truth in list(ranked)[:k]


def reciprocal_rank(ranked: Sequence[str], truth: str) -> float:
    """1 / rank of `truth` in `ranked`, or 0 if absent. Rank is 1-indexed."""
    if not truth:
        return 0.0
    for i, s in enumerate(ranked):
        if s == truth:
            return 1.0 / (i + 1)
    return 0.0


# ── aggregate helpers ──────────────────────────────────────────────────────
def mean(values: Iterable[float]) -> float:
    """Safe mean; 0.0 if empty."""
    xs = list(values)
    return sum(xs) / len(xs) if xs else 0.0
