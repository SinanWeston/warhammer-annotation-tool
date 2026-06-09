"""One-shot fix: pull the 7 gold_v2 images back OUT of the gallery pool.

2026-06-09 straddle check found 7 gold_v2 Death Guard gw_shop images with
pool="gallery" — seed_dg_gallery.py (06-06) swept them in, clobbering the
deliberate 06-05 re-pooling to pool="gold" (recorded at the time as "to avoid
train/eval leakage"). While they sit in the gallery they are Tier 3 retrieval
candidates and Tier 2 probe TRAINING data — i.e. eval images inside the
training/index set. seed_dg_gallery.py now guards against this; this script
repairs the existing state. Idempotent.

USER-RUN ON PURPOSE (mutates the FiftyOne DB):
  fiftyone_env/bin/python scripts/curation/fix_gold_pool_contamination.py
"""
from __future__ import annotations

import collections
import json


def main() -> None:
    import fiftyone as fo
    from fiftyone import ViewField as F

    ds = fo.load_dataset("wh40k_pile")
    gold_fps = [im["filepath"]
                for im in json.load(open("data/gold/gold_v2.json"))["images"]]
    bad = ds.match(F("filepath").is_in(gold_fps) & (F("pool") == "gallery"))
    n = 0
    for s in bad.iter_samples(autosave=True):
        print(f"  gallery -> gold: {s.filepath.split('training_data/')[-1]}")
        s["pool"] = "gold"
        n += 1
    print(f"re-pooled {n} gold images")
    pools = ds.match(F("filepath").is_in(gold_fps)).values("pool")
    print("gold_v2 pools now:", dict(collections.Counter(map(str, pools))))
    print("gallery size now:", ds.match(F("pool") == "gallery").count())
    print("\nAfter this, re-run for clean numbers:")
    print("  fiftyone_env/bin/python scripts/phase3/eval_gold_domain_retrieval.py")
    print("  fiftyone_env/bin/python scripts/phase3/eval_compounded_t2t3.py")


if __name__ == "__main__":
    main()
