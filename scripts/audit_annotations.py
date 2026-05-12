#!/usr/bin/env python3
"""Audit and (optionally) normalise the annotation corpus.

Scope: `backend/training_data_annotations/*.json` — the scene-level
human-labelled annotations that feed YOLO training. The four fixes this
script performs, each gated behind its own `--fix-*` flag:

  - `--fix-casing`     Lowercase every `annotatedBy` field. Collapses
                       "Sinan" (27 files) into "sinan" (274 files) so
                       per-annotator analytics treat them as one person.
  - `--fix-duplicates` Remove `modelBbox` entries within a single
                       annotation whose IoU ≥ 0.95 (likely double-clicks
                       or Ctrl-C/V accidents). Keeps the earliest one.
  - `--backup`         Before any `--fix-*`, copy every JSON into
                       `backend/training_data_annotations.bak-<timestamp>/`.
                       Strongly recommended.

Report-only mode (default) prints counts and flagged files but touches
nothing. Use it first, read the diff, then decide on `--fix-*` + `--backup`.

Files flagged but NOT auto-fixed:
  - Zero-bbox files (no skip marker) — ambiguous. Either mark with a
    `.skip.` filename, or annotate at least one box. The script prints
    the paths so you can decide.
  - Tiny-bbox files (< 40 px on either side) — likely misclicks, flagged
    for manual review.

Usage:
    yolo_env/bin/python3 scripts/audit_annotations.py                    # report
    yolo_env/bin/python3 scripts/audit_annotations.py --fix-casing --backup
    yolo_env/bin/python3 scripts/audit_annotations.py --fix-duplicates --backup
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ANNOTATIONS_DIR = REPO_ROOT / "backend" / "training_data_annotations"

# Minimum bbox side (pixels) below which we flag the box as a likely misclick.
MIN_BOX_SIDE = 40
# IoU threshold for deduping identical boxes within one annotation.
DUPE_IOU = 0.95


def iou(a: dict, b: dict) -> float:
    """IoU for two `modelBbox` dicts ({x, y, width, height} in pixel coords)."""
    ax1, ay1 = a["x"], a["y"]
    ax2, ay2 = a["x"] + a["width"], a["y"] + a["height"]
    bx1, by1 = b["x"], b["y"]
    bx2, by2 = b["x"] + b["width"], b["y"] + b["height"]
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    union = a["width"] * a["height"] + b["width"] * b["height"] - inter
    return inter / union if union > 0 else 0.0


def atomic_write(path: Path, content: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content)
    tmp.replace(path)


def parse_args():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--fix-casing", action="store_true",
                   help="Lowercase every annotatedBy field.")
    p.add_argument("--fix-duplicates", action="store_true",
                   help="Remove near-duplicate bboxes (IoU ≥ 0.95) per annotation.")
    p.add_argument("--backup", action="store_true",
                   help="Snapshot the whole annotations dir before writing any fix.")
    return p.parse_args()


def main():
    args = parse_args()
    if not ANNOTATIONS_DIR.exists():
        sys.exit(f"Annotations directory not found at {ANNOTATIONS_DIR}")

    files = sorted(ANNOTATIONS_DIR.glob("*.json"))
    if not files:
        sys.exit("No annotation JSON files found.")

    # ── Pass 1: observe ──
    annotator_counts: Counter = Counter()
    zero_bbox_files: list[Path] = []
    tiny_boxes: list[tuple[Path, int, dict]] = []  # (path, ann_idx, box)
    duplicates: list[tuple[Path, int, int, float]] = []  # (path, i, j, iou)
    for p in files:
        try:
            data = json.loads(p.read_text())
        except json.JSONDecodeError as e:
            print(f"  ✗ {p.name}: JSON decode error — {e}")
            continue
        ab = data.get("annotatedBy")
        if ab is not None:
            annotator_counts[ab] += 1

        anns = data.get("annotations") or []
        if not anns and ".skip." not in p.name and "flaggedAt" not in data:
            zero_bbox_files.append(p)

        # Tiny bboxes
        for i, ann in enumerate(anns):
            bbox = ann.get("modelBbox")
            if not bbox:
                continue
            w, h = bbox.get("width", 0), bbox.get("height", 0)
            if w < MIN_BOX_SIDE or h < MIN_BOX_SIDE:
                tiny_boxes.append((p, i, bbox))

        # Duplicate bboxes within the same annotation
        for i in range(len(anns)):
            for j in range(i + 1, len(anns)):
                a_b = anns[i].get("modelBbox")
                b_b = anns[j].get("modelBbox")
                if not a_b or not b_b:
                    continue
                v = iou(a_b, b_b)
                if v >= DUPE_IOU:
                    duplicates.append((p, i, j, v))

    # ── Report ──
    print(f"Scanned {len(files)} annotation files.\n")

    print("annotatedBy distribution:")
    for k, n in annotator_counts.most_common():
        mark = ""
        if isinstance(k, str) and k != k.lower() and k.lower() in annotator_counts:
            mark = f"  (← merges with '{k.lower()}' under --fix-casing)"
        print(f"  {str(k)!r:<30}  {n}{mark}")

    casing_targets = [
        k for k in annotator_counts
        if isinstance(k, str) and k != k.lower() and k.lower() in annotator_counts
    ]
    if casing_targets:
        affected = sum(annotator_counts[k] for k in casing_targets)
        print(f"\n{affected} file(s) across {len(casing_targets)} casing variant(s) "
              f"will be normalised by --fix-casing.")

    print()
    print(f"Non-skip annotation files with zero bboxes: {len(zero_bbox_files)}")
    for p in zero_bbox_files[:10]:
        print(f"  {p.relative_to(REPO_ROOT)}")
    if len(zero_bbox_files) > 10:
        print(f"  ... and {len(zero_bbox_files) - 10} more")
    print("  (flagged only — decide manually whether to rename .skip. or annotate)")

    print()
    print(f"Tiny bboxes (< {MIN_BOX_SIDE}px on either side): {len(tiny_boxes)}")
    for p, i, b in tiny_boxes[:10]:
        print(f"  {p.name}  #{i}  {int(b['width'])}×{int(b['height'])} @ ({int(b['x'])},{int(b['y'])})")
    if len(tiny_boxes) > 10:
        print(f"  ... and {len(tiny_boxes) - 10} more")
    print("  (flagged only — manual review recommended)")

    print()
    print(f"Near-duplicate bboxes within a single annotation (IoU ≥ {DUPE_IOU}): {len(duplicates)}")
    for p, i, j, v in duplicates[:10]:
        print(f"  {p.name}  #{i} ↔ #{j}  IoU={v:.3f}")
    if len(duplicates) > 10:
        print(f"  ... and {len(duplicates) - 10} more")

    # ── Optional fixes ──
    need_fix = args.fix_casing or args.fix_duplicates
    if not need_fix:
        print("\nNo --fix-* flag passed; nothing written.")
        return

    if args.backup:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        bak = ANNOTATIONS_DIR.parent / f"{ANNOTATIONS_DIR.name}.bak-{ts}"
        print(f"\nBackup → {bak}")
        shutil.copytree(ANNOTATIONS_DIR, bak)
    else:
        print("\n⚠ --backup not set. Proceeding without a snapshot. "
              "Consider Ctrl-C'ing now if you want one.")

    wrote = 0
    for p in files:
        try:
            data = json.loads(p.read_text())
        except json.JSONDecodeError:
            continue

        changed = False
        if args.fix_casing and isinstance(data.get("annotatedBy"), str):
            new = data["annotatedBy"].lower()
            if new != data["annotatedBy"]:
                data["annotatedBy"] = new
                changed = True

        if args.fix_duplicates:
            anns = data.get("annotations") or []
            to_drop = set()
            for i in range(len(anns)):
                if i in to_drop:
                    continue
                for j in range(i + 1, len(anns)):
                    if j in to_drop:
                        continue
                    a_b = anns[i].get("modelBbox")
                    b_b = anns[j].get("modelBbox")
                    if not a_b or not b_b:
                        continue
                    if iou(a_b, b_b) >= DUPE_IOU:
                        to_drop.add(j)
            if to_drop:
                data["annotations"] = [a for k, a in enumerate(anns) if k not in to_drop]
                changed = True

        if changed:
            atomic_write(p, json.dumps(data, indent=2, ensure_ascii=False))
            wrote += 1

    print(f"\n✅ Wrote {wrote} file(s).")


if __name__ == "__main__":
    main()
