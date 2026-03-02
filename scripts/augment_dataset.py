"""
Dataset Augmentation Script

Takes annotated images + their YOLO label files and generates augmented variants.
Bounding boxes are transformed alongside the images using albumentations.

Usage:
    python3 augment_dataset.py [--input backend/yolo_dataset] [--output backend/yolo_dataset_augmented] [--ratio 4]

    First export the dataset using the YOLO export endpoint, then run this script.

Dependencies:
    pip install albumentations opencv-python-headless
"""

import os
import sys
import argparse
import shutil
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="Augment YOLO dataset with bbox-aware transforms")
    parser.add_argument("--input", type=str, default=None, help="Input YOLO dataset directory")
    parser.add_argument("--output", type=str, default=None, help="Output augmented dataset directory")
    parser.add_argument("--ratio", type=int, default=4, help="Augmentation ratio (default: 4x)")
    parser.add_argument("--faction-ratios", type=str, default=None,
                        help="Comma-separated faction=ratio overrides, e.g. 'death_guard=8,adeptus_mechanicus=6'")
    parser.add_argument("--train-only", action="store_true", help="Only augment train split (default)")
    args = parser.parse_args()

    try:
        import albumentations as A
        import cv2
    except ImportError:
        print("ERROR: Missing dependencies. Install with:")
        print("  pip install albumentations opencv-python-headless")
        sys.exit(1)

    script_dir = Path(__file__).parent
    project_root = script_dir.parent

    input_dir = Path(args.input) if args.input else project_root / "backend" / "yolo_dataset"
    output_dir = Path(args.output) if args.output else project_root / "backend" / "yolo_dataset_augmented"

    if not input_dir.exists():
        print(f"ERROR: Input directory not found: {input_dir}")
        print("Run the YOLO export first: curl -X POST http://localhost:3001/api/annotate/export")
        sys.exit(1)

    # Parse per-faction ratio overrides
    faction_ratios = {}
    if args.faction_ratios:
        for pair in args.faction_ratios.split(","):
            faction, ratio = pair.strip().split("=")
            faction_ratios[faction.strip()] = int(ratio.strip())

    # Augmentation pipeline — safe for miniature photography
    transform = A.Compose([
        A.HorizontalFlip(p=0.5),
        A.RandomBrightnessContrast(brightness_limit=0.2, contrast_limit=0.2, p=0.5),
        A.HueSaturationValue(hue_shift_limit=10, sat_shift_limit=20, val_shift_limit=15, p=0.3),
        A.GaussianBlur(blur_limit=(3, 5), p=0.2),
        A.ImageCompression(quality_lower=70, quality_upper=100, p=0.3),
    ], bbox_params=A.BboxParams(format='yolo', label_fields=['class_labels'], min_visibility=0.3))

    # Process train split
    splits = ["train"] if args.train_only else ["train", "val"]

    for split in splits:
        images_dir = input_dir / "images" / split
        labels_dir = input_dir / "labels" / split

        if not images_dir.exists():
            print(f"Skipping {split}: {images_dir} not found")
            continue

        out_images = output_dir / "images" / split
        out_labels = output_dir / "labels" / split
        out_images.mkdir(parents=True, exist_ok=True)
        out_labels.mkdir(parents=True, exist_ok=True)

        # Copy originals first
        image_files = sorted([f for f in images_dir.iterdir() if f.suffix.lower() in {".jpg", ".jpeg", ".png"}])
        print(f"\n{split}: {len(image_files)} original images")

        total_augmented = 0

        for img_path in image_files:
            label_path = labels_dir / f"{img_path.stem}.txt"

            # Copy original
            shutil.copy2(img_path, out_images / img_path.name)
            if label_path.exists():
                shutil.copy2(label_path, out_labels / label_path.name)

            # Read image
            image = cv2.imread(str(img_path))
            if image is None:
                print(f"  WARNING: Could not read {img_path.name}")
                continue
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

            # Read YOLO labels
            bboxes = []
            class_labels = []
            if label_path.exists():
                with open(label_path) as f:
                    for line in f:
                        parts = line.strip().split()
                        if len(parts) >= 5:
                            cls = int(parts[0])
                            x_center, y_center, w, h = map(float, parts[1:5])
                            bboxes.append([x_center, y_center, w, h])
                            class_labels.append(cls)

            # Determine ratio for this image
            # Try to infer faction from filename or label
            ratio = args.ratio
            for faction, custom_ratio in faction_ratios.items():
                if faction in img_path.stem:
                    ratio = custom_ratio
                    break

            # Generate augmented versions
            for aug_idx in range(ratio):
                try:
                    transformed = transform(
                        image=image,
                        bboxes=bboxes,
                        class_labels=class_labels
                    )

                    aug_image = transformed['image']
                    aug_bboxes = transformed['bboxes']
                    aug_classes = transformed['class_labels']

                    # Save augmented image
                    aug_name = f"{img_path.stem}_aug{aug_idx}{img_path.suffix}"
                    aug_img_path = out_images / aug_name
                    cv2.imwrite(str(aug_img_path), cv2.cvtColor(aug_image, cv2.COLOR_RGB2BGR))

                    # Save augmented labels
                    aug_label_path = out_labels / f"{img_path.stem}_aug{aug_idx}.txt"
                    with open(aug_label_path, "w") as f:
                        for cls, bbox in zip(aug_classes, aug_bboxes):
                            x_c, y_c, w, h = bbox
                            f.write(f"{cls} {x_c:.6f} {y_c:.6f} {w:.6f} {h:.6f}\n")

                    total_augmented += 1

                except Exception as e:
                    # Some augmentations may remove all boxes (min_visibility filter)
                    pass

        print(f"  Generated {total_augmented} augmented images")
        print(f"  Total: {len(image_files) + total_augmented} images")

    # Copy data.yaml and classes.txt
    for cfg_file in ["data.yaml", "classes.txt"]:
        src = input_dir / cfg_file
        if src.exists():
            # Update paths in data.yaml
            if cfg_file == "data.yaml":
                with open(src) as f:
                    content = f.read()
                content = content.replace(str(input_dir), str(output_dir))
                with open(output_dir / cfg_file, "w") as f:
                    f.write(content)
            else:
                shutil.copy2(src, output_dir / cfg_file)

    print(f"\nAugmented dataset written to: {output_dir}")
    print("Use this directory for YOLO training instead of the original.")

if __name__ == "__main__":
    main()
