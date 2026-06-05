#!/usr/bin/env python3
"""
Build the gw_shop folder-slug → canonical-unit-slug mapping.

The GW shop scrape uses prefixed/suffixed folder names like
`ael_shining_spear_feature` — the canonical taxonomy in
`scripts/data/units.json` calls it `shining_spears`. The walkthrough
annotator mode (Phase B) needs a fast lookup from one to the other so
images load with `unit_slug` pre-filled.

This script:
  1. Walks `scripts/warhammer_com/images/{faction}/{folder}/`.
  2. Tries to auto-map each folder to a canonical unit via prefix-strip
     + suffix-strip + slugify match against units.json.
  3. Writes `scripts/data/gw_slug_canonical_map.json` — a flat dict
     keyed `"{faction}/{folder_slug}"` → `"canonical_unit_slug"`.
     Unmatched folders get `""` (empty string) so the user can edit
     the file directly to fill them in.
  4. Prints a summary so the user knows how much manual work remains.

Run:
    fiftyone_env/bin/python3 scripts/build_gw_slug_map.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WARCOM_ROOT = REPO_ROOT / "scripts" / "warhammer_com" / "images"
UNITS_JSON = REPO_ROOT / "scripts" / "data" / "units.json"
OUT_PATH = REPO_ROOT / "scripts" / "data" / "gw_slug_canonical_map.json"

# Known gw_shop slug prefixes (sorted longest-first so longer patterns
# strip before their substrings — `ad_mech_` before `ad_`, `nur_mo_n_`
# before `nur_`).
PREFIXES = sorted([
    "ad_mech_", "ad_mec_", "c_tan_", "nur_mo_n_", "blood_angels_",
    "dark_angels_", "deathwatch_", "grey_knights_", "imperial_knights_",
    "primaris_", "ts_", "ael_", "csm_", "eldar_", "sm_", "bt_", "kt_",
    "tau_", "ork_", "orks_", "tyr_", "nec_", "as_", "am_", "ac_", "ba_",
    "s2_d_", "ks_", "sw_", "ig_", "ws_",
], key=len, reverse=True)

# Variant suffixes (also sorted longest-first).
SUFFIXES = sorted([
    "_lead_alt", "_feature_alt", "_repackage_stock", "_x_box",
    "_stock", "_feature", "_lead", "_scale", "_context", "_repackage",
    "_new", "_alt", "_update", "_detail", "_rp",
], key=len, reverse=True)


sys.path.insert(0, str(REPO_ROOT / "src"))
from photoanalyzer.taxonomy import slugify  # noqa: E402


# Chapter folders → which canonical faction owns them. gw_shop scraped
# space-marines chapters under their own folders; canonical taxonomy
# puts every chapter unit under `space_marines`.
CHAPTER_TO_FACTION = {
    "blood_angels": "space_marines",
    "dark_angels": "space_marines",
    "deathwatch": "space_marines",
    "grey_knights": "space_marines",
    "imperial_fists": "space_marines",
    "iron_hands": "space_marines",
    "raven_guard": "space_marines",
    "salamanders": "space_marines",
    "space_wolves": "space_marines",
    "ultramarines": "space_marines",
    "white_scars": "space_marines",
    "black_templars": "space_marines",
}

# Folders that aren't 40K miniatures — skip entirely.
SKIP_FACTIONS = {
    "_non_miniatures",
    "adeptus_titanicus",
    "titanicus_traitoris",
    "unknown",
}


def normalize_canonical(slug: str) -> str:
    """Apply the underscore/dash normalization the rest of the labelling
    pipeline uses. The canonical `slugify()` preserves dashes (e.g.
    `arco-flagellants`); labels.csv always writes underscores. Make both
    match by collapsing dashes to underscores here."""
    return slug.replace("-", "_")


def strip_decoration(slug: str) -> str:
    """Strip known prefix and known variant suffix(es) iteratively."""
    out = slug
    # Strip one prefix (only the longest matching one — sorted).
    for pre in PREFIXES:
        if out.startswith(pre):
            out = out[len(pre):]
            break
    # Strip suffix(es) iteratively (a folder can stack `_repackage_stock`).
    changed = True
    while changed:
        changed = False
        for suf in SUFFIXES:
            if out.endswith(suf) and len(out) > len(suf):
                out = out[:-len(suf)]
                changed = True
    return out


def singular_variants(slug: str) -> list[str]:
    """Generate plausible singular/plural variants. The gw_shop slug
    `ael_shining_spear` (singular) needs to match canonical
    `shining_spears` (plural). Conservative: try base, +s, -s."""
    out = {slug}
    if slug.endswith("s"):
        out.add(slug[:-1])
    else:
        out.add(slug + "s")
    # Plurals on the last word only.
    if "_" in slug:
        head, _, tail = slug.rpartition("_")
        if tail.endswith("s"):
            out.add(f"{head}_{tail[:-1]}")
        else:
            out.add(f"{head}_{tail}s")
    return list(out)


def main():
    if not UNITS_JSON.exists():
        sys.exit(f"units.json not found at {UNITS_JSON}")
    if not WARCOM_ROOT.exists():
        sys.exit(f"warhammer_com images dir not found at {WARCOM_ROOT}")

    units_data = json.loads(UNITS_JSON.read_text())
    factions_obj = units_data.get("factions", {})

    # Build (faction, canonical_slug) -> name for lookup.
    # ALSO build (faction, normalized_canonical) for dash-collapsed match.
    canonical_by_faction: dict[str, dict[str, str]] = defaultdict(dict)
    for fslug, body in factions_obj.items():
        for u in body.get("units") or []:
            name = u.get("name") or ""
            if not name:
                continue
            canon = slugify(name)
            canonical_by_faction[fslug][canon] = name
            # Also index the dash-collapsed variant for matching.
            dash_collapsed = normalize_canonical(canon)
            if dash_collapsed != canon:
                canonical_by_faction[fslug][dash_collapsed] = name

    mapping: dict[str, str] = {}
    matched_via: dict[str, int] = defaultdict(int)
    unmatched: list[str] = []

    skipped_faction_folders = 0
    for faction_dir in sorted(WARCOM_ROOT.iterdir()):
        if not faction_dir.is_dir():
            continue
        scrape_faction = faction_dir.name
        if scrape_faction in SKIP_FACTIONS:
            skipped_faction_folders += sum(1 for _ in faction_dir.iterdir())
            continue
        # Resolve chapter folders to the parent faction.
        canonical_faction = CHAPTER_TO_FACTION.get(scrape_faction, scrape_faction)
        canon_set = canonical_by_faction.get(canonical_faction, {})
        if not canon_set:
            print(f"⚠ No canonical units known for faction {scrape_faction!r}; "
                  f"skipping its {sum(1 for _ in faction_dir.iterdir())} folders.")
            continue
        for folder_dir in sorted(faction_dir.iterdir()):
            if not folder_dir.is_dir():
                continue
            folder_slug = folder_dir.name
            # Key uses the scrape-faction so the symlink filenames match
            # — the backend reads training_data/{scrape_faction}/gw_shop/.
            key = f"{scrape_faction}/{folder_slug}"

            # Try direct match.
            if folder_slug in canon_set:
                mapping[key] = folder_slug
                matched_via["direct"] += 1
                continue

            # Strip decoration.
            stripped = strip_decoration(folder_slug)
            if stripped in canon_set:
                mapping[key] = stripped
                matched_via["stripped"] += 1
                continue

            # Singular/plural variants.
            for variant in singular_variants(stripped):
                if variant in canon_set:
                    mapping[key] = variant
                    matched_via["stripped+plural"] += 1
                    break
            else:
                # Greedy backoff: drop trailing `_word` tokens one at a
                # time and see if a prefix matches a canonical slug.
                # Catches `arco_flagellants_damien` → `arco_flagellants`,
                # `daemonifuge_ephrael_stern_kyganil` → `daemonifuge`, etc.
                # Stops at the first match (most-specific available).
                tokens = stripped.split("_")
                matched_via_backoff = False
                for i in range(len(tokens) - 1, 0, -1):
                    candidate = "_".join(tokens[:i])
                    if candidate in canon_set:
                        mapping[key] = candidate
                        matched_via["greedy_backoff"] += 1
                        matched_via_backoff = True
                        break
                    for variant in singular_variants(candidate):
                        if variant in canon_set:
                            mapping[key] = variant
                            matched_via["greedy_backoff"] += 1
                            matched_via_backoff = True
                            break
                    if matched_via_backoff:
                        break
                if not matched_via_backoff:
                    mapping[key] = ""
                    unmatched.append(key)

    if skipped_faction_folders:
        print(f"Skipped {skipped_faction_folders} folders under non-40K-mini "
              f"factions ({sorted(SKIP_FACTIONS)})")

    # Sort the mapping for stable output.
    sorted_mapping = dict(sorted(mapping.items()))

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(sorted_mapping, indent=2) + "\n")

    total = len(mapping)
    matched = sum(matched_via.values())
    print(f"Wrote {OUT_PATH.relative_to(REPO_ROOT)}")
    print(f"  {total} folder(s) scanned")
    for how, n in matched_via.items():
        print(f"  matched via {how}: {n}")
    print(f"  unmatched (empty value, fill in manually): {len(unmatched)}")
    if unmatched[:8]:
        print("  examples of unmatched:")
        for k in unmatched[:8]:
            print(f"    {k}")
        if len(unmatched) > 8:
            print(f"    ... and {len(unmatched) - 8} more")


if __name__ == "__main__":
    main()
