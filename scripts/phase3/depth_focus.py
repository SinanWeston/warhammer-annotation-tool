#!/usr/bin/env python3
"""
Phase 3a.1 — depth-focused labelling worklist.

Reads scripts/phase3/labels.csv and emits a prioritised worklist of unit
slugs that need more gallery crops. Targets:

  • Priority singletons (gallery depth = 1, ≥1 query crop): each needs
    +2 bboxes to reach depth = 3.
  • Near-target (gallery depth = 2, ≥1 query crop): each needs +1 bbox.

Only units with at least one query crop are listed — those are the ones
the retrieval eval actually scores against, so lifting their depth
moves the scoreboard. Units with 0 queries are gallery-only and
invisible to the eval bar until somebody also adds a query crop.

Output: markdown grouped by faction, ready to open alongside the
annotator. For each target unit the report lists:

  - faction / unit_slug
  - gallery-needed count (+1 or +2)
  - current gallery exemplar(s) — local file path(s) to the reference
    crop(s) already in the gallery. Open these in any image viewer to
    eyeball the look while labelling.
  - source images those crops came from (so the user knows what's
    already covered and can skip dupes).

Run:
    yolo_env/bin/python3 scripts/phase3/depth_focus.py
    yolo_env/bin/python3 scripts/phase3/depth_focus.py --out docs/depth_focus_worklist.md
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LABELS_CSV = REPO_ROOT / "scripts" / "phase3" / "labels.csv"
DEFAULT_OUT = REPO_ROOT / "docs" / "depth_focus_worklist.md"

TARGET_DEPTH = 3


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--labels", type=Path, default=LABELS_CSV, help="Path to scripts/phase3/labels.csv")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Markdown output path")
    p.add_argument("--target-depth", type=int, default=TARGET_DEPTH, help="Lift each unit to this gallery depth")
    return p.parse_args()


def main():
    args = parse_args()
    if not args.labels.exists():
        sys.exit(f"labels.csv not found at {args.labels}")

    # (faction, unit) -> list of (split, crop_path, source_ref)
    rows_by_key: dict[tuple[str, str], list[dict]] = defaultdict(list)
    with args.labels.open() as f:
        for row in csv.DictReader(f):
            unit = (row.get("unit_slug") or "").strip()
            if not unit or unit.startswith("__"):
                continue
            faction = (row.get("faction") or "").strip()
            rows_by_key[(faction, unit)].append({
                "split": (row.get("split") or "").strip(),
                "crop_path": (row.get("crop_path") or "").strip(),
                "source_ref": (row.get("source_ref") or "").strip(),
            })

    targets: list[dict] = []
    for (faction, unit), rows in rows_by_key.items():
        gallery = [r for r in rows if r["split"] == "gallery"]
        query = [r for r in rows if r["split"] == "query"]
        if len(query) == 0:
            continue  # not yet evaluated, skip
        if len(gallery) >= args.target_depth:
            continue  # already at target
        needed = args.target_depth - len(gallery)
        targets.append({
            "faction": faction,
            "unit": unit,
            "gallery_depth": len(gallery),
            "query_count": len(query),
            "needed": needed,
            "gallery_crops": [r["crop_path"] for r in gallery],
        })

    # Sort: gallery_depth ASC (smallest first → priority singletons), then
    # faction, then unit. So the report opens with the highest-impact work.
    targets.sort(key=lambda t: (t["gallery_depth"], t["faction"], t["unit"]))

    total_bboxes = sum(t["needed"] for t in targets)
    by_faction: dict[str, list[dict]] = defaultdict(list)
    for t in targets:
        by_faction[t["faction"]].append(t)

    lines: list[str] = []
    w = lines.append
    w(f"# Phase 3a.1 — depth-focus worklist")
    w("")
    w(f"Generated from `{args.labels.relative_to(REPO_ROOT)}` "
      f"(target gallery depth = {args.target_depth}).")
    w("")
    w(f"**{len(targets)} target unit(s) across {len(by_faction)} faction(s) — "
      f"{total_bboxes} bbox(es) to label.**")
    w("")
    w("Each bbox below means: find an image in the corpus that contains "
      "an instance of this unit, draw a tight bbox around it, and set "
      "`unit_slug` to the listed slug. Re-run "
      "`extract_from_corpus.py → auto_split.py → build_gallery.py → "
      "embed_gallery.py → eval_scoped_retrieval.py` after the sprint to "
      "see the lift.")
    w("")
    w("Reference crops are the existing gallery exemplar(s) — open the "
      "paths in any image viewer to eyeball what the unit looks like, "
      "then go hunting in the annotator with the matching faction "
      "filter set.")
    w("")
    w("---")
    w("")

    # Faction summary table — gives the user a routing decision.
    w("## Faction routing")
    w("")
    w("| Faction | Units | Bboxes | Suggested annotator filter |")
    w("|---|---:|---:|---|")
    for faction in sorted(by_faction, key=lambda f: (
            -sum(t["needed"] for t in by_faction[f]),  # most-bboxes first
            f)):
        units = by_faction[faction]
        bboxes = sum(t["needed"] for t in units)
        w(f"| {faction} | {len(units)} | {bboxes} | "
          f"`faction={faction}` + status=Pending |")
    w("")
    w("---")
    w("")

    # Per-faction detail.
    for faction in sorted(by_faction):
        units = by_faction[faction]
        bboxes = sum(t["needed"] for t in units)
        w(f"## {faction} — {len(units)} unit(s), {bboxes} bbox(es)")
        w("")
        for t in sorted(units, key=lambda u: (u["gallery_depth"], u["unit"])):
            tag = "🟥 SINGLETON" if t["gallery_depth"] == 1 else "🟧 NEAR-TARGET"
            w(f"### `{t['unit']}`   {tag} (depth={t['gallery_depth']} → +{t['needed']})")
            w("")
            w(f"- Current gallery depth: **{t['gallery_depth']}**  ·  "
              f"query crops: {t['query_count']}  ·  "
              f"**bboxes needed: {t['needed']}**")
            w(f"- Reference crop(s) — open to see the unit:")
            for cp in t["gallery_crops"]:
                w(f"  - `{cp}`")
            w("")
        w("---")
        w("")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines))
    rel = args.out.relative_to(REPO_ROOT)
    print(f"Wrote {rel}")
    print(f"  {len(targets)} target units across {len(by_faction)} factions")
    print(f"  {total_bboxes} bboxes to label "
          f"(~{total_bboxes * 30 // 60} min at 30s/bbox)")


if __name__ == "__main__":
    main()
