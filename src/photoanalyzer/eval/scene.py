"""Scene-level benchmark harness.

A scene is an image containing 1..N miniatures, each with ground-truth bbox +
faction + unit_slug. The harness runs a full Pipeline (detect → classify →
retrieve) on every scene and aggregates per-image and per-split metrics.

Headline metric: `scene_top3` — the fraction of scenes where every detected
mini's top-3 unit suggestions include the correct unit. That's the MVP bar.

The actual pipeline lives in `photoanalyzer.pipeline`; this module only
defines the data shapes and the evaluation loop. Phase A ships the skeleton;
Phase C fills in benchmark images and wires up the real Pipeline.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, Sequence

from .metrics import (
    Bbox,
    DetectionTally,
    detection_tally,
    match_detections_to_gt,
    mean,
    reciprocal_rank,
    top_k,
)


# ── ground-truth + prediction shapes ───────────────────────────────────────
@dataclass(frozen=True)
class GroundTruthMini:
    bbox: Bbox
    faction: str        # canonical faction slug (see photoanalyzer.taxonomy)
    unit_slug: str      # canonical unit slug


@dataclass(frozen=True)
class SceneGroundTruth:
    """Ground truth for one scene image."""
    image_path: str                  # repo-relative path to the source image
    minis: tuple[GroundTruthMini, ...]

    @property
    def num_minis(self) -> int:
        return len(self.minis)


@dataclass(frozen=True)
class PredictedMini:
    bbox: Bbox
    faction: str                     # top-1 predicted faction (may be "")
    faction_confidence: float = 0.0
    unit_suggestions: tuple[str, ...] = ()  # ordered top-K unit slugs


@dataclass(frozen=True)
class ScenePrediction:
    image_path: str
    minis: tuple[PredictedMini, ...]


class Pipeline(Protocol):
    """Duck-typed interface the scene harness calls. `photoanalyzer.pipeline`
    implements this; tests can substitute a fake."""

    def predict(self, image_path: str | Path) -> ScenePrediction: ...


# ── per-scene metrics ──────────────────────────────────────────────────────
@dataclass
class SceneResult:
    image_path: str
    num_gt: int
    num_pred: int
    detection: DetectionTally
    # Per matched GT box: was faction_top1 correct?
    faction_top1_flags: list[bool] = field(default_factory=list)
    # Per matched GT box: top-k flags for k in {1, 3, 5}
    unit_top1_flags: list[bool] = field(default_factory=list)
    unit_top3_flags: list[bool] = field(default_factory=list)
    unit_top5_flags: list[bool] = field(default_factory=list)
    reciprocal_ranks: list[float] = field(default_factory=list)

    @property
    def scene_top3_pass(self) -> bool:
        """Every GT mini must have detection + top-3 match."""
        if self.num_gt == 0:
            return True  # empty scene trivially passes
        all_detected = self.detection.fn == 0
        all_units_top3 = (
            len(self.unit_top3_flags) == self.num_gt
            and all(self.unit_top3_flags)
        )
        return all_detected and all_units_top3


# ── aggregated metrics ─────────────────────────────────────────────────────
@dataclass
class SceneMetrics:
    num_scenes: int = 0
    num_minis: int = 0
    detection_recall: float = 0.0
    detection_precision: float = 0.0
    faction_top1: float = 0.0
    unit_top1: float = 0.0
    unit_top3: float = 0.0
    unit_top5: float = 0.0
    mrr: float = 0.0
    scene_top3: float = 0.0  # headline metric
    per_scene: list[SceneResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        """JSON-serialisable summary (drops per_scene detail)."""
        return {
            "num_scenes": self.num_scenes,
            "num_minis": self.num_minis,
            "detection_recall": round(self.detection_recall, 4),
            "detection_precision": round(self.detection_precision, 4),
            "faction_top1": round(self.faction_top1, 4),
            "unit_top1": round(self.unit_top1, 4),
            "unit_top3": round(self.unit_top3, 4),
            "unit_top5": round(self.unit_top5, 4),
            "mrr": round(self.mrr, 4),
            "scene_top3": round(self.scene_top3, 4),
        }


# ── evaluation loop ────────────────────────────────────────────────────────
def evaluate_scene(
    gt: SceneGroundTruth,
    pred: ScenePrediction,
    iou_threshold: float = 0.5,
) -> SceneResult:
    """Evaluate one scene's prediction against ground truth."""
    det = detection_tally(
        [m.bbox for m in gt.minis],
        [m.bbox for m in pred.minis],
        iou_threshold=iou_threshold,
    )
    assignments = match_detections_to_gt(
        [m.bbox for m in gt.minis],
        [m.bbox for m in pred.minis],
        iou_threshold=iou_threshold,
    )
    res = SceneResult(
        image_path=gt.image_path,
        num_gt=len(gt.minis),
        num_pred=len(pred.minis),
        detection=det,
    )
    for gi, pi in enumerate(assignments):
        if pi is None:
            continue
        gt_mini = gt.minis[gi]
        p_mini = pred.minis[pi]
        res.faction_top1_flags.append(p_mini.faction == gt_mini.faction)
        res.unit_top1_flags.append(top_k(p_mini.unit_suggestions, gt_mini.unit_slug, 1))
        res.unit_top3_flags.append(top_k(p_mini.unit_suggestions, gt_mini.unit_slug, 3))
        res.unit_top5_flags.append(top_k(p_mini.unit_suggestions, gt_mini.unit_slug, 5))
        res.reciprocal_ranks.append(
            reciprocal_rank(p_mini.unit_suggestions, gt_mini.unit_slug)
        )
    return res


def aggregate(results: Sequence[SceneResult]) -> SceneMetrics:
    """Fold per-scene results into aggregate metrics."""
    if not results:
        return SceneMetrics()
    total_tp = sum(r.detection.tp for r in results)
    total_fp = sum(r.detection.fp for r in results)
    total_fn = sum(r.detection.fn for r in results)
    det_recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) else 0.0
    det_precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) else 0.0

    # Flatten per-mini flags across matched boxes only.
    all_faction_flags = [b for r in results for b in r.faction_top1_flags]
    all_top1 = [b for r in results for b in r.unit_top1_flags]
    all_top3 = [b for r in results for b in r.unit_top3_flags]
    all_top5 = [b for r in results for b in r.unit_top5_flags]
    all_rr = [v for r in results for v in r.reciprocal_ranks]

    return SceneMetrics(
        num_scenes=len(results),
        num_minis=sum(r.num_gt for r in results),
        detection_recall=det_recall,
        detection_precision=det_precision,
        faction_top1=mean(1.0 if b else 0.0 for b in all_faction_flags),
        unit_top1=mean(1.0 if b else 0.0 for b in all_top1),
        unit_top3=mean(1.0 if b else 0.0 for b in all_top3),
        unit_top5=mean(1.0 if b else 0.0 for b in all_top5),
        mrr=mean(all_rr),
        scene_top3=mean(1.0 if r.scene_top3_pass else 0.0 for r in results),
        per_scene=list(results),
    )


def evaluate(
    pipeline: Pipeline,
    ground_truths: Sequence[SceneGroundTruth],
    iou_threshold: float = 0.5,
) -> SceneMetrics:
    """Run the pipeline over every scene and aggregate metrics."""
    results: list[SceneResult] = []
    for gt in ground_truths:
        pred = pipeline.predict(gt.image_path)
        results.append(evaluate_scene(gt, pred, iou_threshold=iou_threshold))
    return aggregate(results)


# ── ground-truth I/O ───────────────────────────────────────────────────────
def load_ground_truth(manifest_path: str | Path) -> list[SceneGroundTruth]:
    """Load scenes from a JSON manifest at `{path}`.

    Expected format (one file per benchmark split, e.g. data/scene_benchmark/mine.json):

        [
            {
                "image_path": "data/scene_benchmark/mine/img-001.jpg",
                "minis": [
                    {"bbox": [x, y, w, h], "faction": "space_marines", "unit_slug": "captain"},
                    ...
                ]
            },
            ...
        ]
    """
    p = Path(manifest_path)
    with p.open() as f:
        data = json.load(f)
    scenes: list[SceneGroundTruth] = []
    for entry in data:
        minis = tuple(
            GroundTruthMini(
                bbox=tuple(m["bbox"]),  # type: ignore[arg-type]
                faction=m["faction"],
                unit_slug=m["unit_slug"],
            )
            for m in entry.get("minis", [])
        )
        scenes.append(SceneGroundTruth(image_path=entry["image_path"], minis=minis))
    return scenes
