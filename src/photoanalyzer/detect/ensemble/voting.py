"""Ensemble orchestrator — run configured detectors, refine via SAM 2,
NMS with supporter tracking, split into `auto_accept` (≥ 2 detectors
agree) and `review` (only 1 detector).

Detectors are configured at construction time so the pipeline can
run with a subset when one isn't available (e.g. SAM 3 gate pending):

    ensemble = Ensemble(
        detectors=[
            ("dinox",        DinoXDetector()),
            ("owlv2_visual", OwlV2VisualDetector.from_exemplar_dir()),
            # ("sam3",       Sam3Detector()),   # enable once gate granted
        ],
        refiner=SAM2Refiner(),
    )
    auto, review = ensemble.run("path/to/image.jpg")

The output is a pair of lists — each element is an `EnsembleDetection`
carrying the supporter tuple so downstream JSON preserves provenance.
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
# Minimum per-detector-cluster agreement to end up in auto_accept.
# "1" means any single detector is enough (fallback to review-only).
AUTO_ACCEPT_SUPPORTERS = 2


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
    """Multi-detector orchestrator with agreement voting."""

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

        Auto-accept: boxes supported by ≥ AUTO_ACCEPT_SUPPORTERS
        detectors after NMS clustering.
        Review: boxes supported by only one detector — go to the
        annotator's human-review queue.
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


# Production architecture — SAM 3 alone (locked 2026-04-25 after Phase C
# bench showed SAM 3 outperforming alternatives 3x; ensemble's value
# collapsed to "tighten boxes" via SAM 2, which is currently broken).
# DINO-X and OWLv2 paths remain available behind opt-in flags so we can
# A/B against them without re-implementing.
def build_default_ensemble(
    exemplar_dir: Path | None = None,
    include_sam3: bool = True,
    include_dinox: bool = False,
    include_owlv2: bool = False,
    include_sam2_refine: bool = False,
) -> Ensemble:
    detectors: list[tuple[str, Detector]] = []

    if include_sam3:
        from photoanalyzer.detect.ensemble.sam3 import Sam3Detector
        detectors.append(("sam3", Sam3Detector()))

    if include_dinox:
        from photoanalyzer.detect.ensemble.dinox import DinoXDetector
        detectors.append(("dinox", DinoXDetector()))

    if include_owlv2:
        from photoanalyzer.detect.ensemble.owlv2_visual import OwlV2VisualDetector
        if exemplar_dir is not None:
            detectors.append(
                ("owlv2_visual", OwlV2VisualDetector.from_exemplar_dir(exemplar_dir))
            )
        else:
            detectors.append(
                ("owlv2_visual", OwlV2VisualDetector.from_exemplar_dir())
            )

    if not detectors:
        raise ValueError(
            "No detectors enabled. Set at least one of "
            "include_sam3 / include_dinox / include_owlv2 to True."
        )

    refiner: SAM2Refiner | None = SAM2Refiner() if include_sam2_refine else None
    return Ensemble(detectors=detectors, refiner=refiner)


def run_ensemble(
    image: ImageSource,
) -> tuple[list[EnsembleDetection], list[EnsembleDetection]]:
    """Convenience — build the default ensemble and run it once.
    Not recommended for batch pipelines (model load amortises poorly);
    instantiate `build_default_ensemble()` once and reuse."""
    return build_default_ensemble().run(image)
