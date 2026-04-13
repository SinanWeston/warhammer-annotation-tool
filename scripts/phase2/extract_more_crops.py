#!/usr/bin/env python3
"""
Phase 2 — extract additional crops and seed a fresh labels.csv.

Pulls:
  - Every crop already labelled in phase1/labels.csv (copies the labels
    over so the user doesn't re-label them).
  - Additional GT crops from backend/yolo_dataset/images/val/ per the
    Phase 2 target mix in scripts/phase2/README.md (depth + breadth).

Output:
  scripts/phase2/crops/{faction}/*.jpg
  scripts/phase2/labels.csv          (pre-populated with phase1 labels;
                                       new rows have empty unit_slug)
  scripts/phase2/crops_index.jsonl
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PHASE1 = REPO_ROOT / "scripts" / "phase1"
PHASE2 = REPO_ROOT / "scripts" / "phase2"
VAL_IMAGES = REPO_ROOT / "backend" / "yolo_dataset" / "images" / "val"
VAL_LABELS = REPO_ROOT / "backend" / "yolo_dataset" / "labels" / "val"
DATA_YAML = REPO_ROOT / "backend" / "yolo_dataset" / "data.yaml"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from scraper_utils import compute_md5  # noqa: E402

UNITS_JSON = REPO_ROOT / "scripts" / "data" / "units.json"

# New-crop quotas on TOP of Phase 1's existing crops. Tune as needed.
# Roughly: +80 new crops across eight factions, biased for depth on
# YOLO-easy/Phase1-absent classes so the eval set has ≥ 30 queries.
NEW_QUOTA = {
    "chaos_space_marines": 10,
    "death_guard": 10,
    "thousand_sons": 3,
    "genestealer_cult": 15,
    "space_marines": 15,
    "tyranids": 20,
    "necrons": 10,
    "eldar": 10,
}

MIN_CROP_SIDE = 80
PADDING_PCT = 0.05


def load_class_names(yaml_path: Path) -> list[str]:
    for line in yaml_path.read_text().splitlines():
        if line.strip().startswith("names:"):
            raw = line.split(":", 1)[1].strip().strip("[]")
            return [n.strip().strip('"').strip("'") for n in raw.split(",") if n.strip()]
    raise ValueError(f"Could not parse class names from {yaml_path}")


def yolo_to_xyxy_padded(x_c, y_c, w, h, img_w, img_h, pad_pct):
    x_c_a, y_c_a = x_c * img_w, y_c * img_h
    w_a, h_a = w * img_w, h * img_h
    pw = w_a * pad_pct
    ph = h_a * pad_pct
    return (
        max(0, int(round(x_c_a - w_a / 2 - pw))),
        max(0, int(round(y_c_a - h_a / 2 - ph))),
        min(img_w, int(round(x_c_a + w_a / 2 + pw))),
        min(img_h, int(round(y_c_a + h_a / 2 + ph))),
    )


def generate_cheatsheet(target_factions: list[str]) -> str:
    """Produce scripts/phase2/unit_slugs_cheatsheet.md covering the 8 Phase 2 factions."""
    try:
        data = json.loads(UNITS_JSON.read_text())
    except Exception as e:
        return f"# Unit slugs cheatsheet\n\nCould not load units.json: {e}\n"
    factions = data.get("factions", {})
    lines = [
        "# Phase 2 unit slugs cheatsheet",
        "",
        "Extended from Phase 1 with necrons, eldar, thousand_sons coverage. "
        "When unsure, prefer the broader slug over guessing a variant.",
        "",
    ]
    for f in target_factions:
        fd = factions.get(f)
        if not fd:
            lines += [f"## {f}\n\n_Not found in units.json._\n"]
            continue
        lines.append(f"## {f} ({fd.get('name', f)})")
        lines.append("")
        for u in fd.get("units", []):
            slug = u["name"].lower().replace("'", "").replace(" ", "_")
            lines.append(f"- `{slug}` — {u['name']}")
        lines.append("")
    return "\n".join(lines)


def load_phase1_labels() -> list[dict]:
    csv_path = PHASE1 / "labels.csv"
    if not csv_path.exists():
        return []
    with csv_path.open() as f:
        return list(csv.DictReader(f))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    try:
        from PIL import Image
    except ImportError:
        sys.exit("PIL missing. Run from yolo_env.")

    class_names = load_class_names(DATA_YAML)
    crops_dir = PHASE2 / "crops"
    rng = random.Random(args.seed)

    # ── Step 1: copy the Phase 1 labels + crops over ──────────────────
    phase1_labels = load_phase1_labels()
    copied_crops = set()
    carried_rows = []
    for row in phase1_labels:
        crop_path_repo = row["crop_path"]  # "scripts/phase1/crops/faction/x.jpg"
        abs_src = REPO_ROOT / crop_path_repo
        if not abs_src.exists():
            continue
        faction = row["faction"]
        # Write into phase2/crops/{faction}/.
        dst_rel = Path("crops") / faction / abs_src.name
        abs_dst = PHASE2 / dst_rel
        abs_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(abs_src, abs_dst)
        copied_crops.add((faction, abs_src.name))
        new_row = dict(row)
        new_row["crop_path"] = f"scripts/phase2/{dst_rel.as_posix()}"
        # Drop any `split` column — auto_split will re-derive it.
        new_row.pop("split", None)
        carried_rows.append(new_row)
    print(f"Carried over {len(carried_rows)} Phase 1 rows (crops copied into phase2/crops/).")

    # ── Step 2: pull additional unlabelled crops up to NEW_QUOTA ──────
    images = sorted(p for p in VAL_IMAGES.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"))
    print(f"Scanning {len(images)} val images for new crops...")

    by_faction: dict[str, list[dict]] = {f: [] for f in NEW_QUOTA}
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
            if faction not in NEW_QUOTA:
                continue
            x1, y1, x2, y2 = yolo_to_xyxy_padded(x_c, y_c, w, h, img_w, img_h, PADDING_PCT)
            if (x2 - x1) < MIN_CROP_SIDE or (y2 - y1) < MIN_CROP_SIDE:
                continue
            out_name = f"{img_path.stem}__{box_idx:02d}.jpg"
            if (faction, out_name) in copied_crops:
                continue  # already have this from Phase 1
            by_faction[faction].append({
                "image_stem": img_path.stem,
                "box_idx": box_idx,
                "faction": faction,
                "xyxy": [x1, y1, x2, y2],
                "src": img_path,
                "out_name": out_name,
            })

    print("Candidate new crops by faction (already excluding Phase 1 overlap):")
    for f, crops in by_faction.items():
        print(f"  {f}: {len(crops)}  (new-quota target: {NEW_QUOTA[f]})")

    # Seeded random sample per quota.
    new_rows = []
    seen_hashes = set()
    for faction, quota in NEW_QUOTA.items():
        pool = sorted(by_faction[faction], key=lambda c: (c["image_stem"], c["box_idx"]))
        if len(pool) > quota:
            rng.shuffle(pool)
            pool = pool[:quota]
        for c in pool:
            with Image.open(c["src"]) as im:
                from io import BytesIO
                buf = BytesIO()
                im.convert("RGB").crop(c["xyxy"]).save(buf, format="JPEG", quality=92)
                data = buf.getvalue()
            h = compute_md5(data)
            if h in seen_hashes:
                continue
            seen_hashes.add(h)
            dst = crops_dir / c["faction"] / c["out_name"]
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(data)
            new_rows.append({
                "crop_path": f"scripts/phase2/crops/{c['faction']}/{c['out_name']}",
                "faction": c["faction"],
                "unit_slug": "",
                "notes": "",
            })
    print(f"Added {len(new_rows)} new crops across {len(NEW_QUOTA)} factions.")

    # ── Step 3: write phase2/labels.csv (phase1 labels + new empty rows) ──
    labels_path = PHASE2 / "labels.csv"
    headers = ["crop_path", "faction", "unit_slug", "notes"]
    # Deduplicate by crop_path, prefer carried rows (they have labels).
    merged = {}
    for row in carried_rows + new_rows:
        merged[row["crop_path"]] = {k: row.get(k, "") for k in headers}
    with labels_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        for key in sorted(merged):
            w.writerow(merged[key])
    print(f"Wrote {labels_path.relative_to(REPO_ROOT)} with {len(merged)} rows "
          f"({sum(1 for r in merged.values() if r['unit_slug'])} pre-labelled, "
          f"{sum(1 for r in merged.values() if not r['unit_slug'])} empty).")

    # ── Step 4: crops_index.jsonl for downstream scripts ───────────────
    index_rows = []
    for row in merged.values():
        index_rows.append({
            "crop_path": row["crop_path"],
            "faction": row["faction"],
        })
    with (PHASE2 / "crops_index.jsonl").open("w") as f:
        for r in index_rows:
            f.write(json.dumps(r) + "\n")
    print(f"Index: scripts/phase2/crops_index.jsonl ({len(index_rows)} entries)")

    # ── Step 5: write phase2/unit_slugs_cheatsheet.md ──────────────────
    cheatsheet_path = PHASE2 / "unit_slugs_cheatsheet.md"
    cheatsheet_path.write_text(generate_cheatsheet(list(NEW_QUOTA.keys())))
    print(f"Cheatsheet: scripts/phase2/unit_slugs_cheatsheet.md")

    print("\nNext step:")
    print("  1) Point the labeller at phase2:")
    print("       export LABELLING_CROPS_DIR=../scripts/phase2/crops")
    print("       export LABELLING_LABELS_CSV=../scripts/phase2/labels.csv")
    print("  2) (Re)start warhammer-analyzer backend, open /label, fill the new unit_slug rows.")
    print("  3) Run auto_split.py / build_gallery.py / embed_gallery.py / eval_scoped_retrieval.py")


if __name__ == "__main__":
    main()
