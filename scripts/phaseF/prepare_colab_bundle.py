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
OUT_TAR = Path("/tmp/photoanalyzer_f1_bundle.tar")
SRC_IMAGES = Path("backend/training_data")
SRC_ANNS = Path("backend/training_data_annotations")
SCRIPTS = [
    Path("scripts/phaseF/autolabel.py"),
    Path("scripts/phaseF/README.md"),
    Path("scripts/phaseF/setup.sh"),
]
IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def resize_one(src: Path, dst: Path) -> tuple[int, int, int]:
    """Return (src_bytes, dst_bytes, status) where status is:
    0 = resized, 1 = copied as-is (already small), 2 = error."""
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
                return src_bytes, dst.stat().st_size, 1
            # Downscale to LONG_EDGE_CAP keeping aspect ratio.
            scale = LONG_EDGE_CAP / long_edge
            new_size = (int(w * scale), int(h * scale))
            # Convert paletted/alpha → RGB so the JPEG save below doesn't
            # complain. PIL keeps it a no-op for already-RGB images.
            im2 = im.convert("RGB")
            im2 = im2.resize(new_size, Image.LANCZOS)
            im2.save(dst, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        return src_bytes, dst.stat().st_size, 0
    except Exception:
        # Leave the work coordinator to log; keep stdout clean.
        return 0, 0, 2


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


def iter_image_targets(
    staging_root: Path,
    sample: int | None,
    shuffle_seed: int,
) -> list[tuple[Path, Path]]:
    """Walk SRC_IMAGES and pair each input with its staged output path.
    Symlinks are resolved (CMON images live under scripts/cmon/images/
    via symlink) — we want the actual pixels in the bundle.

    When `sample` is set, replicate autolabel.py's shuffle (same seed)
    and take the first N *unlabelled* images so Colab processes
    exactly the bundled set.
    """
    all_paths: list[Path] = []
    for ext in IMG_EXTS:
        all_paths.extend(SRC_IMAGES.rglob(f"*{ext}"))

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
    if args.sample:
        print(f"Sampling {args.sample} images (shuffle seed {args.shuffle_seed})")

    try:
        # 1. Images (resized where needed).
        jobs = iter_image_targets(staging, args.sample, args.shuffle_seed)
        print(f"Resizing {len(jobs)} images to ≤{LONG_EDGE_CAP}px long edge …")
        n_resized = n_copied = n_err = 0
        total_in = total_out = 0
        start = time.monotonic()
        with ProcessPoolExecutor(max_workers=max(2, os.cpu_count() or 4)) as pool:
            futs = {pool.submit(resize_one, s, d): (s, d) for s, d in jobs}
            for fut in tqdm(as_completed(futs), total=len(futs), desc="resize"):
                src_bytes, dst_bytes, status = fut.result()
                total_in += src_bytes
                total_out += dst_bytes
                if status == 0:
                    n_resized += 1
                elif status == 1:
                    n_copied += 1
                else:
                    n_err += 1
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
