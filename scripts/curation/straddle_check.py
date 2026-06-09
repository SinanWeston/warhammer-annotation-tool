"""Near-dup straddle check — do gold/holdout images have embedding-space twins
in the gallery?

The pHash dedup (Hamming <= 10) can miss near-duplicates that an embedding
considers nearly identical; if such a pair straddles gallery and gold/holdout,
every embedding-based eval is quietly inflated (2026-06-09 review, should-fix).
Read-only: reports max-cosine distributions, changes nothing.

  fiftyone_env/bin/python scripts/curation/straddle_check.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

GOLD = "data/gold/gold_v2.json"
THRESHOLDS = (0.95, 0.97, 0.99)


def report(name, sims, paths):
    sims = np.asarray(sims)
    print(f"\n=== {name} (n={len(sims)}) ===")
    if not len(sims):
        return
    print(f"  max-cosine vs gallery: median {np.median(sims):.3f}  "
          f"p90 {np.percentile(sims, 90):.3f}  max {sims.max():.3f}")
    for t in THRESHOLDS:
        n = int((sims >= t).sum())
        print(f"  >= {t}: {n}")
    worst = np.argsort(-sims)[:5]
    for i in worst:
        if sims[i] >= THRESHOLDS[0]:
            print(f"    suspect {sims[i]:.3f}  {paths[i]}")


def main() -> None:
    import fiftyone as fo
    from fiftyone import ViewField as F

    ds = fo.load_dataset("wh40k_pile")
    gal = ds.match((F("pool") == "gallery") & (F("embedding") != None))  # noqa: E711
    G = np.stack([np.asarray(e, np.float32) for e in gal.values("embedding")])
    G /= np.linalg.norm(G, axis=1, keepdims=True) + 1e-9
    print(f"gallery: {len(G)} embedded crops")

    # gold_v2 images (whole scene images — the eval set)
    gold_fps = [im["filepath"] for im in json.loads(Path(GOLD).read_text())["images"]]
    view = ds.match(F("filepath").is_in(gold_fps) & (F("embedding") != None))  # noqa: E711
    fps, embs = view.values(["filepath", "embedding"])
    X = np.stack([np.asarray(e, np.float32) for e in embs])
    X /= np.linalg.norm(X, axis=1, keepdims=True) + 1e-9
    print(f"gold: {len(fps)}/{len(gold_fps)} images found in pile with embeddings")
    report("gold_v2 vs gallery", (X @ G.T).max(axis=1), fps)

    # holdout pool
    hold = ds.match((F("pool") == "holdout") & (F("embedding") != None))  # noqa: E711
    fps, embs = hold.values(["filepath", "embedding"])
    X = np.stack([np.asarray(e, np.float32) for e in embs])
    X /= np.linalg.norm(X, axis=1, keepdims=True) + 1e-9
    report("holdout vs gallery", (X @ G.T).max(axis=1), fps)


if __name__ == "__main__":
    main()
