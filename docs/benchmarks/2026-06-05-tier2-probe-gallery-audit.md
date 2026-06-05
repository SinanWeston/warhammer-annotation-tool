# 2026-06-05 · Tier 2 faction probe + gallery depth audit

Autonomous experiments run while data labeling was in progress. Two results: a
gallery-depth audit (Tier 3 input health) and the first honest Tier 2 faction
linear-probe number.

## Setup
- **Embeddings**: frozen `facebook/dinov2-large`, CLS token, L2-normalized (the
  `embedding` field on `wh40k_pile`).
- **Tier 2 probe**: `LogisticRegression` (StandardScaler) on gallery embeddings →
  `weak_faction`. Trained on the **full** gallery (19,576 crops, 20 factions).
- **Tier 2 test**: 283 crops cut from `gold_v2.json` boxes, embedded fresh with the
  same recipe. **Leakage-free** (gold is separate from gallery) and **real labels**.
- Repro: `scripts/phase2/classify_faction_probe.py`,
  `scripts/phase2/classify_faction_knn.py` (the old KNN-vote baseline).

## Result 1 — Tier 2 faction classification

| Cut | top-1 | top-3 | note |
|---|---|---|---|
| **Gold crops, v1 factions** | **0.676** | — | the honest number (n=145) |
| · Tyranids | 0.907 | 1.000 | bio silhouette is distinctive — near-solved |
| · Necrons | 0.702 | 0.915 | solid |
| · Space Marines | **0.473** | 0.818 | the weak link (see below) |
| · Death Guard | — | — | **0 gallery crops — untestable until DG scrape** |
| Gallery-internal split, 18 fac | 0.670 | 0.858 | ≈ gold number → not leakage-inflated |
| (prior) KNN-vote | ~0.55 | — | the dead end STRATEGY flagged |

**Linear probe beats KNN-vote by +12pp** — confirms STRATEGY's call. But 0.68 is
below the 90% Tier 2 exit bar.

Why Space Marines is the weak link (0.47):
- The entire SM gallery is `dup`-tagged (homogeneous source — see Result 2), so the
  probe trains on low-diversity SM crops and generalizes poorly to real gold SM.
- SM has the most paint-scheme / chapter variance of any faction — the hardest
  single-crop faction call.
- top-3 is 0.82, so a "did you mean?" UI mostly recovers it; and STRATEGY's premise
  is that **Tier 3 unit retrieval rescues the YOLO/faction-bad factions** — SM is
  exactly that case.

### The "unknown" path is mandatory, and must be confidence-thresholded
96 `out_of_scope` gold crops (no gallery class exists for them) were **confidently**
forced into real factions: `astra_militarum` ×32, `tau_empire` ×17, `genestealer_cults`
×10, `orks` ×10, `space_marines` ×9. argmax cannot say "I don't recognize this" — the
Tier 2 "unknown" path **must** be a calibrated confidence/OOD threshold (consistent
with STRATEGY's "I don't recognize this" KPI). This is now an empirically-grounded
requirement, not a nice-to-have.

## Result 2 — Gallery depth audit (Tier 3 input)

Gallery pool: 19,576 images, **800 distinct units, median depth 30, mean 24.5**.

| | units | crops | singletons (depth=1) |
|---|---|---|---|
| Space Marines | 125 | 2,929 | 0 |
| Necrons | 59 | 1,566 | 0 |
| Tyranids | 53 | 1,288 | 0 |
| **Death Guard** | **0** | **0** | — |
| gallery-wide | 800 | — | 5 (1%) |

**The Phase 3a "78% singletons / 109 units need lifting" problem is obsolete** — that
was the small old corpus. The rebuilt pile has median depth 30 and ~0 singletons.
**Phase 3a.1 (depth push) is effectively done for 3/4 v1 factions.** The *entire*
remaining Tier 3 gallery gap is **Death Guard (0 crops)** → the DG scrape is the
single Tier 3 data blocker.

### ⚠ Data artifact: the global `dup` tag nukes the SM + Necron gallery
Deduping the gallery (`match_tags("dup", bool=False)`) drops **all 2,914 SM and all
1,566 Necron** crops — they're 100% `dup`-tagged. `build_pools.py` already documents
this ("global dedup picks representatives blindly and would evict the labeled
gallery") and deliberately keeps dups in the gallery. Implication: **never dedup the
gallery by the `dup` tag** — it silently deletes whole factions. And the SM gallery's
homogeneity (why it's all dup-flagged) is likely *why* SM Tier 2 accuracy is low —
worth a gallery-diversity pass on SM specifically.

## Recommendations
1. **Calibrate a Tier 2 confidence threshold** for the "unknown" path (empirically
   required — oos crops are confidently misclassified).
2. **Diversify the SM gallery** (it's all near-dups) — likely the cheapest SM Tier 2 lift.
3. **DG scrape** unblocks both Tier 3 gallery *and* Tier 2 DG coverage (currently 0).
4. Clean `weak_faction` labels (training-side noise caps the ceiling).
5. Don't chase Tier 2 to 90% standalone — STRATEGY ships Tier 3 retrieval as the real
   discriminator; Tier 2's job is to scope it. top-3 0.82+ is enough to scope.
