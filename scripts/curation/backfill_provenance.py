"""Backfill real provenance into wh40k_pile from td2's scrape_log.csv (Sourcing §A8).

training_data_v2/metadata/scrape_log.csv holds real acquisition metadata
(source_url, page_url, platform, unit_name, search_query, file_hash, timestamp,
dims) for ~28k scraped images. provenance.py left those fields null for the whole
corpus; this fills them in for every sample whose basename matches the log —
turning weak folder-labels into genuine attribution for free.

Join key: image basename. Does not overwrite weak_unit/weak_faction (the folder
slugs are cleaner than the log's free-text product names); the log's unit_name +
search_query go into caption_title.

Usage:
  fiftyone_env/bin/python scripts/curation/backfill_provenance.py [--name wh40k_pile]
"""
from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path

import fiftyone as fo

REPO = Path(__file__).resolve().parents[2]
LOG = REPO / "training_data_v2" / "metadata" / "scrape_log.csv"

PLATFORM_LICENSE = {
    "ebay": "marketplace_seller",
    "reddit": "forum_user",
    "instagram": "forum_user",
    "youtube": "forum_user",
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="wh40k_pile")
    args = ap.parse_args()

    # basename -> log row (last occurrence wins)
    rows = {}
    with open(LOG, newline="") as f:
        for r in csv.DictReader(f):
            fn = r.get("filename")
            if fn:
                rows[os.path.basename(fn)] = r
    print(f"loaded {len(rows)} provenance rows from scrape_log.csv")

    ds = fo.load_dataset(args.name)
    for field in ("source_platform", "file_hash"):
        if not ds.has_sample_field(field):
            ds.add_sample_field(field, fo.StringField)

    matched = 0
    for s in ds.iter_samples(progress=True, autosave=True):
        r = rows.get(os.path.basename(s.filepath))
        if not r:
            continue
        matched += 1
        cap = (r.get("unit_name") or "").strip()
        sq = (r.get("search_query") or "").strip()
        s["caption_title"] = " | ".join(x for x in (cap, sq) if x) or None
        s["source_url"] = (r.get("page_url") or r.get("source_url") or "").strip() or None
        s["scrape_date"] = (r.get("timestamp") or "").strip() or None
        plat = (r.get("source_platform") or "").strip().lower() or None
        s["source_platform"] = plat
        s["file_hash"] = (r.get("file_hash") or "").strip() or None
        s["label_source"] = "scrape_log"
        s["label_confidence"] = 0.6
        if plat in PLATFORM_LICENSE:
            s["license_status"] = PLATFORM_LICENSE[plat]

    print(f"\nbackfilled provenance on {matched} samples")
    print("source_platform:", ds.exists("source_platform").count_values("source_platform"))
    print("with real source_url:", ds.exists("source_url").count())


if __name__ == "__main__":
    main()
