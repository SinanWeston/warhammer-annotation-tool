"""Symlink GW shop scrape into backend/training_data/ as source=gw_shop.

Walks scripts/warhammer_com/images/<gw_faction>/<unit>/clean/*.{jpg,png,webp}
and creates symlinks at backend/training_data/<tgt_faction>/gw_shop/<unit>__<file>.

Deliberately skips:
  - sprues/     (unpainted plastic kit shots, not in the test distribution)
  - details/    (zoom-ins on parts — would teach the detector to fire on helmets)
  - _non_miniatures/, unknown/  (not paint-scheme target material)
  - adeptus_titanicus, titanicus_traitoris  (not in taxonomy)

Faction remapping (GW's naming → our canonical):
  - Space Marine chapters (white_scars, salamanders, raven_guard,
    imperial_fists, ultramarines, iron_hands, dark_angels, blood_angels,
    space_wolves, deathwatch, black_templars, grey_knights) → space_marines
  - Everything else kept as-is; astra_militarum, emperors_children, etc.
    all already match the canonical taxonomy from scripts/data/units.json.

Idempotent: re-running just skips links that already exist.
"""
from __future__ import annotations

import sys
from pathlib import Path

GW_ROOT = Path("scripts/warhammer_com/images")
OUT_ROOT = Path("backend/training_data")

SKIP_FACTIONS = {"_non_miniatures", "unknown", "adeptus_titanicus", "titanicus_traitoris"}
SKIP_SUBDIRS = {"sprues", "details"}
IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

# GW's faction dirs for Space Marine chapters → the canonical `space_marines`
# bucket, mirroring the existing FACTION_REMAP in annotationService.ts.
CHAPTER_REMAP = {
    "white_scars", "salamanders", "raven_guard", "imperial_fists",
    "ultramarines", "iron_hands", "dark_angels", "blood_angels",
    "space_wolves", "deathwatch", "black_templars", "grey_knights",
}


def target_faction(gw_faction: str) -> str | None:
    if gw_faction in SKIP_FACTIONS:
        return None
    if gw_faction in CHAPTER_REMAP:
        return "space_marines"
    return gw_faction


def main() -> int:
    if not GW_ROOT.is_dir():
        print(f"GW scrape not found at {GW_ROOT}", file=sys.stderr)
        return 1
    n_linked = 0
    n_skipped_dup = 0
    n_skipped_rule = 0
    per_tgt: dict[str, int] = {}

    for gw_faction_dir in sorted(GW_ROOT.iterdir()):
        if not gw_faction_dir.is_dir():
            continue
        tgt = target_faction(gw_faction_dir.name)
        if tgt is None:
            n_skipped_rule += sum(1 for _ in gw_faction_dir.rglob("*") if _.is_file())
            continue
        tgt_dir = OUT_ROOT / tgt / "gw_shop"
        tgt_dir.mkdir(parents=True, exist_ok=True)

        for unit_dir in sorted(gw_faction_dir.iterdir()):
            if not unit_dir.is_dir():
                continue
            unit = unit_dir.name
            # GW scraper stashes painted photos under clean/; scanner
            # distribution is painted models, not sprues/details.
            for sub in unit_dir.iterdir():
                if not sub.is_dir() or sub.name in SKIP_SUBDIRS:
                    continue
                # Only traverse `clean/` — other subdirs are shot types
                # we aren't training on (sprues, details, box_art, etc).
                if sub.name != "clean":
                    continue
                for img in sub.iterdir():
                    if img.suffix.lower() not in IMG_EXTS:
                        continue
                    # Flatten: <unit>__<originalname>.ext, so the
                    # annotator's {faction}_{source}_{stem} id scheme
                    # still gives a unique id per (unit, file) pair.
                    dst = tgt_dir / f"{unit}__{img.name}"
                    if dst.exists() or dst.is_symlink():
                        n_skipped_dup += 1
                        continue
                    dst.symlink_to(img.resolve())
                    n_linked += 1
                    per_tgt[tgt] = per_tgt.get(tgt, 0) + 1

    print(f"Linked: {n_linked}")
    print(f"Already-present (skipped): {n_skipped_dup}")
    print(f"Rule-skipped (non-miniatures / not-in-taxonomy): {n_skipped_rule}")
    print()
    print("Per target faction:")
    for f, c in sorted(per_tgt.items(), key=lambda x: -x[1]):
        print(f"  {f:<22} {c:>5}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
