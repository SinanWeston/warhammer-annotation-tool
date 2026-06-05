#!/usr/bin/env python3
"""Backfill `suggested_by` on reliable but untagged rows in data/labels.csv.

Background: auto_split / build_gallery consumers don't filter by
provenance, so any row with a unit_slug ends up in training. That's fine
for human-confirmed rows and for rows scraped from canonical sources
(GW shop pages, prior annotation corpus), but weak-regex rows with
likely-wrong factions shouldn't silently land in the gallery.

Today the `suggested_by` column is empty on two big buckets that ARE
reliable but were never tagged:

  - source=gw_shop     (3k+ rows scraped from official unit pages)
  - source=annotation  (few hundred rows carried over from the
                        desktop annotator's human-annotated corpus)

This script promotes those to `suggested_by='scraped'` and
`suggested_by='annotation'` respectively, so a future filter in the
training pipeline can keep `weak_regex:*` rows out without also
excluding the reliable historical data.

  - Does NOT touch faction / unit_slug / labeller / bbox / notes.
  - Does NOT touch rows with non-sentinel `__bad_crop__` etc.
  - Does NOT touch rows that already have any `suggested_by` value.
  - Backs up `data/labels.csv` to `labels.csv.backup-<UTC-timestamp>`
    before writing.

Usage:
    fiftyone_env/bin/python3 scripts/backfill_provenance.py --dry-run
    fiftyone_env/bin/python3 scripts/backfill_provenance.py
"""

from __future__ import annotations

import argparse
import csv
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LABELS_CSV = REPO_ROOT / "data" / "labels.csv"

# source -> provenance tag to write into suggested_by
SOURCE_TO_PROVENANCE = {
    "gw_shop": "scraped",
    "annotation": "annotation",
}


def parse_args():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Count what would change without writing any files",
    )
    return p.parse_args()


def main():
    args = parse_args()
    if not LABELS_CSV.exists():
        sys.exit(f"labels.csv not found at {LABELS_CSV}")

    with LABELS_CSV.open() as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    if "suggested_by" not in fieldnames:
        sys.exit("labels.csv is missing the `suggested_by` column — wrong schema?")

    touched_by_source: dict[str, int] = {}
    skipped_reasons: dict[str, int] = {}

    for r in rows:
        sb = (r.get("suggested_by") or "").strip()
        if sb:
            skipped_reasons["already tagged"] = skipped_reasons.get("already tagged", 0) + 1
            continue
        slug = (r.get("unit_slug") or "").strip()
        if not slug:
            skipped_reasons["no slug"] = skipped_reasons.get("no slug", 0) + 1
            continue
        if slug.startswith("__") and slug.endswith("__"):
            skipped_reasons["sentinel slug"] = skipped_reasons.get("sentinel slug", 0) + 1
            continue
        src = (r.get("source") or "").strip()
        new_sb = SOURCE_TO_PROVENANCE.get(src)
        if not new_sb:
            skipped_reasons[f"source={src or '(empty)'}"] = (
                skipped_reasons.get(f"source={src or '(empty)'}", 0) + 1
            )
            continue
        r["suggested_by"] = new_sb
        touched_by_source[src] = touched_by_source.get(src, 0) + 1

    total = sum(touched_by_source.values())
    print(f"Rows total: {len(rows)}")
    print(f"Rows to backfill: {total}")
    for src, n in sorted(touched_by_source.items()):
        print(f"  source={src:<12} → suggested_by={SOURCE_TO_PROVENANCE[src]:<10}   {n}")
    if skipped_reasons:
        print("Skipped:")
        for reason, n in sorted(skipped_reasons.items(), key=lambda x: -x[1]):
            print(f"  {reason:<30}  {n}")

    if args.dry_run:
        print("\n--dry-run set; no files touched.")
        return

    if total == 0:
        print("Nothing to backfill.")
        return

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = LABELS_CSV.with_suffix(LABELS_CSV.suffix + f".backup-{ts}")
    shutil.copy2(LABELS_CSV, backup)
    print(f"\nBackup written: {backup.relative_to(REPO_ROOT)}")

    # Atomic write: tmp + rename, matches labelsCsvService.js behaviour.
    tmp = LABELS_CSV.with_suffix(LABELS_CSV.suffix + ".tmp")
    with tmp.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(LABELS_CSV)
    print(f"Wrote {len(rows)} rows to {LABELS_CSV.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
