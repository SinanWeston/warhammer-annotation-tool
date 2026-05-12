"""Tests for photoanalyzer.label.extract — crop extraction loop.

Uses a stub Detector so no model is loaded. Real YOLO is exercised separately
(and skipped if the model file isn't present) in test_detect_yolo.py.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from PIL import Image

from photoanalyzer.detect.base import Detection, Detector
from photoanalyzer.label.extract import (
    SourceImage,
    extract_crops_for_source,
    iter_cmon_source_images,
    pad_bbox,
)
from photoanalyzer.label.schema import read_labels_csv


# ── pad_bbox ───────────────────────────────────────────────────────────────
def test_pad_bbox_interior_adds_padding():
    x0, y0, x1, y1 = pad_bbox((100, 100, 100, 100), img_w=500, img_h=500, pad_frac=0.1)
    # 10% of max(100,100)=100 → 10 pad each side
    assert (x0, y0, x1, y1) == (90, 90, 210, 210)


def test_pad_bbox_clamps_to_image():
    x0, y0, x1, y1 = pad_bbox((0, 0, 100, 100), img_w=200, img_h=200, pad_frac=0.5)
    # Would pad -50 → clamped to 0. Would pad to 150 → clamped to 200.
    assert x0 == 0 and y0 == 0
    assert x1 == 150 and y1 == 150  # Note: +50 pad on far side stays in-bounds


def test_pad_bbox_clamps_at_right_edge():
    x0, y0, x1, y1 = pad_bbox((150, 150, 100, 100), img_w=200, img_h=200, pad_frac=0.5)
    assert x1 == 200 and y1 == 200


def test_pad_bbox_zero_pad():
    assert pad_bbox((10, 20, 30, 40), 500, 500, pad_frac=0.0) == (10, 20, 40, 60)


# ── stub detector ──────────────────────────────────────────────────────────
class _StubDetector(Detector):
    """Deterministic detector for tests — emits the boxes given at construction."""

    def __init__(self, boxes_per_image: dict[str, list[Detection]]):
        self.boxes_per_image = boxes_per_image

    def predict(self, image):
        key = str(image)
        return list(self.boxes_per_image.get(key, []))


def _write_test_image(path: Path, size=(400, 300), color=(80, 120, 160)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path, format="JPEG")


# ── extract_crops_for_source end-to-end ────────────────────────────────────
def test_extract_writes_crops_and_rows():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        img_path = td / "img" / "cmon_1.jpg"
        _write_test_image(img_path)

        detector = _StubDetector({
            str(img_path): [
                Detection(bbox=(50, 50, 100, 100), confidence=0.9,
                          class_id=0, class_name="space_marines"),
                Detection(bbox=(200, 100, 120, 90), confidence=0.7,
                          class_id=1, class_name="orks"),
            ]
        })

        images = [SourceImage(
            image_path=img_path, source="cmon",
            source_ref="cmon:1", instance_id="cmon:1", view_idx=0,
            title="Test Title", artist="Test Artist",
        )]

        stats = extract_crops_for_source(
            images, detector,
            labels_csv_path=td / "labels.csv",
            crops_root=td / "crops",
        )

        assert stats.images_seen == 1
        assert stats.crops_written == 2
        assert stats.multi_box_images == 1  # 2 boxes → multi
        # Crop files exist
        assert (td / "crops" / "cmon" / "1" / "00_00.jpg").exists()
        assert (td / "crops" / "cmon" / "1" / "00_01.jpg").exists()
        # CSV has 2 rows with the right metadata
        rows = list(read_labels_csv(td / "labels.csv"))
        assert len(rows) == 2
        for r in rows:
            assert r.source == "cmon"
            assert r.instance_id == "cmon:1"
            assert r.view_idx == 0
            assert r.source_ref == "cmon:1"
            assert "Test Title" in r.notes
            assert "Test Artist" in r.notes
            assert "detector_conf" in r.notes
            assert "multi-box" in r.notes


def test_extract_single_box_no_multibox_flag():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        img_path = td / "img" / "solo.jpg"
        _write_test_image(img_path)
        detector = _StubDetector({
            str(img_path): [Detection(bbox=(100, 100, 80, 80), confidence=0.8)]
        })
        images = [SourceImage(
            image_path=img_path, source="cmon",
            source_ref="cmon:2", instance_id="cmon:2", view_idx=0,
        )]
        stats = extract_crops_for_source(
            images, detector,
            labels_csv_path=td / "labels.csv",
            crops_root=td / "crops",
        )
        assert stats.crops_written == 1
        assert stats.multi_box_images == 0
        rows = list(read_labels_csv(td / "labels.csv"))
        assert "multi-box" not in rows[0].notes


def test_extract_zero_boxes_skips_and_logs():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        img_path = td / "img" / "empty.jpg"
        _write_test_image(img_path)
        detector = _StubDetector({})  # no boxes for anything
        images = [SourceImage(
            image_path=img_path, source="cmon",
            source_ref="cmon:3", instance_id="cmon:3", view_idx=0,
        )]
        nobox_dir = td / "nobox"
        stats = extract_crops_for_source(
            images, detector,
            labels_csv_path=td / "labels.csv",
            crops_root=td / "crops",
            nobox_log_dir=nobox_dir,
        )
        assert stats.images_no_boxes == 1
        assert stats.crops_written == 0
        # CSV exists (with just header) — loading yields empty list
        assert (td / "labels.csv").exists()
        assert list(read_labels_csv(td / "labels.csv")) == []
        # Sidecar nobox log written
        nobox_files = list(nobox_dir.glob("*.json"))
        assert len(nobox_files) == 1


def test_extract_respects_min_confidence():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        img_path = td / "img" / "lowconf.jpg"
        _write_test_image(img_path)
        detector = _StubDetector({
            str(img_path): [
                Detection(bbox=(10, 10, 50, 50), confidence=0.1),   # below threshold
                Detection(bbox=(100, 100, 50, 50), confidence=0.9),  # above
            ]
        })
        images = [SourceImage(
            image_path=img_path, source="cmon",
            source_ref="cmon:4", instance_id="cmon:4", view_idx=0,
        )]
        stats = extract_crops_for_source(
            images, detector,
            labels_csv_path=td / "labels.csv",
            crops_root=td / "crops",
            min_detector_confidence=0.5,
        )
        assert stats.crops_written == 1


def test_extract_is_resume_safe():
    """Re-running over the same SourceImage twice should not duplicate rows."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        img_path = td / "img" / "resume.jpg"
        _write_test_image(img_path)
        detector = _StubDetector({
            str(img_path): [Detection(bbox=(100, 100, 80, 80), confidence=0.9)]
        })
        images = [SourceImage(
            image_path=img_path, source="cmon",
            source_ref="cmon:5", instance_id="cmon:5", view_idx=0,
        )]
        # First run
        s1 = extract_crops_for_source(
            images, detector,
            labels_csv_path=td / "labels.csv",
            crops_root=td / "crops",
        )
        assert s1.crops_written == 1
        # Second run — must skip
        s2 = extract_crops_for_source(
            images, detector,
            labels_csv_path=td / "labels.csv",
            crops_root=td / "crops",
        )
        assert s2.crops_written == 0
        assert s2.images_skipped_resume == 1
        rows = list(read_labels_csv(td / "labels.csv"))
        assert len(rows) == 1


def test_extract_multiple_views_of_same_instance():
    """Three views of one CMON entry: different view_idx, same instance_id."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        imgs: list[SourceImage] = []
        preds = {}
        for i in range(3):
            p = td / "img" / f"v{i}.jpg"
            _write_test_image(p)
            preds[str(p)] = [Detection(bbox=(50, 50, 80, 80), confidence=0.85)]
            imgs.append(SourceImage(
                image_path=p, source="cmon",
                source_ref="cmon:6", instance_id="cmon:6", view_idx=i,
                title="Shared title",
            ))
        detector = _StubDetector(preds)
        stats = extract_crops_for_source(
            imgs, detector,
            labels_csv_path=td / "labels.csv",
            crops_root=td / "crops",
        )
        assert stats.crops_written == 3
        rows = list(read_labels_csv(td / "labels.csv"))
        assert sorted(r.view_idx for r in rows) == [0, 1, 2]
        assert all(r.instance_id == "cmon:6" for r in rows)


# ── CMON manifest iterator ─────────────────────────────────────────────────
def test_iter_cmon_source_images_parses_manifest():
    """Minimal fixture: a fake cmon_root with one manifest."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "cmon"
        man_dir = root / "images" / "single" / "475293"
        man_dir.mkdir(parents=True)
        # Create 2 fake images referenced by the manifest
        for i in range(2):
            img = man_dir / f"{i:02d}.jpg"
            _write_test_image(img)
        manifest = {
            "id": "475293",
            "title": "Necromunda",
            "artist": "DEN of IMAGINATION",
            "local_paths": [
                "images/single/475293/00.jpg",
                "images/single/475293/01.jpg",
            ],
        }
        (man_dir / "manifest.json").write_text(json.dumps(manifest))

        sources = list(iter_cmon_source_images(root))
        assert len(sources) == 2
        assert all(s.source == "cmon" for s in sources)
        assert all(s.instance_id == "cmon:475293" for s in sources)
        assert [s.view_idx for s in sources] == [0, 1]
        assert sources[0].title == "Necromunda"
        assert sources[0].artist == "DEN of IMAGINATION"
        assert sources[0].image_path.exists()


def test_iter_cmon_source_images_respects_limit():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "cmon"
        for entry_id in ["1", "2", "3"]:
            d = root / "images" / "single" / entry_id
            d.mkdir(parents=True)
            img = d / "00.jpg"
            _write_test_image(img)
            (d / "manifest.json").write_text(json.dumps({
                "id": entry_id,
                "local_paths": [f"images/single/{entry_id}/00.jpg"],
            }))
        sources = list(iter_cmon_source_images(root, limit=2))
        # limit counts entries, each with one view → 2 images
        assert len(sources) == 2


def test_iter_cmon_source_images_dedupes_across_runs():
    """Same entry_id under two run directories — keep only the first."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "cmon"
        for run in ("all", "single"):
            d = root / "images" / run / "475293"
            d.mkdir(parents=True)
            img = d / "00.jpg"
            _write_test_image(img)
            (d / "manifest.json").write_text(json.dumps({
                "id": "475293",
                "local_paths": [f"images/{run}/475293/00.jpg"],
            }))
        sources = list(iter_cmon_source_images(root))
        assert len(sources) == 1  # dedupe
