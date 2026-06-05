"""Ingest the Warhammer Community scrape into the pile (detection-pool depth).

`scripts/warhammer_community/scraper.py` saves GW hobby-article images to
`images/{faction}/{article_slug}/`. These are studio painted minis across every
faction, but the labels are *article-level* (weak faction, no per-unit) and many
articles are multi-mini battle/showcase shots — so they're **detection-pool**
material (Tier 1 training depth), not per-unit gallery references.

This adds them to `wh40k_pile`: weak_faction from the folder (None for `unknown`),
faction_v1 resolved for the four v1 factions (chapters/sub-factions collapse via
taxonomy), source/provenance set, pool=detection. **No embedding** — that's a
later Colab batch; until embedded these are excluded from dedup + the gallery.
Skips `_below_threshold` (scraper-rejected) and basenames already in the pile.

  fiftyone_env/bin/python scripts/curation/ingest_warhammer_community.py [--dry-run]
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

IMG_ROOT = Path("scripts/warhammer_community/images")
V1 = {"space_marines", "necrons", "tyranids", "death_guard"}
SKIP_DIRS = {"_below_threshold"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    import collections

    import fiftyone as fo
    from photoanalyzer.taxonomy import resolve_faction

    ds = fo.load_dataset("wh40k_pile")
    have = {os.path.basename(p) for p in ds.values("filepath")}

    todo = []  # (path, weak_faction, faction_v1)
    for f in IMG_ROOT.glob("*/*/*.jpg"):
        faction_dir = f.parts[-3]
        if faction_dir in SKIP_DIRS or f.name in have:
            continue
        wf = None if faction_dir == "unknown" else faction_dir
        resolved = resolve_faction(wf) if wf else None
        fv1 = resolved if resolved in V1 else None
        todo.append((str(f.resolve()), wf, fv1))

    by_fac = collections.Counter(t[1] or "unknown" for t in todo)
    print(f"to ingest: {len(todo)} images")
    print("by faction:", dict(by_fac.most_common()))
    print("v1-resolved:", collections.Counter(t[2] for t in todo if t[2]))
    if not todo or args.dry_run:
        print("(dry-run or nothing to do)")
        return

    samples = [
        fo.Sample(
            filepath=path, source="warhammer_community", corpus="warhammer_community",
            weak_faction=wf, faction_v1=fv1, pool="detection",
            label_source="wc_article", label_confidence=0.3,
        )
        for path, wf, fv1 in todo
    ]
    ds.add_samples(samples)
    det = ds.match_tags  # noqa: keep import surface small
    print(f"\nadded {len(samples)} → detection pool (un-embedded). "
          f"Run a Colab embed batch before dedup / gallery use.")


if __name__ == "__main__":
    main()
