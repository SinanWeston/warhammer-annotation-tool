#!/usr/bin/env python3
"""
Sync training_data_v2 images into the annotator's backend/training_data/ directory.

Creates symlinks (not copies) from:
  training_data_v2/{faction}/isolation/{unit_slug}/*.jpg
  training_data_v2/{faction}/combat_patrol/*.jpg

Into:
  backend/training_data/{faction}/ebay/*.jpg  (flat, no unit subfolders)

Run this any time after scraping to make new images visible in the annotator.

Usage:
    python3 scripts/sync_to_annotator.py
    python3 scripts/sync_to_annotator.py --dry-run
"""

import argparse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
V2_DIR   = BASE_DIR / "training_data_v2"
ANNOT_DIR = BASE_DIR / "backend" / "training_data"


def sync(dry_run: bool = False):
    if not V2_DIR.exists():
        print("training_data_v2/ not found — nothing to sync.")
        return

    total_new = 0
    total_existing = 0

    for faction_dir in sorted(V2_DIR.iterdir()):
        if not faction_dir.is_dir() or faction_dir.name == "metadata":
            continue

        faction = faction_dir.name
        dest_dir = ANNOT_DIR / faction / "ebay"

        if not dry_run:
            dest_dir.mkdir(parents=True, exist_ok=True)

        faction_new = 0

        # isolation/{unit_slug}/*.jpg
        isolation = faction_dir / "isolation"
        if isolation.exists():
            for unit_dir in sorted(isolation.iterdir()):
                if not unit_dir.is_dir():
                    continue
                for jpg in sorted(unit_dir.glob("*.jpg")):
                    link = dest_dir / jpg.name
                    if link.exists() or link.is_symlink():
                        total_existing += 1
                        continue
                    if dry_run:
                        print(f"  [DRY RUN] {faction}/ebay/{jpg.name}")
                    else:
                        link.symlink_to(jpg.resolve())
                    faction_new += 1
                    total_new += 1

        # combat_patrol/*.jpg
        cp_dir = faction_dir / "combat_patrol"
        if cp_dir.exists():
            for jpg in sorted(cp_dir.glob("*.jpg")):
                link = dest_dir / jpg.name
                if link.exists() or link.is_symlink():
                    total_existing += 1
                    continue
                if dry_run:
                    print(f"  [DRY RUN] {faction}/ebay/{jpg.name}")
                else:
                    link.symlink_to(jpg.resolve())
                faction_new += 1
                total_new += 1

        if faction_new > 0 or dry_run:
            all_links = len(list(dest_dir.glob("*.jpg"))) if dest_dir.exists() else 0
            print(f"  {faction:30s} +{faction_new:4d} new  ({all_links} total in ebay/)")

    print(f"\nDone. {total_new} new symlinks created, {total_existing} already existed.")
    if dry_run:
        print("(dry run — no files written)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    sync(args.dry_run)
