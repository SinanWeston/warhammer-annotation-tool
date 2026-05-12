"""Crop extraction loop — runs a detector over a stream of source images and
writes (crop_image, label_row) pairs into `data/`.

Source-agnostic: takes an iterator of SourceImage records so the same loop
handles CMON, GW shop, Dakka, user photos, and future sources.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, Optional

from PIL import Image

from ..detect.base import Detection, Detector
from .schema import LabelRecord, V2_COLUMNS, read_labels_csv, write_labels_csv


log = logging.getLogger(__name__)


# ── source-image record ────────────────────────────────────────────────────
@dataclass
class SourceImage:
    """One input image that belongs to an instance (an entry / mini / photo set)."""
    image_path: Path          # absolute path on disk
    source: str               # "cmon" | "gw_shop" | etc. (photoanalyzer.label.schema.VALID_SOURCES)
    source_ref: str           # URL or "{source}:{id}"
    instance_id: str          # groups multi-view shots of the same mini
    view_idx: int             # 0-based view index within the instance
    title: str = ""           # free-text title (for notes)
    artist: str = ""          # free-text artist (for notes)
    extra_notes: str = ""     # anything else worth capturing


@dataclass
class ExtractStats:
    images_seen: int = 0
    images_skipped_resume: int = 0
    images_no_boxes: int = 0
    crops_written: int = 0
    multi_box_images: int = 0
    per_source: dict[str, int] = field(default_factory=dict)


# ── padding + cropping helpers ─────────────────────────────────────────────
def pad_bbox(
    bbox: tuple[float, float, float, float],
    img_w: int,
    img_h: int,
    pad_frac: float = 0.05,
) -> tuple[int, int, int, int]:
    """Add `pad_frac` of max(w,h) on all sides; clamp to image bounds.

    Matches `scripts/phase1/extract_gt_crops.py:75-85` behaviour."""
    x, y, w, h = bbox
    pad = max(w, h) * pad_frac
    x0 = max(0, int(round(x - pad)))
    y0 = max(0, int(round(y - pad)))
    x1 = min(img_w, int(round(x + w + pad)))
    y1 = min(img_h, int(round(y + h + pad)))
    return x0, y0, x1, y1


def _build_crop_path(
    out_root: Path,
    source: str,
    instance_id: str,
    view_idx: int,
    box_idx: int,
) -> Path:
    # instance_id looks like "cmon:475293" — strip the source prefix for on-disk
    # layout; crop_path is then stable independent of source-key naming.
    iid = instance_id.split(":", 1)[-1] if ":" in instance_id else instance_id
    return out_root / source / iid / f"{view_idx:02d}_{box_idx:02d}.jpg"


def _rel_path_str(p: Path) -> str:
    """Return a path string relative to `cwd` if possible, else the absolute
    path. We prefer repo-relative so labels.csv stays portable across checkouts.
    """
    if not p.is_absolute():
        return str(p)
    try:
        return str(p.relative_to(Path.cwd()))
    except ValueError:
        return str(p)


# ── main loop ──────────────────────────────────────────────────────────────
def extract_crops_for_source(
    images: Iterable[SourceImage],
    detector: Detector,
    labels_csv_path: Path,
    crops_root: Path,
    *,
    min_detector_confidence: float = 0.25,
    pad_frac: float = 0.05,
    jpeg_quality: int = 92,
    resume: bool = True,
    batch_size: int = 50,
    nobox_log_dir: Optional[Path] = None,
) -> ExtractStats:
    """Extract crops from `images`, appending label rows to `labels_csv_path`.

    - If `resume=True`: reads labels_csv_path first and skips any `SourceImage`
      whose (source, instance_id, view_idx) already has a row — safe across
      interruptions.
    - Writes a new `data/labels.csv` with the v2 header if the file doesn't exist.
    - JPEG quality 92 balances disk size vs. faithfulness for retrieval embedding.
    """
    labels_csv_path = Path(labels_csv_path)
    crops_root = Path(crops_root)
    crops_root.mkdir(parents=True, exist_ok=True)

    stats = ExtractStats()

    # Build resume index: any crop_path already present means we skip that image.
    existing_crop_paths: set[str] = set()
    if resume and labels_csv_path.exists():
        for rec in read_labels_csv(labels_csv_path):
            if rec.crop_path:
                existing_crop_paths.add(rec.crop_path)

    # If labels.csv doesn't exist, create it with just the header.
    if not labels_csv_path.exists():
        write_labels_csv(labels_csv_path, [])

    pending: list[LabelRecord] = []

    def _flush():
        nonlocal pending
        if not pending:
            return
        write_labels_csv(labels_csv_path, pending, append=True)
        stats.crops_written += len(pending)
        pending = []

    for src in images:
        stats.images_seen += 1
        stats.per_source[src.source] = stats.per_source.get(src.source, 0) + 1

        # Resume check: if the first-box crop path already exists in labels.csv,
        # assume this (instance, view) was processed. We don't know box count in
        # advance, so we match on the `00_00.jpg` sentinel.
        sentinel_path = _build_crop_path(
            crops_root, src.source, src.instance_id, src.view_idx, 0
        )
        sentinel_rel = _rel_path_str(sentinel_path)
        if resume and (sentinel_rel in existing_crop_paths
                       or str(sentinel_path) in existing_crop_paths):
            stats.images_skipped_resume += 1
            continue

        # Load + detect
        try:
            img = Image.open(src.image_path).convert("RGB")
        except Exception as e:
            log.warning("open failed: %s (%s)", src.image_path, e)
            continue

        detections = detector.predict(src.image_path)
        detections = [d for d in detections if d.confidence >= min_detector_confidence]
        if not detections:
            stats.images_no_boxes += 1
            if nobox_log_dir is not None:
                nobox_log_dir.mkdir(parents=True, exist_ok=True)
                (nobox_log_dir / f"{src.instance_id.replace(':','_')}_v{src.view_idx}_nobox.json"
                 ).write_text(json.dumps({
                    "image_path": str(src.image_path),
                    "source": src.source,
                    "source_ref": src.source_ref,
                    "instance_id": src.instance_id,
                    "view_idx": src.view_idx,
                }))
            continue

        if len(detections) > 1:
            stats.multi_box_images += 1

        for box_idx, det in enumerate(detections):
            out_path = _build_crop_path(
                crops_root, src.source, src.instance_id, src.view_idx, box_idx,
            )
            out_path.parent.mkdir(parents=True, exist_ok=True)

            x0, y0, x1, y1 = pad_bbox(det.bbox, img.width, img.height, pad_frac)
            crop = img.crop((x0, y0, x1, y1))
            # Ultra-defensive: degenerate crops (zero area) shouldn't be written
            if crop.width <= 0 or crop.height <= 0:
                continue
            crop.save(out_path, format="JPEG", quality=jpeg_quality)

            # Build label row. `confidence` column is reserved for label confidence,
            # not detection confidence — the latter goes into `notes`. We ALSO
            # preserve the detector's predicted class (faction) because the YOLO
            # model is actually a 15-24-way faction classifier; its prediction
            # is a useful second opinion alongside the title.
            notes_bits = [f"detector_conf={det.confidence:.3f}"]
            if det.class_name:
                notes_bits.append(f"detector_faction={det.class_name}")
            if src.title:
                notes_bits.append(f"title: {src.title!r}")
            if src.artist:
                notes_bits.append(f"artist: {src.artist!r}")
            if len(detections) > 1:
                notes_bits.append("multi-box")
            if src.extra_notes:
                notes_bits.append(src.extra_notes)
            notes = "; ".join(notes_bits)

            # Repo-relative path (callers pass crops_root under repo root)
            crop_path_rel = _rel_path_str(out_path)

            pending.append(LabelRecord(
                crop_path=crop_path_rel,
                source=src.source,
                source_ref=src.source_ref,
                instance_id=src.instance_id,
                view_idx=src.view_idx,
                faction="",
                unit_slug="",
                suggested_by="",
                confidence=None,
                labeller="",
                split="",
                notes=notes,
            ))

            if len(pending) >= batch_size:
                _flush()

    _flush()
    return stats


# ── CMON manifest → SourceImage stream ─────────────────────────────────────
def iter_cmon_source_images(
    cmon_root: Path,
    *,
    limit: int | None = None,
) -> Iterator[SourceImage]:
    """Yield one SourceImage per CMON image.

    `cmon_root` is the top-level `scripts/cmon/` directory. Manifests are
    expected at `{cmon_root}/images/{run}/{entry_id}/manifest.json` with
    `local_paths` entries relative to `cmon_root` (e.g.
    `images/single/475293/00.jpg`).

    Yields in stable order: by run, then by entry_id.
    """
    cmon_root = Path(cmon_root)
    # De-dupe: one entry_id may have manifests under multiple run dirs; keep
    # the first we find (alphabetical run order: 'all' before 'single').
    seen_entries: set[str] = set()
    manifests = sorted(cmon_root.glob("images/*/*/manifest.json"))
    yielded = 0
    for mp in manifests:
        try:
            m = json.loads(mp.read_text())
        except Exception as e:
            log.warning("bad manifest %s: %s", mp, e)
            continue
        entry_id = str(m.get("id", mp.parent.name))
        if entry_id in seen_entries:
            continue
        seen_entries.add(entry_id)
        instance_id = f"cmon:{entry_id}"
        title = m.get("title") or m.get("tile_title") or ""
        artist = m.get("artist") or m.get("tile_artist") or ""
        for view_idx, p in enumerate(m.get("local_paths") or []):
            abs_path = Path(p)
            if not abs_path.is_absolute():
                abs_path = cmon_root / p
            if not abs_path.exists():
                log.warning("image missing for %s: %s", instance_id, abs_path)
                continue
            yield SourceImage(
                image_path=abs_path,
                source="cmon",
                source_ref=f"cmon:{entry_id}",
                instance_id=instance_id,
                view_idx=view_idx,
                title=title,
                artist=artist,
            )
        yielded += 1
        if limit is not None and yielded >= limit:
            return
