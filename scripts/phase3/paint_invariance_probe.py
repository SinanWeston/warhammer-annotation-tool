"""Paint-invariance probe — the central bet, measured directly.

The architecture bets that frozen DINOv2 embeddings encode sculpt identity
strongly enough that (1) the same sculpt under different paint schemes still
matches, and (2) different sculpts don't match just because the paint is
similar. Until now nothing measured this (2026-06-09 review gap).

Proxy with the Death Guard gallery (the one v1 gallery with TRUSTED unit
labels and two paint regimes per sculpt: gw_shop = studio scheme, cmon =
community paint, 41 different artists):

  SAME-SCULPT / DIFF-PAINT pairs : same weak_unit, different source_url
                                   (different listing/artist — different paint job)
  DIFF-SCULPT pairs              : different weak_unit, same faction

Headline: ROC-AUC of cosine similarity separating the two pair sets, i.e.
"if I pick a same-sculpt-differently-painted pair and a different-sculpt pair,
how often does the embedding rank the former higher?" 0.5 = paint drowns
sculpt; 1.0 = perfect sculpt invariance.

  fiftyone_env/bin/python scripts/phase3/paint_invariance_probe.py
"""
from __future__ import annotations

import collections
import itertools

import numpy as np

FACTIONS = ("death_guard", "necrons", "tyranids")  # SM skipped: single-source gallery


def pair_stats(name, sims):
    s = np.asarray(sims)
    if not len(s):
        print(f"  {name:34} n=0")
        return s
    print(f"  {name:34} n={len(s):6}  median {np.median(s):.3f}  "
          f"p10 {np.percentile(s, 10):.3f}  p90 {np.percentile(s, 90):.3f}")
    return s


def auc(pos, neg, rng):
    if not len(pos) or not len(neg):
        return float("nan")
    pos = np.asarray(pos)
    neg = np.asarray(neg)
    k = min(len(pos) * len(neg), 2_000_000)
    i = rng.integers(0, len(pos), k)
    j = rng.integers(0, len(neg), k)
    return float(np.mean(pos[i] > neg[j]) + 0.5 * np.mean(pos[i] == neg[j]))


def main() -> None:
    import fiftyone as fo
    from fiftyone import ViewField as F

    rng = np.random.default_rng(40)
    ds = fo.load_dataset("wh40k_pile")

    for fac in FACTIONS:
        gal = ds.match((F("pool") == "gallery") & (F("weak_faction") == fac)
                       & (F("embedding") != None))  # noqa: E711
        units, urls, srcs, embs = gal.values(
            ["weak_unit", "source_url", "source", "embedding"])
        X = np.stack([np.asarray(e, np.float32) for e in embs])
        X /= np.linalg.norm(X, axis=1, keepdims=True) + 1e-9
        units = [str(u) for u in units]
        # listing key = source_url when present, else the source corpus —
        # DG's seeded crops have null source_url, but gw_shop (studio scheme)
        # vs cmon (community paint) is still a hard different-paint boundary.
        urls = [u if u else f"src:{s}" for u, s in zip(urls, srcs)]
        n = len(units)
        label_trust = "TRUSTED labels" if fac == "death_guard" else "weak labels — noisy"
        print(f"\n=== {fac} ({n} crops, {len(set(units))} units; {label_trust}) ===")

        S = X @ X.T
        same_paint, diff_paint, diff_sculpt = [], [], []
        for i, j in itertools.combinations(range(n), 2):
            if units[i] == units[j]:
                (same_paint if urls[i] == urls[j] else diff_paint).append(S[i, j])
            else:
                diff_sculpt.append(S[i, j])

        sp = pair_stats("same sculpt, same listing", same_paint)
        dp = pair_stats("same sculpt, DIFFERENT paint", diff_paint)
        ns = pair_stats("different sculpt (negatives)", diff_sculpt)
        print(f"  AUC same-sculpt-diff-paint vs diff-sculpt: "
              f"{auc(dp, ns, rng):.3f}   (0.5 = paint drowns sculpt)")
        if len(sp):
            print(f"  AUC same-listing vs diff-sculpt (ceiling): {auc(sp, ns, rng):.3f}")

        # how often is a query's single nearest neighbour (excl. self-listing)
        # the same sculpt despite different paint?
        hits = total = 0
        for i in range(n):
            mask = np.array([urls[k] != urls[i] for k in range(n)])
            mask[i] = False
            if not mask.any():
                continue
            j = np.where(mask)[0][np.argmax(S[i, mask])]
            total += 1
            hits += int(units[j] == units[i])
        if total:
            print(f"  cross-listing NN same-unit rate: {hits}/{total} = {hits/total:.3f}")


if __name__ == "__main__":
    main()
