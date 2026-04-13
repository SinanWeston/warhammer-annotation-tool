#!/usr/bin/env python3
"""
Phase 1 — copy labelled crops into gallery/ and queries/ directories.

Reads scripts/phase2/labels.csv (must have a `split` column from auto_split.py)
and copies each crop to:

    scripts/phase2/gallery/{faction}/{unit_slug}/{crop_basename}
    scripts/phase2/queries/{faction}/{unit_slug}/{crop_basename}

Idempotent: re-running overwrites the existing layout.

Usage:
    yolo_env/bin/python3 scripts/phase2/build_gallery.py
"""

from __future__ import annotations

import csv
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PHASE2 = REPO_ROOT / "scripts" / "phase2"
LABELS_CSV = PHASE2 / "labels.csv"
GALLERY_DIR = PHASE2 / "gallery"
QUERIES_DIR = PHASE2 / "queries"


def main():
    if not LABELS_CSV.exists():
        sys.exit(f"labels.csv not found at {LABELS_CSV}.")

    # Wipe and recreate (idempotent).
    for d in (GALLERY_DIR, QUERIES_DIR):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)

    gallery_count = 0
    query_count = 0
    missing: list[str] = []

    with LABELS_CSV.open() as f:
        for row in csv.DictReader(f):
            crop_path = REPO_ROOT / row["crop_path"]
            if not crop_path.exists():
                missing.append(row["crop_path"])
                continue
            faction = row["faction"].strip()
            unit = row["unit_slug"].strip()
            split = row["split"].strip()
            if not unit or not split:
                continue
            target_root = GALLERY_DIR if split == "gallery" else QUERIES_DIR
            target_dir = target_root / faction / unit
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / crop_path.name
            shutil.copy2(crop_path, target)
            if split == "gallery":
                gallery_count += 1
            else:
                query_count += 1

    print(f"Gallery: {gallery_count} crops → {GALLERY_DIR.relative_to(REPO_ROOT)}")
    print(f"Queries: {query_count} crops → {QUERIES_DIR.relative_to(REPO_ROOT)}")
    if missing:
        print(f"\n⚠ {len(missing)} rows referenced missing crop files:")
        for m in missing[:5]:
            print(f"    {m}")
        if len(missing) > 5:
            print(f"    ... and {len(missing) - 5} more")


if __name__ == "__main__":
    main()
