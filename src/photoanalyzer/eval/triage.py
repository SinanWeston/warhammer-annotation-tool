"""Triage SAM 3 pseudo-labels into review buckets (Phase F3 prep).

The decided strategy (2026-06-05): the junk filter is deliberately *not*
exhaustive — instead, bucket on the **detector's own output** and route the
ambiguous cases to human review rather than auto-dropping them.

  zero-box   → REVIEW, not drop. "junk OR a hard SAM-3 miss" — and the missed
               hard minis are exactly the valuable active-learning cases. Only
               confirmed-empty images get dropped (or kept as terrain negatives).
  has-boxes  → goes to training, but a *prioritized* review queue surfaces the
               likely errors first, so F3 human-hours hit the highest-value cases:
                 • low_conf      — low max/mean box score (SAM 3 unsure)
                 • count_outlier — far more boxes than typical (tiling FP storms)
                 • geom_outlier  — a box covering ≫half the frame or a wild aspect
                                   ratio (terrain / vehicle false positives)

This module is pure (no FiftyOne / I/O); the CLI in
`scripts/phaseF/triage_pseudolabels.py` loads the box JSONs and writes the queue.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median
from typing import Sequence

# default thresholds — tune from the real distribution once SAM 3 has run
LOW_CONF = 0.40      # image whose best box scores below this is "SAM 3 unsure"
AREA_HI = 0.55       # a box covering >55% of the frame → likely terrain/vehicle FP
ASPECT_HI = 5.0      # box long/short ratio above this → likely a bad box
COUNT_OUTLIER_MULT = 3.0   # n_boxes > mult × median(nonzero counts) → count outlier


@dataclass
class ImageTriage:
    basename: str
    n_boxes: int
    max_score: float
    mean_score: float
    max_area_frac: float       # largest box area / image area
    max_aspect: float
    reasons: list[str] = field(default_factory=list)

    @property
    def bucket(self) -> str:
        return "zero_box" if self.n_boxes == 0 else "has_boxes"

    @property
    def needs_review(self) -> bool:
        return bool(self.reasons)

    # priority: lower sorts first in the review queue. Ordered to match the
    # decided review priorities (low-conf > count outlier > geometry > 0-box sample).
    @property
    def priority(self) -> tuple:
        rank = (
            0 if "low_conf" in self.reasons else
            1 if "count_outlier" in self.reasons else
            2 if "geom_outlier" in self.reasons else
            3 if "zero_box" in self.reasons else 9
        )
        return (rank, self.max_score, -self.n_boxes)

    def as_dict(self) -> dict:
        return {
            "basename": self.basename, "bucket": self.bucket,
            "n_boxes": self.n_boxes, "max_score": round(self.max_score, 4),
            "mean_score": round(self.mean_score, 4),
            "max_area_frac": round(self.max_area_frac, 4),
            "max_aspect": round(self.max_aspect, 3),
            "reasons": self.reasons,
        }


def _features(record: dict) -> dict:
    """Per-image geometry/score features from a pseudo-label record."""
    boxes = record.get("boxes", [])
    w = record.get("width") or 1
    h = record.get("height") or 1
    img_area = float(w * h) or 1.0
    scores, areas, aspects = [], [], []
    for b in boxes:
        x, y, bw, bh = b["xywh"]
        scores.append(float(b.get("score", 1.0)))
        areas.append((bw * bh) / img_area)
        long_, short_ = max(bw, bh), max(1e-6, min(bw, bh))
        aspects.append(long_ / short_)
    return {
        "n": len(boxes),
        "max_score": max(scores) if scores else 0.0,
        "mean_score": sum(scores) / len(scores) if scores else 0.0,
        "max_area": max(areas) if areas else 0.0,
        "max_aspect": max(aspects) if aspects else 0.0,
    }


def triage_predictions(
    records: Sequence[dict],
    low_conf: float = LOW_CONF,
    area_hi: float = AREA_HI,
    aspect_hi: float = ASPECT_HI,
    count_mult: float = COUNT_OUTLIER_MULT,
) -> list[ImageTriage]:
    """Triage a batch of pseudo-label records (`{basename/imagePath, width,
    height, boxes:[{xywh,score}]}`). Count-outlier threshold is derived from the
    batch's own nonzero box-count distribution."""
    feats = [(r, _features(r)) for r in records]
    nonzero = [f["n"] for _, f in feats if f["n"] > 0]
    count_thresh = (count_mult * median(nonzero)) if nonzero else float("inf")

    out: list[ImageTriage] = []
    for r, f in feats:
        bn = _basename(r)
        reasons: list[str] = []
        if f["n"] == 0:
            reasons.append("zero_box")
        else:
            if f["max_score"] < low_conf:
                reasons.append("low_conf")
            if f["n"] > count_thresh:
                reasons.append("count_outlier")
            if f["max_area"] > area_hi or f["max_aspect"] > aspect_hi:
                reasons.append("geom_outlier")
        out.append(ImageTriage(
            basename=bn, n_boxes=f["n"], max_score=f["max_score"],
            mean_score=f["mean_score"], max_area_frac=f["max_area"],
            max_aspect=f["max_aspect"], reasons=reasons,
        ))
    return out


def _basename(record: dict) -> str:
    from pathlib import Path

    path = record.get("imagePath") or record.get("filepath") or record.get("imageId", "")
    return Path(path).name if path else record.get("imageId", "?")


def summarize(triaged: Sequence[ImageTriage]) -> dict:
    """Counts per bucket + per review reason, for the run summary."""
    zero = sum(1 for t in triaged if t.bucket == "zero_box")
    review = sum(1 for t in triaged if t.needs_review)
    reasons: dict[str, int] = {}
    for t in triaged:
        for r in t.reasons:
            reasons[r] = reasons.get(r, 0) + 1
    return {
        "n_images": len(triaged),
        "zero_box": zero,
        "has_boxes": len(triaged) - zero,
        "needs_review": review,
        "by_reason": dict(sorted(reasons.items(), key=lambda kv: -kv[1])),
    }
