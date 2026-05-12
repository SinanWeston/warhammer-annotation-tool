#!/usr/bin/env python3
"""Migrate legacy labels.csv files into unified data/labels.csv (v2 schema).

Sources:
- scripts/phase1/labels.csv  — v1 columns, no `source` column (seeded default)
- scripts/phase3/labels.csv  — v1+source column with bespoke source values

Output: data/labels.csv in v2 schema per photoanalyzer.label.schema.

Source mapping (phase3 legacy → v2):
    post_export   → annotation    (crops from scene annotations via YOLO export)
    yolo_split    → annotation    (same, different extraction path)
    phase2_carry  → annotation    (rows carried forward from phase 2 corpus)
    gw_shop       → gw_shop       (already matches v2)

Faction strings are preserved verbatim so this is a pure-schema migration.
Follow-up work lives in photoanalyzer.taxonomy (add aliases or new canonical
factions for death_guard / thousand_sons / world_eaters / emperors_children).

Usage:
    yolo_env/bin/python3 scripts/migrate_labels.py
    yolo_env/bin/python3 scripts/migrate_labels.py --dry-run
    yolo_env/bin/python3 scripts/migrate_labels.py --out data/labels.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from photoanalyzer import taxonomy  # noqa: E402
from photoanalyzer.label.schema import LabelRecord, write_labels_csv  # noqa: E402


LEGACY_SOURCES = {
    "post_export":  "annotation",
    "yolo_split":   "annotation",
    "phase2_carry": "annotation",
    "gw_shop":      "gw_shop",
    # "" (empty) is handled separately below
}


def _read_v1_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open() as f:
        return list(csv.DictReader(f))


def migrate() -> tuple[list[LabelRecord], Counter]:
    """Return (records, stats). Stats includes per-source counts, warnings."""
    stats: Counter = Counter()
    recs: list[LabelRecord] = []

    # phase1 → source=annotation (scripts/phase1/extract_gt_crops.py seeds from YOLO val)
    phase1_rows = _read_v1_rows(REPO_ROOT / "scripts" / "phase1" / "labels.csv")
    stats["phase1_rows"] = len(phase1_rows)
    for row in phase1_rows:
        rec = LabelRecord.from_v1_row(row, default_source="annotation")
        # phase1 was the original crop set; source_ref stays empty (not from URL-addressable source)
        recs.append(rec)
        stats[f"phase1.source={rec.source}"] += 1
        if rec.unit_slug:
            stats["phase1.labelled"] += 1

    # phase3 → source column already populated but uses legacy values; remap
    phase3_rows = _read_v1_rows(REPO_ROOT / "scripts" / "phase3" / "labels.csv")
    stats["phase3_rows"] = len(phase3_rows)
    for row in phase3_rows:
        raw_source = (row.get("source") or "").strip()
        mapped = LEGACY_SOURCES.get(raw_source, "")
        if raw_source and not mapped:
            stats[f"phase3.unmapped_source={raw_source}"] += 1
            # Keep raw value — validate() will flag it later; we don't want to
            # lose the provenance signal.
            mapped = raw_source
        rec = LabelRecord.from_v1_row(row, default_source=mapped or "annotation")
        # Override source with the mapping (from_v1_row preserves existing value)
        rec.source = mapped or "annotation"
        recs.append(rec)
        stats[f"phase3.source={rec.source}"] += 1
        if rec.unit_slug:
            stats["phase3.labelled"] += 1

    # Warn on non-canonical factions (alias-unresolvable)
    for rec in recs:
        if rec.faction and taxonomy.resolve_faction(rec.faction) is None:
            stats[f"non_canonical_faction={rec.faction}"] += 1

    return recs, stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path,
                    default=REPO_ROOT / "data" / "labels.csv",
                    help="Output path (default: data/labels.csv)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Don't write; just report counts")
    args = ap.parse_args()

    recs, stats = migrate()

    print(f"Migrated {len(recs)} rows total:")
    for k in sorted(stats):
        print(f"  {k}: {stats[k]}")

    # Quick sanity-check report
    labelled = sum(1 for r in recs if r.unit_slug)
    print(f"\nLabelled: {labelled} / {len(recs)} ({100*labelled/max(1,len(recs)):.1f}%)")
    per_split = Counter(r.split or "(unassigned)" for r in recs)
    print(f"Splits: {dict(per_split)}")

    if args.dry_run:
        print("\n--dry-run: not writing.")
        return

    n = write_labels_csv(args.out, recs)
    print(f"\nWrote {n} rows to {args.out}")

    # Roundtrip verify: re-read and compare count
    from photoanalyzer.label.schema import read_labels_csv
    reloaded = list(read_labels_csv(args.out))
    if len(reloaded) != n:
        print(f"⚠ roundtrip count mismatch: wrote {n}, read back {len(reloaded)}",
              file=sys.stderr)
        sys.exit(1)
    print(f"Roundtrip verified: {len(reloaded)} rows readable.")


if __name__ == "__main__":
    main()
