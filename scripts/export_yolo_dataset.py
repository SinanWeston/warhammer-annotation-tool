"""
Export annotated images to YOLO detection format.

Reads annotation JSONs from backend/training_data_annotations/,
copies images and creates YOLO label files in backend/yolo_dataset/.

Usage:
    python3 scripts/export_yolo_dataset.py
    python3 scripts/export_yolo_dataset.py --balanced
    python3 scripts/export_yolo_dataset.py --train-split 0.85
"""

import json
import os
import shutil
import argparse
import random
from pathlib import Path
from collections import defaultdict


def main():
    parser = argparse.ArgumentParser(description="Export annotations to YOLO format")
    parser.add_argument("--train-split", type=float, default=0.8, help="Train/val split ratio")
    parser.add_argument("--balanced", action="store_true", help="Cap each faction at min count")
    parser.add_argument("--balanced-cap", type=int, default=None, help="Custom per-faction cap")
    parser.add_argument("--output", type=str, default=None, help="Output directory")
    args = parser.parse_args()

    project_root = Path(__file__).parent.parent
    annotations_dir = project_root / "backend" / "training_data_annotations"
    output_dir = Path(args.output) if args.output else project_root / "backend" / "yolo_dataset"

    # Clean output
    for subdir in ["images/train", "images/val", "labels/train", "labels/val"]:
        d = output_dir / subdir
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True, exist_ok=True)

    # Load all annotations
    entries = []
    classes_set = set()
    skipped = 0
    missing = 0

    for fname in sorted(os.listdir(annotations_dir)):
        if not fname.endswith(".json") or fname.endswith(".skip.json"):
            continue

        fpath = annotations_dir / fname
        with open(fpath) as f:
            data = json.load(f)

        anns = data.get("annotations", [])
        if not anns:
            skipped += 1
            continue

        image_path = Path(data["imagePath"])
        if not image_path.exists():
            missing += 1
            continue

        for ann in anns:
            classes_set.add(ann["classLabel"])

        entries.append(data)

    print(f"Loaded {len(entries)} annotated images ({skipped} empty, {missing} missing)")

    # Build class mapping (sorted alphabetically)
    classes = sorted(classes_set)
    class_to_idx = {c: i for i, c in enumerate(classes)}
    print(f"Classes ({len(classes)}): {', '.join(classes)}")

    # Group by faction for balanced export
    if args.balanced or args.balanced_cap:
        by_faction = defaultdict(list)
        for entry in entries:
            by_faction[entry["faction"]].append(entry)

        cap = args.balanced_cap or min(len(v) for v in by_faction.values())
        print(f"Balanced export: capping each faction at {cap}")

        balanced = []
        for faction, faction_entries in sorted(by_faction.items()):
            random.shuffle(faction_entries)
            capped = faction_entries[:cap]
            balanced.extend(capped)
            print(f"  {faction}: {len(capped)}/{len(faction_entries)}")

        entries = balanced

    # Shuffle and split
    random.shuffle(entries)
    train_count = int(len(entries) * args.train_split)
    train_set = entries[:train_count]
    val_set = entries[train_count:]

    print(f"\nSplit: {len(train_set)} train / {len(val_set)} val")

    # Export
    def export_entry(entry, split):
        img_dir = output_dir / "images" / split
        lbl_dir = output_dir / "labels" / split

        src_path = Path(entry["imagePath"])
        img_name = src_path.name
        lbl_name = src_path.stem + ".txt"

        # Copy image
        shutil.copy2(str(src_path), str(img_dir / img_name))

        # Write YOLO label
        lines = []
        w = entry["width"]
        h = entry["height"]

        for ann in entry["annotations"]:
            cls_idx = class_to_idx.get(ann["classLabel"])
            if cls_idx is None:
                continue

            bbox = ann["modelBbox"]
            x_center = (bbox["x"] + bbox["width"] / 2) / w
            y_center = (bbox["y"] + bbox["height"] / 2) / h
            bw = bbox["width"] / w
            bh = bbox["height"] / h

            # Clamp to [0, 1]
            x_center = max(0, min(1, x_center))
            y_center = max(0, min(1, y_center))
            bw = max(0, min(1, bw))
            bh = max(0, min(1, bh))

            lines.append(f"{cls_idx} {x_center:.6f} {y_center:.6f} {bw:.6f} {bh:.6f}")

        with open(lbl_dir / lbl_name, "w") as f:
            f.write("\n".join(lines))

    for entry in train_set:
        export_entry(entry, "train")
    for entry in val_set:
        export_entry(entry, "val")

    # Write data.yaml
    yaml_content = f"""# YOLO Dataset Configuration
path: {output_dir.resolve()}
train: images/train
val: images/val

# Classes
nc: {len(classes)}
names: [{', '.join(f'"{c}"' for c in classes)}]
"""
    with open(output_dir / "data.yaml", "w") as f:
        f.write(yaml_content)

    # Write classes.txt
    with open(output_dir / "classes.txt", "w") as f:
        f.write("\n".join(classes))

    # Per-faction summary
    faction_counts = defaultdict(int)
    for entry in entries:
        faction_counts[entry["faction"]] += 1

    print(f"\nPer-faction breakdown:")
    for faction, count in sorted(faction_counts.items(), key=lambda x: -x[1]):
        print(f"  {faction}: {count}")

    print(f"\nExported to {output_dir}")
    print(f"  Train: {len(train_set)} images")
    print(f"  Val:   {len(val_set)} images")
    print(f"  Classes: {len(classes)}")
    print(f"\ndata.yaml written with {len(classes)} classes")


if __name__ == "__main__":
    main()
