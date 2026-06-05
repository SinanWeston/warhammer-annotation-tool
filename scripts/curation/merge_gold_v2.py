"""Merge CVAT-labeled gold_v2 images into the frozen gold set (Plan §3).

Reads the base frozen file (gold_v1.json, the original 35) and appends the
images tagged 'gold_v2' that now carry `ground_truth` detections — producing a
new frozen file gold_v2.json. The base file is never modified.

Prereq: run `gold_to_cvat.py pull v2` first so the CVAT annotations are loaded
into the `ground_truth` field on the dataset.

FiftyOne Detection.bounding_box is [x, y, w, h] normalized top-left — the same
convention as the gold schema's `bbox_xywh_norm`, so no coord transform needed.

Usage:
  fiftyone_env/bin/python scripts/curation/merge_gold_v2.py
  fiftyone_env/bin/python scripts/curation/merge_gold_v2.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import fiftyone as fo

GOLD_DIR = Path(__file__).resolve().parents[2] / "data" / "gold"
BASE = GOLD_DIR / "gold_v1.json"
OUT = GOLD_DIR / "gold_v2.json"
# every quota-fill round, in order; each is a CVAT task pulled into ground_truth
TAGS = ["gold_v2", "gold_v3", "gold_v4", "gold_v5"]


def round5(v: float) -> float:
    return round(float(v), 5)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would be added without writing")
    args = ap.parse_args()

    base = json.loads(BASE.read_text())
    have_bn = {i["basename"] for i in base["images"]}

    ds = fo.load_dataset("wh40k_pile")
    view = ds.match_tags(TAGS).exists("ground_truth")
    for t in TAGS:
        tagged = ds.match_tags(t).count()
        labeled = ds.match_tags(t).exists("ground_truth").count()
        skip = tagged - labeled
        print(f"  {t}: {labeled}/{tagged} labeled" +
              (f" ({skip} skipped/unlabeled)" if skip else ""))

    new_images, added_boxes, skipped = [], 0, []
    for s in view:
        bn = os.path.basename(s.filepath)
        if bn in have_bn:
            skipped.append(bn)
            continue
        boxes = [
            {"label": d.label,
             "bbox_xywh_norm": [round5(v) for v in d.bounding_box]}
            for d in s.ground_truth.detections
        ]
        new_images.append({
            "filepath": s.filepath,
            "basename": bn,
            "faction_v1": s.faction_v1,
            "source": s.source,
            "boxes": boxes,
        })
        added_boxes += len(boxes)

    merged_images = base["images"] + new_images
    out = {
        "name": "gold_v2",
        "n_images": len(merged_images),
        "n_boxes": sum(len(i["boxes"]) for i in merged_images),
        "images": merged_images,
    }

    print(f"base:  {base['n_images']} imgs / {base['n_boxes']} boxes")
    print(f"add:   {len(new_images)} imgs / {added_boxes} boxes")
    if skipped:
        print(f"skip:  {len(skipped)} already in base ({', '.join(skipped[:3])}...)")
    print(f"merged: {out['n_images']} imgs / {out['n_boxes']} boxes")

    # per-faction box tally on the merged set
    tally: dict[str, int] = {}
    for i in merged_images:
        for b in i["boxes"]:
            tally[b["label"]] = tally.get(b["label"], 0) + 1
    print("per-faction boxes:", dict(sorted(tally.items(), key=lambda kv: -kv[1])))

    if args.dry_run:
        print("\n--dry-run: nothing written")
        return
    OUT.write_text(json.dumps(out, indent=2))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
