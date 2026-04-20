"""Build the Colab bundle — downscaled image mirror + annotations + phaseF scripts.

`backend/training_data/` is 16 GB at native resolution; Google Drive's free
tier is 15 GB, so we can't ship the originals. Grounding DINO internally
resizes to a short-edge of 800 and a long-edge cap of 1333, so a 1333-px
downscale is effectively **lossless for this task** while cutting the bundle
to ~3–5 GB.

Usage:
    yolo_env/bin/python scripts/phaseF/prepare_colab_bundle.py

Outputs:
    /tmp/photoanalyzer_f1_bundle.tar    (upload this to Google Drive)
"""
from __future__ import annotations

import os
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


def iter_image_targets(staging_root: Path) -> list[tuple[Path, Path]]:
    """Walk SRC_IMAGES and pair each input with its staged output path.
    Symlinks are resolved (CMON images live under scripts/cmon/images/
    via symlink) — we want the actual pixels in the bundle."""
    jobs: list[tuple[Path, Path]] = []
    for ext in IMG_EXTS:
        for p in SRC_IMAGES.rglob(f"*{ext}"):
            rel = p.relative_to(SRC_IMAGES)
            dst = staging_root / SRC_IMAGES / rel.with_suffix(".jpg")  # always JPEG out
            jobs.append((p.resolve(), dst))
    return jobs


def main() -> int:
    if not SRC_IMAGES.is_dir() or not SRC_ANNS.is_dir():
        print("Run me from the repo root.", file=sys.stderr)
        return 1
    for s in SCRIPTS:
        if not s.is_file():
            print(f"Missing expected script: {s}", file=sys.stderr)
            return 1

    # Staging area off the repo so we don't pollute backend/. /tmp is
    # typically plenty given the downscaled size (~3–5 GB).
    staging = Path(tempfile.mkdtemp(prefix="phaseF-bundle-", dir="/tmp"))
    print(f"Staging in {staging}")

    try:
        # 1. Images (resized where needed).
        jobs = iter_image_targets(staging)
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
    print()
    print("Next steps (your side):")
    print(f"  1. Drag {OUT_TAR} onto Google Drive (root of MyDrive).")
    print( "  2. Drag scripts/phaseF/autolabel_colab.ipynb onto Drive too.")
    print( "  3. Double-click the .ipynb in Drive → 'Open with Google Colab'.")
    print( "  4. Runtime → Change runtime type → T4 GPU.")
    print( "  5. Runtime → Run all. Walk away.")
    print( "  6. When done (~10h), download f1_outputs.tar from Drive to")
    print( "     <repo>/ and run: tar -xf f1_outputs.tar   (yields data/pseudo_labels/).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
