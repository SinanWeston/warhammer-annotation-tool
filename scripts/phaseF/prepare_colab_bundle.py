"""Build the Colab bundle — downscaled image mirror + annotations + phaseF scripts.

`backend/training_data/` is 16 GB at native resolution; Google Drive's free
tier is 15 GB, so we can't ship the originals. Grounding DINO internally
resizes to a short-edge of 800 and a long-edge cap of 1333, so a 1333-px
downscale is effectively **lossless for this task** while cutting the bundle
to ~3–5 GB.

Usage:
    yolo_env/bin/python scripts/phaseF/prepare_colab_bundle.py
    yolo_env/bin/python scripts/phaseF/prepare_colab_bundle.py --sample 500

--sample N keeps the bundle under ~150 MB (for hotspot uploads) by
packing only the first N images in the same shuffled order autolabel.py
processes. Annotations + scripts are still bundled in full.

Outputs:
    /tmp/photoanalyzer_f1_bundle.tar    (upload this to Google Drive)
"""
from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from PIL import Image
from tqdm import tqdm

LONG_EDGE_CAP = 1333       # matches Grounding DINO's internal resize target
JPEG_QUALITY = 92          # keep a margin above the dataset's ~85–90 floor
# ~/Downloads so file managers can actually find it — /tmp is hidden
# by most GUIs.
OUT_TAR = Path.home() / "Downloads" / "photoanalyzer_f1_bundle.tar"
SRC_IMAGES = Path("backend/training_data")
SRC_ANNS = Path("backend/training_data_annotations")
SRC_SCENE_BENCHMARK = Path("data/scene_benchmark")
# All phaseF scripts that the Colab notebook imports from. The SAM 3 pipeline
# needs the `src/photoanalyzer/` library too (shipped separately below).
SCRIPTS = [
    Path("scripts/phaseF/autolabel_ensemble.py"),  # SAM 3 autolabel driver
    Path("scripts/phaseF/bench_ensemble.py"),      # frozen-eval scorer
    Path("scripts/phaseF/README.md"),
    Path("scripts/phaseF/setup.sh"),
]
LIBRARY_ROOT = Path("src/photoanalyzer")
IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def resize_one(src: Path, dst: Path) -> tuple[int, int, int, int, int]:
    """Return (src_bytes, dst_bytes, status, orig_w, orig_h) where status is:
    0 = resized, 1 = copied as-is (already small), 2 = error.
    orig_w / orig_h are the original image's dimensions — the caller
    uses them to build `original_dims.json` so the Colab autolabeler
    can emit coords in the original coordinate system."""
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        src_bytes = src.stat().st_size
        # Quick-path: if already small, copy bytes verbatim (preserves the
        # original encoding and avoids a recompress pass).
        with Image.open(src) as im:
            w, h = im.size
            long_edge = max(w, h)
            if long_edge <= LONG_EDGE_CAP:
                shutil.copyfile(src, dst)
                return src_bytes, dst.stat().st_size, 1, w, h
            # Downscale to LONG_EDGE_CAP keeping aspect ratio.
            scale = LONG_EDGE_CAP / long_edge
            new_size = (int(w * scale), int(h * scale))
            # Convert paletted/alpha → RGB so the JPEG save below doesn't
            # complain. PIL keeps it a no-op for already-RGB images.
            im2 = im.convert("RGB")
            im2 = im2.resize(new_size, Image.LANCZOS)
            im2.save(dst, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        return src_bytes, dst.stat().st_size, 0, w, h
    except Exception:
        # Leave the work coordinator to log; keep stdout clean.
        return 0, 0, 2, 0, 0


def _image_id_from_path(p: Path) -> str:
    """Must match autolabel.py's scheme so exclusion agrees across
    sides — `{faction}_{source}_{stem}`."""
    return f"{p.parts[-3]}_{p.parts[-2]}_{p.stem}"


def _load_annotated_ids() -> set[str]:
    ids: set[str] = set()
    for p in SRC_ANNS.glob("*.json"):
        try:
            d = json.loads(p.read_text())
        except Exception:
            continue
        img_id = d.get("imageId")
        if img_id:
            ids.add(img_id)
    return ids


def _load_phase_c_paths(limit: int | None = None) -> list[Path]:
    """Paths for the Phase C frozen-eval images, returned as paths
    relative to the repo root (matching SRC_IMAGES' convention) so the
    rest of the bundler can stage them the same way it stages rglob
    results. `eval_200.json` records absolute paths — convert them.

    When `limit` is set, sample a stratified subset that preserves the
    single/sparse/medium/crowded bucket ratios. Smoke-test mode for
    dialling the pipeline before a full 200-image run.
    """
    manifest = Path("data/scene_benchmark/eval_200.json")
    if not manifest.is_file():
        print(f"WARN: {manifest} not found — phase-c mode unavailable.")
        return []
    data = json.loads(manifest.read_text())
    src_abs = SRC_IMAGES.resolve()

    records = data.get("images", [])
    if limit is not None and limit < len(records):
        # Stratify proportionally by bucket so each density regime is
        # represented in the smoke test.
        from collections import defaultdict
        by_bucket: dict[str, list[dict]] = defaultdict(list)
        for rec in records:
            by_bucket[rec.get("bucket", "?")].append(rec)
        # Allocate slots proportional to each bucket's share of the 200.
        total = sum(len(v) for v in by_bucket.values())
        picked: list[dict] = []
        for bucket, recs in sorted(by_bucket.items()):
            n_for_bucket = max(1, round(limit * len(recs) / total))
            picked.extend(recs[:n_for_bucket])
        # Trim/pad to exactly `limit`.
        if len(picked) > limit:
            picked = picked[:limit]
        elif len(picked) < limit:
            picked.extend(records[len(picked):limit])
        records = picked
        from collections import Counter
        print(f"  phase-c limit={limit}: stratified bucket mix = "
              f"{dict(Counter(r['bucket'] for r in records))}")

    out: list[Path] = []
    for rec in records:
        # Use .absolute() (doesn't follow symlinks) so CMON-symlinked
        # imagePaths under backend/training_data/_unknown/cmon/ stay
        # rooted in SRC_IMAGES instead of resolving out to scripts/cmon/.
        p = Path(rec["imagePath"]).absolute()
        if not p.exists():
            print(f"  phase-c: missing {rec['imageId']} at {p}")
            continue
        try:
            rel = p.relative_to(src_abs)
        except ValueError:
            print(f"  phase-c: {p} is outside {src_abs} — skipping")
            continue
        # Re-assemble as path relative to CWD so downstream relative_to
        # against `Path('backend/training_data')` works.
        out.append(SRC_IMAGES / rel)
    return out


def iter_image_targets(
    staging_root: Path,
    sample: int | None,
    shuffle_seed: int,
    source: str | None,
    phase_c: bool = False,
    phase_c_limit: int | None = None,
) -> list[tuple[Path, Path]]:
    """Walk SRC_IMAGES and pair each input with its staged output path.
    Symlinks are resolved (CMON images live under scripts/cmon/images/
    via symlink) — we want the actual pixels in the bundle.

    When `phase_c` is set, use exactly the 200 images from
    `data/scene_benchmark/eval_200.json` (benchmark mode — we have
    ground-truth bboxes for these, so Colab output can be scored).
    `phase_c` overrides `source` and `sample`.

    When `source` is set (and phase_c isn't), only images whose
    parent-dir name equals it are included.

    When `sample` is set (and phase_c isn't), replicate autolabel.py's
    shuffle (same seed) and take the first N *unlabelled* images.
    """
    if phase_c:
        all_paths = _load_phase_c_paths(limit=phase_c_limit)
    else:
        all_paths: list[Path] = []
        for ext in IMG_EXTS:
            all_paths.extend(SRC_IMAGES.rglob(f"*{ext}"))

        if source is not None:
            # Layout is backend/training_data/<faction>/<source>/<file>, so
            # parts[-2] is the source directory name. Filtering there skips
            # the rglob descent into sibling sources.
            all_paths = [p for p in all_paths if p.parts[-2] == source]

        if sample is not None:
            annotated = _load_annotated_ids()
            # Sort for deterministic enumeration before shuffle (rglob order
            # is fs-dependent).
            unlabelled = sorted(
                (p for p in all_paths if _image_id_from_path(p) not in annotated),
                key=lambda p: str(p),
            )
            random.Random(shuffle_seed).shuffle(unlabelled)
            all_paths = unlabelled[:sample]

    jobs: list[tuple[Path, Path]] = []
    for p in all_paths:
        rel = p.relative_to(SRC_IMAGES)
        dst = staging_root / SRC_IMAGES / rel.with_suffix(".jpg")  # always JPEG out
        jobs.append((p.resolve(), dst))
    return jobs


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--sample", type=int, default=None,
        help="Bundle only N images (first N in autolabel.py's shuffle order). "
             "Matches autolabel.py's default seed, so the bundle and Colab runner "
             "agree on which images exist. Use for hotspot-friendly small bundles.",
    )
    ap.add_argument(
        "--shuffle-seed", type=int, default=42,
        help="Shuffle seed, must match autolabel.py's --shuffle-seed (default 42).",
    )
    ap.add_argument(
        "--source", default=None,
        help="Bundle only images whose source directory matches (e.g. 'gw_shop'). "
             "Use when you want to auto-label one source at a time. Combines with "
             "--sample if you also want to cap the count.",
    )
    ap.add_argument(
        "--phase-c", action="store_true",
        help="Bundle the 200 Phase C frozen-eval images (overrides --sample "
             "and --source). Use this for bench validation: we have gold "
             "bboxes for these, so Colab output can be scored locally.",
    )
    ap.add_argument(
        "--phase-c-limit", type=int, default=None,
        help="With --phase-c, sample a stratified subset of N Phase C images "
             "(proportional across single/sparse/medium/crowded buckets). "
             "Smoke-test mode before committing to a full 200-image run.",
    )
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    if not SRC_IMAGES.is_dir() or not SRC_ANNS.is_dir():
        print("Run me from the repo root.", file=sys.stderr)
        return 1
    for s in SCRIPTS:
        if not s.is_file():
            print(f"Missing expected script: {s}", file=sys.stderr)
            return 1

    # Staging area off the repo so we don't pollute backend/. /tmp is
    # typically plenty given the downscaled size (~3–5 GB, or <200 MB
    # with --sample).
    staging = Path(tempfile.mkdtemp(prefix="phaseF-bundle-", dir="/tmp"))
    print(f"Staging in {staging}")
    if args.phase_c:
        print("Phase C bench mode — bundling the 200 frozen-eval images.")
    if args.source:
        print(f"Source filter: {args.source}")
    if args.sample:
        print(f"Sampling {args.sample} images (shuffle seed {args.shuffle_seed})")

    try:
        # 1. Images (resized where needed).
        jobs = iter_image_targets(
            staging, args.sample, args.shuffle_seed, args.source,
            args.phase_c, args.phase_c_limit,
        )
        print(f"Resizing {len(jobs)} images to ≤{LONG_EDGE_CAP}px long edge …")
        n_resized = n_copied = n_err = 0
        total_in = total_out = 0
        # Map of bundle-relative-path → [orig_w, orig_h]. Shipped into the
        # tarball so the Colab autolabeler can scale its outputs back up to
        # the original image's coordinate system before writing the pseudo
        # label JSONs. Without this, coords are in 1333-space but the
        # annotator draws them against 2560+ originals, and all boxes
        # squash into the top-left corner (Phase F1 bug, 2026-04-24).
        original_dims: dict[str, list[int]] = {}
        start = time.monotonic()
        with ProcessPoolExecutor(max_workers=max(2, os.cpu_count() or 4)) as pool:
            futs = {pool.submit(resize_one, s, d): (s, d) for s, d in jobs}
            for fut in tqdm(as_completed(futs), total=len(futs), desc="resize"):
                src_bytes, dst_bytes, status, ow, oh = fut.result()
                total_in += src_bytes
                total_out += dst_bytes
                if status == 0:
                    n_resized += 1
                elif status == 1:
                    n_copied += 1
                else:
                    n_err += 1
                if status in (0, 1) and ow and oh:
                    _src, _dst = futs[fut]
                    rel = str(_dst.relative_to(staging))
                    original_dims[rel] = [ow, oh]
        elapsed = time.monotonic() - start
        print(
            f"  resized {n_resized}, copied-as-is {n_copied}, failed {n_err} "
            f"({elapsed:.1f}s, {total_in/1e9:.2f} GB → {total_out/1e9:.2f} GB)"
        )

        # 2. Annotations (verbatim).
        print("Copying annotations …")
        ann_dst = staging / SRC_ANNS
        ann_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(SRC_ANNS, ann_dst, dirs_exist_ok=True)

        # 3. Scripts (verbatim).
        for s in SCRIPTS:
            d = staging / s
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(s, d)

        # 3.2 photoanalyzer library — ensemble driver imports it.
        if LIBRARY_ROOT.is_dir():
            lib_dst = staging / LIBRARY_ROOT
            shutil.copytree(LIBRARY_ROOT, lib_dst, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            print(f"  shipped photoanalyzer library ({LIBRARY_ROOT})")

        # 3.45 Scene benchmark manifest — tiny JSON but lets bench_ensemble.py
        # run on Colab against the same frozen eval set as local.
        if SRC_SCENE_BENCHMARK.is_dir():
            sb_dst = staging / SRC_SCENE_BENCHMARK
            shutil.copytree(SRC_SCENE_BENCHMARK, sb_dst, dirs_exist_ok=True)
            print(f"  shipped scene benchmark ({SRC_SCENE_BENCHMARK})")

        # 3.47 Mode marker — lets the Colab notebook pick bench vs autolabel
        # without needing a separate flag from the user.
        if args.phase_c:
            marker = staging / "PHASE_C_BENCH_MODE"
            marker.write_text("phase_c\n")
            print("  mode marker: PHASE_C_BENCH_MODE")

        # 3.5 Original-dims manifest — autolabel reads this and scales
        # detections back to the original image's coordinate system, so
        # pseudo-label JSONs always carry full-resolution coords.
        dims_path = staging / "data" / "pseudo_labels" / "original_dims.json"
        dims_path.parent.mkdir(parents=True, exist_ok=True)
        dims_path.write_text(json.dumps(original_dims, indent=2))
        print(f"  original_dims.json: {len(original_dims)} entries")

        # 4. Tar the staging dir (no compression; JPEGs don't shrink further).
        print(f"Tarballing → {OUT_TAR} …")
        OUT_TAR.unlink(missing_ok=True)
        subprocess.run(
            ["tar", "-cf", str(OUT_TAR), "-C", str(staging), "."],
            check=True,
        )
        size = OUT_TAR.stat().st_size
        print(f"  bundle: {size/1e9:.2f} GB")

    finally:
        # Staging dir is large — always clean up.
        shutil.rmtree(staging, ignore_errors=True)

    print()
    print(f"Done. {OUT_TAR} is {size/1e9:.2f} GB.")
    fits_drive = size < 14_500_000_000  # leave margin under the 15 GB free cap
    if not fits_drive:
        print("⚠  Bundle exceeds 14.5 GB — won't fit Drive free tier cleanly.")
        print("   Drop LONG_EDGE_CAP to 1024 and re-run, or upgrade Drive.")

    # Rough Colab T4 runtime: ~1 s/image with SAHI disabled-or-small,
    # ~1.5–3 s/image with SAHI on crowded scenes.
    n = len(jobs)
    if n <= 1000:
        eta = f"~{max(5, n // 100):d}–{max(10, n // 50):d} min on T4"
    elif n <= 10_000:
        eta = f"~{n // 600}–{n // 300} min on T4"
    else:
        eta = f"~{n // 3600:d}–{n // 1800:d} h on T4"

    print()
    print("Next steps (your side):")
    print(f"  1. Drag {OUT_TAR} onto Google Drive (root of MyDrive).")
    print( "  2. Drag scripts/phaseF/autolabel_colab.ipynb onto Drive too.")
    print( "  3. Double-click the .ipynb in Drive → 'Open with Google Colab'.")
    print( "  4. Runtime → Change runtime type → T4 GPU.")
    print(f"  5. Runtime → Run all. Walk away ({eta} for {n} images).")
    print( "  6. When done, download f1_outputs.tar from Drive to <repo>/")
    print( "     and run: tar -xf f1_outputs.tar   (yields data/pseudo_labels/).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
