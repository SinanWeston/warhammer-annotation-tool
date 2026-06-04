"""Wave 0: pull CC-licensed Roboflow Universe Warhammer datasets (Image Sourcing Plan).

Downloads named Roboflow Universe datasets (labeled bboxes) and ingests them into the
wh40k_pile FiftyOne dataset with the provenance sidecar (§A8). These are the cleanest-
licensed seed we get; ingested license_status='cc_by' but product_safe=False until the
license is confirmed per-dataset and deliberately promoted.

Disk-floor guard: aborts before download if free space < FLOOR_GB (default 10).

Reads ROBOFLOW_API_KEY from .env. Reuses the labels as detection ground truth.

Usage:
  fiftyone_env/bin/python scripts/curation/acquire_roboflow.py [--floor-gb 10]
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import fiftyone as fo
import fiftyone.types as fot

REPO = Path(__file__).resolve().parents[2]
STAGING = REPO / "acquisition" / "roboflow"

# (workspace, project, realism_tier)  — found via Roboflow Universe search
DATASETS = [
    ("davide-puopolo-9xomj", "warhammer-40.000-miniature", "T1"),
    ("jonas-krger", "warhammer-40k-minins", "T1"),
]


def read_api_key() -> str:
    for line in (REPO / ".env").read_text().splitlines():
        if line.strip().startswith("ROBOFLOW_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("ROBOFLOW_API_KEY not found in .env")


def free_gb(path: Path) -> float:
    return shutil.disk_usage(path).free / 1e9


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--floor-gb", type=float, default=10.0)
    args = ap.parse_args()

    if free_gb(REPO) <= args.floor_gb:
        raise SystemExit(f"disk floor hit ({free_gb(REPO):.1f} GB free <= {args.floor_gb}); abort")

    from roboflow import Roboflow
    rf = Roboflow(api_key=read_api_key())
    STAGING.mkdir(parents=True, exist_ok=True)

    ds = fo.load_dataset("wh40k_pile")
    added_total = 0

    for ws, proj, tier in DATASETS:
        if free_gb(REPO) <= args.floor_gb:
            print(f"disk floor hit before {proj}; stopping.")
            break
        slug = f"roboflow:{proj}"
        dest = STAGING / proj
        try:
            project = rf.workspace(ws).project(proj)
            version = project.versions()[0]  # latest
            print(f"downloading {ws}/{proj} v{version.version} -> {dest}")
            version.download("yolov8", location=str(dest), overwrite=True)
        except Exception as e:
            print(f"  ! download failed for {proj}: {type(e).__name__}: {str(e)[:120]}")
            continue

        # load the downloaded YOLO dataset (has detections) and stamp provenance
        try:
            tmp = fo.Dataset.from_dir(
                dataset_dir=str(dest),
                dataset_type=fot.YOLOv5Dataset,
                split="train",
                label_field="roboflow_gt",
            )
        except Exception as e:
            print(f"  ! load failed for {proj}: {type(e).__name__}: {str(e)[:120]}")
            continue

        for s in tmp:
            s["source"] = slug
            s["corpus"] = "roboflow"
            s["weak_faction"] = None
            s["weak_unit"] = None
            s["pool"] = "detection"
            s["source_url"] = f"https://universe.roboflow.com/{ws}/{proj}"
            s["label_source"] = "roboflow_bbox"
            s["label_confidence"] = 0.9
            s["finish_state"] = "painted"
            s["realism_tier"] = tier
            s["is_negative"] = False
            s["not_gw"] = False
            s["license_status"] = "cc_by"
            s["product_safe"] = False  # promote after confirming license
            s.tags.append("roboflow")
        ds.add_samples(tmp)
        added_total += len(tmp)
        print(f"  ingested {len(tmp)} images from {proj}")
        tmp.delete()

    print(f"\nWave 0 Roboflow: added {added_total} images. Dataset now {ds.count()}.")
    print("source counts (roboflow):",
          {k: v for k, v in ds.count_values("source").items() if str(k).startswith("roboflow")})
    print(f"free disk: {free_gb(REPO):.1f} GB")


if __name__ == "__main__":
    main()
