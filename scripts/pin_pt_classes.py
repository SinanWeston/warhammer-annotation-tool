#!/usr/bin/env python3
"""Extract the class list baked into every YOLO `.pt` under `runs/` and write
a companion `<stem>.classes.txt` file next to each one.

The point: the deployed model's class indices are immutable once the model
was trained — they live in `model.names` on the .pt. But our export pipeline
(`scripts/export_yolo_dataset.py:72`) regenerates `data.yaml` classes from
`sorted(classes_set)` of the annotation corpus on every run. Add one new
faction and the indices shift alphabetically, the exported `data.yaml`
silently disagrees with the .pt, and inference maps predictions to the
wrong classes.

The companion `.classes.txt` is a **frozen ground-truth** that:
  - Checks into git (small plain text; see `.gitignore` exclusions).
  - `export_yolo_dataset.py` can diff against before overwriting `data.yaml`,
    failing loudly on any drift.
  - Serves as human-readable documentation of "what this model was
    trained against."

Usage:
    yolo_env/bin/python3 scripts/pin_pt_classes.py                 # pin every .pt
    yolo_env/bin/python3 scripts/pin_pt_classes.py --pt runs/foo.pt  # pin one
    yolo_env/bin/python3 scripts/pin_pt_classes.py --dry-run        # no writes

Idempotent — re-running produces no change unless a .pt was replaced.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = REPO_ROOT / "runs"


def extract_names(pt_path: Path) -> list[str]:
    """Load the .pt via Ultralytics and return `model.names` as a list
    indexed by class ID. YOLO stores names as {int: str}; we turn that
    into a list where `names[i]` is the class name at index i."""
    from ultralytics import YOLO
    m = YOLO(str(pt_path))
    raw = m.names
    # names is sometimes a dict {0: "x", 1: "y"} and sometimes a list.
    # Normalise to a dict first, then produce a positionally-ordered list.
    if isinstance(raw, dict):
        ids = sorted(int(k) for k in raw)
        if ids != list(range(len(ids))):
            raise RuntimeError(
                f"{pt_path.name}: .names indices are not contiguous 0..N-1: {ids[:10]}…"
            )
        return [str(raw[i]) for i in ids]
    if isinstance(raw, list):
        return [str(n) for n in raw]
    raise RuntimeError(f"{pt_path.name}: unexpected .names type {type(raw).__name__}")


def companion_path(pt_path: Path) -> Path:
    """<runs>/yolo11_colab_best.pt -> <runs>/yolo11_colab_best.classes.txt"""
    return pt_path.with_suffix(".classes.txt")


def write_atomic(path: Path, content: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content)
    tmp.replace(path)


def parse_args():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--pt", type=Path, action="append",
                   help="Only pin this .pt (can pass multiple). Default: every .pt under runs/.")
    p.add_argument("--dry-run", action="store_true",
                   help="Print what would be written; don't touch any files.")
    return p.parse_args()


def main():
    args = parse_args()
    if args.pt:
        pts = [p.resolve() for p in args.pt]
    else:
        if not RUNS_DIR.exists():
            sys.exit(f"runs/ directory not found at {RUNS_DIR}")
        pts = sorted(RUNS_DIR.glob("*.pt"))
    if not pts:
        sys.exit("No .pt files found to pin.")

    wrote = 0
    unchanged = 0
    failed = []

    for pt in pts:
        print(f"▶ {pt.relative_to(REPO_ROOT)}")
        try:
            names = extract_names(pt)
        except Exception as e:
            failed.append((pt, str(e)))
            print(f"    ✗ failed to load: {e}")
            continue

        content = "\n".join(names) + "\n"
        target = companion_path(pt)

        if target.exists() and target.read_text() == content:
            print(f"    ✓ unchanged ({len(names)} classes): {target.name}")
            unchanged += 1
            continue

        print(f"    → {target.name}  ({len(names)} classes)")
        print(f"      first 5: {names[:5]}")
        if args.dry_run:
            continue
        write_atomic(target, content)
        wrote += 1

    print()
    print(f"Summary: {wrote} written, {unchanged} unchanged, {len(failed)} failed")
    if failed:
        for pt, err in failed:
            print(f"  ✗ {pt.name}: {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
