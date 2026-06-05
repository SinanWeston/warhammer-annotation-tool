"""F1 — Auto-label miniatures with SAM 3 (+ optional SAM 2 mask refinement).

Single-detector pipeline (the SAM 3 + Grounding DINO + OWLv2 ensemble was retired
2026-04-25 / 2026-06-05). Emits one JSON per image under
`data/pseudo_labels/boxes/<imageId>.json`:

    {
      "imageId": "...",
      "imagePath": "...",
      "width": <original>, "height": <original>,
      "detectors_used": ["sam3"],
      "mode": "sam3",
      "boxes": [
        {
          "xywh": [x, y, w, h],
          "score": 0.87,
          "supporters": ["sam3"],
          "refinement_iou": 0.91
        },
        ...
      ]
    }

Resumable: images whose output already exists are skipped. Honours the
`data/pseudo_labels/original_dims.json` coord-rescale manifest written by
`prepare_colab_bundle.py` (falls back gracefully when missing).

Usage:
    fiftyone_env/bin/python scripts/phaseF/autolabel_ensemble.py --limit 5
    fiftyone_env/bin/python scripts/phaseF/autolabel_ensemble.py                 # full run
    fiftyone_env/bin/python scripts/phaseF/autolabel_ensemble.py --with-sam2-refine
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from tqdm import tqdm


# --- Paths -------------------------------------------------------------

TRAINING_DATA = Path("backend/training_data")
ANN_DIR = Path("backend/training_data_annotations")
OUT_ROOT = Path("data/pseudo_labels")
BOX_DIR = OUT_ROOT / "boxes"
MANIFEST_PATH = OUT_ROOT / "manifest.json"
ERROR_LOG = OUT_ROOT / "errors.log"
ORIGINAL_DIMS_PATH = OUT_ROOT / "original_dims.json"

IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


# --- Helpers -----------------------------------------------------------


@dataclass
class ImageJob:
    image_id: str
    path: Path
    faction: str
    source: str


def image_id_from_path(path: Path) -> str:
    return f"{path.parts[-3]}_{path.parts[-2]}_{path.stem}"


def load_annotated_ids() -> set[str]:
    ids: set[str] = set()
    for p in ANN_DIR.glob("*.json"):
        if p.name.endswith(".skip.json"):
            continue
        try:
            d = json.loads(p.read_text())
        except Exception:
            continue
        img_id = d.get("imageId")
        # Exclude only gold / human-reviewed annotations. Pseudo-flagged
        # files are fair game to re-label — we're replacing them.
        if img_id and not d.get("pseudoLabelled"):
            ids.add(img_id)
    return ids


def iter_unlabelled(annotated: set[str]) -> list[ImageJob]:
    jobs: list[ImageJob] = []
    for ext in IMG_EXTS:
        for p in TRAINING_DATA.rglob(f"*{ext}"):
            if len(p.parts) < 3:
                continue
            img_id = image_id_from_path(p)
            if img_id in annotated:
                continue
            if (BOX_DIR / f"{img_id}.json").exists():
                continue
            jobs.append(ImageJob(
                image_id=img_id,
                path=p,
                faction=p.parts[-3],
                source=p.parts[-2],
            ))
    return jobs


# --- Main --------------------------------------------------------------


def build_ensemble(include_sam3: bool, include_sam2_refine: bool):
    """Lazy import so `--help` doesn't drag model deps in."""
    from photoanalyzer.detect.ensemble.voting import build_default_ensemble
    return build_default_ensemble(
        include_sam3=include_sam3,
        include_sam2_refine=include_sam2_refine,
    )


def rescale_if_downscaled(
    path: Path, original_dims: dict[str, list[int]] | None
) -> tuple[int, int, float, float]:
    """Return (orig_w, orig_h, sx, sy) — scale factors to convert
    coords from the on-disk image's resolution back to the original.
    Identity (1.0, 1.0) when no manifest entry or dims match."""
    with Image.open(path) as im:
        w, h = im.size
    if not original_dims:
        return w, h, 1.0, 1.0
    key = str(path)
    dims = original_dims.get(key)
    if not dims or len(dims) != 2:
        return w, h, 1.0, 1.0
    ow, oh = dims
    if (ow, oh) == (w, h):
        return w, h, 1.0, 1.0
    return int(ow), int(oh), float(ow) / w, float(oh) / h


def process_one(ensemble, job: ImageJob, original_dims: dict | None) -> dict:
    # Load ensemble-style detections.
    auto, review = ensemble.run(job.path)
    # Scale back to original resolution if the on-disk image was
    # downscaled for bundling (see prepare_colab_bundle.py).
    orig_w, orig_h, sx, sy = rescale_if_downscaled(job.path, original_dims)

    def _to_schema(ed, is_auto: bool) -> dict:
        x, y, w, h = ed.bbox
        return {
            "xywh": [round(x * sx, 2), round(y * sy, 2),
                     round(w * sx, 2), round(h * sy, 2)],
            "score": round(ed.confidence, 4),
            "supporters": list(ed.supporters),
            "refinement_iou": round(ed.refinement_iou, 4),
            "tier": "auto" if is_auto else "review",
        }

    boxes = [_to_schema(ed, True) for ed in auto] + [_to_schema(ed, False) for ed in review]
    return {
        "imageId": job.image_id,
        "imagePath": str(job.path),
        "faction": job.faction,
        "source": job.source,
        "width": orig_w,
        "height": orig_h,
        "detectors_used": [name for name, _ in ensemble.detectors],
        "mode": "sam3",
        "boxes": boxes,
    }


def write_manifest(n_done: int) -> None:
    # Minimal manifest — enough to see progress; deeper stats in F1.7 bench.
    manifest = {
        "version": 2,
        "mode": "sam3",
        "n_images_processed": n_done,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None,
                    help="Only process the first N unlabelled images (smoke test).")
    ap.add_argument("--shuffle", action="store_true",
                    help="Shuffle (seeded) so early progress spans sources.")
    ap.add_argument("--shuffle-seed", type=int, default=42)
    ap.add_argument("--no-sam3", action="store_true",
                    help="Skip SAM 3 (use when Meta gate is still pending).")
    # SAM 2 refinement is currently broken with transformers 5.0
    # (KeyError: 'reshaped_input_sizes' on the post-process call).
    # Default OFF until fixed; `--with-sam2-refine` opts in.
    ap.add_argument("--with-sam2-refine", action="store_true",
                    help="Enable SAM 2 mask refinement (currently broken on transformers 5.0).")
    ap.add_argument("--no-sam2-refine", action="store_true",
                    help="DEPRECATED — refinement is off by default now. Kept for back-compat.")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    BOX_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(ERROR_LOG),
        level=logging.WARNING,
        format="%(asctime)s %(message)s",
    )

    original_dims: dict[str, list[int]] | None = None
    if ORIGINAL_DIMS_PATH.exists():
        try:
            original_dims = json.loads(ORIGINAL_DIMS_PATH.read_text())
            print(f"  original_dims.json: {len(original_dims)} entries (will scale to originals)")
        except Exception as e:
            print(f"  original_dims.json unreadable ({e}); proceeding without rescale")

    print("Enumerating unlabelled images…")
    annotated = load_annotated_ids()
    print(f"  {len(annotated)} already-gold IDs (excluded)")
    jobs = iter_unlabelled(annotated)
    print(f"  {len(jobs)} unlabelled images to process")
    if args.shuffle:
        random.Random(args.shuffle_seed).shuffle(jobs)
    if args.limit:
        jobs = jobs[: args.limit]
        print(f"  --limit {args.limit} → processing {len(jobs)}")
    if not jobs:
        print("Nothing to do.")
        return 0

    print("Building ensemble…")
    ensemble = build_ensemble(
        include_sam3=not args.no_sam3,
        # SAM 2 refinement off by default; --with-sam2-refine opts in.
        # The legacy --no-sam2-refine flag is a no-op since the new
        # default is "off" — kept only so old commands don't error.
        include_sam2_refine=args.with_sam2_refine,
    )
    print(f"  detectors: {[name for name, _ in ensemble.detectors]}")
    print(f"  refiner: {'sam2' if ensemble.refiner is not None else 'off'}")

    t0 = time.monotonic()
    n_done = 0
    n_err = 0
    try:
        for job in tqdm(jobs, desc="ensemble"):
            out_path = BOX_DIR / f"{job.image_id}.json"
            if out_path.exists():
                continue
            try:
                result = process_one(ensemble, job, original_dims)
                out_path.write_text(json.dumps(result))
                n_done += 1
            except Exception as e:
                n_err += 1
                logging.warning(
                    "failed %s: %s\n%s",
                    job.image_id, e, traceback.format_exc(limit=3),
                )
            if n_done and n_done % 50 == 0:
                write_manifest(n_done)
    except KeyboardInterrupt:
        print("\nInterrupted; writing final manifest.")

    write_manifest(n_done)
    elapsed = time.monotonic() - t0
    print(f"\nDone in {elapsed:.1f}s  ({n_done} processed, {n_err} errors)")
    if n_err:
        print(f"See {ERROR_LOG} for error details.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
