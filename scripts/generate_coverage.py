#!/usr/bin/env python3
"""
Generate coverage report for clean unit reference images.

Parses the UNIT_DATABASE from consumer/src/data/units.ts,
scans backend/training_data/{faction}/clean/ for accepted images and
backend/training_data_candidates/{faction}/{unit}/ for unreviewed candidates.

Outputs:
  - backend/training_data_candidates/coverage.json  (gap report)
  - backend/training_data_candidates/units.json     (all units with slugs)

Usage:
    python scripts/generate_coverage.py
    python scripts/generate_coverage.py --target 15
"""

import json
import os
import re
import sys
from datetime import datetime, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNITS_TS = os.path.join(REPO_ROOT, "consumer", "src", "data", "units.ts")

# Accepted clean images — separate from the noisy main training_data
# Structure: clean_references/{faction}/clean/{unit_slug}_{idx}.jpg
CLEAN_REFS_DIR = os.path.join(REPO_ROOT, "backend", "clean_references")
# Unreviewed scraped candidates (held here until review)
CANDIDATES_DIR = os.path.join(REPO_ROOT, "backend", "training_data_candidates")
# Output files
COVERAGE_JSON = os.path.join(CANDIDATES_DIR, "coverage.json")
UNITS_JSON = os.path.join(CANDIDATES_DIR, "units.json")

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

# Faction display names for search queries
FACTION_DISPLAY = {
    "space_marines": "Space Marines",
    "necrons": "Necrons",
    "chaos_space_marines": "Chaos Space Marines",
    "orks": "Orks",
    "tau_empire": "T'au Empire",
    "tyranids": "Tyranids",
    "astra_militarum": "Astra Militarum",
    "adeptus_custodes": "Adeptus Custodes",
    "adeptus_mechanicus": "Adeptus Mechanicus",
    "adepta_sororitas": "Adepta Sororitas",
    "craftworld_aeldari": "Craftworld Aeldari",
    "chaos_daemons": "Chaos Daemons",
    "drukhari": "Drukhari",
    "genestealer_cults": "Genestealer Cults",
    "leagues_of_votann": "Leagues of Votann",
    "imperial_knights": "Imperial Knights",
    "chaos_knights": "Chaos Knights",
}

# Mapping from UNIT_DATABASE faction keys to training_data/ directory names
# (where they differ)
FACTION_DIR_MAP = {
    "astra_militarum": "imperial_guard",
    "craftworld_aeldari": "eldar",
    "adeptus_custodes": "custodes",
}

# Alternative names used in image search
FACTION_ALIASES = {
    "astra_militarum": ["Imperial Guard"],
    "adepta_sororitas": ["Sisters of Battle"],
    "craftworld_aeldari": ["Eldar", "Aeldari"],
    "drukhari": ["Dark Eldar"],
    "adeptus_custodes": ["Custodes"],
    "adeptus_mechanicus": ["Ad Mech", "Admech"],
    "tau_empire": ["Tau"],
}


def slugify(name: str) -> str:
    """Convert unit name to directory-safe slug."""
    slug = name.lower()
    slug = re.sub(r"[''`]", "", slug)
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    return slug.strip("_")


def faction_dir(faction_key: str) -> str:
    """Get the training_data directory name for a faction key."""
    return FACTION_DIR_MAP.get(faction_key, faction_key)


def parse_units() -> list[dict]:
    """Extract units from the TypeScript UNIT_DATABASE."""
    with open(UNITS_TS) as f:
        content = f.read()

    pattern = r"\{\s*name:\s*'([^']+)',\s*faction:\s*'([^']+)',\s*role:\s*'([^']+)'"
    matches = re.findall(pattern, content)

    units = []
    for name, faction, role in matches:
        units.append(
            {
                "name": name,
                "slug": slugify(name),
                "faction": faction,
                "factionDir": faction_dir(faction),
                "factionDisplay": FACTION_DISPLAY.get(faction, faction),
                "factionAliases": FACTION_ALIASES.get(faction, []),
                "role": role,
            }
        )
    return units


def count_images(directory: str) -> int:
    """Count image files in a directory."""
    if not os.path.isdir(directory):
        return 0
    return sum(
        1 for f in os.listdir(directory) if os.path.splitext(f)[1].lower() in IMAGE_EXTS
    )


def count_images_with_prefix(directory: str, prefix: str) -> int:
    """Count image files in a directory whose names start with a given prefix."""
    if not os.path.isdir(directory):
        return 0
    return sum(
        1 for f in os.listdir(directory)
        if f.startswith(prefix + "_") and os.path.splitext(f)[1].lower() in IMAGE_EXTS
    )


def generate(target: int = 12):
    units = parse_units()
    if not units:
        print("ERROR: Could not parse any units from", UNITS_TS)
        sys.exit(1)

    coverage = []
    factions: dict[str, dict] = {}

    for unit in units:
        # Accepted images: backend/clean_references/{factionDir}/clean/ (flat, prefixed by unit slug)
        # Count images whose filename starts with the unit slug
        clean_dir = os.path.join(CLEAN_REFS_DIR, unit["factionDir"], "clean")
        # Candidates: backend/training_data_candidates/{faction}/{unit_slug}/
        candidates_dir = os.path.join(
            CANDIDATES_DIR, unit["faction"], unit["slug"]
        )

        accepted = count_images_with_prefix(clean_dir, unit["slug"])
        candidates = count_images(candidates_dir)
        gap = max(0, target - accepted)

        entry = {
            **unit,
            "accepted": accepted,
            "candidates": candidates,
            "target": target,
            "gap": gap,
            "complete": accepted >= target,
        }
        coverage.append(entry)

        fkey = unit["faction"]
        if fkey not in factions:
            factions[fkey] = {
                "displayName": unit["factionDisplay"],
                "totalUnits": 0,
                "completeUnits": 0,
                "totalAccepted": 0,
                "totalCandidates": 0,
                "totalGap": 0,
            }
        factions[fkey]["totalUnits"] += 1
        if entry["complete"]:
            factions[fkey]["completeUnits"] += 1
        factions[fkey]["totalAccepted"] += accepted
        factions[fkey]["totalCandidates"] += candidates
        factions[fkey]["totalGap"] += gap

    total_units = len(units)
    complete_units = sum(1 for c in coverage if c["complete"])
    total_accepted = sum(c["accepted"] for c in coverage)
    total_gap = sum(c["gap"] for c in coverage)

    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "targetPerUnit": target,
        "totalUnits": total_units,
        "completeUnits": complete_units,
        "totalAccepted": total_accepted,
        "totalGap": total_gap,
        "factions": factions,
        "units": coverage,
    }

    # Ensure candidates dir exists
    os.makedirs(CANDIDATES_DIR, exist_ok=True)

    with open(COVERAGE_JSON, "w") as f:
        json.dump(report, f, indent=2)

    with open(UNITS_JSON, "w") as f:
        json.dump(units, f, indent=2)

    # Print summary
    print(f"\n{'='*60}")
    print(f"  CLEAN UNIT IMAGE COVERAGE REPORT")
    print(f"{'='*60}")
    print(f"  Target per unit: {target}")
    print(f"  Total units:     {total_units}")
    print(f"  Complete:        {complete_units}/{total_units} ({100*complete_units/total_units:.1f}%)")
    print(f"  Total accepted:  {total_accepted}")
    print(f"  Total gap:       {total_gap} images needed")
    print(f"{'='*60}")
    print(f"  Accepted dir:   backend/clean_references/{{faction}}/clean/{{unit_slug}}_*.jpg")
    print(f"  Candidates dir: backend/training_data_candidates/{{faction}}/{{unit}}/")
    print(f"{'='*60}\n")

    # Per-faction summary
    print(f"  {'Faction':<25} {'Units':>6} {'Done':>6} {'Accepted':>9} {'Gap':>6}")
    print(f"  {'-'*25} {'-'*6} {'-'*6} {'-'*9} {'-'*6}")
    for fkey, fdata in sorted(factions.items()):
        print(
            f"  {fdata['displayName']:<25} {fdata['totalUnits']:>6} "
            f"{fdata['completeUnits']:>6} {fdata['totalAccepted']:>9} {fdata['totalGap']:>6}"
        )

    # Show units needing most work (top 10 gaps)
    incomplete = sorted(
        [c for c in coverage if c["gap"] > 0], key=lambda x: -x["gap"]
    )
    if incomplete:
        print(f"\n  Top gaps (need most images):")
        for u in incomplete[:10]:
            print(
                f"    {u['factionDisplay']} / {u['name']}: "
                f"{u['accepted']}/{target} accepted, {u['candidates']} candidates"
            )

    print(f"\n  Wrote: {COVERAGE_JSON}")
    print(f"  Wrote: {UNITS_JSON}")
    print()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate clean unit image coverage report")
    parser.add_argument(
        "--target", type=int, default=12, help="Target images per unit (default: 12)"
    )
    args = parser.parse_args()
    generate(args.target)
