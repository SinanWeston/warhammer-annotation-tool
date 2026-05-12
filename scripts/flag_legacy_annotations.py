#!/usr/bin/env python3
"""One-shot grandfathering script. Tags every existing annotation JSON
that predates the `unit_slug` per-bbox field with:

    "legacy_no_unit": true

The backend's `isImagePending` check skips rows carrying this flag, so
the ~900 pre-unit_slug annotations don't flood the Pending queue when
you just want to see NEW incomplete work. The flag is not destructive —
a dedicated `status=legacy` query reveals them later if you want to
backfill units on the old corpus.

Rules:
  - Skip files that already have ANY bbox with a non-empty unit_slug
    (they're already "complete" in the new sense).
  - Skip files with a `migratedFrom` field (e.g. entries the
    migrate_labels_csv_to_annotator.py script just wrote — those are
    intentionally incomplete so the user can finish them).
  - Skip `.skip.json` files (those are flagged images, not
    annotations).
  - Idempotent: re-running is a no-op on already-flagged files.

Usage:
    yolo_env/bin/python3 scripts/flag_legacy_annotations.py --dry-run
    yolo_env/bin/python3 scripts/flag_legacy_annotations.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ANNOTATIONS_DIR = REPO_ROOT / "backend" / "training_data_annotations"


def parse_args():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


def is_candidate(data: dict) -> bool:
    """True if this annotation file should get the legacy flag."""
    if data.get("legacy_no_unit") is True:
        return False  # already flagged
    if data.get("migratedFrom"):
        return False  # intentionally incomplete — let it sit in Pending
    anns = data.get("annotations") or []
    if not anns:
        return False  # empty annotations aren't "pending" anyway
    # If ANY bbox already has a unit_slug set, treat the whole file as
    # "user knew about units by this point" — don't grandfather.
    if any(a.get("unit_slug") for a in anns):
        return False
    return True


def main():
    args = parse_args()
    if not ANNOTATIONS_DIR.exists():
        sys.exit(f"annotations dir not found at {ANNOTATIONS_DIR}")

    files = [
        p for p in ANNOTATIONS_DIR.rglob("*.json")
        if not p.name.endswith(".skip.json")
        and not p.name.endswith(".tmp")
        and ".bak-" not in p.name
    ]
    print(f"Scanning {len(files)} annotation files...")

    flagged = 0
    already = 0
    not_candidate = 0
    errored = 0

    for path in files:
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError as e:
            print(f"  ✗ {path.name}: {e}")
            errored += 1
            continue

        if data.get("legacy_no_unit") is True:
            already += 1
            continue
        if not is_candidate(data):
            not_candidate += 1
            continue

        data["legacy_no_unit"] = True

        if args.dry_run:
            flagged += 1
            continue

        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        tmp.replace(path)
        flagged += 1

    print()
    print(f"Would flag: {flagged}" if args.dry_run else f"Flagged: {flagged}")
    print(f"Already flagged (no-op): {already}")
    print(f"Not a candidate (has unit_slug, migrated, or empty): {not_candidate}")
    if errored:
        print(f"Errored (malformed JSON): {errored}")
    if args.dry_run:
        print("\n--dry-run: no files touched.")


if __name__ == "__main__":
    main()
