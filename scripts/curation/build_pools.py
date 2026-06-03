"""Build the clean view + role-split pools on wh40k_pile (Battle Scanner Plan D1).

Reproducible curation step. Assumes embeddings + 'dup'/'low_unique' tags already
exist (run load_embeddings.py first). Non-destructive: no files deleted, no samples
removed — just a saved 'clean' view (excludes near-duplicates) and a per-sample
`pool` field.

Pools:
  excluded  -> parked near-duplicates ('dup' tag)
  gallery   -> clean isolation single-model shots WITH a weak_unit label (Tier 3 ref)
  holdout   -> seeded ~1000-image frozen slice of clean non-gallery (dev proxy eval;
               the REAL eval is your own tabletop photos — see plan §4.5)
  detection -> remaining clean (Tier 1 counting)

Usage:
  fiftyone_env/bin/python scripts/curation/build_pools.py [--name wh40k_pile] [--holdout 1000] [--seed 42]
"""
from __future__ import annotations

import argparse
import random

import fiftyone as fo
from fiftyone import ViewField as F


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="wh40k_pile")
    ap.add_argument("--holdout", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    ds = fo.load_dataset(args.name)

    # clean view = exclude near-duplicates (non-destructive)
    clean = ds.match_tags("dup", bool=False)
    ds.save_view("clean", clean, overwrite=True)

    if not ds.has_sample_field("pool"):
        ds.add_sample_field("pool", fo.StringField)
    ds.set_field("pool", "excluded").save()

    # gallery
    gallery = clean.match(F("source") == "isolation").exists("weak_unit")
    gallery.set_field("pool", "gallery").save()
    gal_ids = set(gallery.values("id"))

    # holdout (seeded, frozen)
    rest_ids = [i for i in clean.values("id") if i not in gal_ids]
    random.seed(args.seed)
    random.shuffle(rest_ids)
    holdout_ids = rest_ids[: args.holdout]
    ds.select(holdout_ids).set_field("pool", "holdout").save()

    # detection = the rest of clean
    hold = set(holdout_ids)
    det_ids = [i for i in rest_ids if i not in hold]
    ds.select(det_ids).set_field("pool", "detection").save()

    for name in ("gallery", "detection", "holdout"):
        ds.save_view(name, ds.match(F("pool") == name), overwrite=True)

    print("POOL COUNTS")
    for k, v in sorted(ds.count_values("pool").items(), key=lambda kv: -kv[1]):
        print(f"  {v:>6}  {k}")
    print(f"gallery distinct units: {len(ds.match(F('pool')=='gallery').distinct('weak_unit'))}")


if __name__ == "__main__":
    main()
