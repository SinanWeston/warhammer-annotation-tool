# 2026-06-10 · Tier 2 — DG routing & "unknown" threshold (two honest negatives)

Follow-ups to the 2026-06-09 review experiments. Both came back negative, and
both point at the same root cause: **gallery quality**. Repro:
`scripts/phase2/tune_dg_routing.py`, `scripts/phase2/calibrate_unknown_threshold.py`
(both read the new eval-crop embedding cache —
`scripts/phase2/embed_eval_crops.py` → `data/embeddings/eval_crops_cache.npz`).

## 1. DG routing: class weighting does NOTHING — it's a domain problem

Hypothesis: DG's 0.27 v1-restricted faction routing is class imbalance (182 DG
training crops vs 2,914 SM). Tested baseline vs `class_weight="balanced"` vs
sqrt-inverse-frequency:

| variant | queries v1 top-1 | queries DG | gold v1 top-1 | gold DG |
|---|---|---|---|---|
| baseline (production) | 0.588 | 0.270 | 0.759 | 0.29 |
| balanced | 0.598 | 0.270 | 0.775 | 0.36 |
| sqrt-inv-freq | 0.578 | 0.270 | 0.749 | 0.29 |

The DG confusion on real crops is **byte-identical across all weightings**
(26/37 → space_marines every time). Weighting can't fix what the features
don't separate: DG's training crops are gw_shop studio + CMON glamour shots —
the most domain-shifted training set of the four — and grimy tabletop DG reads
as SM. Overall deltas are within noise; **production stays unweighted**.

**The real fix:** real-photo DG crops in probe training. Natural source: the
SAM 3 autolabel run will box the DG detection-pool scenes (1,045 images) —
those crops feed the probe. DG routing is therefore blocked-on-Tier-1, not a
Tier 2 tuning problem.

Side note: v1-restricted gold v1 top-1 = **0.759** (the 06-05 bench's 0.676
was 20-way — restriction helps on gold too, +8pp).

## 2. "Unknown" threshold: no usable gate exists on the current gallery

gold_v2's 96 `out_of_scope` boxes are **non-v1 miniatures** (LABELING_GUIDE
§labels) — the hardest open-set case. Three signals swept:

| signal | AUC (v1-correct vs oos) | best operating point |
|---|---|---|
| softmax confidence (renormalized v1) | 0.652 | reject 22% oos, lose 8pp v1 @ t=0.95 |
| mean-top5 cosine, full gallery | ~0.5 | useless (non-v1 minis match their own faction) |
| mean-top5 cosine, predicted-faction slice | 0.643 | reject 35% oos, keep 64% v1 @ t=0.75 |
| conf × cosine | 0.651 | no gain from combining |

Softmax confidence is saturated (oos median 0.999 — terrain-level junk would
be rejected, but non-v1 minis are confidently misrouted), and even the
production-correct signal (scoped gallery cosine, the Tier 3 quantity) only
reaches 0.64 AUC. A usable gate needs ~0.9.

**Conclusion: defer the operating point, keep the mechanism.**
`FactionProbe.predict(unknown_threshold=...)` is implemented and tested; the
calibration script is the standing harness. The gate becomes viable when the
gallery models v1 tightly enough — i.e. after the DG-recipe gallery curation —
and should be re-swept after the gold v6/v7 merge grows the oos sample.

## Implications
1. Both Tier 2 levers left (DG routing, unknown gate) are **blocked on data,
   not modelling**: SAM 3 run (→ real-photo DG crops) and gallery curation.
   Tuning the probe further is wasted effort until then.
2. The eval-crop embedding cache makes all future probe experiments ~instant —
   no more 8-minute re-embeds.
