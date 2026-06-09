"""Compounded Tier 2 × Tier 3 eval — the pipeline number, not the per-tier number.

Per-tier exit bars hide multiplication: 0.90 faction × 0.80 unit ≈ 0.72 per-crop
before detection losses (2026-06-09 review, P3). This measures the actual
compounded path on the gold-domain queries: Tier 2 probe predicts the faction →
Tier 3 retrieves scoped to the PREDICTED faction → correct iff faction is right
AND the true unit is in the top-3. Compare against the oracle-scoped number
(2026-06-09 gold-domain bench) to see what Tier 2 errors cost Tier 3.

Tier 1 (detection) multiplies on top of this — v0 baseline recall was 0.66.

  fiftyone_env/bin/python scripts/phase3/eval_compounded_t2t3.py
"""
from __future__ import annotations

import collections
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from eval_gold_domain_retrieval import V1, embed_crops, load_queries  # noqa: E402
from photoanalyzer.classify import FactionProbe  # noqa: E402

PROBE_ARTIFACT = Path("models/tier2_faction_probe.joblib")


def main() -> None:
    import fiftyone as fo
    from fiftyone import ViewField as F

    ds = fo.load_dataset("wh40k_pile")
    gal = ds.match((F("pool") == "gallery") & (F("embedding") != None))  # noqa: E711
    gfac, gunit, gemb = gal.values(["weak_faction", "weak_unit", "embedding"])
    G = np.stack([np.asarray(e, np.float32) for e in gemb])
    G /= np.linalg.norm(G, axis=1, keepdims=True) + 1e-9
    gfac = np.array([str(x) for x in gfac])
    gunit = np.array([str(x) for x in gunit])

    # Tier 2: the PRODUCTION probe (photoanalyzer.classify.FactionProbe).
    # Use the saved artifact when present so this evals what production ships;
    # otherwise train in-place with the same recipe.
    if PROBE_ARTIFACT.exists():
        probe = FactionProbe.load(PROBE_ARTIFACT)
        print(f"tier 2 probe loaded from {PROBE_ARTIFACT}")
    else:
        probe = FactionProbe().fit(G, gfac)
        print(f"tier 2 probe trained in-place on {len(gfac)} gallery crops "
              f"(no {PROBE_ARTIFACT}; run scripts/phase2/train_faction_probe.py)")

    queries = load_queries()
    imgs = [q.pop("_crop") for q in queries]
    Q = embed_crops(imgs).astype(np.float32)
    Q /= np.linalg.norm(Q, axis=1, keepdims=True) + 1e-9

    pred_fac = np.array([p.faction for p in probe.predict(Q, restrict=None)])
    # production default: v1-restricted routing
    pred_fac_v1 = np.array([p.faction for p in probe.predict(Q)])

    for variant, preds in (("20-way probe", pred_fac),
                           ("v1-restricted probe (production)", pred_fac_v1)):
        run_variant(variant, queries, Q, preds, gfac, gunit, G)


def run_variant(variant, queries, Q, pred_fac, gfac, gunit, G):
    per_fac = collections.defaultdict(lambda: collections.Counter())
    for q, qe, pf in zip(queries, Q, pred_fac):
        fac, unit = q["faction"], q["unit_slug"]
        c = per_fac[fac]
        c["n"] += 1
        fac_ok = pf == fac
        c["fac_ok"] += int(fac_ok)
        gi = np.where(gfac == pf)[0]  # scoped to PREDICTED faction
        if not (unit in set(gunit[np.where(gfac == fac)[0]])):
            c["uncovered"] += 1  # oracle gallery lacks the unit — depth gap
            continue
        c["covered"] += 1
        if len(gi):
            order = gi[np.argsort(-(G[gi] @ qe))]
            top_units = list(dict.fromkeys(gunit[order]))[:3]
            if fac_ok and unit in top_units:
                c["compound_ok"] += 1

    print(f"\n=== compounded Tier2→Tier3 [{variant}] on gold-domain queries "
          f"(oracle-scoped top-3 reference: 0.519) ===")
    print(f"  {'faction':16} {'n':>4} {'fac top-1':>10} {'covered':>8} "
          f"{'compound top-3':>15}")
    tot = collections.Counter()
    for fac in V1:
        c = per_fac[fac]
        tot.update(c)
        if c["n"]:
            comp = c["compound_ok"] / c["covered"] if c["covered"] else 0.0
            print(f"  {fac:16} {c['n']:>4} {c['fac_ok'] / c['n']:>10.3f} "
                  f"{c['covered']:>8} {comp:>15.3f}")
    comp = tot["compound_ok"] / tot["covered"] if tot["covered"] else 0.0
    print(f"  {'v1 overall':16} {tot['n']:>4} {tot['fac_ok'] / tot['n']:>10.3f} "
          f"{tot['covered']:>8} {comp:>15.3f}")
    print(f"\n  per-crop pipeline estimate incl. v0-baseline detection recall 0.66: "
          f"{0.66 * comp:.3f}")


if __name__ == "__main__":
    main()
