#!/usr/bin/env python3
"""Symlink every CMON-scraped scene image into the annotator's
per-faction directory layout so the desktop annotator can browse them.

The annotator walks `backend/training_data/{faction}/{source}/*.{jpg,png,...}`
and treats each file as a row. CMON scrape output lives at
`scripts/cmon/images/{run}/{entry_id}/{view}.jpg` — a wholly different
shape. This script bridges the two with filesystem symlinks: no image is
copied, the annotator sees the CMON scenes under
`backend/training_data/{faction}/cmon/cmon_{entry_id}_{view_idx}.jpg`,
and the underlying JPEG is the canonical CMON file.

Faction bucketing: `photoanalyzer.label.weak.classify_title` infers a
best-guess faction from the entry's title. About 71% of CMON titles
match (tested on the 1075-entry corpus). Anything the classifier can't
place lands in `backend/training_data/_unknown/cmon/` so you can still
browse + annotate them; the annotator UI lets you re-classify per-bbox
regardless of which directory the image was discovered under.

Output is idempotent: re-running skips symlinks that already exist and
point at the correct target. `--force` re-creates every symlink.

Usage:
    fiftyone_env/bin/python3 scripts/seed_cmon_for_annotator.py --dry-run
    fiftyone_env/bin/python3 scripts/seed_cmon_for_annotator.py
    fiftyone_env/bin/python3 scripts/seed_cmon_for_annotator.py --force
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CMON_ROOT = REPO_ROOT / "scripts" / "cmon"
TRAINING_DATA = REPO_ROOT / "backend" / "training_data"

# Faction used for CMON scenes whose title the weak classifier can't bucket.
# Keeping them visible (vs dropping) lets the user annotate them regardless
# and assign factions via the per-bbox classLabel.
UNKNOWN_FACTION_DIR = "_unknown"

sys.path.insert(0, str(REPO_ROOT / "src"))
from photoanalyzer.label.weak import (  # noqa: E402
    classify_title, normalise_title,
)


def parse_args():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--dry-run", action="store_true",
                   help="Print what would be linked; don't touch the filesystem.")
    p.add_argument("--force", action="store_true",
                   help="Recreate every symlink, even ones already pointing at the right target.")
    return p.parse_args()


def load_manifests() -> list[tuple[Path, dict]]:
    """Return [(manifest_path, parsed_dict)] for every CMON entry."""
    out = []
    for mp in CMON_ROOT.glob("images/*/*/manifest.json"):
        try:
            d = json.loads(mp.read_text())
        except json.JSONDecodeError as e:
            print(f"  ✗ malformed manifest: {mp} — {e}")
            continue
        out.append((mp, d))
    return out


def infer_faction(manifest: dict) -> str:
    """Best-guess faction from the manifest's title. Returns the
    faction slug on match, empty string on no-match."""
    title = normalise_title(manifest.get("title") or manifest.get("tile_title") or "")
    if not title:
        return ""
    r = classify_title(title)
    return r.faction if r and r.faction else ""


def resolve_link_target(entry_dir: Path, local_rel: str) -> Path:
    """Absolute filesystem path to a manifest-declared CMON JPEG.
    `local_rel` is relative to the CMON root (e.g. `images/single/472941/00.jpg`)."""
    if os.path.isabs(local_rel):
        return Path(local_rel)
    return (CMON_ROOT / local_rel).resolve()


def main():
    args = parse_args()
    if not CMON_ROOT.exists():
        sys.exit(f"CMON root not found at {CMON_ROOT}")
    if not TRAINING_DATA.exists():
        sys.exit(f"backend/training_data not found at {TRAINING_DATA}")

    manifests = load_manifests()
    if not manifests:
        sys.exit(f"No CMON manifests found under {CMON_ROOT}/images/")

    stats: Counter = Counter()
    per_faction: Counter = Counter()

    for manifest_path, manifest in manifests:
        entry_id = manifest.get("id") or manifest_path.parent.name
        faction = infer_faction(manifest) or UNKNOWN_FACTION_DIR
        per_faction[faction] += 1

        local_paths = manifest.get("local_paths") or []
        if not local_paths:
            stats["no_local_paths"] += 1
            continue

        for view_idx, rel in enumerate(local_paths):
            target_abs = resolve_link_target(manifest_path.parent, rel)
            if not target_abs.exists():
                stats["missing_target"] += 1
                continue

            link_dir = TRAINING_DATA / faction / "cmon"
            link_name = f"cmon_{entry_id}_{view_idx:02d}{target_abs.suffix.lower()}"
            link_path = link_dir / link_name

            # Compute a relative symlink — easier to move the repo around.
            try:
                rel_target = os.path.relpath(target_abs, start=link_dir)
            except ValueError:
                rel_target = str(target_abs)

            # Idempotent: skip if already pointing at the right place.
            if link_path.is_symlink():
                try:
                    current = os.readlink(link_path)
                except OSError:
                    current = ""
                if current == rel_target and not args.force:
                    stats["unchanged"] += 1
                    continue
                if args.dry_run:
                    stats["would_replace"] += 1
                    continue
                link_path.unlink()
                stats["replaced"] += 1
            elif link_path.exists():
                # Something real (not a symlink) is sitting here. Leave it alone
                # — don't clobber the user's data.
                stats["conflict_real_file"] += 1
                continue
            else:
                if args.dry_run:
                    stats["would_create"] += 1
                    continue
                stats["created"] += 1

            link_dir.mkdir(parents=True, exist_ok=True)
            os.symlink(rel_target, link_path)

    print(f"Scanned {len(manifests)} CMON entries.")
    print(f"Per-faction bucket:")
    for f, n in sorted(per_faction.items(), key=lambda x: -x[1]):
        print(f"  {f:<30} {n}")
    print(f"\nSymlink stats:")
    for k, n in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"  {k:<30} {n}")
    if args.dry_run:
        print("\n--dry-run: no symlinks created.")


if __name__ == "__main__":
    main()
