"""Select gold v7 candidates — the Space Marines fill round.

gold_v2 has only 7 SM images / 55 boxes (2026-06-09 review): every SM number
(Tier 2 probe 0.47, Tier 3 retrieval 0.20) rests on a handful of images. This
picks ~25 SM candidate scenes for a CVAT v7 round, following the established
recipe: faction-quota seeded, source-diversified away from dakkadakka, skipping
anything already gold / gallery / dup / lowq.

Dry-run by default (prints + writes the candidate list). Tagging the samples
`gold_v7` mutates the FiftyOne DB — run with --apply yourself, then:
  fiftyone_env/bin/python scripts/curation/gold_to_cvat.py push v7

  fiftyone_env/bin/python scripts/curation/select_gold_v7_sm.py [--n 25] [--apply]
"""
from __future__ import annotations

import argparse
import collections
import json
import random
from pathlib import Path

OUT = Path("data/gold/gold_v7_sm_candidates.json")
GOLD = Path("data/gold/gold_v2.json")
# spread across sources; dakka deprioritized per the v2-v5 lesson
SOURCE_QUOTA = {"reddit": 8, "ebay": 8, "cmon": 4, "gw_shop": 2, "dakkadakka": 3}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=25)
    ap.add_argument("--apply", action="store_true",
                    help="tag the selected samples 'gold_v7' in FiftyOne (mutates DB)")
    ap.add_argument("--seed", type=int, default=40)
    args = ap.parse_args()

    import fiftyone as fo
    from fiftyone import ViewField as F

    gold_fps = {im["filepath"] for im in json.loads(GOLD.read_text())["images"]}

    ds = fo.load_dataset("wh40k_pile")
    cand = ds.match(
        (F("faction_v1") == "space_marines")
        & F("pool").is_in(["holdout", "detection"])
        & ~F("tags").contains("dup")
        & ~F("tags").contains("lowq")
        & ~F("tags").contains("low_unique")
    )
    by_source = collections.defaultdict(list)
    for fp, src in zip(*cand.values(["filepath", "source"])):
        if fp not in gold_fps:
            by_source[str(src)].append(fp)

    rng = random.Random(args.seed)
    picked: list[str] = []
    for src, quota in SOURCE_QUOTA.items():
        pool = by_source.get(src, [])
        rng.shuffle(pool)
        take = pool[:quota]
        picked.extend(take)
        print(f"  {src:14} pool {len(pool):5}  picked {len(take)}")
    picked = picked[: args.n]
    print(f"\n{len(picked)} candidates")

    OUT.write_text(json.dumps({"profile": "v7", "faction": "space_marines",
                               "filepaths": picked}, indent=2) + "\n")
    print(f"wrote {OUT}")

    if args.apply:
        view = ds.match(F("filepath").is_in(picked))
        for s in view.iter_samples(autosave=True):
            if "gold_v7" not in s.tags:
                s.tags.append("gold_v7")
        print(f"tagged {view.count()} samples 'gold_v7' — next: gold_to_cvat.py push v7")
    else:
        print("dry-run (no DB change). Re-run with --apply to tag, then push v7.")


if __name__ == "__main__":
    main()
