"""Add the provenance metadata sidecar to wh40k_pile (Image Sourcing Plan §A8, Wave 0).

Local-only migration: stamps the existing corpus with the schema that makes
"maximise now, sort legality later" possible. New images from the acquisition
waves must be ingested with these fields populated from their real source.

Existing samples lack true source_url/uploader/caption, so those stay null; we set
what's derivable from folder source + sensible defaults. realism_tier and
license_status are SOURCE HEURISTICS (refined later by the detector pass /
manual review); product_safe defaults False for everything.

weak_faction / weak_unit already serve as the schema's faction / unit weak labels.

Usage:
  fiftyone_env/bin/python scripts/curation/provenance.py [--name wh40k_pile]
"""
from __future__ import annotations

import argparse

import fiftyone as fo
from fiftyone import ViewField as F

# source folder -> realism tier (heuristic; detector pass refines via num_minis_est)
SOURCE_TIER = {
    "gw_shop": "T0", "isolation": "T1", "combat_patrol": "T1",
    "ebay": "T1", "cmon": "T1", "dakkadakka": "T1", "reddit": "T2",
}
# source folder -> license posture (heuristic)
SOURCE_LICENSE = {
    "gw_shop": "official_gw", "ebay": "marketplace_seller",
    "reddit": "forum_user", "dakkadakka": "forum_user", "cmon": "forum_user",
    "isolation": "unknown", "combat_patrol": "unknown",
}

# field -> default value applied to the whole dataset
CONSTANT_DEFAULTS = {
    "source_url": None,
    "scrape_date": None,
    "uploader": None,
    "caption_title": None,
    "label_source": "path",       # folder-derived weak labels
    "label_confidence": 0.3,
    "finish_state": "unknown",    # don't guess painted/bare for existing
    "num_minis_est": None,        # filled by the detector pass later
    "is_negative": False,
    "not_gw": False,
    "realism_tier": "T1",         # default; overridden per-source below
    "license_status": "unknown",  # default; overridden per-source below
    "product_safe": False,        # promoted later for own/CC/official-permitted
}

FIELD_TYPES = {
    "label_confidence": fo.FloatField,
    "num_minis_est": fo.IntField,
    "is_negative": fo.BooleanField,
    "not_gw": fo.BooleanField,
    "product_safe": fo.BooleanField,
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="wh40k_pile")
    args = ap.parse_args()

    ds = fo.load_dataset(args.name)

    for field, default in CONSTANT_DEFAULTS.items():
        if not ds.has_sample_field(field):
            ds.add_sample_field(field, FIELD_TYPES.get(field, fo.StringField))
        ds.set_field(field, default).save()

    # per-source overrides
    for src, tier in SOURCE_TIER.items():
        ds.match(F("source") == src).set_field("realism_tier", tier).save()
    for src, lic in SOURCE_LICENSE.items():
        ds.match(F("source") == src).set_field("license_status", lic).save()

    print("provenance schema applied.")
    print("realism_tier:", ds.count_values("realism_tier"))
    print("license_status:", ds.count_values("license_status"))
    print("product_safe:", ds.count_values("product_safe"))


if __name__ == "__main__":
    main()
