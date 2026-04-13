#!/usr/bin/env python3
"""
Phase 1 — extract ground-truth crops from the YOLO val set.

Walks backend/yolo_dataset/images/val/, reads matching labels/val/*.txt,
and crops every GT box to a JPEG in scripts/phase1/crops/{faction}/.
Writes crops_index.jsonl for downstream scripts.

Also produces a seeded labels.csv containing the target-mix subset ready
for hand-labelling (unit_slug column is left blank for Sinan to fill).

Target mix (biased toward YOLO-problem classes per phase0 findings):
    chaos_space_marines   15  (Phase 0 faction top-1: 8.0%)
    death_guard           10  (7.7%)
    genestealer_cult       8  (6.7%)
    tyranids               5  (control — YOLO-easy)
    space_marines          2  (control)

Usage:
    yolo_env/bin/python3 scripts/phase1/extract_gt_crops.py
    yolo_env/bin/python3 scripts/phase1/extract_gt_crops.py --seed 42

Outputs:
    scripts/phase1/crops/{faction}/{val_stem}__{box_idx}.jpg
    scripts/phase1/crops_index.jsonl
    scripts/phase1/labels.csv
    scripts/phase1/unit_slugs_cheatsheet.md
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PHASE1_DIR = REPO_ROOT / "scripts" / "phase1"
VAL_IMAGES = REPO_ROOT / "backend" / "yolo_dataset" / "images" / "val"
VAL_LABELS = REPO_ROOT / "backend" / "yolo_dataset" / "labels" / "val"
DATA_YAML = REPO_ROOT / "backend" / "yolo_dataset" / "data.yaml"
UNITS_JSON = REPO_ROOT / "scripts" / "data" / "units.json"

# Reuse scripts/scraper_utils.compute_md5
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from scraper_utils import compute_md5  # noqa: E402

TARGET_MIX = {
    "chaos_space_marines": 15,
    "death_guard": 10,
    "genestealer_cult": 8,
    "tyranids": 5,
    "space_marines": 2,
}

MIN_CROP_SIDE = 80  # px
PADDING_PCT = 0.05  # 5% padding on each side to avoid cutting limbs


def load_class_names(yaml_path: Path) -> list[str]:
    """Parse class names list from data.yaml without pulling in a YAML dep."""
    for line in yaml_path.read_text().splitlines():
        if line.strip().startswith("names:"):
            raw = line.split(":", 1)[1].strip()
            # Strip the [...] wrapper and split on commas that are outside quotes.
            raw = raw.strip("[]")
            names = [n.strip().strip('"').strip("'") for n in raw.split(",")]
            return [n for n in names if n]
    raise ValueError(f"Could not parse class names from {yaml_path}")


def yolo_to_xyxy_padded(x_c, y_c, w, h, img_w, img_h, pad_pct):
    """YOLO normalized → absolute xyxy with padding, clipped to image bounds."""
    x_c_a, y_c_a = x_c * img_w, y_c * img_h
    w_a, h_a = w * img_w, h * img_h
    pad_w = w_a * pad_pct
    pad_h = h_a * pad_pct
    x1 = max(0, int(round(x_c_a - w_a / 2 - pad_w)))
    y1 = max(0, int(round(y_c_a - h_a / 2 - pad_h)))
    x2 = min(img_w, int(round(x_c_a + w_a / 2 + pad_w)))
    y2 = min(img_h, int(round(y_c_a + h_a / 2 + pad_h)))
    return x1, y1, x2, y2


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--seed", type=int, default=42, help="Seed for target-mix sampling")
    p.add_argument("--skip-cheatsheet", action="store_true")
    return p.parse_args()


def generate_cheatsheet(target_factions: list[str]) -> str:
    """Pull the unit list for each target faction from units.json."""
    try:
        data = json.loads(UNITS_JSON.read_text())
    except Exception as e:
        return f"# Unit slugs cheatsheet\n\nCould not load units.json: {e}\n"

    factions = data.get("factions", {})
    lines = [
        "# Unit slugs cheatsheet",
        "",
        "Suggested `unit_slug` values for each target faction, pulled from",
        "`scripts/data/units.json`. Use the `name` verbatim (lowercase, underscores),",
        "e.g. `chaos_lord`, `legionaries`, `termagants`.",
        "",
        "When in doubt, prefer a broader slug (e.g. `intercessors` rather than",
        "`heavy_intercessors` if you can't tell the variant).",
        "",
    ]
    for faction in target_factions:
        fdata = factions.get(faction)
        if not fdata:
            lines.append(f"## {faction}\n\n_Not found in units.json._\n")
            continue
        unit_names = [u["name"] for u in fdata.get("units", [])]
        lines.append(f"## {faction} ({fdata.get('name', faction)})")
        lines.append("")
        for name in unit_names:
            slug = name.lower().replace("'", "").replace(" ", "_")
            lines.append(f"- `{slug}` — {name}")
        lines.append("")
    return "\n".join(lines)


def main():
    args = parse_args()
    class_names = load_class_names(DATA_YAML)
    target_factions = list(TARGET_MIX.keys())

    # Verify target factions exist in the model's class list.
    for f in target_factions:
        if f not in class_names:
            sys.exit(f"Target faction '{f}' not in class list {class_names}")

    # Import PIL lazily — it's in yolo_env but isn't on a stock system python.
    try:
        from PIL import Image
    except ImportError:
        sys.exit("PIL not installed. Run from yolo_env: yolo_env/bin/python3 ...")

    # Walk val, collect all crops.
    all_crops: list[dict] = []  # each entry: {image_stem, box_idx, faction, xyxy, img_w, img_h, src_image}
    images = sorted(p for p in VAL_IMAGES.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"))
    print(f"Scanning {len(images)} val images for ground-truth boxes...")

    for img_path in images:
        label_path = VAL_LABELS / f"{img_path.stem}.txt"
        if not label_path.exists():
            continue
        with Image.open(img_path) as im:
            img_w, img_h = im.size
        for box_idx, line in enumerate(label_path.read_text().splitlines()):
            parts = line.strip().split()
            if len(parts) < 5:
                continue
            cls_id = int(parts[0])
            x_c, y_c, w, h = (float(v) for v in parts[1:5])
            faction = class_names[cls_id]
            if faction not in TARGET_MIX:
                continue
            x1, y1, x2, y2 = yolo_to_xyxy_padded(x_c, y_c, w, h, img_w, img_h, PADDING_PCT)
            if (x2 - x1) < MIN_CROP_SIDE or (y2 - y1) < MIN_CROP_SIDE:
                continue
            all_crops.append({
                "image_stem": img_path.stem,
                "box_idx": box_idx,
                "faction": faction,
                "xyxy_abs": [x1, y1, x2, y2],
                "img_w": img_w,
                "img_h": img_h,
                "src_image": str(img_path.relative_to(REPO_ROOT)),
            })

    by_faction: dict[str, list[dict]] = {f: [] for f in TARGET_MIX}
    for c in all_crops:
        by_faction[c["faction"]].append(c)
    print("Candidate crops by faction (after size filter):")
    for f, crops in by_faction.items():
        print(f"  {f}: {len(crops)} (target: {TARGET_MIX[f]})")

    # Seeded sample per target mix. If fewer crops exist than target, take them all.
    rng = random.Random(args.seed)
    selected: list[dict] = []
    for faction, quota in TARGET_MIX.items():
        crops = sorted(by_faction[faction], key=lambda c: (c["image_stem"], c["box_idx"]))
        if len(crops) <= quota:
            selected.extend(crops)
            if len(crops) < quota:
                print(f"  ⚠ {faction}: only {len(crops)} available, target was {quota}")
        else:
            rng.shuffle(crops)
            selected.extend(crops[:quota])

    print(f"\nSelected {len(selected)} crops total.")

    # Write crops to disk (dedup by MD5 of the cropped bytes).
    seen_hashes: set[str] = set()
    crops_dir = PHASE1_DIR / "crops"
    index_entries: list[dict] = []
    for c in selected:
        faction_dir = crops_dir / c["faction"]
        faction_dir.mkdir(parents=True, exist_ok=True)
        x1, y1, x2, y2 = c["xyxy_abs"]
        src_path = REPO_ROOT / c["src_image"]
        with Image.open(src_path) as im:
            crop = im.convert("RGB").crop((x1, y1, x2, y2))
            from io import BytesIO
            buf = BytesIO()
            crop.save(buf, format="JPEG", quality=92)
            data = buf.getvalue()
        md5 = compute_md5(data)
        if md5 in seen_hashes:
            continue
        seen_hashes.add(md5)

        out_name = f"{c['image_stem']}__{c['box_idx']:02d}.jpg"
        out_path = faction_dir / out_name
        out_path.write_bytes(data)
        index_entries.append({
            "crop_path": str(out_path.relative_to(REPO_ROOT)),
            "faction": c["faction"],
            "source_image": c["src_image"],
            "box_idx": c["box_idx"],
            "xyxy_abs": c["xyxy_abs"],
            "md5": md5,
        })

    # Write crops_index.jsonl.
    index_path = PHASE1_DIR / "crops_index.jsonl"
    with index_path.open("w") as f:
        for entry in index_entries:
            f.write(json.dumps(entry) + "\n")
    print(f"\nWrote {len(index_entries)} unique crops to {crops_dir.relative_to(REPO_ROOT)}/")
    print(f"Index: {index_path.relative_to(REPO_ROOT)}")

    # Seed labels.csv for hand-labelling.
    labels_path = PHASE1_DIR / "labels.csv"
    with labels_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["crop_path", "faction", "unit_slug", "notes"])
        for entry in sorted(index_entries, key=lambda e: (e["faction"], e["crop_path"])):
            writer.writerow([entry["crop_path"], entry["faction"], "", ""])
    print(f"Seeded: {labels_path.relative_to(REPO_ROOT)} — fill the unit_slug column.")

    # Cheatsheet.
    if not args.skip_cheatsheet:
        cheatsheet_path = PHASE1_DIR / "unit_slugs_cheatsheet.md"
        cheatsheet_path.write_text(generate_cheatsheet(target_factions))
        print(f"Cheatsheet: {cheatsheet_path.relative_to(REPO_ROOT)}")

    print("\nNext step: open scripts/phase1/labels.csv and fill unit_slug for each row.")
    print("Reference scripts/phase1/unit_slugs_cheatsheet.md for valid slug suggestions.")


if __name__ == "__main__":
    main()
