#!/usr/bin/env python3
"""
Phase 3a — extract crops from the FULL annotation corpus.

The central insight of Phase 3a: we've been using <3% of the 3,525
already-labelled bboxes sitting in backend/training_data_annotations/.
14 factions have zero Phase 2 coverage even though the corpus has
hundreds of bboxes in each.

This script walks every annotation JSON, crops every bbox, and seeds
scripts/phase3/labels.csv with:

  - All Phase 2 labels carried over (so Sinan doesn't re-label).
  - Additional unlabelled crops biased toward the 14 missing factions
    and depth for existing thin units. ~300 new rows target.
  - Metadata on whether each crop's source image is post-YOLO-export
    (i.e. never seen by the current YOLO model) — useful for
    preferring those as queries in a future auto_split pass.

Usage:
    yolo_env/bin/python3 scripts/phase3/extract_from_corpus.py
    yolo_env/bin/python3 scripts/phase3/extract_from_corpus.py --seed 42 --target 300
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import defaultdict, Counter
from io import BytesIO
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PHASE2 = REPO_ROOT / "scripts" / "phase2"
PHASE3 = REPO_ROOT / "scripts" / "phase3"
ANNOT_DIR = REPO_ROOT / "backend" / "training_data_annotations"
TRAIN_IMG = REPO_ROOT / "backend" / "yolo_dataset" / "images" / "train"
VAL_IMG = REPO_ROOT / "backend" / "yolo_dataset" / "images" / "val"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from scraper_utils import compute_md5  # noqa: E402

# Minimum crop side (px) — filters out bboxes too small to be useful.
MIN_CROP_SIDE = 80
# Padding around bbox when cropping (fraction of box dims).
PADDING_PCT = 0.05

# Phase 2 covered factions. Anything NOT in here is a Phase 3a breadth target.
PHASE2_COVERED = {
    "chaos_space_marines",
    "death_guard",
    "thousand_sons",
    "genestealer_cult",
    "space_marines",
    "tyranids",
    "necrons",
    "eldar",
    "drukhari",
}


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--target", type=int, default=300,
                   help="Target number of NEW unlabelled crops to add (on top of Phase 2 carry-over)")
    p.add_argument("--per-faction-min", type=int, default=12,
                   help="Aim for at least this many new crops per uncovered faction (breadth)")
    p.add_argument("--per-faction-max", type=int, default=20,
                   help="Cap per uncovered faction to keep the labelling workload bounded")
    return p.parse_args()


def yolo_box_to_xyxy_padded(x, y, w, h, img_w, img_h, pad_pct):
    """Convert modelBbox {x,y,width,height} absolute pixel coords with padding."""
    pad_w = w * pad_pct
    pad_h = h * pad_pct
    return (
        max(0, int(round(x - pad_w))),
        max(0, int(round(y - pad_h))),
        min(img_w, int(round(x + w + pad_w))),
        min(img_h, int(round(y + h + pad_h))),
    )


def load_phase2_labels() -> list[dict]:
    csv_path = PHASE2 / "labels.csv"
    if not csv_path.exists():
        return []
    with csv_path.open() as f:
        return list(csv.DictReader(f))


def walk_annotations():
    """Yield every (annotation_json, image_path, bboxes, is_post_export) tuple."""
    train_stems = {p.stem for p in TRAIN_IMG.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")}
    val_stems = {p.stem for p in VAL_IMG.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")}
    for f in sorted(ANNOT_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text())
        except Exception:
            continue
        image_path = data.get("imagePath")
        if not image_path:
            continue
        faction = data.get("faction", "")
        abs_img = Path(image_path)
        if not abs_img.is_absolute():
            abs_img = REPO_ROOT / abs_img
        if not abs_img.exists():
            # Fallback: look for the same stem under training_data/
            candidates = list((REPO_ROOT / "backend" / "training_data").rglob(abs_img.name))
            if not candidates:
                continue
            abs_img = candidates[0]
        bboxes = data.get("annotations", [])
        is_post_export = abs_img.stem not in train_stems and abs_img.stem not in val_stems
        yield {
            "json": f,
            "image_path": abs_img,
            "faction": faction,
            "bboxes": bboxes,
            "is_post_export": is_post_export,
        }


def main():
    args = parse_args()
    try:
        from PIL import Image
    except ImportError:
        sys.exit("PIL not available. Run from yolo_env.")

    rng = random.Random(args.seed)
    crops_dir = PHASE3 / "crops"

    # ── Step 1: carry over Phase 2 labels (crops AND their labels) ─────
    carried = []
    carried_seen = set()  # (faction, filename) tuples of crops already present
    for row in load_phase2_labels():
        # Phase 2 crop_path: "scripts/phase2/crops/{faction}/{file}"
        src_rel = row["crop_path"]
        src_abs = REPO_ROOT / src_rel
        if not src_abs.exists():
            continue
        faction = row["faction"]
        fname = src_abs.name
        dst = crops_dir / faction / fname
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists():
            dst.write_bytes(src_abs.read_bytes())
        carried_seen.add((faction, fname))
        new_row = {
            "crop_path": f"scripts/phase3/crops/{faction}/{fname}",
            "faction": faction,
            "unit_slug": row.get("unit_slug", ""),
            "notes": row.get("notes", ""),
            "source": "phase2_carry",
        }
        carried.append(new_row)
    print(f"Carried over {len(carried)} crops from Phase 2 "
          f"({sum(1 for r in carried if r['unit_slug'])} already labelled).")

    # ── Step 2: walk the full annotation corpus and build candidate pool ─
    by_faction: dict[str, list[dict]] = defaultdict(list)
    for entry in walk_annotations():
        if not entry["faction"]:
            continue
        with Image.open(entry["image_path"]) as im:
            img_w, img_h = im.size
        for bi, bbox in enumerate(entry["bboxes"]):
            m = bbox.get("modelBbox")
            if not m:
                continue
            xyxy = yolo_box_to_xyxy_padded(
                m["x"], m["y"], m["width"], m["height"], img_w, img_h, PADDING_PCT
            )
            if (xyxy[2] - xyxy[0]) < MIN_CROP_SIDE or (xyxy[3] - xyxy[1]) < MIN_CROP_SIDE:
                continue
            fname = f"{entry['image_path'].stem}__{bi:02d}.jpg"
            if (entry["faction"], fname) in carried_seen:
                continue  # already in Phase 2
            by_faction[entry["faction"]].append({
                "src": entry["image_path"],
                "faction": entry["faction"],
                "xyxy": xyxy,
                "fname": fname,
                "is_post_export": entry["is_post_export"],
            })

    print("\nCandidate new crops available (excluding Phase 2 overlap):")
    for f, pool in sorted(by_faction.items(), key=lambda kv: -len(kv[1])):
        cov = "✓" if f in PHASE2_COVERED else " "
        post_export = sum(1 for c in pool if c["is_post_export"])
        print(f"  {cov} {f:28s} {len(pool):>4d} available  ({post_export} post-export)")

    # ── Step 3: target mix ─────────────────────────────────────────────
    # Phase 3a-Big: prioritise the 14 uncovered factions (at least per_faction_min
    # each, capped at per_faction_max), fill remainder with depth on covered
    # factions. Within each faction, shuffle and prefer post-export crops.
    selected = []
    uncovered = [f for f in by_faction if f not in PHASE2_COVERED and len(by_faction[f]) > 0]
    covered = [f for f in by_faction if f in PHASE2_COVERED and len(by_faction[f]) > 0]

    def pick(pool: list[dict], n: int) -> list[dict]:
        # Prefer post-export crops; fill remainder from rest.
        rng.shuffle(pool)
        post = [c for c in pool if c["is_post_export"]]
        rest = [c for c in pool if not c["is_post_export"]]
        ordered = post + rest
        return ordered[:n]

    # Breadth: cover every uncovered faction.
    for fac in uncovered:
        want = min(args.per_faction_max, max(args.per_faction_min, len(by_faction[fac])))
        want = min(want, len(by_faction[fac]))
        selected.extend(pick(by_faction[fac], want))

    breadth_count = len(selected)
    print(f"\nBreadth picks from uncovered factions: {breadth_count}")

    # Depth: fill remaining target with covered factions, proportional.
    remaining = max(0, args.target - breadth_count)
    if remaining > 0 and covered:
        # Weight by available-pool size (more options = more picks).
        total_covered_pool = sum(len(by_faction[f]) for f in covered)
        for fac in sorted(covered, key=lambda f: -len(by_faction[f])):
            share = int(round(remaining * len(by_faction[fac]) / total_covered_pool))
            share = min(share, len(by_faction[fac]))
            selected.extend(pick(by_faction[fac], share))
    print(f"Total new crops selected: {len(selected)}")

    # ── Step 4: materialise crops ──────────────────────────────────────
    new_rows = []
    seen_hashes = set()
    for c in selected:
        dst = crops_dir / c["faction"] / c["fname"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            continue
        with Image.open(c["src"]) as im:
            buf = BytesIO()
            im.convert("RGB").crop(c["xyxy"]).save(buf, format="JPEG", quality=92)
            data = buf.getvalue()
        h = compute_md5(data)
        if h in seen_hashes:
            continue
        seen_hashes.add(h)
        dst.write_bytes(data)
        new_rows.append({
            "crop_path": f"scripts/phase3/crops/{c['faction']}/{c['fname']}",
            "faction": c["faction"],
            "unit_slug": "",
            "notes": "",
            "source": "post_export" if c["is_post_export"] else "yolo_split",
        })
    print(f"Materialised {len(new_rows)} new crop files.")

    # ── Step 5: write labels.csv ───────────────────────────────────────
    labels_path = PHASE3 / "labels.csv"
    headers = ["crop_path", "faction", "unit_slug", "notes", "source"]
    merged: dict[str, dict] = {}
    for r in carried + new_rows:
        merged[r["crop_path"]] = {h: r.get(h, "") for h in headers}
    with labels_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        for k in sorted(merged):
            w.writerow(merged[k])

    total = len(merged)
    labelled = sum(1 for r in merged.values() if r["unit_slug"])
    unlabelled = total - labelled
    print(f"\nWrote {labels_path.relative_to(REPO_ROOT)}:")
    print(f"  Total rows: {total}")
    print(f"  Labelled:   {labelled}  (Phase 2 carry-over)")
    print(f"  Unlabelled: {unlabelled}  (for Sinan to label in the web tool)")

    # ── Step 6: write crops_index.jsonl for future scripts ─────────────
    idx_path = PHASE3 / "crops_index.jsonl"
    with idx_path.open("w") as f:
        for k in sorted(merged):
            r = merged[k]
            f.write(json.dumps({
                "crop_path": r["crop_path"],
                "faction": r["faction"],
                "source": r.get("source", ""),
            }) + "\n")
    print(f"Index: {idx_path.relative_to(REPO_ROOT)} ({total} entries)")

    print()
    print("Next step: re-point the labeller at phase3 and label unlabelled rows.")
    print("  export LABELLING_CROPS_DIR=../scripts/phase3/crops")
    print("  export LABELLING_LABELS_CSV=../scripts/phase3/labels.csv")
    print("  export LABELLING_CHEATSHEET=../scripts/phase3/unit_slugs_cheatsheet.md  # generate separately if needed")


if __name__ == "__main__":
    main()
