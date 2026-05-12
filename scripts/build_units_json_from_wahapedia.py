#!/usr/bin/env python3
"""Rebuild scripts/data/units.json from the Wahapedia CSV exports.

Wahapedia (https://wahapedia.ru) is the most complete current-edition index
of Warhammer 40,000 datasheets. They publish pipe-delimited CSV exports at
https://wahapedia.ru/wh40k10ed/<Filename>.csv. This script reads those,
maps their 27-faction taxonomy onto our canonical 20 factions, and writes
a v2 units.json that preserves the existing file's shape so
photoanalyzer.taxonomy keeps working unchanged.

Mapping decisions:
- Chaos sub-factions (DG, TS, WE, EC) are merged into chaos_space_marines
  with a `chapter` tag on each unit. They're collected as separate factions
  by Wahapedia but our 20-faction classifier treats them as one.
- Grey Knights (GK) → space_marines with chapter=grey_knights.
- Harlequins and Ynnari units are folded into Aeldari by Wahapedia; we
  route them back out using Datasheets_keywords.csv where they carry a
  HARLEQUINS or YNNARI faction keyword.
- Skipped Wahapedia factions: Adeptus Titanicus (TL — Legions Imperialis,
  not 40K proper), Unaligned Forces (UN), Unbound Adversaries (UA).

Output preserves any `combat_patrol` entries already present in the old
units.json — those were hand-curated and Wahapedia doesn't carry that shape.

Re-run the migration any time by re-downloading the CSVs and running this
script; the old units.json becomes a `.backup.N.json` sibling.

Usage:
    yolo_env/bin/python3 scripts/build_units_json_from_wahapedia.py
    yolo_env/bin/python3 scripts/build_units_json_from_wahapedia.py --dry-run
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

WAHAPEDIA_DIR = REPO / "scripts" / "data" / "wahapedia_raw"
UNITS_JSON = REPO / "scripts" / "data" / "units.json"


# Wahapedia faction_id → (canonical_faction_slug, chapter_tag)
# chapter is '' when the Wahapedia faction *is* one of our canonical ones;
# non-empty when we're flattening a sub-faction into a canonical parent.
FACTION_MAP: dict[str, tuple[str, str]] = {
    "AM": ("astra_militarum",   ""),
    "AoI": ("imperial_agents",  ""),
    "GC": ("genestealer_cults", ""),
    "NEC": ("necrons",          ""),
    "AE": ("aeldari",           ""),   # Harlequin/Ynnari keyword re-routes below
    "ORK": ("orks",             ""),
    "GK": ("space_marines",     "grey_knights"),
    "TAU": ("tau_empire",       ""),
    "LoV": ("leagues_of_votann",""),
    "AdM": ("adeptus_mechanicus",""),
    "TS": ("chaos_space_marines", "thousand_sons"),
    "DG": ("chaos_space_marines", "death_guard"),
    "EC": ("chaos_space_marines", "emperors_children"),
    "WE": ("chaos_space_marines", "world_eaters"),
    "QT": ("chaos_knights",     ""),
    "CD": ("chaos_daemons",     ""),
    "QI": ("imperial_knights",  ""),
    "SM": ("space_marines",     ""),
    "TYR": ("tyranids",         ""),
    "AC": ("adeptus_custodes",  ""),
    "AS": ("adepta_sororitas",  ""),
    "CSM": ("chaos_space_marines", ""),
    "DRU": ("drukhari",         ""),
    # Skipped: TL (Adeptus Titanicus), UN (Unaligned), UA (Unbound Adversaries)
}

# Display names for the canonical 20 (preserved from old units.json).
FACTION_DISPLAY: dict[str, str] = {
    "space_marines":      "Space Marines",
    "necrons":            "Necrons",
    "orks":               "Orks",
    "tyranids":           "Tyranids",
    "tau_empire":         "T'au Empire",
    "aeldari":            "Aeldari",
    "astra_militarum":    "Astra Militarum",
    "adepta_sororitas":   "Adepta Sororitas",
    "adeptus_mechanicus": "Adeptus Mechanicus",
    "adeptus_custodes":   "Adeptus Custodes",
    "genestealer_cults":  "Genestealer Cults",
    "leagues_of_votann":  "Leagues of Votann",
    "imperial_knights":   "Imperial Knights",
    "chaos_knights":      "Chaos Knights",
    "chaos_space_marines": "Chaos Space Marines",
    "chaos_daemons":      "Chaos Daemons",
    "drukhari":           "Drukhari",
    "harlequins":         "Harlequins",
    "ynnari":             "Ynnari",
    "imperial_agents":    "Imperial Agents",
}


def _read_pipe_csv(path: Path) -> tuple[list[str], list[dict]]:
    """Return (headers, rows) for a Wahapedia pipe-delimited CSV. Strips the
    UTF-8 BOM that Wahapedia leaves on the first header cell."""
    with path.open("r", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="|")
        headers = next(reader)
        if headers and headers[0].startswith("\ufeff"):
            headers[0] = headers[0].lstrip("\ufeff")
        headers = [h.strip() for h in headers if h.strip()]
        rows: list[dict] = []
        for raw in reader:
            if not raw or not any(c.strip() for c in raw):
                continue
            rec = {}
            for i, h in enumerate(headers):
                rec[h] = raw[i].strip() if i < len(raw) else ""
            rows.append(rec)
        return headers, rows


def _load_harlequin_ynnari_ids() -> tuple[set[str], set[str]]:
    """Return (harlequin_ids, ynnari_ids) — datasheet IDs carrying those
    faction keywords. Used to reroute Aeldari entries to our harlequins/
    ynnari canonical factions."""
    _, kws = _read_pipe_csv(WAHAPEDIA_DIR / "Datasheets_keywords.csv")
    hq: set[str] = set()
    yn: set[str] = set()
    for row in kws:
        kw = (row.get("keyword") or "").strip()
        if not kw:
            continue
        ds_id = row.get("datasheet_id", "").strip()
        kw_low = kw.lower()
        if "harlequin" in kw_low:
            hq.add(ds_id)
        if "ynnari" in kw_low:
            yn.add(ds_id)
    return hq, yn


def _role_to_category(role: str) -> str:
    r = (role or "").strip().lower()
    if r in ("characters", "epic hero"):
        return "character"
    if r == "battleline":
        return "battleline"
    if r in ("transport", "dedicated transport"):
        return "transport"
    if r:
        return r
    return "other"


def migrate() -> tuple[dict, dict]:
    """Return (new_units_json, stats)."""
    stats: dict[str, int] = defaultdict(int)

    _, datasheets = _read_pipe_csv(WAHAPEDIA_DIR / "Datasheets.csv")
    stats["datasheets_total"] = len(datasheets)

    hq_ids, yn_ids = _load_harlequin_ynnari_ids()
    stats["harlequin_keyword_ids"] = len(hq_ids)
    stats["ynnari_keyword_ids"] = len(yn_ids)

    # Preserve anything worth keeping from the existing file
    existing: dict = {}
    if UNITS_JSON.exists():
        try:
            existing = json.loads(UNITS_JSON.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"⚠ couldn't parse existing {UNITS_JSON}: {e}", file=sys.stderr)

    existing_factions = existing.get("factions") or {}

    # Gather units per canonical faction
    units_by_faction: dict[str, list[dict]] = defaultdict(list)
    for rec in datasheets:
        fid = rec.get("faction_id", "").strip()
        if fid not in FACTION_MAP:
            stats["skipped_wahapedia_faction_" + (fid or "empty")] += 1
            continue
        canonical, chapter = FACTION_MAP[fid]

        # Reroute Aeldari → harlequins / ynnari by keyword
        ds_id = rec.get("id", "").strip()
        if canonical == "aeldari":
            if ds_id in yn_ids:
                canonical, chapter = "ynnari", ""
            elif ds_id in hq_ids:
                canonical, chapter = "harlequins", ""

        name = rec.get("name", "").strip()
        if not name:
            continue

        unit: dict = {
            "name": name,
            "category": _role_to_category(rec.get("role", "")),
        }
        if chapter:
            unit["chapter"] = chapter
        # Keep a stable xref for future re-imports + anyone wanting to deep-link
        if ds_id:
            unit["wahapedia_id"] = ds_id
        role = (rec.get("role", "") or "").strip()
        if role:
            unit["role"] = role
        link = (rec.get("link", "") or "").strip()
        if link:
            unit["wahapedia_link"] = link

        units_by_faction[canonical].append(unit)
        stats[f"faction.{canonical}"] += 1

    # Build the output, preserving the existing top-level shape
    out_factions: dict[str, dict] = {}
    for canonical in FACTION_DISPLAY:
        old = existing_factions.get(canonical) or {}
        block: dict = {
            "name": FACTION_DISPLAY[canonical],
        }
        if "combat_patrol" in old:
            block["combat_patrol"] = old["combat_patrol"]
        # Sort units by name for deterministic diffs
        block["units"] = sorted(
            units_by_faction.get(canonical, []),
            key=lambda u: u["name"].lower(),
        )
        out_factions[canonical] = block

    out: dict = {}
    # Preserve search_templates block if present
    if "search_templates" in existing:
        out["search_templates"] = existing["search_templates"]
    out["factions"] = out_factions
    out["_source"] = {
        "imported_from": "wahapedia.ru/wh40k10ed",
        "last_update_file": (WAHAPEDIA_DIR / "Last_update.csv").read_text(encoding="utf-8").strip().replace("\ufeff", ""),
    }
    return out, dict(stats)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="Don't write; report counts + diff vs. existing")
    ap.add_argument("--out", type=Path, default=UNITS_JSON)
    args = ap.parse_args()

    if not WAHAPEDIA_DIR.exists():
        raise SystemExit(f"{WAHAPEDIA_DIR} not found. Re-download the CSVs first.")

    new_data, stats = migrate()

    # Compare to existing
    old_slugs_by_faction: dict[str, set[str]] = {}
    if args.out.exists():
        old_data = json.loads(args.out.read_text(encoding="utf-8"))
        for f, body in (old_data.get("factions") or {}).items():
            slugs = {
                u["name"].lower().replace("'", "").replace(" ", "_")
                for u in (body.get("units") or [])
                if u.get("name")
            }
            old_slugs_by_faction[f] = slugs

    print("=== MIGRATION STATS ===")
    for k in sorted(stats):
        print(f"  {k:40s} {stats[k]}")

    print("\n=== PER-FACTION UNIT COUNTS ===")
    for f, body in new_data["factions"].items():
        n = len(body["units"])
        old_n = len(old_slugs_by_faction.get(f, ()))
        delta = n - old_n
        marker = "+" if delta > 0 else ("-" if delta < 0 else "·")
        print(f"  {marker} {f:22s}  old={old_n:4d}  new={n:4d}  delta={delta:+d}")

    print("\n=== NEW UNIT COUNT: ===")
    print(f"  old total: {sum(len(v) for v in old_slugs_by_faction.values())}")
    print(f"  new total: {sum(len(b['units']) for b in new_data['factions'].values())}")

    # Which old slugs are now missing?
    print("\n=== OLD SLUGS NOT IN NEW (potential regressions) ===")
    missing_total = 0
    for f, old_slugs in old_slugs_by_faction.items():
        new_slugs = {
            u["name"].lower().replace("'", "").replace(" ", "_")
            for u in new_data["factions"].get(f, {}).get("units", ())
        }
        missing = old_slugs - new_slugs
        if missing:
            missing_total += len(missing)
            sample = sorted(missing)[:8]
            print(f"  {f}: {len(missing)} missing — e.g. {sample}")
    print(f"  total missing: {missing_total}")

    if args.dry_run:
        print("\n--dry-run: not writing.")
        return

    # Backup existing
    if args.out.exists():
        backup = args.out.with_suffix(".json.backup")
        i = 0
        while backup.exists():
            i += 1
            backup = args.out.with_suffix(f".json.backup.{i}")
        shutil.copy2(args.out, backup)
        print(f"\nbacked up existing → {backup.relative_to(REPO)}")

    args.out.write_text(
        json.dumps(new_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"wrote {args.out.relative_to(REPO)} ({args.out.stat().st_size:,}B)")


if __name__ == "__main__":
    main()
