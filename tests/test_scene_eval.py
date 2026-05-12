"""Tests for photoanalyzer.eval.metrics + photoanalyzer.eval.scene.

Uses a fake Pipeline to exercise the evaluation loop without any model.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from photoanalyzer.eval import metrics, scene


# ── metrics primitives ─────────────────────────────────────────────────────
def test_iou_identical_boxes():
    box = (10.0, 20.0, 30.0, 40.0)
    assert metrics.iou(box, box) == pytest.approx(1.0)


def test_iou_no_overlap():
    a = (0.0, 0.0, 10.0, 10.0)
    b = (100.0, 100.0, 10.0, 10.0)
    assert metrics.iou(a, b) == 0.0


def test_iou_half_overlap_x():
    a = (0.0, 0.0, 10.0, 10.0)
    b = (5.0, 0.0, 10.0, 10.0)
    # intersection = 5*10=50, union = 100+100-50=150 → 1/3
    assert metrics.iou(a, b) == pytest.approx(1 / 3, abs=1e-6)


def test_iou_degenerate_returns_zero():
    a = (0.0, 0.0, 0.0, 10.0)  # zero width
    b = (0.0, 0.0, 10.0, 10.0)
    assert metrics.iou(a, b) == 0.0


def test_match_detections_greedy_one_to_one():
    gt = [(0.0, 0.0, 10.0, 10.0), (100.0, 0.0, 10.0, 10.0)]
    pred = [(0.0, 0.0, 10.0, 10.0), (100.0, 0.0, 10.0, 10.0)]
    assert metrics.match_detections_to_gt(gt, pred) == [0, 1]


def test_match_detections_prefers_higher_iou_when_contested():
    gt = [(0.0, 0.0, 10.0, 10.0), (2.0, 0.0, 10.0, 10.0)]
    # Single pred exactly at (0,0,10,10) — matches gt[0] perfectly, partial for gt[1]
    pred = [(0.0, 0.0, 10.0, 10.0)]
    assignments = metrics.match_detections_to_gt(gt, pred)
    assert assignments[0] == 0
    assert assignments[1] is None


def test_match_detections_below_threshold_none():
    gt = [(0.0, 0.0, 10.0, 10.0)]
    pred = [(7.0, 0.0, 10.0, 10.0)]  # IoU ~0.176
    assert metrics.match_detections_to_gt(gt, pred, iou_threshold=0.5) == [None]


def test_detection_tally_all_hit():
    gt = [(0.0, 0.0, 10.0, 10.0)]
    pred = [(0.0, 0.0, 10.0, 10.0)]
    t = metrics.detection_tally(gt, pred)
    assert t.tp == 1 and t.fp == 0 and t.fn == 0
    assert t.recall == 1.0 and t.precision == 1.0


def test_detection_tally_missed_gt():
    gt = [(0.0, 0.0, 10.0, 10.0)]
    pred = []
    t = metrics.detection_tally(gt, pred)
    assert t.tp == 0 and t.fn == 1 and t.fp == 0
    assert t.recall == 0.0


def test_detection_tally_spurious_pred():
    gt = []
    pred = [(0.0, 0.0, 10.0, 10.0)]
    t = metrics.detection_tally(gt, pred)
    assert t.fp == 1 and t.tp == 0


def test_top_k():
    assert metrics.top_k(["a", "b", "c"], "b", k=3) is True
    assert metrics.top_k(["a", "b", "c"], "b", k=1) is False
    assert metrics.top_k(["a", "b", "c"], "d", k=3) is False
    assert metrics.top_k([], "a", k=3) is False
    assert metrics.top_k(["a"], "", k=1) is False  # empty truth never matches


def test_reciprocal_rank():
    assert metrics.reciprocal_rank(["a", "b", "c"], "a") == 1.0
    assert metrics.reciprocal_rank(["a", "b", "c"], "b") == pytest.approx(0.5)
    assert metrics.reciprocal_rank(["a", "b", "c"], "c") == pytest.approx(1 / 3)
    assert metrics.reciprocal_rank(["a", "b", "c"], "z") == 0.0


# ── scene eval end-to-end ──────────────────────────────────────────────────
class _FakePipeline:
    def __init__(self, prediction: scene.ScenePrediction):
        self._pred = prediction

    def predict(self, image_path):
        return self._pred


def _gt_with_two_minis() -> scene.SceneGroundTruth:
    return scene.SceneGroundTruth(
        image_path="fixtures/scene.jpg",
        minis=(
            scene.GroundTruthMini(
                bbox=(10.0, 10.0, 100.0, 100.0),
                faction="space_marines", unit_slug="captain",
            ),
            scene.GroundTruthMini(
                bbox=(300.0, 10.0, 100.0, 100.0),
                faction="orks", unit_slug="boyz",
            ),
        ),
    )


def test_evaluate_scene_perfect():
    gt = _gt_with_two_minis()
    pred = scene.ScenePrediction(
        image_path=gt.image_path,
        minis=(
            scene.PredictedMini(
                bbox=(10.0, 10.0, 100.0, 100.0),
                faction="space_marines", faction_confidence=0.9,
                unit_suggestions=("captain", "primaris_captain", "chapter_master"),
            ),
            scene.PredictedMini(
                bbox=(300.0, 10.0, 100.0, 100.0),
                faction="orks", faction_confidence=0.85,
                unit_suggestions=("boyz", "nobz", "warboss"),
            ),
        ),
    )
    res = scene.evaluate_scene(gt, pred)
    assert res.detection.tp == 2 and res.detection.fn == 0 and res.detection.fp == 0
    assert all(res.faction_top1_flags)
    assert all(res.unit_top1_flags)
    assert res.scene_top3_pass is True


def test_evaluate_scene_misses_detection():
    gt = _gt_with_two_minis()
    # Only one of the two GT boxes predicted
    pred = scene.ScenePrediction(
        image_path=gt.image_path,
        minis=(
            scene.PredictedMini(
                bbox=(10.0, 10.0, 100.0, 100.0),
                faction="space_marines",
                unit_suggestions=("captain",),
            ),
        ),
    )
    res = scene.evaluate_scene(gt, pred)
    assert res.detection.tp == 1 and res.detection.fn == 1
    assert res.scene_top3_pass is False


def test_evaluate_scene_detection_without_unit_top3():
    gt = _gt_with_two_minis()
    pred = scene.ScenePrediction(
        image_path=gt.image_path,
        minis=(
            scene.PredictedMini(
                bbox=(10.0, 10.0, 100.0, 100.0),
                faction="space_marines",
                unit_suggestions=("wrong_1", "wrong_2", "wrong_3"),
            ),
            scene.PredictedMini(
                bbox=(300.0, 10.0, 100.0, 100.0),
                faction="orks", unit_suggestions=("boyz",),
            ),
        ),
    )
    res = scene.evaluate_scene(gt, pred)
    assert res.detection.tp == 2
    # One matched box has wrong unit → scene_top3 should fail
    assert res.scene_top3_pass is False


def test_aggregate_composes_per_scene_correctly():
    gt = _gt_with_two_minis()
    # Scene 1: perfect
    pred1 = scene.ScenePrediction(
        image_path="s1.jpg",
        minis=(
            scene.PredictedMini(
                bbox=(10.0, 10.0, 100.0, 100.0), faction="space_marines",
                unit_suggestions=("captain",)),
            scene.PredictedMini(
                bbox=(300.0, 10.0, 100.0, 100.0), faction="orks",
                unit_suggestions=("boyz",)),
        ),
    )
    # Scene 2: misses one
    pred2 = scene.ScenePrediction(
        image_path="s2.jpg",
        minis=(
            scene.PredictedMini(
                bbox=(10.0, 10.0, 100.0, 100.0), faction="space_marines",
                unit_suggestions=("captain",)),
        ),
    )
    results = [
        scene.evaluate_scene(gt, pred1),
        scene.evaluate_scene(gt, pred2),
    ]
    agg = scene.aggregate(results)
    assert agg.num_scenes == 2
    assert agg.num_minis == 4
    # Total tp=3, fn=1 → recall 0.75
    assert agg.detection_recall == pytest.approx(0.75)
    # unit_top1 = 3/3 matched boxes correct = 1.0
    assert agg.unit_top1 == pytest.approx(1.0)
    # scene_top3: scene 1 pass, scene 2 fail (detection miss) → 0.5
    assert agg.scene_top3 == pytest.approx(0.5)


def test_evaluate_loop_with_fake_pipeline():
    gt = _gt_with_two_minis()
    pred = scene.ScenePrediction(
        image_path=gt.image_path,
        minis=(
            scene.PredictedMini(
                bbox=(10.0, 10.0, 100.0, 100.0), faction="space_marines",
                unit_suggestions=("captain",)),
            scene.PredictedMini(
                bbox=(300.0, 10.0, 100.0, 100.0), faction="orks",
                unit_suggestions=("boyz",)),
        ),
    )
    pipe = _FakePipeline(pred)
    agg = scene.evaluate(pipe, [gt])
    assert agg.num_scenes == 1
    assert agg.scene_top3 == 1.0


def test_scene_metrics_to_dict_serializable():
    agg = scene.SceneMetrics(
        num_scenes=1, num_minis=2, detection_recall=0.5, unit_top3=0.75,
    )
    d = agg.to_dict()
    # Should be JSON-safe
    s = json.dumps(d)
    assert "scene_top3" in s
    # per_scene field excluded from dict
    assert "per_scene" not in d


def test_load_ground_truth_from_manifest():
    manifest = [
        {
            "image_path": "fixtures/s.jpg",
            "minis": [
                {"bbox": [0, 0, 10, 10], "faction": "space_marines",
                 "unit_slug": "captain"},
                {"bbox": [20, 20, 10, 10], "faction": "orks",
                 "unit_slug": "boyz"},
            ],
        }
    ]
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "m.json"
        p.write_text(json.dumps(manifest))
        scenes = scene.load_ground_truth(p)
        assert len(scenes) == 1
        assert scenes[0].num_minis == 2
        assert scenes[0].minis[0].faction == "space_marines"
