"""Seed the Death Guard gallery from already-scraped (not-yet-ingested) data.

DG had **zero** gallery crops — the gallery was built only from the `isolation`
corpus (td2), which lacked Death Guard, and DG's holdout is exhausted. But DG
photos were already on disk from two prior scrapes, just unclassified / mis-pooled:

  gw_shop : ~60 official GW product shots (detection pool, faction_v1=death_guard,
            no weak_unit). Canonical per-unit, studio, shallow.
  cmon    : ~129 community-painted shots across 41 CoolMiniOrNot entries whose
            title/description mention DG (faction_v1=None, source=cmon). Varied
            paint schemes — the retrieval-robustness depth.

This promotes both into the gallery (set weak_unit + pool=gallery). Idempotent.
Pairs with the `build_pools.py` gallery rule, which now admits gw_shop/cmon images
that carry a weak_unit. Result: DG gallery ≈ 189 crops / 29 units.

  fiftyone_env/bin/python scripts/curation/seed_dg_gallery.py
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

DG_KEYWORDS = [
    "death guard", "death-guard", "deathguard", "nurgle", "plague marine",
    "poxwalker", "mortarion", "typhus", "deathshroud", "blightlord", "bloat drone",
    "plaguebearer", "foul blight", "biologus", "plague", "rotbone", "myphitic",
    "malignant",
]
# title keyword → weak_unit slug (aligned with the gw_shop slugs so depth accrues)
UNIT_MAP = [
    ("mortarion", "daemon_primarch_mortarion"), ("typhus", "death_guard_typhus"),
    ("deathshroud", "deathshroud_bodyguard"), ("poxwalker", "csmdg_poxwalkers"),
    ("blight-hauler", "myphitic_blight_hauler"), ("blighthauler", "myphitic_blight_hauler"),
    ("blight hauler", "myphitic_blight_hauler"), ("biologus", "biologus_putrifier"),
    ("bloat drone", "bloat_drone"), ("blightlord", "death_guard_blight_lord_terminators"),
    ("plaguebearer", "plaguebearers"), ("foul blight", "death_guard_foul_blight_spawn"),
]
CMON_ENTRIES = [
    "scripts/cmon/data/entries_single.jsonl",
    "scripts/cmon/data/entries_all.jsonl",
]


def _unit_from_title(title: str) -> str:
    t = title.lower()
    for kw, slug in UNIT_MAP:
        if kw in t:
            return slug
    return "plague_marines"  # generic DG infantry catch-all


def _dg_cmon_ids() -> dict[str, str]:
    """{cmon entry id: weak_unit} for entries whose text mentions Death Guard."""
    out: dict[str, str] = {}
    for fn in CMON_ENTRIES:
        if not Path(fn).exists():
            continue
        for line in Path(fn).read_text().splitlines():
            try:
                r = json.loads(line)
            except Exception:
                continue
            text = (r.get("title", "") + " " + r.get("description", "") + " "
                    + " ".join(r.get("tags", []))).lower()
            if any(k in text for k in DG_KEYWORDS):
                out[str(r["id"])] = _unit_from_title(r.get("title", ""))
    return out


def main() -> None:
    import collections

    import fiftyone as fo
    from fiftyone import ViewField as F

    ds = fo.load_dataset("wh40k_pile")

    # 1. gw_shop DG → gallery (unit from filename slug before '__')
    gw = ds.match((F("weak_faction") == "death_guard") & (F("source") == "gw_shop"))
    gw = gw.select_fields(["filepath", "faction_v1", "weak_unit", "pool"])
    n_gw = 0
    for s in gw:
        bn = os.path.basename(s.filepath)
        if "__" not in bn:
            continue
        s["weak_unit"] = bn.split("__")[0]
        s["faction_v1"] = "death_guard"
        s["pool"] = "gallery"
        s.save()
        n_gw += 1

    # 2. cmon DG → gallery (unit from CMON entry title)
    id_unit = _dg_cmon_ids()
    cm = ds.match(F("source") == "cmon").select_fields(
        ["filepath", "embedding", "faction_v1", "weak_faction", "weak_unit", "pool"])
    n_cm = 0
    for s in cm:
        m = re.search(r"cmon_(\d+)_", os.path.basename(s.filepath))
        if not m or m.group(1) not in id_unit or s.embedding is None:
            continue
        s["faction_v1"] = "death_guard"
        s["weak_faction"] = "death_guard"
        s["weak_unit"] = id_unit[m.group(1)]
        s["pool"] = "gallery"
        s.save()
        n_cm += 1

    gal = ds.match(F("pool") == "gallery")
    ds.save_view("gallery", gal, overwrite=True)
    dgg = gal.match(F("faction_v1") == "death_guard")
    dep = collections.Counter(dgg.values("weak_unit"))
    print(f"seeded DG gallery: gw_shop +{n_gw}, cmon +{n_cm}")
    print(f"DG gallery now: {dgg.count()} crops / {len(dep)} units "
          f"(depth>=5: {sum(1 for d in dep.values() if d >= 5)})")


if __name__ == "__main__":
    main()
