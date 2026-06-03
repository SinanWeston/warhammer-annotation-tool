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

sys.path.insert(0, str(REPO_ROOT / "src"))
from photoanalyzer.label.schema import is_sentinel  # noqa: E402


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
    # Sentinel slugs (`__bad_crop__`, `__unknown__`, `__ambiguous__`) are
    # also excluded — they're audit-trail markers, not training data, and
    # should never be grouped into gallery/query.
    def _is_real_label(r):
        slug = (r.get("unit_slug") or "").strip()
        return bool(slug) and not is_sentinel(slug)

    unlabelled = [r for r in rows if not (r.get("unit_slug") or "").strip()]
    sentinels = [r for r in rows
                 if (r.get("unit_slug") or "").strip()
                 and is_sentinel(r.get("unit_slug", "").strip())]
    labelled_rows = [r for r in rows if _is_real_label(r)]
    if unlabelled:
        print(f"Skipping {len(unlabelled)} unlabelled rows (stay blank in CSV).")
    if sentinels:
        print(f"Skipping {len(sentinels)} sentinel-slug rows (__bad_crop__ / etc.)")
    if not labelled_rows:
        sys.exit("No labelled rows — nothing to split.")
    rows_to_split = labelled_rows

    # Instance-aware grouping. `phase3/labels.csv` now carries `instance_id`
    # and `view_idx` (as of the sync-from-canonical bridge). Multiple views
    # of the same physical miniature share an instance_id — if one view
    # lands in `gallery` and another in `query`, the retrieval eval is
    # doing instance-level memorisation instead of unit-level
    # discrimination. Group at the instance level and pin every crop in
    # an instance to the same split.
    #
    # Rows without an instance_id (annotation corpus, gw_shop) get a
    # synthetic per-row id derived from crop_path. This makes them behave
    # as singleton instances, which matches today's per-crop assignment.
    def _inst_key(r: dict) -> str:
        iid = (r.get("instance_id") or "").strip()
        return iid or f"_path:{r['crop_path']}"

    # Build: (faction, unit) -> {instance_id -> [crop rows]}
    group_instances: dict[tuple[str, str], dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for r in rows_to_split:
        key = (r["faction"].strip(), r["unit_slug"].strip())
        group_instances[key][_inst_key(r)].append(r)

    # Stage 1 — carry forward existing assignments per instance.
    # Rule: if every member of an instance agrees on a non-empty split, pin
    # the instance to that split. If members disagree (pre-existing
    # instance-leaked state), normalise every member to `gallery` and warn.
    split_for: dict[str, str] = {}
    leaked_instances: list[tuple[str, str, str, set[str]]] = []

    for (faction, unit), by_instance in group_instances.items():
        for iid, members in by_instance.items():
            existing = {(m.get("split") or "").strip() for m in members}
            existing.discard("")
            if not existing:
                continue  # assigned in stage 2
            if len(existing) > 1:
                # Split-leaked: the same instance was in gallery AND query
                # in the previous run. Collapse to gallery (safer — query
                # acts as the held-out probe, so we never want to train
                # data leaking into it).
                leaked_instances.append((faction, unit, iid, existing))
                for m in members:
                    split_for[m["crop_path"]] = "gallery"
            else:
                pinned = next(iter(existing))
                for m in members:
                    split_for[m["crop_path"]] = pinned

    if leaked_instances:
        print(f"\n⚠ {len(leaked_instances)} instance(s) were previously split-leaked "
              f"(same instance_id in both gallery AND query). Normalised to gallery:")
        for faction, unit, iid, existing in leaked_instances[:10]:
            print(f"    {faction}/{unit} instance={iid}  splits={sorted(existing)}")
        if len(leaked_instances) > 10:
            print(f"    ... and {len(leaked_instances) - 10} more")

    # Stage 2 — assign splits to (faction, unit) groups that have instances
    # without any existing assignment. Deterministic given --seed: sort
    # instance_ids ascending, seeded-shuffle, pick one as query, rest
    # gallery. Groups with a single unassigned instance → gallery.
    rng = random.Random(args.seed)
    newly_assigned_groups: int = 0

    for (faction, unit), by_instance in group_instances.items():
        unassigned = [iid for iid, members in by_instance.items()
                      if not any((m.get("split") or "").strip() for m in members)]
        if not unassigned:
            continue
        newly_assigned_groups += 1

        # If the whole group (assigned + unassigned) has NO query instance
        # yet, we need to pick one so the unit has a held-out probe. Do
        # this from the unassigned pool first; if all instances were already
        # pinned to gallery and there's no query, flip one (and record it
        # so the CLI output is honest about the disturbance).
        has_query_instance = any(
            (m.get("split") or "").strip() == "query" or
            split_for.get(m["crop_path"]) == "query"
            for members in by_instance.values()
            for m in members
        )
        total_instances = len(by_instance)

        unassigned_sorted = sorted(unassigned)
        rng.shuffle(unassigned_sorted)

        if total_instances == 1:
            # Single instance — goes to gallery; no query for this unit.
            for m in by_instance[unassigned_sorted[0]]:
                split_for[m["crop_path"]] = "gallery"
            continue

        if not has_query_instance:
            # Promote the first unassigned instance to query.
            query_iid = unassigned_sorted[0]
            for m in by_instance[query_iid]:
                split_for[m["crop_path"]] = "query"
            for iid in unassigned_sorted[1:]:
                for m in by_instance[iid]:
                    split_for[m["crop_path"]] = "gallery"
        else:
            # Already have a query; new instances all go to gallery.
            for iid in unassigned_sorted:
                for m in by_instance[iid]:
                    split_for[m["crop_path"]] = "gallery"

    # Stage 3 — reconciliation across (faction, unit) groups. A single scene
    # can contain multiple unit types (e.g. Orks battlewagon + attack_fighta
    # in the same photo). The per-group instance pinning above keeps each
    # group's own instance consistent, but an instance showing up in group A
    # as `gallery` and group B as `query` still leaks scene-level features
    # into the query set. Collapse any multi-split instance to `gallery` —
    # losing a query probe for one unit is cheaper than retrieval eval that
    # memorises the scene.
    by_instance_global: dict[str, set[str]] = defaultdict(set)
    by_instance_paths: dict[str, list[str]] = defaultdict(list)
    for r in rows_to_split:
        iid = (r.get("instance_id") or "").strip()
        if not iid:
            continue
        path = r["crop_path"]
        s = split_for.get(path, "")
        if s:
            by_instance_global[iid].add(s)
            by_instance_paths[iid].append(path)
    reconciled_instances = [iid for iid, s in by_instance_global.items() if len(s) > 1]
    for iid in reconciled_instances:
        for path in by_instance_paths[iid]:
            split_for[path] = "gallery"
    if reconciled_instances:
        print(f"↺ Reconciled {len(reconciled_instances)} instance(s) with cross-unit split "
              f"leakage — collapsed every affected crop to `gallery`:")
        for iid in reconciled_instances[:10]:
            print(f"    {iid}")
        if len(reconciled_instances) > 10:
            print(f"    ... and {len(reconciled_instances) - 10} more")

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
    print(f"  Groups with newly-assigned instances this run: {newly_assigned_groups}")
    print()

    # Leakage sanity check: no instance_id should appear in both gallery
    # AND query after this run. Guarantees retrieval eval is measuring
    # unit-level discrimination, not instance-level memorisation.
    inst_splits: dict[str, set[str]] = defaultdict(set)
    for r in rows_to_split:
        iid = (r.get("instance_id") or "").strip()
        if iid and r["split"]:
            inst_splits[iid].add(r["split"])
    leaks = {iid: s for iid, s in inst_splits.items() if len(s) > 1}
    if leaks:
        print("✗ CRITICAL — instance_id split leakage (same mini in gallery AND query):")
        for iid, s in list(leaks.items())[:5]:
            print(f"    {iid}  splits={sorted(s)}")
        sys.exit(1)
    else:
        print(f"✓ No instance_id split leakage across {len(inst_splits)} CMON instances.")
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
