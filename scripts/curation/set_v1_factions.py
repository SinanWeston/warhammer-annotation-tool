"""Tag the locked v1 faction set on wh40k_pile (Battle Scanner Plan §2).

v1 scope locked 2026-06-04: Space Marines, Necrons, Tyranids, Death Guard.
Maps noisy weak_faction folder names to a canonical `faction_v1` field and saves
a 'v1' view. Folder-faction is weak — loyalist chapter folders fold into
space_marines; tyranid unit-folders fold into tyranids.

Note: death_guard has 0 isolation/unit shots in the corpus, so its retrieval
gallery must be sourced from GW official multi-angle photos (plan §6.2).

Usage:
  fiftyone_env/bin/python scripts/curation/set_v1_factions.py [--name wh40k_pile]
"""
from __future__ import annotations

import argparse

import fiftyone as fo
from fiftyone import ViewField as F

V1 = {
    "space_marines": {"space_marines", "blood_angels", "dark_angels",
                      "space_wolves", "black_templars", "deathwatch"},
    "necrons": {"necrons"},
    "tyranids": {"tyranids", "hormagaunts", "tyranid_ripper_swarm"},
    "death_guard": {"death_guard"},
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="wh40k_pile")
    args = ap.parse_args()

    ds = fo.load_dataset(args.name)
    if not ds.has_sample_field("faction_v1"):
        ds.add_sample_field("faction_v1", fo.StringField)
    ds.set_field("faction_v1", None).save()

    for canon, folders in V1.items():
        ds.match(F("weak_faction").is_in(list(folders))).set_field("faction_v1", canon).save()

    ds.save_view("v1", ds.exists("faction_v1"), overwrite=True)
    print("faction_v1 counts:", ds.count_values("faction_v1"))


if __name__ == "__main__":
    main()
