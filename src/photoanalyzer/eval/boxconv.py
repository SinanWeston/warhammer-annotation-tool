"""Reconcile SAM-derived box convention with the gold convention.

The problem (the silent recall-killer): gold boxes are **model + integral base**
(LABELING_GUIDE §1 — the base is the deliberate, stable anchor and the unit of
counting). SAM 3 / SAM 2 masks are **mask-tight** and clip the base at the
figure's feet. Scoring mask-tight boxes against base-inclusive gold makes a
*correct* detection fall below the IoU threshold → counted as a miss → recall
craters from a localization mismatch, not a detection failure.

Two tools here:

- `extend_box_to_base(box, pad_frac)` — pad a box's **bottom** edge downward by a
  fraction of its height, so the detector's output unit matches gold's "one
  base". The cv-researcher literature pass (SAM 3 paper + HF) recommends ~8–12%;
  default 0.10. Keep gold fixed; adapt the *prediction*.
- `convention_diagnostic(gold, preds)` — quantify the mismatch *before* picking a
  pad value: median IoU of matched pairs, and how much of the shortfall is a
  systematic *bottom* gap (the base) vs. all-round looseness. A large
  bottom-only gap → base clipping → padding fixes it; an all-round gap → genuine
  localization error that padding won't help.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from . import metrics
from .metrics import Bbox


def extend_box_to_base(box: Bbox, pad_frac: float = 0.10,
                       img_h: float | None = None) -> Bbox:
    """Pad the bottom edge of an (x, y, w, h) box downward by `pad_frac * h`.

    Clamped to `img_h` if given. Only the bottom grows — minis stand *on* their
    base, so the clipped region is always below the mask, never above."""
    x, y, w, h = box
    new_h = h * (1.0 + pad_frac)
    if img_h is not None:
        new_h = min(new_h, img_h - y)
    return (x, y, w, max(h, new_h))


def apply_base_extension(preds: dict[str, list[Bbox]], pad_frac: float = 0.10,
                         dims: dict[str, tuple[int, int]] | None = None,
                         ) -> dict[str, list[Bbox]]:
    """Vectorized `extend_box_to_base` over a {basename: [boxes]} prediction map.

    `dims` optionally supplies {basename: (w, h)} for bottom-clamping."""
    out: dict[str, list[Bbox]] = {}
    for bn, boxes in preds.items():
        ih = dims[bn][1] if dims and bn in dims else None
        out[bn] = [extend_box_to_base(b, pad_frac, ih) for b in boxes]
    return out


@dataclass
class ConventionDiagnostic:
    n_matched: int
    median_iou: float
    # mean directional gap between matched pred and gold edges, as a fraction
    # of gold box height/width. Positive bottom_gap = gold extends below pred
    # (the base-clip signature).
    bottom_gap: float
    top_gap: float
    side_gap: float

    @property
    def base_clip_signature(self) -> bool:
        """Bottom gap dominates the other edges → it's base clipping, paddable."""
        others = max(abs(self.top_gap), abs(self.side_gap), 1e-6)
        return self.bottom_gap > 0.05 and self.bottom_gap > 1.8 * others

    def as_dict(self) -> dict:
        return {
            "n_matched": self.n_matched,
            "median_iou": round(self.median_iou, 4),
            "bottom_gap": round(self.bottom_gap, 4),
            "top_gap": round(self.top_gap, 4),
            "side_gap": round(self.side_gap, 4),
            "base_clip_signature": self.base_clip_signature,
        }


def convention_diagnostic(
    gold_boxes_by_img: dict[str, Sequence[Bbox]],
    preds: dict[str, list[Bbox]],
    iou_threshold: float = 0.3,
) -> ConventionDiagnostic:
    """Compare matched (pred, gold) pairs edge-by-edge to localize the mismatch.

    Matches at a *loose* IoU (default 0.3) so base-clipped-but-correct boxes
    still pair up — the whole point is to measure their edge offsets."""
    ious: list[float] = []
    bottom: list[float] = []
    top: list[float] = []
    side: list[float] = []

    for bn, gboxes in gold_boxes_by_img.items():
        pboxes = preds.get(bn, [])
        assigns = metrics.match_detections_to_gt(gboxes, pboxes, iou_threshold)
        for gi, pi in enumerate(assigns):
            if pi is None:
                continue
            gx, gy, gw, gh = gboxes[gi]
            px, py, pw, ph = pboxes[pi]
            if gh <= 0 or gw <= 0:
                continue
            ious.append(metrics.iou(gboxes[gi], pboxes[pi]))
            # gold_bottom - pred_bottom, normalized by gold height. >0 ⇒ gold
            # extends lower than pred ⇒ pred clipped the base.
            bottom.append(((gy + gh) - (py + ph)) / gh)
            top.append((py - gy) / gh)
            side.append(((px - gx) + ((gx + gw) - (px + pw))) / (2 * gw))

    if not ious:
        return ConventionDiagnostic(0, 0.0, 0.0, 0.0, 0.0)
    ious.sort()
    median = ious[len(ious) // 2]
    return ConventionDiagnostic(
        n_matched=len(ious),
        median_iou=median,
        bottom_gap=metrics.mean(bottom),
        top_gap=metrics.mean(top),
        side_gap=metrics.mean(side),
    )
