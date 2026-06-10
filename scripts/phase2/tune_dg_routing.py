"""Tier 2 DG-routing experiment — can class weighting fix the 0.27?

DG is the v1-restricted probe's residual weak link (faction top-1 0.270 on
real crops) while being Tier 3's best faction. Suspected cause: class
imbalance (182 DG training crops vs 2,914 SM) + the most domain-shifted
training set (gw_shop studio / cmon glamour vs real tabletop). This tests the
cheap lever — LogisticRegression class weighting — on both eval sets:

  queries : 102 gold-domain unit crops (the compounded-bench query set)
  gold    : gold_v2 box crops, v1 factions only (the canonical Tier 2 test)

Needs the cache from embed_eval_crops.py.

  fiftyone_env/bin/python scripts/phase2/tune_dg_routing.py
"""
from __future__ import annotations

import collections
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from photoanalyzer.classify import FactionProbe  # noqa: E402
from photoanalyzer.taxonomy import V1_FACTIONS  # noqa: E402

CACHE = Path("data/embeddings/eval_crops_cache.npz")

VARIANTS = [
    ("baseline (current production)", None),
    ("class_weight=balanced", "balanced"),
    # halfway: sqrt-inverse-frequency — balanced can over-correct massively
    # imbalanced classes; computed at runtime
    ("class_weight=sqrt-inv-freq", "sqrt"),
]


def score(name, probe, sets):
    print(f"\n=== {name} ===")
    for set_name, X, y in sets:
        preds = np.array([p.faction for p in probe.predict(X)])
        m_all = np.isin(y, V1_FACTIONS)
        line = [f"  {set_name:8} v1 top-1 {np.mean(preds[m_all] == y[m_all]):.3f} |"]
        for fac in V1_FACTIONS:
            m = y == fac
            if m.any():
                line.append(f" {fac.split('_')[0][:4]} {np.mean(preds[m] == fac):.2f}")
        print("".join(line))
        if set_name == "queries":
            dg = y == "death_guard"
            conf = collections.Counter(preds[dg])
            print(f"           DG routed to: {dict(conf.most_common())}")


def main() -> None:
    import fiftyone as fo
    from fiftyone import ViewField as F

    if not CACHE.exists():
        raise SystemExit(f"missing {CACHE} — run scripts/phase2/embed_eval_crops.py")
    c = np.load(CACHE, allow_pickle=False)
    Xq = c["q_emb"].astype(np.float32)
    yq = np.array([str(s) for s in c["q_faction"]])
    Xg = c["g_emb"].astype(np.float32)
    yg = np.array([str(s) for s in c["g_label"]])
    gv1 = np.isin(yg, V1_FACTIONS)
    sets = [("queries", Xq, yq), ("gold", Xg[gv1], yg[gv1])]

    ds = fo.load_dataset("wh40k_pile")
    gal = ds.match((F("pool") == "gallery") & (F("embedding") != None))  # noqa: E711
    facs, embs = gal.values(["weak_faction", "embedding"])
    Xtr = np.stack([np.asarray(e, np.float32) for e in embs])
    ytr = np.asarray([str(f) for f in facs])
    print(f"train: {len(ytr)} gallery crops")

    counts = collections.Counter(ytr)
    for name, cw in VARIANTS:
        if cw == "sqrt":
            n = len(ytr)
            cw = {c_: float(np.sqrt(n / cnt)) for c_, cnt in counts.items()}
        probe = FactionProbe().fit(Xtr, ytr, class_weight=cw)
        score(name, probe, sets)


if __name__ == "__main__":
    main()
