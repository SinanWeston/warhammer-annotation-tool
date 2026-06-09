"""Tier 2 failure decomposition — WHERE does the probe lose its 22 points?

The 2026-06-05 probe scored 0.676 v1 top-1 on gold crops (bar: 0.90). Three
hypotheses: (a) domain shift gallery→tabletop, (b) gallery weak_faction label
noise, (c) gallery homogeneity (SM 100% dup). This decomposes by evaluating the
same probe recipe on gallery-internal splits:

  RANDOM 80/20 crop split   — dup-inflated upper bound (near-dup twins straddle).
  UNIT-GROUPED 80/20 split  — all crops of a (faction, weak_unit) stay together:
                              no dup leakage, still in-domain. The honest
                              "can it classify faction on unseen units" number.

Reading: unit-grouped >> 0.676 (gold)  → domain shift dominates.
         unit-grouped ≈  0.676         → label noise / homogeneity dominates.

  OMP_NUM_THREADS=4 fiftyone_env/bin/python scripts/phase2/probe_split_decomposition.py
"""
from __future__ import annotations

import numpy as np

V1 = ("space_marines", "necrons", "tyranids", "death_guard")
SEED = 40


def evaluate(name, Xtr, ytr, Xte, yte):
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    scaler = StandardScaler().fit(Xtr)
    clf = LogisticRegression(max_iter=3000, C=1.0).fit(scaler.transform(Xtr), ytr)
    pred = clf.predict(scaler.transform(Xte))
    print(f"\n=== {name} (train {len(ytr)}, test {len(yte)}) ===")
    overall = float(np.mean(pred == yte))
    print(f"  all-faction top-1: {overall:.3f}")
    for fac in V1:
        m = yte == fac
        if m.any():
            print(f"  {fac:14} n={int(m.sum()):4}  top-1 {float(np.mean(pred[m] == fac)):.3f}")
    v1m = np.isin(yte, V1)
    if v1m.any():
        v1 = float(np.mean(pred[v1m] == yte[v1m]))
        print(f"  v1 overall: {v1:.3f}  (gold-domain reference: 0.676)")
    return overall


def main() -> None:
    import fiftyone as fo
    from fiftyone import ViewField as F
    from sklearn.model_selection import GroupShuffleSplit, train_test_split

    ds = fo.load_dataset("wh40k_pile")
    gal = ds.match((F("pool") == "gallery") & (F("embedding") != None))  # noqa: E711
    facs, units, embs = gal.values(["weak_faction", "weak_unit", "embedding"])
    X = np.stack([np.asarray(e, np.float32) for e in embs])
    y = np.asarray([str(f) for f in facs])
    groups = np.asarray([f"{f}/{u}" for f, u in zip(facs, units)])
    print(f"gallery: {len(y)} crops, {len(set(y))} factions, {len(set(groups))} unit groups")

    # random crop split — near-dup twins land on both sides (upper bound)
    itr, ite = train_test_split(np.arange(len(y)), test_size=0.2,
                                random_state=SEED, stratify=y)
    evaluate("RANDOM crop split (dup-inflated)", X[itr], y[itr], X[ite], y[ite])

    # unit-grouped split — no crop of a test unit was seen in training
    gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=SEED)
    itr, ite = next(gss.split(X, y, groups))
    evaluate("UNIT-GROUPED split (honest in-domain)", X[itr], y[itr], X[ite], y[ite])


if __name__ == "__main__":
    main()
