"""Tier 3 retrieval eval — leave-one-out over the gallery, per faction.

For each gallery crop whose unit has >=2 crops, query the rest of the gallery by
cosine similarity on the frozen DINOv2 embedding and check whether the same
`weak_unit` appears in the top-1 / top-3. Scoped = restrict the gallery to the
query's own faction (the production path: Tier 2 picks the faction, Tier 3
retrieves within it). This is the cheapest honest read on whether a faction's
gallery actually retrieves — no separate query set needed.

  fiftyone_env/bin/python scripts/phase3/eval_gallery_retrieval.py [--factions a,b]
"""
from __future__ import annotations

import argparse
import collections

import numpy as np


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--factions", default="space_marines,necrons,tyranids,death_guard")
    args = ap.parse_args()

    import fiftyone as fo
    from fiftyone import ViewField as F

    ds = fo.load_dataset("wh40k_pile")
    gal = ds.match(F("pool") == "gallery")
    fac, unit, emb = gal.values(["weak_faction", "weak_unit", "embedding"])
    X = np.stack([np.asarray(e, np.float32) for e in emb])
    X /= np.linalg.norm(X, axis=1, keepdims=True) + 1e-9
    fac = np.array([str(f) for f in fac])
    unit = np.array([str(u) for u in unit])

    def scoped(faction: str):
        gi = np.where(fac == faction)[0]
        G = X[gi]
        uc = collections.Counter(unit[gi])
        t1 = t3 = n = 0
        fails: list[str] = []
        for i in gi:
            if uc[unit[i]] < 2:
                continue
            order = gi[np.argsort(-(G @ X[i]))]
            order = order[order != i][:3]
            ru = unit[order]
            n += 1
            t1 += int(ru[0] == unit[i])
            t3 += int(unit[i] in ru[:3])
            if unit[i] not in ru[:3]:
                fails.append(unit[i])
        return n, (t1 / n if n else 0.0), (t3 / n if n else 0.0), fails

    print(f"  {'faction':16} {'n':>5} {'units':>6} {'top-1':>7} {'top-3':>7}  pass(>=0.80)")
    for f in args.factions.split(","):
        n, t1, t3, fails = scoped(f)
        nu = len(set(unit[fac == f]))
        ok = "✅" if t3 >= 0.80 else "⚠️"
        print(f"  {f:16} {n:>5} {nu:>6} {t1:>7.3f} {t3:>7.3f}  {ok}")
        if fails:
            top = collections.Counter(fails).most_common(4)
            print(f"      worst units: {dict(top)}")


if __name__ == "__main__":
    main()
