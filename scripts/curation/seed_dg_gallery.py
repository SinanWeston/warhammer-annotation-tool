"""Seed the Death Guard gallery from already-scraped gw_shop product shots.

DG had **zero** gallery crops — the gallery was built only from the `isolation`
corpus (td2), which lacked Death Guard, and DG's holdout is exhausted. But ~60
official GW-shop DG product photos were already scraped (April) and sit in the
detection pool with `faction_v1=death_guard`, `source=gw_shop`, no `weak_unit`.

This promotes them to the gallery: derive `weak_unit` from the filename (the
gw_shop slug before `__`, e.g. `deathshroud_bodyguard__99070102008_...`), and set
`pool=gallery`. Idempotent. Pairs with the `build_pools.py` gallery rule, which
now admits `gw_shop` images that carry a `weak_unit` (only DG does).

These are canonical per-unit reference shots but shallow (~3 crops/unit, a few
angles per kit) — community-painted depth comes from a separate CMON scrape.

  fiftyone_env/bin/python scripts/curation/seed_dg_gallery.py
"""
from __future__ import annotations

import os


def main() -> None:
    import fiftyone as fo
    from fiftyone import ViewField as F

    ds = fo.load_dataset("wh40k_pile")
    dg = ds.match((F("weak_faction") == "death_guard") & (F("source") == "gw_shop"))

    n = 0
    units = set()
    for s in dg.select_fields(["filepath"]):
        bn = os.path.basename(s.filepath)
        unit = bn.split("__")[0] if "__" in bn else None
        if not unit:
            continue
        s.weak_unit = unit
        s.faction_v1 = "death_guard"
        s.pool = "gallery"
        s.save()
        units.add(unit)
        n += 1

    gal = ds.match(F("pool") == "gallery")
    ds.save_view("gallery", gal, overwrite=True)
    dg_gal = gal.match(F("faction_v1") == "death_guard")
    print(f"seeded {n} DG gw_shop crops → gallery across {len(units)} units; "
          f"DG now {dg_gal.count()} gallery crops / "
          f"{len(set(dg_gal.values('weak_unit')))} units.")


if __name__ == "__main__":
    main()
