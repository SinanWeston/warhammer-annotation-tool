"""SAM 2 mask refinement — tightens candidate boxes to the silhouette
they actually enclose, and drops candidates whose refined bbox has
low IoU with the original (strong signal of a false positive on
terrain / props / empty space).

SAM 2 (facebook/sam2-hiera-large) is public on HuggingFace (not gated)
as of 2026-04. Given a box prompt, it generates up to 3 masks with
predicted IoU scores; we take the best and recompute the tight bbox
from the mask pixels.

Usage:
    refined = refine_boxes(image, detections)
    # refined is a list[RefinedDetection]; each carries the original
    # Detection, the mask-derived bbox, and the IoU between the two.
    # Callers filter: drop entries where refinement_iou < 0.3.

License: Apache-2.0.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import torch
from PIL import Image

from photoanalyzer.detect.base import Detection, ImageSource


DEFAULT_MODEL_ID = "facebook/sam2-hiera-large"
# Drop candidates whose refined bbox IoU with the original is below
# this — strong signal SAM 2 snapped to something other than the
# candidate's intended object. Loosened from 0.30 → 0.10 after the
# 2026-04-25 bench showed `sam3_refined` returning 0 boxes on every
# image, suggesting the threshold was over-aggressive. We'd rather
# accept slightly looser refined boxes than drop everything.
DEFAULT_MIN_IOU = 0.10


@dataclass(frozen=True)
class RefinedDetection:
    """Original candidate + mask-derived tight bbox + sanity metric."""
    original: Detection
    refined_bbox: tuple[float, float, float, float]   # x, y, w, h in image pixels
    refinement_iou: float
    mask_iou_score: float                              # SAM 2's own IoU head


class SAM2Refiner:
    """Holds the SAM 2 model + processor, amortises loading across calls."""

    def __init__(self, model_id: str = DEFAULT_MODEL_ID, device: str | None = None) -> None:
        self.model_id = model_id
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self._model = None
        self._processor = None

    def _load(self) -> None:
        if self._model is not None:
            return
        from transformers import Sam2Model, Sam2Processor
        self._processor = Sam2Processor.from_pretrained(self.model_id)
        self._model = Sam2Model.from_pretrained(self.model_id).to(self.device)
        self._model.eval()

    @torch.inference_mode()
    def refine(
        self,
        image: ImageSource,
        detections: Iterable[Detection],
        min_iou: float = DEFAULT_MIN_IOU,
    ) -> list[RefinedDetection]:
        self._load()
        assert self._model is not None and self._processor is not None

        if isinstance(image, (str, Path)):
            pil = Image.open(image).convert("RGB")
        elif isinstance(image, np.ndarray):
            pil = Image.fromarray(image)
        elif isinstance(image, Image.Image):
            pil = image.convert("RGB")
        else:
            raise TypeError(f"unsupported image type: {type(image)}")

        W, H = pil.size
        dets = list(detections)
        if not dets:
            return []

        # SAM 2 wants boxes nested 3 deep: [image_idx, box_idx, coordinates].
        # transformers 5.0's Sam2Processor stopped counting tuples as a level,
        # so we explicitly convert each xyxy tuple to a list of floats.
        # Format: outermost = batch (1 image), middle = boxes for that image,
        # innermost = the 4 box coordinates as a list[float].
        input_boxes = [
            [[float(c) for c in d.xyxy] for d in dets],   # one image, N boxes
        ]
        inputs = self._processor(
            images=pil,
            input_boxes=input_boxes,
            return_tensors="pt",
        ).to(self.device)

        outputs = self._model(**inputs, multimask_output=True)
        # Post-process masks to original image size.
        masks = self._processor.post_process_masks(
            outputs.pred_masks.cpu(),
            inputs["original_sizes"].cpu(),
            inputs["reshaped_input_sizes"].cpu(),
        )
        # masks is a list[Tensor] len=1 (one image); tensor shape (N_boxes, 3, H, W).
        per_box_masks = masks[0]
        # iou_scores: (1, N_boxes, 3) — SAM 2's own self-scored IoU per candidate mask.
        iou_scores = outputs.iou_scores.squeeze(0).cpu().numpy()

        out: list[RefinedDetection] = []
        n_empty_masks = 0
        n_low_iou = 0
        for i, det in enumerate(dets):
            masks_i = per_box_masks[i].cpu().numpy()  # (3, H, W), bool
            scores_i = iou_scores[i]                  # (3,)
            # Pick the best-scoring of SAM 2's 3 candidate masks.
            best = int(np.argmax(scores_i))
            mask = masks_i[best].astype(bool)
            if not mask.any():
                # SAM 2 returned empty mask — drop this candidate.
                n_empty_masks += 1
                continue
            # Tight bbox from mask pixels.
            ys, xs = np.where(mask)
            rx0, ry0 = int(xs.min()), int(ys.min())
            rx1, ry1 = int(xs.max()), int(ys.max())
            refined = (float(rx0), float(ry0), float(rx1 - rx0), float(ry1 - ry0))
            r_iou = _box_iou(det.bbox, refined)
            if r_iou < min_iou:
                n_low_iou += 1
                continue
            out.append(RefinedDetection(
                original=det,
                refined_bbox=refined,
                refinement_iou=float(r_iou),
                mask_iou_score=float(scores_i[best]),
            ))
        # Diagnostic: tells us why refinement is dropping candidates so
        # we can tell "SAM 2 returned nothing" from "thresholds too tight"
        # without re-running.
        if (n_empty_masks or n_low_iou) and len(out) < len(dets) // 2:
            print(f"  [sam2_refine] of {len(dets)} candidates: "
                  f"{len(out)} kept, {n_empty_masks} empty masks, "
                  f"{n_low_iou} below IoU {min_iou:.2f}")
        return out


def _box_iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    """IoU between two xywh boxes."""
    ax0, ay0, aw, ah = a
    ax1, ay1 = ax0 + aw, ay0 + ah
    bx0, by0, bw, bh = b
    bx1, by1 = bx0 + bw, by0 + bh
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
    inter = iw * ih
    union = aw * ah + bw * bh - inter
    return (inter / union) if union > 0 else 0.0


# Convenience function for callers who don't want to manage the refiner.
_default_refiner: SAM2Refiner | None = None


def refine_boxes(
    image: ImageSource,
    detections: Iterable[Detection],
    min_iou: float = DEFAULT_MIN_IOU,
) -> list[RefinedDetection]:
    """Refine a single image's detections with SAM 2. Lazily-loaded
    module-global refiner so repeated calls amortise model load."""
    global _default_refiner
    if _default_refiner is None:
        _default_refiner = SAM2Refiner()
    return _default_refiner.refine(image, detections, min_iou=min_iou)
