"""Build a downsized image bundle for GPU embedding on Colab (Battle Scanner Plan D1).

The 60k-image pile lives locally; Colab GPU can't see it. Rather than ship ~28 GB
of originals, downsize every sample to a small JPEG (max side 384) and tar it up
(~2-3 GB). A manifest maps bundle index -> original filepath so embeddings can be
matched back to FiftyOne samples after the GPU run.

Corrupt/unreadable images are recorded as failures in the manifest (status=fail)
and skipped — that list is itself useful junk-filter signal.

Usage:
  fiftyone_env/bin/python scripts/curation/prepare_embed_bundle.py \
      [--name wh40k_pile] [--out ~/Downloads/wh40k_embed_bundle] [--max-side 384] [--workers 8]
"""
from __future__ import annotations

import argparse
import csv
import os
import tarfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import fiftyone as fo
from PIL import Image, ImageOps

Image.MAX_IMAGE_PIXELS = None  # tolerate large scraped images


def resize_one(args) -> tuple:
    idx, filepath, out_dir, max_side, quality = args
    dst = Path(out_dir) / f"{idx:06d}.jpg"
    try:
        with Image.open(filepath) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            im.thumbnail((max_side, max_side), Image.BILINEAR)
            im.save(dst, "JPEG", quality=quality)
        return idx, filepath, "ok"
    except Exception as e:  # corrupt / unreadable / truncated
        return idx, filepath, f"fail:{type(e).__name__}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="wh40k_pile")
    ap.add_argument("--out", default=str(Path.home() / "Downloads" / "wh40k_embed_bundle"))
    ap.add_argument("--max-side", type=int, default=384)
    ap.add_argument("--quality", type=int, default=88)
    ap.add_argument("--workers", type=int, default=max(2, (os.cpu_count() or 4) - 2))
    args = ap.parse_args()

    out_dir = Path(args.out)
    img_dir = out_dir / "images"
    img_dir.mkdir(parents=True, exist_ok=True)

    ds = fo.load_dataset(args.name)
    # stable order; index is the bundle key
    items = [(i, s.filepath) for i, s in enumerate(ds.iter_samples(progress=False))]
    print(f"preparing {len(items)} images -> {img_dir} (max_side={args.max_side})")

    jobs = [(i, fp, str(img_dir), args.max_side, args.quality) for i, fp in items]
    rows = []
    ok = fail = 0
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futures = [ex.submit(resize_one, j) for j in jobs]
        for n, fut in enumerate(as_completed(futures), 1):
            idx, fp, status = fut.result()
            rows.append((idx, fp, status))
            if status == "ok":
                ok += 1
            else:
                fail += 1
            if n % 5000 == 0:
                print(f"  {n}/{len(jobs)}  ok={ok} fail={fail}")

    rows.sort(key=lambda r: r[0])
    manifest = out_dir / "manifest.csv"
    with open(manifest, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["idx", "filepath", "status"])
        w.writerows(rows)

    print(f"\nresized ok={ok} fail={fail}; manifest -> {manifest}")

    tar_path = Path(str(out_dir) + ".tar")
    print(f"taring -> {tar_path}")
    with tarfile.open(tar_path, "w") as tar:
        tar.add(img_dir, arcname="images")
        tar.add(manifest, arcname="manifest.csv")
    size_gb = tar_path.stat().st_size / 1e9
    print(f"bundle ready: {tar_path} ({size_gb:.2f} GB)")
    print("Next: upload this tar to Colab/Drive and run scripts/curation/embed_colab.ipynb")


if __name__ == "__main__":
    main()
