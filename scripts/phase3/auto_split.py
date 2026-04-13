#!/usr/bin/env python3
"""
Phase 1 — assign gallery vs query from labels.csv.

Rule: for each unit_slug with ≥2 labelled crops, mark one as `query`, the
rest as `gallery`. For units with a single crop, mark it `gallery`. This
guarantees every query unit has at least one gallery match.

Writes split assignments back to labels.csv in a `split` column. Also
prints a coverage report flagging any query unit whose gallery has only
one image (under-represented — retrieval signal from that unit will be
noisy).

Usage:
    yolo_env/bin/python3 scripts/phase3/auto_split.py
    yolo_env/bin/python3 scripts/phase3/auto_split.py --seed 42
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LABELS_CSV = REPO_ROOT / "scripts" / "phase3" / "labels.csv"


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--seed", type=int, default=42, help="Seed for deterministic query picking")
    return p.parse_args()


def main():
    args = parse_args()
    if not LABELS_CSV.exists():
        sys.exit(f"labels.csv not found at {LABELS_CSV}. Run extract_gt_crops.py first.")

    rows: list[dict] = []
    with LABELS_CSV.open() as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        for r in reader:
            rows.append(r)

    if not rows:
        sys.exit("labels.csv is empty.")

    # Rows with empty unit_slug are excluded from the split — the user
    # couldn't confidently identify them. They stay in the CSV with a
    # blank split column so we can come back to them later.
    unlabelled = [r for r in rows if not (r.get("unit_slug") or "").strip()]
    labelled_rows = [r for r in rows if (r.get("unit_slug") or "").strip()]
    if unlabelled:
        print(f"Skipping {len(unlabelled)} unlabelled rows (stay blank in CSV).")
    if not labelled_rows:
        sys.exit("No labelled rows — nothing to split.")
    rows_to_split = labelled_rows

    # Group by (faction, unit_slug) — same unit name across factions is unusual
    # but keep the tuple to stay safe (e.g. 'scout' exists in several factions).
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows_to_split:
        key = (r["faction"].strip(), r["unit_slug"].strip())
        groups[key].append(r)

    rng = random.Random(args.seed)
    split_for: dict[str, str] = {}  # crop_path -> 'gallery' | 'query'
    for (faction, unit), members in groups.items():
        if len(members) == 1:
            split_for[members[0]["crop_path"]] = "gallery"
            continue
        # Pick one query, deterministically given the seed.
        ordered = sorted(members, key=lambda m: m["crop_path"])
        rng.shuffle(ordered)
        query = ordered[0]
        split_for[query["crop_path"]] = "query"
        for m in ordered[1:]:
            split_for[m["crop_path"]] = "gallery"

    # Write back with split column.
    if "split" not in fieldnames:
        fieldnames = fieldnames + ["split"]
    for r in rows:
        r["split"] = split_for.get(r["crop_path"], "")  # unlabelled rows get blank split
    with LABELS_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # Coverage report.
    gallery_counts: dict[tuple[str, str], int] = defaultdict(int)
    query_counts: dict[tuple[str, str], int] = defaultdict(int)
    for r in rows_to_split:
        key = (r["faction"], r["unit_slug"])
        if r["split"] == "gallery":
            gallery_counts[key] += 1
        elif r["split"] == "query":
            query_counts[key] += 1

    n_gallery = sum(gallery_counts.values())
    n_query = sum(query_counts.values())
    distinct_query_units = len(query_counts)
    print(f"Split written to {LABELS_CSV.relative_to(REPO_ROOT)}")
    print(f"  Gallery: {n_gallery} crops across {len(gallery_counts)} (faction, unit) pairs")
    print(f"  Query:   {n_query} crops across {distinct_query_units} (faction, unit) pairs")
    print()

    # Under-represented query units (gallery has only 1 image).
    thin = [(f, u, gallery_counts.get((f, u), 0)) for (f, u) in query_counts if gallery_counts.get((f, u), 0) < 2]
    if thin:
        print("⚠ Query units with a single gallery example (retrieval will be noisy):")
        for f, u, g in thin:
            print(f"    {f} / {u}: {g} gallery image(s)")
    else:
        print("✓ Every query unit has ≥2 gallery examples.")

    # Sanity: any query unit without ANY gallery match?
    orphans = [(f, u) for (f, u) in query_counts if gallery_counts.get((f, u), 0) == 0]
    if orphans:
        print("\n✗ CRITICAL — query units with zero gallery examples:")
        for f, u in orphans:
            print(f"    {f} / {u}")
        sys.exit(1)


if __name__ == "__main__":
    main()
