"""Detection orchestrator — run SAM 3, optionally refine via SAM 2, and
dedup overlapping boxes (incl. SAHI tile-seam duplicates) via IoU clustering.

History: this was a multi-detector *ensemble* with agreement voting (SAM 3 +
Grounding DINO + OWLv2-visual, ≥2-supporter auto-accept). The ensemble was
killed 2026-04-25 (Phase C bench showed SAM 3 beating the alternatives 3× and
the weaker votes only hurt precision); the DINO/OWLv2 detectors were removed
2026-06-05. The class is kept (it still does the necessary SAHI-output IoU
dedup for the single SAM 3 detector), but there is no longer any voting —
per-image review routing now lives in `photoanalyzer.eval.triage`.

    ensemble = build_default_ensemble(include_sam2_refine=True)
    auto, review = ensemble.run("path/to/image.jpg")
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
import torch
import torchvision.ops as ops
from PIL import Image

from photoanalyzer.detect.base import Detection, Detector, ImageSource
from photoanalyzer.detect.ensemble.sam2_refine import (
    DEFAULT_MIN_IOU as DEFAULT_SAM2_MIN_IOU,
    RefinedDetection,
    SAM2Refiner,
)


DEFAULT_NMS_IOU = 0.5
# Single-detector pipeline (SAM 3 only) — every clustered box has exactly one
# supporter, so the historical ≥2-detector "auto-accept vs review" vote is moot.
# Kept at 1 so detections aren't silently all-routed to `review`; the real
# per-image review prioritisation is done downstream by `eval.triage`.
AUTO_ACCEPT_SUPPORTERS = 1


@dataclass(frozen=True)
class EnsembleDetection:
    """A merged detection plus its provenance — tracks which configured
    detectors supported this box through NMS clustering. The tier is
    derived from `supporters` length downstream."""
    bbox: tuple[float, float, float, float]
    confidence: float
    supporters: tuple[str, ...]
    refinement_iou: float

    @property
    def is_auto_accept(self) -> bool:
        return len(self.supporters) >= AUTO_ACCEPT_SUPPORTERS


class Ensemble:
    """SAM 3 (+ optional SAM 2) detector runner with SAHI-output IoU dedup.

    Name retained for the existing call sites; it no longer ensembles multiple
    detectors (see module docstring)."""

    def __init__(
        self,
        detectors: Sequence[tuple[str, Detector]],
        refiner: SAM2Refiner | None = None,
        nms_iou: float = DEFAULT_NMS_IOU,
        sam2_min_iou: float = DEFAULT_SAM2_MIN_IOU,
    ) -> None:
        if not detectors:
            raise ValueError("Ensemble needs at least one detector")
        self.detectors = list(detectors)
        self.refiner = refiner
        self.nms_iou = nms_iou
        self.sam2_min_iou = sam2_min_iou

    def run(
        self, image: ImageSource,
    ) -> tuple[list[EnsembleDetection], list[EnsembleDetection]]:
        """Return (auto_accept, review).

        With the single SAM 3 detector every clustered box has one supporter,
        so all boxes land in `auto_accept` and `review` is empty here — review
        prioritisation is done per-image downstream by `eval.triage`. The pair
        return is kept for the existing call sites.
        """
        if isinstance(image, (str, Path)):
            pil = Image.open(image).convert("RGB")
        elif isinstance(image, np.ndarray):
            pil = Image.fromarray(image)
        elif isinstance(image, Image.Image):
            pil = image.convert("RGB")
        else:
            raise TypeError(f"unsupported image type: {type(image)}")

        # 1. Collect per-detector raw detections.
        per_detector: list[tuple[str, list[Detection]]] = []
        for name, det in self.detectors:
            try:
                per_detector.append((name, det.predict(pil)))
            except Exception as e:
                # One detector failing shouldn't kill the whole ensemble.
                # Log via print — callers can capture stderr.
                import sys
                print(f"  [ensemble] detector {name!r} failed: {e}", file=sys.stderr)
                per_detector.append((name, []))

        # 2. Refine every candidate with SAM 2 (box prompt → tight mask-bbox).
        #    Refinement is done once per detector, with provenance preserved
        #    on the original Detection reference.
        if self.refiner is not None:
            refined_per_detector: list[tuple[str, list[RefinedDetection]]] = []
            for name, dets in per_detector:
                if not dets:
                    refined_per_detector.append((name, []))
                    continue
                refined = self.refiner.refine(pil, dets, min_iou=self.sam2_min_iou)
                refined_per_detector.append((name, refined))
        else:
            # No refiner — wrap raw detections in RefinedDetection so the
            # downstream code path is uniform.
            refined_per_detector = [
                (name, [RefinedDetection(original=d, refined_bbox=d.bbox,
                                          refinement_iou=1.0, mask_iou_score=0.0)
                        for d in dets])
                for name, dets in per_detector
            ]

        # 3. Flatten + NMS across all detectors, tracking supporter membership.
        flat: list[tuple[int, RefinedDetection, str]] = []  # idx, refined, detector-name
        for name, refs in refined_per_detector:
            for r in refs:
                flat.append((len(flat), r, name))

        if not flat:
            return [], []

        xyxy = np.array([
            [r.refined_bbox[0], r.refined_bbox[1],
             r.refined_bbox[0] + r.refined_bbox[2],
             r.refined_bbox[1] + r.refined_bbox[3]]
            for (_, r, _) in flat
        ], dtype=np.float32)
        scores = np.array(
            [r.original.confidence for (_, r, _) in flat],
            dtype=np.float32,
        )

        # Cluster overlapping boxes greedily by IoU — this is how we
        # discover "multiple detectors agree on the same object". The
        # representative box for a cluster is the highest-confidence
        # member; supporters are the set of detector names involved.
        clusters = _iou_cluster(xyxy, self.nms_iou)

        out_auto: list[EnsembleDetection] = []
        out_review: list[EnsembleDetection] = []
        for cluster in clusters:
            # Representative: highest-confidence member in the cluster.
            rep_idx = max(cluster, key=lambda i: scores[i])
            rep = flat[rep_idx][1]
            supporters = tuple(sorted({flat[i][2] for i in cluster}))
            ed = EnsembleDetection(
                bbox=rep.refined_bbox,
                confidence=float(scores[rep_idx]),
                supporters=supporters,
                refinement_iou=rep.refinement_iou,
            )
            if ed.is_auto_accept:
                out_auto.append(ed)
            else:
                out_review.append(ed)
        return out_auto, out_review


def _iou_cluster(xyxy: np.ndarray, iou_threshold: float) -> list[list[int]]:
    """Greedy IoU clustering. Each output list is a cluster of box
    indices that all overlap ≥ iou_threshold with at least one other
    member via transitive closure. Used instead of plain NMS because we
    need to *preserve* which detectors contributed to each cluster.
    """
    n = len(xyxy)
    if n == 0:
        return []
    # IoU matrix — torchvision handles this efficiently.
    t = torch.from_numpy(xyxy)
    iou_mat = ops.box_iou(t, t).numpy()
    visited = [False] * n
    clusters: list[list[int]] = []
    for i in range(n):
        if visited[i]:
            continue
        # BFS transitive closure.
        stack = [i]
        members: list[int] = []
        while stack:
            j = stack.pop()
            if visited[j]:
                continue
            visited[j] = True
            members.append(j)
            neighbours = np.where(iou_mat[j] >= iou_threshold)[0]
            for k in neighbours:
                if not visited[k]:
                    stack.append(int(k))
        clusters.append(members)
    return clusters


# Production architecture — SAM 3 alone (locked 2026-04-25 after Phase C bench
# showed SAM 3 outperforming alternatives 3×). The DINO-X / OWLv2 detector paths
# were removed 2026-06-05; resurrect from git history if an A/B is ever wanted.
def build_default_ensemble(
    include_sam3: bool = True,
    include_sam2_refine: bool = False,
) -> Ensemble:
    detectors: list[tuple[str, Detector]] = []

    if include_sam3:
        from photoanalyzer.detect.ensemble.sam3 import Sam3Detector
        detectors.append(("sam3", Sam3Detector()))

    if not detectors:
        raise ValueError("No detectors enabled — set include_sam3=True.")

    refiner: SAM2Refiner | None = SAM2Refiner() if include_sam2_refine else None
    return Ensemble(detectors=detectors, refiner=refiner)


def run_ensemble(
    image: ImageSource,
) -> tuple[list[EnsembleDetection], list[EnsembleDetection]]:
    """Convenience — build the default ensemble and run it once.
    Not recommended for batch pipelines (model load amortises poorly);
    instantiate `build_default_ensemble()` once and reuse."""
    return build_default_ensemble().run(image)
