#!/usr/bin/env python3
"""One-shot migration: split death_guard / thousand_sons / world_eaters
/ emperors_children out of chaos_space_marines in scripts/data/units.json
and make them top-level factions on par with the others.

Rationale: these four have their own codexes in 10th-edition 40K and,
importantly, the deployed YOLO model (runs/yolo11x_run2_best.classes.txt)
already treats them as distinct classes. Merging them into
chaos_space_marines was a coarse-classifier shortcut that this project
doesn't need any more.

Preserves everything else in units.json unchanged. Backs up the file
to units.json.backup-<UTC-timestamp> before writing.

Usage:
    yolo_env/bin/python3 scripts/split_chaos_subfactions.py --dry-run
    yolo_env/bin/python3 scripts/split_chaos_subfactions.py
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
UNITS_JSON = REPO_ROOT / "scripts" / "data" / "units.json"

# Chapter-tag → new faction-slug for the chaos split. Each entry takes
# every unit under chaos_space_marines whose `chapter` field matches the
# key and promotes it to a new top-level faction keyed by the value.
CHAPTER_TO_FACTION = {
    "death_guard": "death_guard",
    "thousand_sons": "thousand_sons",
    "world_eaters": "world_eaters",
    "emperors_children": "emperors_children",
}


def parse_args():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


def main():
    args = parse_args()
    if not UNITS_JSON.exists():
        sys.exit(f"units.json not found at {UNITS_JSON}")
    data = json.loads(UNITS_JSON.read_text())
    factions = data.setdefault("factions", {})

    csm = factions.get("chaos_space_marines")
    if not csm:
        sys.exit("chaos_space_marines faction missing — nothing to split.")

    csm_units = csm.get("units") or []
    # Partition by chapter tag.
    kept_csm: list[dict] = []
    new_factions: dict[str, list[dict]] = {v: [] for v in CHAPTER_TO_FACTION.values()}

    for u in csm_units:
        chap = (u.get("chapter") or "").strip()
        if chap in CHAPTER_TO_FACTION:
            # Drop the chapter tag — unit now lives under its own faction.
            u2 = dict(u)
            u2.pop("chapter", None)
            new_factions[CHAPTER_TO_FACTION[chap]].append(u2)
        else:
            kept_csm.append(u)

    print(f"Starting chaos_space_marines units: {len(csm_units)}")
    print(f"  → kept in chaos_space_marines: {len(kept_csm)}")
    for slug, units in new_factions.items():
        print(f"  → moved to {slug}: {len(units)}")

    # Collisions — if the target faction already exists we'd need to
    # merge; flag loudly so the user can decide rather than silently
    # overwriting.
    collisions = [s for s in new_factions if s in factions]
    if collisions:
        sys.exit(f"Faction(s) already exist in units.json: {collisions}. "
                 f"Cannot safely auto-split — hand-resolve then re-run.")

    # Build the new faction objects. Preserve the parent codex's category
    # metadata loosely: units.json currently stores a faction-level
    # object with at minimum a `units` list. Some factions carry extra
    # keys (e.g. `combat_patrol`); we don't inherit those here.
    for slug, units in new_factions.items():
        factions[slug] = {"units": sorted(units, key=lambda x: x.get("name") or "")}

    factions["chaos_space_marines"] = {
        **csm,
        "units": sorted(kept_csm, key=lambda x: x.get("name") or ""),
    }

    if args.dry_run:
        print("\n--dry-run: not writing units.json.")
        return

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = UNITS_JSON.with_suffix(UNITS_JSON.suffix + f".backup-{ts}")
    shutil.copy2(UNITS_JSON, backup)
    print(f"\nBackup: {backup.name}")

    tmp = UNITS_JSON.with_suffix(UNITS_JSON.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    tmp.replace(UNITS_JSON)
    print(f"Wrote {UNITS_JSON.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
