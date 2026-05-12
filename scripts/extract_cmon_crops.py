#!/usr/bin/env python3
"""Run the YOLO detector over every CMON image and emit crops + label rows.

Writes:
- `data/crops/cmon/{entry_id}/{view_idx:02}_{box_idx:02}.jpg`
- appended rows in `data/labels.csv` (v2 schema)
- `data/logs/extract_cmon_YYYY-MM-DD.log`
- sidecar `{instance}_v{N}_nobox.json` under `data/logs/cmon_nobox/` for
  images the detector rejected, so we can audit the zero-box rate.

Resume-safe: already-labelled entries are skipped based on the presence of
their sentinel crop_path (`…/00_00.jpg`) in `data/labels.csv`.

Usage:
    yolo_env/bin/python3 scripts/extract_cmon_crops.py                  # full run
    yolo_env/bin/python3 scripts/extract_cmon_crops.py --limit 20       # spot-check
    yolo_env/bin/python3 scripts/extract_cmon_crops.py --min-confidence 0.4
    yolo_env/bin/python3 scripts/extract_cmon_crops.py --no-resume      # re-extract all
    yolo_env/bin/python3 scripts/extract_cmon_crops.py --device cpu     # force CPU
"""

from __future__ import annotations

import argparse
import datetime as _dt
import logging
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "src"))

from photoanalyzer.detect.yolo import DEFAULT_MODEL_PATH, YoloDetector  # noqa: E402
from photoanalyzer.label.extract import (  # noqa: E402
    extract_crops_for_source,
    iter_cmon_source_images,
)


def _setup_logging(log_dir: Path):
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"extract_cmon_{_dt.date.today().isoformat()}.log"
    handler = logging.FileHandler(log_path)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    # Also echo to stderr
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    root.addHandler(sh)
    return log_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cmon-root", type=Path,
                    default=REPO / "scripts" / "cmon")
    ap.add_argument("--labels-csv", type=Path,
                    default=REPO / "data" / "labels.csv")
    ap.add_argument("--crops-root", type=Path,
                    default=REPO / "data" / "crops")
    ap.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH,
                    help="YOLO .pt path (default: runs/yolo11x_run2_best.pt)")
    ap.add_argument("--min-confidence", type=float, default=0.25)
    ap.add_argument("--device", type=str, default=None,
                    help="Force device (cpu | cuda | mps). Default: auto.")
    ap.add_argument("--limit", type=int, default=None,
                    help="Only process first N CMON entries (spot-check)")
    ap.add_argument("--no-resume", action="store_true",
                    help="Re-process entries even if their crop rows exist")
    args = ap.parse_args()

    log_dir = REPO / "data" / "logs"
    log_path = _setup_logging(log_dir)

    # Ensure output dirs exist
    args.crops_root.mkdir(parents=True, exist_ok=True)
    args.labels_csv.parent.mkdir(parents=True, exist_ok=True)

    log = logging.getLogger("extract_cmon_crops")
    log.info("start: cmon_root=%s labels=%s crops=%s model=%s",
             args.cmon_root, args.labels_csv, args.crops_root, args.model)

    detector = YoloDetector(
        model_path=args.model,
        conf_threshold=args.min_confidence,
        device=args.device,
    )

    sources = iter_cmon_source_images(args.cmon_root, limit=args.limit)

    stats = extract_crops_for_source(
        sources,
        detector,
        labels_csv_path=args.labels_csv,
        crops_root=args.crops_root,
        min_detector_confidence=args.min_confidence,
        resume=not args.no_resume,
        nobox_log_dir=log_dir / "cmon_nobox",
    )

    print(f"\nDone. log → {log_path}")
    print(f"  images_seen           : {stats.images_seen}")
    print(f"  images_skipped_resume : {stats.images_skipped_resume}")
    print(f"  images_no_boxes       : {stats.images_no_boxes}")
    print(f"  multi_box_images      : {stats.multi_box_images}")
    print(f"  crops_written         : {stats.crops_written}")
    print(f"  per_source            : {dict(stats.per_source)}")


if __name__ == "__main__":
    main()
