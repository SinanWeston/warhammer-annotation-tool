#!/usr/bin/env python3
"""
Post-scrape image classifier — separates the scraped corpus into three buckets:

  clean      single-model painted shot → stays in images/{faction}/{unit}/
  sprue      bare plastic sprue frame  → moved to images/_sprues/{faction}/{unit}/
  composite  multi-panel detail shot   → moved to images/_details/{faction}/{unit}/

Nothing is deleted. Both quarantine folders sit alongside the faction folders,
remain manifest-tracked (scrape_log.csv filename + image_type updated), and
are available for later use (classifier training, data augmentation, audits).

Two heuristics:
  1. Sprue      — low "colourfulness" (Hasler-Suesstrunk) + low saturation.
                  Bare plastic is uniform gray; painted minis hit 20-60+.
  2. Composite  — detect internal dividing white lines: if ≥15% interior of the
                  image has a row (or column) that is ≥85% near-white (i.e. a
                  thin horizontal/vertical white strip splitting sub-panels),
                  flag as composite.

Usage:
    yolo_env/bin/python3 scripts/warhammer_com/classify_images.py            # dry-run
    yolo_env/bin/python3 scripts/warhammer_com/classify_images.py --apply    # move files
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

from gw_shop_constants import IMAGES_ROOT, STATE_DIR  # noqa: E402
from scraper_utils import BASE_DIR, SCRAPE_LOG  # noqa: E402


# ─── Quarantine folder layout ───────────────────────────────────────────────

SPRUE_DIR = IMAGES_ROOT / "_sprues"
DETAIL_DIR = IMAGES_ROOT / "_details"
AUDIT_CSV = STATE_DIR / "classification.csv"

# ─── Thresholds (conservative; err toward "clean" so we don't false-positive) ─

# Sprue: low colourfulness AND low saturation. Both must hold to be confident.
SPRUE_COLOURFULNESS_MAX = 15.0   # painted minis rarely fall below ~20
SPRUE_SAT_MEAN_MAX = 12.0        # 0-255 range

# Composite: white horizontal or vertical divider strip in the interior.
COMPOSITE_WHITE_THRESHOLD = 240  # pixel value ≥ this = "near white"
COMPOSITE_ROW_PCT = 0.85         # row must be ≥85% near-white to count as divider
COMPOSITE_MIN_STRIP_PX = 2       # divider must be ≥2 pixels thick (not speckle)
COMPOSITE_INTERIOR_PCT = 0.15    # only check rows in middle 70% (strip top/bottom 15%)


# ─── Per-image analysis ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class ImageStats:
    path: Path
    width: int
    height: int
    colourfulness: float
    sat_mean: float
    horiz_dividers: int
    vert_dividers: int
    verdict: str      # "clean" | "sprue" | "composite"


def _colourfulness_and_saturation(arr: np.ndarray) -> tuple[float, float]:
    """Hasler-Suesstrunk colourfulness + mean HSV-style saturation (0-255)."""
    r = arr[..., 0].astype(float)
    g = arr[..., 1].astype(float)
    b = arr[..., 2].astype(float)
    rg = r - g
    yb = 0.5 * (r + g) - b
    colourfulness = float(
        np.sqrt(rg.std() ** 2 + yb.std() ** 2)
        + 0.3 * np.sqrt(rg.mean() ** 2 + yb.mean() ** 2)
    )
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1), 0)
    return colourfulness, float(sat.mean() * 255)


FLANK_CHECK_PX = 15  # how far above/below a strip to look for content
FLANK_MAX_WHITE = 0.50  # flank region must be <50% near-white = "has content"


def _count_interior_dividers(gray: np.ndarray, axis: int) -> int:
    """
    Count internal near-white dividing strips along `axis` (0=horiz rows,
    1=vert cols). "Interior" excludes the outer 15% of each side.

    A strip only counts as a divider if it is FLANKED by content on BOTH
    sides: the N rows/cols immediately above and below the strip must have
    <50% near-white pixels. This prevents white-background margins around
    a single model from being mis-detected as panel dividers.
    """
    h, w = gray.shape
    if axis == 0:  # rows
        lo, hi = int(COMPOSITE_INTERIOR_PCT * h), int((1 - COMPOSITE_INTERIOR_PCT) * h)
        slab = gray[lo:hi, :]
    else:  # cols
        lo, hi = int(COMPOSITE_INTERIOR_PCT * w), int((1 - COMPOSITE_INTERIOR_PCT) * w)
        slab = gray[:, lo:hi]

    white_frac = (slab >= COMPOSITE_WHITE_THRESHOLD).mean(axis=1 if axis == 0 else 0)

    above_mask = white_frac >= COMPOSITE_ROW_PCT
    # Find strips (contiguous runs of mostly-white rows/cols)
    strips: list[tuple[int, int]] = []
    run_start = -1
    for i, v in enumerate(above_mask):
        if v and run_start < 0:
            run_start = i
        elif not v and run_start >= 0:
            if i - run_start >= COMPOSITE_MIN_STRIP_PX:
                strips.append((run_start, i))
            run_start = -1
    if run_start >= 0 and len(above_mask) - run_start >= COMPOSITE_MIN_STRIP_PX:
        strips.append((run_start, len(above_mask)))

    # Filter: each strip must be flanked by content (non-white) on both sides.
    n = 0
    for s_start, s_end in strips:
        before_lo = max(0, s_start - FLANK_CHECK_PX)
        after_hi = min(len(white_frac), s_end + FLANK_CHECK_PX)
        has_content_before = white_frac[before_lo:s_start].mean() < FLANK_MAX_WHITE if s_start > before_lo else False
        has_content_after = white_frac[s_end:after_hi].mean() < FLANK_MAX_WHITE if after_hi > s_end else False
        if has_content_before and has_content_after:
            n += 1
    return n


def _classify_array(arr: np.ndarray) -> tuple[str, float, float, int, int]:
    """Return (verdict, colourfulness, sat_mean, horiz, vert)."""
    colourfulness, sat_mean = _colourfulness_and_saturation(arr)

    is_sprue = (
        colourfulness < SPRUE_COLOURFULNESS_MAX
        and sat_mean < SPRUE_SAT_MEAN_MAX
    )
    if is_sprue:
        return "sprue", colourfulness, sat_mean, 0, 0

    gray = arr.mean(axis=-1) if arr.ndim == 3 else arr
    h_div = _count_interior_dividers(gray, axis=0)
    v_div = _count_interior_dividers(gray, axis=1)
    if h_div >= 1 or v_div >= 1:
        return "composite", colourfulness, sat_mean, h_div, v_div
    return "clean", colourfulness, sat_mean, h_div, v_div


def analyse_image(path: Path) -> ImageStats | None:
    try:
        img = Image.open(path).convert("RGB")
        arr = np.asarray(img)
    except Exception as e:
        print(f"  ✖ decode failed: {path.name}: {e}", flush=True)
        return None
    verdict, cf, sm, h, v = _classify_array(arr)
    return ImageStats(
        path=path, width=arr.shape[1], height=arr.shape[0],
        colourfulness=cf, sat_mean=sm, horiz_dividers=h, vert_dividers=v,
        verdict=verdict,
    )


# ─── Filesystem + manifest ──────────────────────────────────────────────────

def _iter_scrape_images() -> list[Path]:
    """All .jpgs under images/{faction}/{unit}/, excluding quarantine dirs."""
    out: list[Path] = []
    for faction_dir in IMAGES_ROOT.iterdir():
        if not faction_dir.is_dir():
            continue
        if faction_dir.name.startswith("_"):  # skip existing _sprues / _details
            continue
        for unit_dir in faction_dir.iterdir():
            if not unit_dir.is_dir():
                continue
            out.extend(unit_dir.glob("*.jpg"))
    return sorted(out)


def _quarantine_target(src: Path, bucket: Path) -> Path:
    """Map images/{faction}/{unit}/{file} → bucket/{faction}/{unit}/{file}."""
    rel = src.relative_to(IMAGES_ROOT)
    return bucket / rel


def _patch_manifest_for_moves(moves: list[tuple[Path, Path, str]]) -> int:
    """
    For every moved image, rewrite its scrape_log.csv row: update `filename`
    to the new path (repo-root-relative) and set `image_type` to 'sprue' or
    'studio_detail'.
    """
    if not SCRAPE_LOG.exists():
        return 0
    rows = list(csv.DictReader(SCRAPE_LOG.open()))
    if not rows:
        return 0
    fieldnames = list(rows[0].keys())

    # Key lookup: basename → (new rel_path, new image_type)
    # (Basenames are unique within the warhammer_shop corpus.)
    lookup: dict[str, tuple[str, str]] = {}
    for src, dst, verdict in moves:
        try:
            new_rel = str(dst.relative_to(BASE_DIR))
        except ValueError:
            new_rel = str(dst)
        new_type = "sprue" if verdict == "sprue" else "studio_detail"
        lookup[src.name] = (new_rel, new_type)

    patched = 0
    for r in rows:
        if r.get("source_platform") != "warhammer_shop":
            continue
        bn = Path(r["filename"]).name
        if bn in lookup:
            new_rel, new_type = lookup[bn]
            r["filename"] = new_rel
            r["image_type"] = new_type
            patched += 1

    with SCRAPE_LOG.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    return patched


def _write_audit(stats: list[ImageStats]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with AUDIT_CSV.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "verdict", "faction", "unit_slug", "basename",
            "colourfulness", "sat_mean", "horiz_dividers", "vert_dividers",
            "width", "height", "path",
        ])
        for s in sorted(stats, key=lambda x: (x.verdict, x.path.as_posix())):
            rel = s.path.relative_to(IMAGES_ROOT)
            parts = rel.parts  # (faction, unit_slug, basename)
            faction = parts[0] if len(parts) >= 1 else ""
            unit = parts[1] if len(parts) >= 2 else ""
            w.writerow([
                s.verdict, faction, unit, s.path.name,
                f"{s.colourfulness:.2f}", f"{s.sat_mean:.2f}",
                s.horiz_dividers, s.vert_dividers,
                s.width, s.height, str(s.path),
            ])


# ─── Main ───────────────────────────────────────────────────────────────────

def run(apply_changes: bool, workers: int = 8) -> int:
    images = _iter_scrape_images()
    print(f"Scanning {len(images)} images under {IMAGES_ROOT} …")

    stats: list[ImageStats] = []
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(analyse_image, p): p for p in images}
        for fut in as_completed(futures):
            s = fut.result()
            done += 1
            if s is not None:
                stats.append(s)
            if done % 500 == 0:
                print(f"  {done}/{len(images)} analysed", flush=True)

    from collections import Counter
    verdicts = Counter(s.verdict for s in stats)
    print()
    print("=== classification summary ===")
    for v in ("clean", "sprue", "composite"):
        print(f"  {v:10s}  {verdicts.get(v, 0):5d}")
    print(f"  total     {len(stats):5d}")

    # Show the most-confident examples of each flagged category (lowest colourfulness
    # for sprues, highest divider count for composites).
    print()
    print("=== sample sprues (lowest colourfulness) ===")
    sprues = sorted([s for s in stats if s.verdict == "sprue"], key=lambda x: x.colourfulness)
    for s in sprues[:10]:
        print(f"  cf={s.colourfulness:5.1f}  sat={s.sat_mean:5.1f}  "
              f"{s.path.relative_to(IMAGES_ROOT)}")
    print()
    print("=== sample composites (most divider lines) ===")
    composites = sorted(
        [s for s in stats if s.verdict == "composite"],
        key=lambda x: -(x.horiz_dividers + x.vert_dividers),
    )
    for s in composites[:10]:
        print(f"  h={s.horiz_dividers}  v={s.vert_dividers}  "
              f"cf={s.colourfulness:5.1f}  {s.path.relative_to(IMAGES_ROOT)}")

    _write_audit(stats)
    print(f"\nAudit written to {AUDIT_CSV}")

    if not apply_changes:
        print("\n(dry-run — no files moved. Re-run with --apply to move.)")
        return len(stats)

    # ─── Apply: move files to quarantine, patch manifest ───────────────────
    moves: list[tuple[Path, Path, str]] = []
    for s in stats:
        if s.verdict == "clean":
            continue
        bucket = SPRUE_DIR if s.verdict == "sprue" else DETAIL_DIR
        dst = _quarantine_target(s.path, bucket)
        moves.append((s.path, dst, s.verdict))

    print(f"\n=== moving {len(moves)} files ===")
    for src, dst, _v in moves:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))

    n_patched = _patch_manifest_for_moves(moves)
    print(f"  moved {len(moves)} files")
    print(f"  patched {n_patched} manifest rows")

    # Clean up empty unit/faction dirs left behind by the moves
    empties_removed = 0
    for d in sorted(IMAGES_ROOT.rglob("*"), reverse=True):
        if d.is_dir() and not d.name.startswith("_") and d != IMAGES_ROOT:
            try:
                d.rmdir()
                empties_removed += 1
            except OSError:
                pass
    if empties_removed:
        print(f"  removed {empties_removed} empty folder(s)")

    return len(stats)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Classify scraped images: clean / sprue / composite")
    ap.add_argument("--apply", action="store_true",
                    help="Move flagged files to _sprues/ and _details/ (default: dry-run)")
    ap.add_argument("--workers", type=int, default=8,
                    help="Parallel workers for image analysis")
    args = ap.parse_args(argv)
    run(apply_changes=args.apply, workers=args.workers)
    return 0


if __name__ == "__main__":
    sys.exit(main())
