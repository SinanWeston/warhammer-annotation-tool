"""Load GPU embeddings back into FiftyOne, then dedup + score uniqueness (Plan D1).

Takes the embeddings.npz produced on Colab by embed_gpu.py, attaches each vector to
its FiftyOne sample (matched by filepath), then runs the FiftyOne Brain curation
pass: near-duplicate detection + uniqueness scoring + a UMAP visualization.

Tags applied (review in the App, then act):
  - "dup"        : near-duplicate of a kept representative (candidate for removal)
  - "low_unique" : bottom-decile uniqueness (often junk / redundant)

Requires: fiftyone-brain + umap-learn
  fiftyone_env/bin/pip install fiftyone-brain umap-learn

Usage:
  fiftyone_env/bin/python scripts/curation/load_embeddings.py \
      --npz ~/Downloads/embeddings.npz [--name wh40k_pile] [--dup-thresh 0.04]
"""
from __future__ import annotations

import argparse

import numpy as np

import fiftyone as fo
import fiftyone.brain as fob


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--npz", required=True)
    ap.add_argument("--name", default="wh40k_pile")
    ap.add_argument("--dup-thresh", type=float, default=0.04,
                    help="cosine distance below which samples are near-duplicates")
    args = ap.parse_args()

    data = np.load(args.npz, allow_pickle=True)
    filepaths = [str(p) for p in data["filepaths"]]
    embeddings = data["embeddings"].astype(np.float32)
    print(f"loaded {embeddings.shape} embeddings (model={data['model']})")

    ds = fo.load_dataset(args.name)

    # attach embeddings by filepath (skip if already attached on a prior run)
    already = ds.exists("embedding").count()
    if already == len(ds):
        print(f"embeddings already attached ({already}); skipping attach")
    else:
        fp_to_vec = {fp: embeddings[i] for i, fp in enumerate(filepaths)}
        n_set = 0
        for s in ds.iter_samples(progress=True, autosave=True):
            v = fp_to_vec.get(s.filepath)
            if v is not None:
                s["embedding"] = v
                n_set += 1
        print(f"attached embeddings to {n_set}/{len(ds)} samples")

    view = ds.exists("embedding")
    emb_field = "embedding"

    # 1) near-duplicates
    print("computing near-duplicates...")
    dup_index = fob.compute_near_duplicates(view, embeddings=emb_field, threshold=args.dup_thresh)
    dup_ids = set(dup_index.duplicate_ids)
    for s in view.select(list(dup_ids)).iter_samples(autosave=True):
        s.tags.append("dup")
    print(f"  flagged {len(dup_ids)} near-duplicates (thresh={args.dup_thresh})")

    # 2) uniqueness
    print("computing uniqueness...")
    fob.compute_uniqueness(view, embeddings=emb_field)
    cutoff = view.values("uniqueness")
    cutoff = float(np.percentile([u for u in cutoff if u is not None], 10))
    low = view.match({"uniqueness": {"$lte": cutoff}})
    for s in low.iter_samples(autosave=True):
        s.tags.append("low_unique")
    print(f"  flagged {low.count()} low-uniqueness samples (<= p10 {cutoff:.3f})")

    # 3) UMAP visualization for the App
    print("computing UMAP visualization...")
    fob.compute_visualization(view, embeddings=emb_field, brain_key="umap", method="umap")

    print("\nDone. Launch the App and inspect the 'dup' / 'low_unique' tags + UMAP:")
    print("  fiftyone_env/bin/fiftyone app launch", args.name)


if __name__ == "__main__":
    main()
