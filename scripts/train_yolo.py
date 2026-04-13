#!/usr/bin/env python3
"""
YOLO training for the Warhammer 40K miniature detector.

Supersedes the earlier train_yolo.py / train_yolo11.py / train_yolo_max.py
trio — same behaviour, exposed as CLI flags.

For production training runs, prefer Google Colab (train_yolo_colab.ipynb).
This script is useful for local smoke tests and CPU-only runs.

Examples:
    # Quick smoke test on CPU (nano model, low resolution, few epochs)
    python scripts/train_yolo.py --model yolov8n.pt --epochs 30 --imgsz 416 --batch 8

    # Full YOLO11x run matching runs/warhammer_yolo11x_r2/
    python scripts/train_yolo.py --model yolo11x.pt --epochs 100 --imgsz 640 --batch 2

    # Maximum augmentation (YOLOv8s, heavy augment preset)
    python scripts/train_yolo.py --model yolov8s.pt --epochs 100 --imgsz 640 --batch 4 --heavy-augment

    # GPU run
    python scripts/train_yolo.py --model yolo11x.pt --device cuda:0 --batch 16
"""

import argparse
from pathlib import Path
from ultralytics import YOLO

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_YAML = REPO_ROOT / "backend" / "yolo_dataset" / "data.yaml"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "runs"


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", default="yolo11x.pt",
                   help="Pretrained model weights (yolov8n.pt, yolov8s.pt, yolo11x.pt, ...). Default: yolo11x.pt")
    p.add_argument("--data", default=str(DEFAULT_DATA_YAML), help="Path to data.yaml")
    p.add_argument("--output", default=str(DEFAULT_OUTPUT_DIR), help="Training output directory")
    p.add_argument("--name", default=None, help="Run name (defaults to warhammer_<model_stem>)")

    p.add_argument("--epochs", type=int, default=100)
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument("--batch", type=int, default=2, help="Batch size. Keep small (2-4) for CPU.")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--patience", type=int, default=20, help="Early-stop patience in epochs")
    p.add_argument("--device", default="cpu", help="'cpu', 'cuda:0', '0', etc.")
    p.add_argument("--save-period", type=int, default=5)
    p.add_argument("--heavy-augment", action="store_true",
                   help="Enable aggressive HSV + perspective augmentation (matches old train_yolo_max.py)")
    return p.parse_args()


def train(args):
    model = YOLO(args.model)
    run_name = args.name or f"warhammer_{Path(args.model).stem}"

    train_kwargs = dict(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        workers=args.workers,
        patience=args.patience,
        device=args.device,

        # Core augmentation (shared across all runs)
        degrees=15,
        translate=0.1,
        scale=0.5,
        shear=5,
        flipud=0.1,
        fliplr=0.5,
        mosaic=1.0,
        mixup=0.15,
        copy_paste=0.1,
        dropout=0.1,

        save=True,
        save_period=args.save_period,
        project=args.output,
        name=run_name,
        exist_ok=True,
        verbose=True,
        plots=True,
    )

    if args.heavy_augment:
        # Paint-scheme and angle variation — mirrors the old train_yolo_max.py preset.
        train_kwargs.update(
            hsv_h=0.015,
            hsv_s=0.7,
            hsv_v=0.4,
            perspective=0.0005,
            lr0=0.01,
            lrf=0.01,
            warmup_epochs=5,
            weight_decay=0.0005,
            box=7.5,
            cls=0.5,
        )

    model.train(**train_kwargs)

    best_weights = Path(args.output) / run_name / "weights" / "best.pt"
    if best_weights.exists():
        metrics = YOLO(str(best_weights)).val(data=args.data)
        print("\n=== Final metrics ===")
        print(f"mAP50:    {metrics.box.map50:.3f}")
        print(f"mAP50-95: {metrics.box.map:.3f}")
        print(f"Precision: {metrics.box.mp:.3f}")
        print(f"Recall:    {metrics.box.mr:.3f}")
        print(f"\nBest weights: {best_weights}")


if __name__ == "__main__":
    train(parse_args())
