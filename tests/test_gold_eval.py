"""Tests for the gold-set detection eval harness (eval/gold.py, eval/boxconv.py)."""
from __future__ import annotations

import json

import pytest

from photoanalyzer.eval import boxconv, gold
from photoanalyzer.eval.gold import GoldImage, Slice


# ── density buckets ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("n,expected", [
    (0, "single"), (1, "single"), (2, "sparse"), (4, "sparse"),
    (5, "medium"), (10, "medium"), (11, "crowded"), (40, "crowded"),
])
def test_density_bucket(n, expected):
    assert gold.density_bucket(n) == expected


# ── helpers ─────────────────────────────────────────────────────────────────
def _img(basename, boxes, labels, bucket_faction="necrons", w=100, h=100):
    return GoldImage(basename=basename, filepath=f"/x/{basename}",
                     faction_v1=bucket_faction, source="test",
                     width=w, height=h, boxes=tuple(boxes), labels=tuple(labels))


# ── score_gold ──────────────────────────────────────────────────────────────
def test_gold_vs_gold_is_perfect():
    """Scoring gold against itself → recall 1.0, count-MAE 0."""
    g = [
        _img("a.jpg", [(0, 0, 10, 10)], ["necrons"]),
        _img("b.jpg", [(0, 0, 10, 10), (50, 50, 10, 10)], ["tyranids", "tyranids"]),
    ]
    preds = {gi.basename: list(gi.boxes) for gi in g}
    r = gold.score_gold(g, preds)
    assert r.overall.recall == 1.0
    assert r.overall.precision == 1.0
    assert r.overall.count_mae == 0.0
    assert r.overall.pct_within1 == 1.0


def test_merge_failure_is_penalized():
    """The product-fatal bug: two adjacent models detected as one box.
    Recall must drop AND count-MAE must register the under-count."""
    g = [_img("crowd.jpg", [(0, 0, 10, 10), (12, 0, 10, 10)], ["necrons", "necrons"])]
    # one pred box swallowing both models — high overlap with neither at IoU 0.5
    preds = {"crowd.jpg": [(0, 0, 22, 10)]}
    r = gold.score_gold(g, preds, iou_threshold=0.5)
    assert r.overall.recall < 1.0           # at least one GT unmatched
    assert r.overall.count_mae == 1.0       # |1 pred − 2 gt| = 1
    # a perfect-count detector on the same scene scores count-MAE 0
    good = {"crowd.jpg": [(0, 0, 10, 10), (12, 0, 10, 10)]}
    assert gold.score_gold(g, good).overall.count_mae == 0.0


def test_per_faction_recall_slices_by_gt_label():
    g = [_img("m.jpg",
              [(0, 0, 10, 10), (50, 0, 10, 10), (0, 50, 10, 10)],
              ["death_guard", "necrons", "necrons"])]
    # detect the death_guard + one necron, miss the other necron
    preds = {"m.jpg": [(0, 0, 10, 10), (50, 0, 10, 10)]}
    r = gold.score_gold(g, preds)
    assert r.by_faction["death_guard"].recall == 1.0
    assert r.by_faction["necrons"].recall == 0.5
    assert r.by_faction["necrons"].n_gt == 2


def test_density_slicing_routes_images_to_buckets():
    g = [
        _img("s.jpg", [(0, 0, 5, 5)], ["necrons"]),                       # single
        _img("c.jpg", [(i * 6, 0, 5, 5) for i in range(12)],
             ["necrons"] * 12),                                           # crowded
    ]
    preds = {gi.basename: list(gi.boxes) for gi in g}
    r = gold.score_gold(g, preds)
    assert r.by_density["single"].n_images == 1
    assert r.by_density["crowded"].n_images == 1
    assert r.by_density["crowded"].n_gt == 12
    assert r.by_density["sparse"].n_images == 0


def test_missing_prediction_counts_as_full_miss():
    g = [_img("gone.jpg", [(0, 0, 10, 10)], ["necrons"])]
    r = gold.score_gold(g, {})
    assert r.overall.recall == 0.0
    assert r.missing_predictions == ["gone.jpg"]
    assert r.overall.count_mae == 1.0       # |0 pred − 1 gt|


def test_recall_at_iou_sweep_reveals_loose_localization():
    """A box that's close but not tight matches at 0.3 but not 0.7 — the
    box-convention signature the sweep is meant to surface."""
    g = [_img("x.jpg", [(0, 0, 10, 10)], ["necrons"])]
    preds = {"x.jpg": [(0, 0, 13, 13)]}     # IoU ≈ 0.59
    r = gold.score_gold(g, preds, iou_sweep=(0.3, 0.5, 0.7))
    assert r.recall_at_iou[0.3] == 1.0
    assert r.recall_at_iou[0.7] == 0.0
    assert r.recall_at_iou[0.3] >= r.recall_at_iou[0.5] >= r.recall_at_iou[0.7]


# ── load_gold / load_predictions (real file I/O) ────────────────────────────
def test_load_gold_denormalizes_with_real_dims(tmp_path):
    from PIL import Image

    img_path = tmp_path / "pic.jpg"
    Image.new("RGB", (200, 100), "white").save(img_path)
    gold_json = tmp_path / "gold.json"
    gold_json.write_text(json.dumps({
        "name": "t", "n_images": 1, "n_boxes": 1,
        "images": [{
            "filepath": str(img_path), "basename": "pic.jpg",
            "faction_v1": "necrons", "source": "test",
            "boxes": [{"label": "necrons", "bbox_xywh_norm": [0.5, 0.0, 0.5, 1.0]}],
        }],
    }))
    loaded = gold.load_gold(gold_json, dims_cache=tmp_path / "dims.json")
    assert len(loaded) == 1
    g = loaded[0]
    assert (g.width, g.height) == (200, 100)
    # 0.5*200=100, 0.0*100=0, 0.5*200=100, 1.0*100=100
    assert g.boxes[0] == (100.0, 0.0, 100.0, 100.0)
    assert (tmp_path / "dims.json").exists()       # cache written


def test_load_predictions_applies_score_threshold(tmp_path):
    (tmp_path / "im1.json").write_text(json.dumps({
        "imagePath": "/data/im1.jpg",
        "boxes": [{"xywh": [0, 0, 5, 5], "score": 0.9},
                  {"xywh": [9, 9, 5, 5], "score": 0.1}],
    }))
    preds = gold.load_predictions(tmp_path, score_thresh=0.5)
    assert preds["im1.jpg"] == [(0, 0, 5, 5)]      # low-score box dropped


# ── boxconv ─────────────────────────────────────────────────────────────────
def test_extend_box_to_base_pads_bottom_only():
    assert boxconv.extend_box_to_base((10, 20, 30, 40), 0.10) == (10, 20, 30, 44.0)


def test_extend_box_to_base_clamps_to_image_height():
    # box bottom at y+h=95, img_h=100 → can grow at most to h=80
    assert boxconv.extend_box_to_base((0, 20, 30, 75), 0.5, img_h=100) == (0, 20, 30, 80)


def test_base_extension_recovers_recall_on_clipped_boxes():
    """End-to-end: mask-tight (base-clipped) preds miss at IoU 0.5; after
    base extension they match. This is the whole reconciliation case."""
    g = [GoldImage("p.jpg", "/x/p.jpg", "necrons", "t", 100, 100,
                   boxes=((10, 10, 30, 60),), labels=("necrons",))]
    # pred clips the bottom 12px of the base → IoU with gold ≈ 0.78... make it tighter
    clipped = {"p.jpg": [(10, 10, 30, 40)]}        # IoU = (30*40)/(30*60)=0.667
    before = gold.score_gold(g, clipped, iou_threshold=0.7)
    assert before.overall.recall == 0.0
    fixed = boxconv.apply_base_extension(clipped, pad_frac=0.5)   # 40→60
    after = gold.score_gold(g, fixed, iou_threshold=0.7)
    assert after.overall.recall == 1.0


def test_convention_diagnostic_flags_base_clipping():
    # gold extends 20px lower than pred (clipped base), aligned otherwise
    gboxes = {"p.jpg": [(10, 10, 30, 60)]}         # bottom at 70
    preds = {"p.jpg": [(10, 10, 30, 40)]}          # bottom at 50 → gap 20/60=0.33
    d = boxconv.convention_diagnostic(gboxes, preds, iou_threshold=0.3)
    assert d.n_matched == 1
    assert d.bottom_gap > 0.3
    assert abs(d.top_gap) < 0.01
    assert d.base_clip_signature is True
