#!/usr/bin/env python3
"""One-shot migration: Weston's human-confirmed rows in data/labels.csv
→ equivalent annotation JSONs under backend/training_data_annotations/.

Context: the warhammer-analyzer labeller (v1 of the hand-labelling
workflow) wrote per-crop rows into data/labels.csv with bbox encoded in
notes. The project has since moved to the desktop annotator which keeps
per-scene JSONs with multiple bboxes per file. This script groups the
labels.csv rows by (instance_id, view_idx) and emits one JSON per scene
so nothing gets lost when we deprecate labels.csv.

Rules:
  - Only rows where suggested_by='human' AND labeller='Weston' are
    migrated. Anything else (weak_regex, scraped, test, etc.) is skipped.
  - `__bad_crop__` rows are deleted, not migrated. They represented
    "this detector proposal is wrong" in the old system; in the new
    annotator the equivalent is "no bbox drawn there", so nothing to
    carry forward.
  - `__unknown__` and empty unit_slug → migrated as bboxes with no
    unit_slug set (→ shows up as Pending in the annotator).

Idempotent: writes only scenes that don't already have an annotation
JSON, unless --force is passed. Backs up any overwritten JSON to a
sibling .bak-<timestamp> file.

Usage:
    yolo_env/bin/python3 scripts/migrate_labels_csv_to_annotator.py --dry-run
    yolo_env/bin/python3 scripts/migrate_labels_csv_to_annotator.py
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LABELS_CSV = REPO_ROOT / "data" / "labels.csv"
TRAINING_DATA = REPO_ROOT / "backend" / "training_data"
ANNOTATIONS_DIR = REPO_ROOT / "backend" / "training_data_annotations"

_BBOX_RE = re.compile(r"\bbbox=(\d+),(\d+),(\d+),(\d+)")


def parse_args():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force", action="store_true",
                   help="Overwrite existing JSONs (backed up to .bak-<ts>).")
    p.add_argument("--labeller", default="Weston",
                   help="Only migrate rows whose labeller matches this (default: Weston).")
    return p.parse_args()


def resolve_scene_path(faction: str, entry_id: str, view_idx: int) -> Path:
    """Match the symlink layout from scripts/seed_cmon_for_annotator.py:
    backend/training_data/<faction>/cmon/cmon_<entry>_<view:02d>.jpg"""
    return TRAINING_DATA / faction / "cmon" / f"cmon_{entry_id}_{view_idx:02d}.jpg"


def read_dimensions(path: Path) -> tuple[int, int]:
    """(width, height) from the image at `path`. Uses PIL so the
    migration doesn't need the full Node stack running."""
    from PIL import Image
    with Image.open(path) as im:
        return im.width, im.height


def image_id_from_path(abs_path: Path) -> str:
    """Mirror backend/src/services/annotationService.ts:getImageId —
    relative path from training_data with / → _ and extension stripped."""
    rel = abs_path.relative_to(TRAINING_DATA)
    return str(rel).replace("/", "_").replace("\\", "_").rsplit(".", 1)[0]


def main():
    args = parse_args()
    if not LABELS_CSV.exists():
        sys.exit(f"labels.csv not found at {LABELS_CSV}")

    # Pull qualifying rows.
    rows = [
        r for r in csv.DictReader(LABELS_CSV.open())
        if r.get("suggested_by") == "human"
        and r.get("labeller") == args.labeller
    ]
    if not rows:
        sys.exit(f"No rows with suggested_by=human and labeller={args.labeller!r}.")
    print(f"Loaded {len(rows)} rows.")

    # Group by (instance_id, view_idx). Each group → one annotation JSON.
    groups: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for r in rows:
        iid = r["instance_id"]
        if not iid or not iid.startswith("cmon:"):
            print(f"  ✗ skipping row with non-CMON instance_id: {iid!r}")
            continue
        try:
            vi = int(r["view_idx"] or 0)
        except ValueError:
            print(f"  ✗ skipping row with bad view_idx: {r['view_idx']!r}")
            continue
        groups[(iid, vi)].append(r)

    print(f"Scenes to emit: {len(groups)}")

    written = 0
    skipped_existing = 0
    skipped_no_scene = 0
    skipped_empty_group = 0

    for (instance_id, view_idx), members in sorted(groups.items()):
        entry_id = instance_id[len("cmon:"):]
        # Drop bad_crop rows — not annotations in the new model.
        usable = [m for m in members if m.get("unit_slug") != "__bad_crop__"]
        if not usable:
            print(f"  ○ {instance_id} view={view_idx}: all rows are __bad_crop__, skipping")
            skipped_empty_group += 1
            continue

        # Scene faction: take the most common among the usable rows;
        # ties break to whichever appears first. Non-sentinel classLabels
        # are set per-bbox from the row's faction.
        scene_faction = usable[0].get("faction") or "_unknown"

        scene_path = resolve_scene_path(scene_faction, entry_id, view_idx)
        if not scene_path.exists():
            # Check if a different faction's symlink exists (the symlink lives
            # under whatever faction the seed script inferred, not necessarily
            # what the user later labelled). Fall back to glob.
            candidates = list(TRAINING_DATA.glob(f"*/cmon/cmon_{entry_id}_{view_idx:02d}.jpg"))
            if not candidates:
                print(f"  ✗ {instance_id} view={view_idx}: no scene symlink found")
                skipped_no_scene += 1
                continue
            scene_path = candidates[0]
            scene_faction = scene_path.parent.parent.name

        image_id = image_id_from_path(scene_path)
        annotation_path = ANNOTATIONS_DIR / f"{image_id}.json"

        if annotation_path.exists() and not args.force:
            print(f"  ⤷ {image_id}: annotation already exists, skipping (use --force)")
            skipped_existing += 1
            continue

        try:
            width, height = read_dimensions(scene_path)
        except Exception as e:
            print(f"  ✗ {image_id}: failed to read dimensions: {e}")
            skipped_no_scene += 1
            continue

        # Build per-bbox annotations from the bbox=x,y,w,h in each row's notes.
        anns = []
        for i, r in enumerate(usable):
            m = _BBOX_RE.search(r.get("notes") or "")
            if not m:
                print(f"  !  {image_id}: row {i} has no bbox= tag — skipping bbox")
                continue
            bx, by, bw, bh = (int(x) for x in m.groups())
            ann: dict = {
                "id": f"migrated-{entry_id}-v{view_idx}-b{i}",
                "modelBbox": {"x": float(bx), "y": float(by), "width": float(bw), "height": float(bh)},
                "classLabel": r.get("faction") or scene_faction,
            }
            slug = (r.get("unit_slug") or "").strip()
            # Sentinel __unknown__ and empty slugs both become "no unit
            # set" in the annotator (→ this image shows up as Pending).
            if slug and not (slug.startswith("__") and slug.endswith("__")):
                ann["unit_slug"] = slug
            anns.append(ann)

        if not anns:
            print(f"  ○ {image_id}: no usable bboxes after parse — skipping")
            skipped_empty_group += 1
            continue

        # Pick an `annotatedAt`: latest created_at in the group so the
        # JSON reflects when the last row was touched.
        last_touched = max(r.get("created_at") or "" for r in usable) or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        payload = {
            "imageId": image_id,
            "imagePath": str(scene_path),
            "faction": scene_faction,
            "source": "cmon",
            "width": width,
            "height": height,
            "annotations": anns,
            "rejectedPredictions": [],
            "redrawnPredictions": [],
            "annotatedAt": last_touched,
            "annotatedBy": args.labeller.lower(),
            "migratedFrom": "data/labels.csv",
        }

        if args.dry_run:
            print(f"  [dry] {image_id}: {len(anns)} bbox(es), faction={scene_faction}")
            continue

        # Atomic write with .bak backup if overwriting.
        if annotation_path.exists():
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            shutil.copy2(annotation_path, annotation_path.with_suffix(annotation_path.suffix + f".bak-{ts}"))

        ANNOTATIONS_DIR.mkdir(parents=True, exist_ok=True)
        tmp = annotation_path.with_suffix(annotation_path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        tmp.replace(annotation_path)
        print(f"  ✓ {image_id}: wrote {len(anns)} bbox(es), faction={scene_faction}")
        written += 1

    print()
    print(f"Summary:")
    print(f"  written: {written}")
    print(f"  skipped (already exists): {skipped_existing}")
    print(f"  skipped (no scene image): {skipped_no_scene}")
    print(f"  skipped (no usable bboxes): {skipped_empty_group}")
    if args.dry_run:
        print("\n--dry-run: no files touched.")


if __name__ == "__main__":
    main()
