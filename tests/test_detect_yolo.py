"""Smoke test for photoanalyzer.detect.yolo.

Skipped automatically when `runs/yolo11x_run2_best.pt` is absent, so CI /
minimal installs don't fail just because the 110 MB model isn't checked out.
"""

from __future__ import annotations

from pathlib import Path

import pytest

MODEL = Path("runs/yolo11x_run2_best.pt")
if not MODEL.exists():
    pytest.skip(f"YOLO model not at {MODEL} — skipping smoke test",
                allow_module_level=True)

try:
    import ultralytics  # noqa: F401
except Exception as e:  # pragma: no cover
    pytest.skip(f"ultralytics not importable: {e}", allow_module_level=True)

from photoanalyzer.detect.yolo import YoloDetector


def _find_annotated_image():
    """Pick any CMON image that's on disk for a smoke predict."""
    candidates = list(Path("scripts/cmon/images").rglob("*.jpg"))
    return candidates[0] if candidates else None


def test_yolo_loads_and_predicts_once():
    img = _find_annotated_image()
    if img is None:
        pytest.skip("no CMON image available to smoke-predict against")
    det = YoloDetector(model_path=MODEL, conf_threshold=0.05)
    results = det.predict(img)
    # Model loaded without error, returned a list (possibly empty)
    assert isinstance(results, list)
    # If it returned any, they're well-formed Detection objects
    for r in results:
        assert r.confidence >= 0.05
        x, y, w, h = r.bbox
        assert w > 0 and h > 0


def test_yolo_predict_many_returns_aligned_list():
    imgs = list(Path("scripts/cmon/images").rglob("*.jpg"))[:2]
    if len(imgs) < 2:
        pytest.skip("need at least 2 images for batch smoke test")
    det = YoloDetector(model_path=MODEL, conf_threshold=0.05)
    batched = det.predict_many(imgs)
    assert len(batched) == len(imgs)
    for result in batched:
        assert isinstance(result, list)
