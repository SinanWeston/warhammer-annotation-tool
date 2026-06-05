"""Tests for SAM 3 pseudo-label triage (eval/triage.py)."""
from __future__ import annotations

from photoanalyzer.eval import triage


def _rec(name, boxes, w=100, h=100):
    return {"imagePath": f"/d/{name}", "width": w, "height": h, "boxes": boxes}


def _box(x, y, bw, bh, score=0.9):
    return {"xywh": [x, y, bw, bh], "score": score}


def test_zero_box_routes_to_review_not_drop():
    t = triage.triage_predictions([_rec("empty.jpg", [])])[0]
    assert t.bucket == "zero_box"
    assert t.reasons == ["zero_box"]
    assert t.needs_review is True            # review, never silent-drop


def test_confident_normal_image_is_clean():
    boxes = [_box(0, 0, 10, 20, 0.9), _box(30, 0, 10, 20, 0.85)]
    t = triage.triage_predictions([_rec("ok.jpg", boxes)])[0]
    assert t.bucket == "has_boxes"
    assert t.reasons == []
    assert t.needs_review is False


def test_low_confidence_flagged():
    t = triage.triage_predictions([_rec("unsure.jpg", [_box(0, 0, 10, 20, 0.2)])])[0]
    assert "low_conf" in t.reasons


def test_geom_outlier_big_box_is_terrain_fp():
    # one box covering 80% of the frame → terrain/vehicle false positive
    t = triage.triage_predictions([_rec("terrain.jpg", [_box(0, 0, 90, 90, 0.9)])])[0]
    assert "geom_outlier" in t.reasons


def test_geom_outlier_extreme_aspect():
    t = triage.triage_predictions([_rec("sliver.jpg", [_box(0, 0, 60, 5, 0.9)])])[0]
    assert "geom_outlier" in t.reasons


def test_count_outlier_relative_to_batch_median():
    # batch median nonzero count = 2; an image with 12 boxes is a count outlier
    normal = [_rec(f"n{i}.jpg", [_box(0, 0, 5, 5), _box(6, 0, 5, 5)]) for i in range(5)]
    storm = _rec("storm.jpg", [_box(j * 6, 0, 5, 5) for j in range(12)])
    triaged = {t.basename: t for t in triage.triage_predictions(normal + [storm])}
    assert "count_outlier" in triaged["storm.jpg"].reasons
    assert triaged["n0.jpg"].reasons == []


def test_priority_orders_low_conf_before_zero_box():
    recs = [_rec("z.jpg", []), _rec("lc.jpg", [_box(0, 0, 10, 20, 0.1)])]
    triaged = triage.triage_predictions(recs)
    ordered = sorted(triaged, key=lambda t: t.priority)
    assert ordered[0].basename == "lc.jpg"      # low-conf reviewed before 0-box
    assert ordered[-1].basename == "z.jpg"


def test_summarize_counts():
    recs = [
        _rec("a.jpg", [_box(0, 0, 10, 20, 0.9)]),       # clean
        _rec("b.jpg", []),                               # zero-box
        _rec("c.jpg", [_box(0, 0, 10, 20, 0.1)]),        # low-conf
    ]
    s = triage.summarize(triage.triage_predictions(recs))
    assert s["n_images"] == 3
    assert s["zero_box"] == 1
    assert s["has_boxes"] == 2
    assert s["needs_review"] == 2                        # zero-box + low-conf
    assert s["by_reason"]["zero_box"] == 1
    assert s["by_reason"]["low_conf"] == 1
