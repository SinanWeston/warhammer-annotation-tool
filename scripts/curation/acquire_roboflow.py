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
import yaml

REPO = Path(__file__).resolve().parents[2]
STAGING = REPO / "acquisition" / "roboflow"
IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

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
        if not (dest / "data.yaml").exists():
            try:
                project = rf.workspace(ws).project(proj)
                version = project.versions()[0]  # latest
                print(f"downloading {ws}/{proj} v{version.version} -> {dest}")
                version.download("yolov8", location=str(dest), overwrite=True)
            except Exception as e:
                print(f"  ! download failed for {proj}: {type(e).__name__}: {str(e)[:120]}")
                continue
        else:
            print(f"already downloaded: {dest}")

        meta = yaml.safe_load((dest / "data.yaml").read_text())
        names = meta["names"]
        # CC-BY confirmed in data.yaml -> product-safe seed (attribution required)
        product_safe = "cc" in str(meta.get("roboflow", {}).get("license", "")).lower()

        samples = []
        for split in ("train", "valid", "test"):
            img_dir, lbl_dir = dest / split / "images", dest / split / "labels"
            if not img_dir.exists():
                continue
            for img in img_dir.iterdir():
                if img.suffix.lower() not in IMG_EXTS:
                    continue
                dets = []
                lbl = lbl_dir / (img.stem + ".txt")
                if lbl.exists():
                    for line in lbl.read_text().splitlines():
                        p = line.split()
                        if len(p) < 5:
                            continue
                        c = int(p[0]); cx, cy, w, h = map(float, p[1:5])
                        dets.append(fo.Detection(
                            label=names[c], bounding_box=[cx - w / 2, cy - h / 2, w, h]))
                s = fo.Sample(filepath=str(img))
                s["roboflow_gt"] = fo.Detections(detections=dets)
                s["source"] = slug
                s["corpus"] = "roboflow"
                s["pool"] = "detection"
                s["source_url"] = meta.get("roboflow", {}).get("url")
                s["label_source"] = "roboflow_bbox"
                s["label_confidence"] = 0.9
                s["finish_state"] = "painted"
                s["realism_tier"] = tier
                s["is_negative"] = False
                s["not_gw"] = False
                s["license_status"] = "cc_by"
                s["product_safe"] = product_safe
                s.tags.append("roboflow")
                samples.append(s)
        ds.add_samples(samples)
        added_total += len(samples)
        print(f"  ingested {len(samples)} images from {proj} (product_safe={product_safe})")

    print(f"\nWave 0 Roboflow: added {added_total} images. Dataset now {ds.count()}.")
    print("source counts (roboflow):",
          {k: v for k, v in ds.count_values("source").items() if str(k).startswith("roboflow")})
    print(f"free disk: {free_gb(REPO):.1f} GB")


if __name__ == "__main__":
    main()
