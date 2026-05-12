#!/usr/bin/env python3
"""Regenerate `scripts/phase3/labels.csv` from the canonical `data/labels.csv`.

The motivation: `data/labels.csv` (v2, 13 cols) is the live labelling surface
— the web UI, `apply_weak_sup.py`, and the CMON scraper all write here. But
every phase3 pipeline script (`auto_split.py`, `build_gallery.py`,
`embed_gallery.py`, `eval_scoped_retrieval.py`) reads from
`scripts/phase3/labels.csv`, which was a separate 5-col snapshot that hadn't
been rebuilt since 2026-04-16. Every label the user wrote after that date
was invisible to retrieval. This bridge closes the gap.

Filter policy:
  - `filter_trainable` (from `photoanalyzer.label.schema`) — no sentinel
    slugs, must have faction + unit_slug.
  - Trusted provenance only: `suggested_by in {human, human_redraw, scraped,
    annotation}`. Excludes `weak_regex:*` keyword matches until the human
    has had a chance to audit them.
  - Taxonomy validation: `resolve_faction` must return a canonical slug.
    Non-40K factions (adeptus_titanicus, titanicus_traitoris) and the
    scraper "unknown" placeholder are explicitly dropped.

Output schema:
  - The full v2 13-col schema is written so `instance_id` / `view_idx` /
    `suggested_by` / `labeller` / `confidence` / `created_at` / `source_ref`
    all carry through. Phase3 consumers that use `csv.DictReader` ignore
    columns they don't need; new consumers (e.g. the instance-aware
    `auto_split.py`) can lean on the extra columns.
  - Existing `split` assignments are preserved verbatim — run `auto_split.py`
    afterwards to assign splits to new rows.

Usage:
    yolo_env/bin/python3 scripts/phase3/sync_from_canonical.py --dry-run
    yolo_env/bin/python3 scripts/phase3/sync_from_canonical.py
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CANONICAL_CSV = REPO_ROOT / "data" / "labels.csv"
PHASE3_CSV = REPO_ROOT / "scripts" / "phase3" / "labels.csv"

sys.path.insert(0, str(REPO_ROOT / "src"))

from photoanalyzer.label.schema import (  # noqa: E402
    LabelRecord, V2_COLUMNS, read_labels_csv, filter_trainable, is_sentinel,
)
from photoanalyzer.taxonomy import resolve_faction  # noqa: E402


#: `suggested_by` values whose rows we trust enough to pass into training.
#: Anything else (notably `weak_regex:*`) is kept out — a future session can
#: re-audit those rows via the labelling UI and promote them to `human`.
TRUSTED_PROVENANCE = frozenset({"human", "human_redraw", "scraped", "annotation"})

#: Faction values we deliberately drop even if every other filter passes.
#: `adeptus_titanicus` / `titanicus_traitoris` are a different game system
#: that got swept in from the GW shop scraper but don't belong in 40K
#: training. `unknown` is the scraper's "couldn't categorise" placeholder.
BLOCKED_FACTIONS = frozenset({
    "adeptus_titanicus",
    "titanicus_traitoris",
    "unknown",
})


def parse_args():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Print the counts; don't write scripts/phase3/labels.csv.",
    )
    p.add_argument(
        "--include-weak", action="store_true",
        help=("Include weak_regex:* rows in the output. Off by default — the "
              "whole point of this bridge is to gate unverified weak-sup "
              "labels from reaching training."),
    )
    return p.parse_args()


def main():
    args = parse_args()
    if not CANONICAL_CSV.exists():
        sys.exit(f"Canonical CSV not found at {CANONICAL_CSV}. Nothing to sync.")

    rows = list(read_labels_csv(CANONICAL_CSV))
    print(f"Loaded {len(rows)} rows from {CANONICAL_CSV.relative_to(REPO_ROOT)}")

    # Stage 1: filter_trainable — drops sentinels, rows without faction or
    # unit_slug. This is the canonical "is this a training example?" check.
    stage1 = list(filter_trainable(rows, require_split=False))
    print(f"  stage 1 (trainable: non-sentinel, has faction + slug): {len(stage1)}")

    # Stage 2: trusted provenance. Without --include-weak, we drop every
    # weak_regex:* row so the audit pile stays out of training until a
    # human has reviewed it.
    if args.include_weak:
        stage2 = stage1
        print(f"  stage 2 (--include-weak: keeping all provenance): {len(stage2)}")
    else:
        stage2 = [r for r in stage1 if r.suggested_by in TRUSTED_PROVENANCE]
        dropped_by_prov = Counter(
            r.suggested_by or "(empty)" for r in stage1 if r.suggested_by not in TRUSTED_PROVENANCE
        )
        print(f"  stage 2 (trusted provenance): {len(stage2)}")
        for sb, n in sorted(dropped_by_prov.items(), key=lambda x: -x[1]):
            print(f"    dropped {sb:<30} {n}")

    # Stage 3: canonicalise faction + drop out-of-taxonomy values.
    # `resolve_faction` turns aliases into their canonical slug; returns
    # None for anything not in the 20 + not in FACTION_ALIASES.
    stage3 = []
    blocked_count: Counter = Counter()
    alias_normalised: Counter = Counter()
    for r in stage2:
        if r.faction in BLOCKED_FACTIONS:
            blocked_count[r.faction] += 1
            continue
        canonical = resolve_faction(r.faction)
        if canonical is None:
            blocked_count[r.faction or "(empty)"] += 1
            continue
        if canonical != r.faction:
            alias_normalised[(r.faction, canonical)] += 1
            r.faction = canonical
        stage3.append(r)
    print(f"  stage 3 (taxonomy-valid faction): {len(stage3)}")
    if blocked_count:
        print(f"    dropped by taxonomy:")
        for f, n in sorted(blocked_count.items(), key=lambda x: -x[1]):
            print(f"      {f:<30} {n}")
    if alias_normalised:
        print(f"    alias-normalised at write time:")
        for (alias, canonical), n in sorted(alias_normalised.items(), key=lambda x: -x[1]):
            print(f"      {alias:<25} → {canonical:<22} {n}")

    # Extra invariant: every emitted row must have a slug (filter_trainable
    # covers this, but double-check after canonicalisation).
    for r in stage3:
        assert r.unit_slug and not is_sentinel(r.unit_slug), f"sentinel slipped: {r.crop_path}"

    # Summary stats for the write.
    by_source = Counter(r.source for r in stage3)
    with_instance = sum(1 for r in stage3 if r.instance_id)
    with_split = sum(1 for r in stage3 if r.split)
    print()
    print(f"Emitting {len(stage3)} rows:")
    for src, n in sorted(by_source.items(), key=lambda x: -x[1]):
        print(f"  source={src:<15} {n}")
    print(f"  rows with instance_id: {with_instance}")
    print(f"  rows with split (preserved): {with_split}")

    if args.dry_run:
        print("\n--dry-run: not writing.")
        return

    # Atomic write: tmp + rename. Use the full v2 column order so consumers
    # that want instance_id / view_idx / suggested_by / labeller can see
    # them. csv.DictReader ignores columns it doesn't know about, so this
    # is backwards-compatible with phase3 scripts that haven't been updated.
    PHASE3_CSV.parent.mkdir(parents=True, exist_ok=True)
    tmp = PHASE3_CSV.with_suffix(PHASE3_CSV.suffix + ".tmp")
    with tmp.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(V2_COLUMNS))
        writer.writeheader()
        for r in stage3:
            writer.writerow(r.to_csv_row())
    tmp.replace(PHASE3_CSV)
    print(f"\n✅ wrote {len(stage3)} rows to {PHASE3_CSV.relative_to(REPO_ROOT)}")
    print("    Next: re-run auto_split.py + build_gallery.py + embed_gallery.py")


if __name__ == "__main__":
    main()
