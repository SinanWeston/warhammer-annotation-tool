"""Calibrate the Tier 2 "unknown" confidence threshold (the open-set path).

gold_v2 carries 96 hand-labeled out_of_scope boxes — terrain, scenery,
non-v1 minis. The v1-restricted probe currently classifies ALL of them as some
v1 faction. This sweeps `unknown_threshold` over the renormalized confidence
and reports, per threshold:

  oos rejected : fraction of out_of_scope crops routed to "unknown"  (want high)
  v1 kept+ok   : fraction of v1 crops still classified AND correct   (want high)
  objective    : mean of the two (balanced operating point)

Uses the production artifact when present (else trains the production recipe
in-place) and the cache from embed_eval_crops.py.

  fiftyone_env/bin/python scripts/phase2/calibrate_unknown_threshold.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from photoanalyzer.classify import FactionProbe  # noqa: E402
from photoanalyzer.taxonomy import V1_FACTIONS  # noqa: E402

CACHE = Path("data/embeddings/eval_crops_cache.npz")
PROBE_ARTIFACT = Path("models/tier2_faction_probe.joblib")
THRESHOLDS = np.arange(0.30, 0.96, 0.05)


def main() -> None:
    if not CACHE.exists():
        raise SystemExit(f"missing {CACHE} — run scripts/phase2/embed_eval_crops.py")
    c = np.load(CACHE, allow_pickle=False)
    X = c["g_emb"].astype(np.float32)
    y = np.array([str(s) for s in c["g_label"]])

    if PROBE_ARTIFACT.exists():
        probe = FactionProbe.load(PROBE_ARTIFACT)
        print(f"probe: {PROBE_ARTIFACT}")
    else:
        import fiftyone as fo
        from fiftyone import ViewField as F

        ds = fo.load_dataset("wh40k_pile")
        gal = ds.match((F("pool") == "gallery") & (F("embedding") != None))  # noqa: E711
        facs, embs = gal.values(["weak_faction", "embedding"])
        probe = FactionProbe().fit(
            np.stack([np.asarray(e, np.float32) for e in embs]),
            [str(f) for f in facs])
        print("probe: trained in-place (no artifact)")

    preds = probe.predict(X)  # v1-restricted, no threshold
    fac = np.array([p.faction for p in preds])
    conf = np.array([p.confidence for p in preds])

    oos = y == "out_of_scope"
    v1 = np.isin(y, V1_FACTIONS)
    v1_correct = v1 & (fac == y)
    print(f"gold crops: {len(y)} ({int(oos.sum())} out_of_scope, {int(v1.sum())} v1)")
    print(f"no threshold: v1 acc {v1_correct.sum() / v1.sum():.3f}; "
          f"oos rejected 0.000 (all confidently misrouted)")
    print(f"oos confidence: median {np.median(conf[oos]):.3f} "
          f"vs v1-correct median {np.median(conf[v1_correct]):.3f}")

    print(f"\n  {'thresh':>6} {'oos rejected':>13} {'v1 kept+ok':>11} {'objective':>10}")
    best = (None, -1.0)
    for t in THRESHOLDS:
        rej = float(np.mean(conf[oos] < t))
        kept = float(np.mean(v1_correct[v1] & (conf[v1] >= t)))
        obj = (rej + kept) / 2
        mark = ""
        if obj > best[1]:
            best = (float(t), obj)
            mark = "  ←"
        print(f"  {t:>6.2f} {rej:>13.3f} {kept:>11.3f} {obj:>10.3f}{mark}")

    print(f"\nbest threshold: {best[0]:.2f} (objective {best[1]:.3f})")

    # ── signal 2: gallery cosine (the Tier 3 quantity) ───────────────────────
    # Softmax confidence is typically saturated/useless open-set; the
    # architecture's own bet (STRATEGY §3: "retrieval with a confidence
    # threshold can say unknown") is that embedding similarity separates.
    import fiftyone as fo
    from fiftyone import ViewField as F

    ds = fo.load_dataset("wh40k_pile")
    gal = ds.match((F("pool") == "gallery") & (F("embedding") != None))  # noqa: E711
    gfac, gemb = gal.values(["weak_faction", "embedding"])
    G = np.stack([np.asarray(e, np.float32) for e in gemb])
    G /= np.linalg.norm(G, axis=1, keepdims=True) + 1e-9
    gfac = np.array([str(f) for f in gfac])
    Xn = X / (np.linalg.norm(X, axis=1, keepdims=True) + 1e-9)
    # production quantity: similarity within the PREDICTED faction's gallery
    # slice (gold oos = non-v1 minis; vs the full 20-faction gallery they
    # legitimately match their own faction — the scoped slice is what Tier 3
    # actually searches)
    top5 = np.empty(len(Xn), dtype=np.float32)
    for f in set(fac):
        m = fac == f
        Gf = G[gfac == f]
        Sf = Xn[m] @ Gf.T
        k = min(5, Sf.shape[1])
        top5[m] = np.sort(Sf, axis=1)[:, -k:].mean(axis=1)

    print(f"\n=== signal 2: mean-top5 cosine within PREDICTED faction's gallery ===")
    print(f"oos: median {np.median(top5[oos]):.3f}  "
          f"v1-correct: median {np.median(top5[v1_correct]):.3f}")
    print(f"\n  {'thresh':>6} {'oos rejected':>13} {'v1 kept+ok':>11} {'objective':>10}")
    best2 = (None, -1.0)
    for t in np.arange(0.40, 0.86, 0.05):
        rej = float(np.mean(top5[oos] < t))
        kept = float(np.mean(v1_correct[v1] & (top5[v1] >= t)))
        obj = (rej + kept) / 2
        mark = ""
        if obj > best2[1]:
            best2 = (float(t), obj)
            mark = "  ←"
        print(f"  {t:>6.2f} {rej:>13.3f} {kept:>11.3f} {obj:>10.3f}{mark}")
    print(f"\nbest cosine threshold: {best2[0]:.2f} (objective {best2[1]:.3f}) "
          f"vs softmax best {best[1]:.3f}")
    print("Re-check the winning operating point after gold v6/v7 merge.")


if __name__ == "__main__":
    main()
