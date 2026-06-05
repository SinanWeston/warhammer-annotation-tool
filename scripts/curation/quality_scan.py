"""Cheap CPU quality scan over the detection pool → junk-filter seed (Tier 1 prep).

Auto-labeling junk (blurry / tiny / banner-strip meme images) wastes the SAM 3
Colab run and noises the RF-DETR distillation. This computes cheap per-image
quality signals so the worst inputs can be tagged out before the auto-label pass:

  - blur_var : variance of the Laplacian (low = out of focus / motion blur)
  - min_side : shorter image dimension in px (low = thumbnail / unusable)
  - aspect   : long/short side ratio (high = banner / meme strip / collage)

Writes a resumable CSV (one row per image); a separate tagging step applies
thresholds so the cutoffs can be tuned from the score distribution without
re-reading 34k images. Semantic junk (terrain, memes) is better caught by the
existing `low_unique` tag + embeddings — combine both at tag time.

After scanning, apply tags from the CSV (tunable thresholds, no image re-read):

  lowq_blur  : blur_var < --blur   (default 60 ≈ p04 of the detection pool)
  lowq_tiny  : min_side < --minpx  (default 256)
  lowq_strip : aspect   > --aspect (default 2.8 — banners / collages / memes)
  lowq       : union of the above — the SAM 3 auto-label list should exclude it
               (along with the semantic `low_unique` tag).

Usage:
  fiftyone_env/bin/python scripts/curation/quality_scan.py            # scan → CSV
  fiftyone_env/bin/python scripts/curation/quality_scan.py --tag      # CSV → FiftyOne tags
"""
from __future__ import annotations

import argparse
import csv
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import cv2

OUT = Path(__file__).resolve().parents[2] / "data" / "quality_scan.csv"
FIELDS = ["filepath", "width", "height", "min_side", "aspect", "blur_var", "error"]


def score_one(fp: str) -> dict:
    try:
        img = cv2.imread(fp, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return {"filepath": fp, "error": "unreadable"}
        h, w = img.shape[:2]
        long_, short_ = max(h, w), max(1, min(h, w))
        # downscale large images before Laplacian — blur signal survives, ~10x faster
        if long_ > 1024:
            s = 1024 / long_
            img = cv2.resize(img, (max(1, int(w * s)), max(1, int(h * s))))
        blur = float(cv2.Laplacian(img, cv2.CV_64F).var())
        return {"filepath": fp, "width": w, "height": h, "min_side": short_,
                "aspect": round(long_ / short_, 3), "blur_var": round(blur, 2),
                "error": ""}
    except Exception as e:  # noqa: BLE001 - want every failure recorded, not fatal
        return {"filepath": fp, "error": str(e)[:120]}


def tag_from_csv(blur: float, minpx: int, aspect: float) -> None:
    """Read the scan CSV and apply lowq_* tags to FiftyOne (no image re-read)."""
    import fiftyone as fo

    ds = fo.load_dataset("wh40k_pile")
    flagged: dict[str, set[str]] = {}
    with OUT.open() as f:
        for r in csv.DictReader(f):
            if r["error"]:
                continue
            tags = set()
            if r["blur_var"] and float(r["blur_var"]) < blur:
                tags.add("lowq_blur")
            if r["min_side"] and int(r["min_side"]) < minpx:
                tags.add("lowq_tiny")
            if r["aspect"] and float(r["aspect"]) > aspect:
                tags.add("lowq_strip")
            if tags:
                flagged[r["filepath"]] = tags | {"lowq"}

    for t in ("lowq", "lowq_blur", "lowq_tiny", "lowq_strip"):
        ex = ds.match_tags(t)
        if ex.count():
            ex.untag_samples(t)            # idempotent re-tag

    n = 0
    for s in ds.select_by("filepath", list(flagged), ordered=False):
        s.tags = list(set(s.tags) | flagged[s.filepath])
        s.save()
        n += 1
    counts = {t: ds.match_tags(t).count()
              for t in ("lowq", "lowq_blur", "lowq_tiny", "lowq_strip")}
    print(f"tagged {n} images:  {counts}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", default="detection")
    ap.add_argument("--workers", type=int, default=max(2, (os.cpu_count() or 4) - 2))
    ap.add_argument("--tag", action="store_true", help="apply tags from the CSV")
    ap.add_argument("--blur", type=float, default=60.0)
    ap.add_argument("--minpx", type=int, default=256)
    ap.add_argument("--aspect", type=float, default=2.8)
    args = ap.parse_args()

    if args.tag:
        tag_from_csv(args.blur, args.minpx, args.aspect)
        return

    import fiftyone as fo
    from fiftyone import ViewField as F
    ds = fo.load_dataset("wh40k_pile")
    paths = ds.match(F("pool") == args.pool).values("filepath")
    print(f"{args.pool} pool: {len(paths)} images")

    done = set()
    if OUT.exists():
        with OUT.open() as f:
            done = {r["filepath"] for r in csv.DictReader(f)}
        print(f"resuming — {len(done)} already scored")
    todo = [p for p in paths if p not in done]
    print(f"scanning {len(todo)} with {args.workers} workers")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    new = not OUT.exists()
    with OUT.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        n = 0
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            for fut in as_completed(ex.submit(score_one, p) for p in todo):
                row = fut.result()
                w.writerow({k: row.get(k, "") for k in FIELDS})
                n += 1
                if n % 2000 == 0:
                    f.flush()
                    print(f"  {n}/{len(todo)}")
    print(f"done — wrote {OUT}")


if __name__ == "__main__":
    main()
