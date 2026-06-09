# 2026-06-09 · Review should-fix experiments — Tier 2 decomposition, paint probe, compounding, straddle audit

Four measurements queued by the 2026-06-09 peer review. Together they re-rank the
roadmap: **Tier 2 is the pipeline chokepoint, gallery label quality is the Tier 3
bottleneck, and the central embedding bet survives.**

## 1. Tier 2 failure decomposition (`scripts/phase2/probe_split_decomposition.py`)

Where do the probe's missing 22 points (0.676 vs 0.90 bar) come from?

| split | v1 top-1 | reading |
|---|---|---|
| random crop 80/20 (dup-inflated ceiling) | 0.743 | even cheating, in-domain only 0.74 |
| unit-grouped 80/20 (honest in-domain) | **0.600** | *worse than* the 0.676 gold number |
| gold crops (2026-06-05 bench) | 0.676 | — |

**Domain shift is NOT the dominant Tier 2 problem** — the probe can't classify
faction reliably even in-domain on unseen units (0.600). The gallery itself
(weak_faction noise + homogeneity) caps the ceiling. SM does carry extra domain
shift on top (random-split 0.695 → gold 0.473).

## 2. Paint-invariance probe (`scripts/phase3/paint_invariance_probe.py`)

The central bet, measured for the first time: does sculpt identity survive paint
variation in frozen DINOv2 space? AUC = P(same-sculpt-different-paint pair ranks
above different-sculpt pair); 0.5 = paint drowns sculpt.

| faction (labels) | cross-paint AUC | same-listing ceiling AUC |
|---|---|---|
| death_guard (TRUSTED, gw studio vs cmon community) | **0.835** | 0.610* |
| necrons (weak labels — noise deflates) | 0.719 | 0.828 |
| tyranids (weak labels — noise deflates) | 0.686 | 0.866 |

*DG "same-listing" lumps whole corpora (null source_url) — ignore that cell.

**The bet holds where labels are trusted (0.835)** and the weak-label factions'
lower AUCs are consistent with label noise, not embedding failure. Not perfect —
0.84 means ~1 in 6 cross-paint comparisons ranks wrong, which top-3 + multi-view
galleries must absorb. SM unmeasurable (single-source gallery).

## 3. Compounded Tier 2 × Tier 3 (`scripts/phase3/eval_compounded_t2t3.py`)

The pipeline number the per-tier bars hide: Tier 2 predicts the faction → Tier 3
retrieves scoped to the *predicted* faction. Same 102 gold-domain queries as the
gold-domain retrieval bench (oracle-scoped reference: 0.519 top-3).

| | fac top-1 | compound top-3 (covered) |
|---|---|---|
| 20-way probe | 0.294 | **0.089** |
| v1-restricted probe (the v1 product path) | 0.588 | **0.228** |

With v0-baseline detection recall (0.66) on top: **0.06 per-crop (20-way) /
0.15 (v1-restricted)** — the army-list product does not exist at current
component quality; the per-tier exit bars were hiding this. The chokepoint is
Tier 2 misrouting, and most of it is *class-space* misrouting: restricting the
probe to the 4 v1 factions (the actual v1 product path) doubles everything, and
SM faction top-1 goes 0.389 → **0.944** (its 20-way failure was bleed into
chaos/marine-like factions — also reframes the old "SM 0.47" canary). The
residual weak link is DG routing (0.270 even v1-restricted; 189 product-shot
training crops vs 2,914 SM) — ironic, since DG's oracle-scoped retrieval is 0.93:
**Tier 3's best faction is the one Tier 2 can't route to.**

## 4. Straddle audit (`scripts/curation/straddle_check.py`)

Embedding-space near-dup check across pool boundaries (pHash dedup can't see
these):

- **gold_v2 vs gallery: 18/89 images at cosine ≥ 0.99** — 7 of them were
  *literally in the gallery pool* (gold DG gw_shop images swept in by
  `seed_dg_gallery.py` on 06-06, clobbering the deliberate 06-05 `pool="gold"`
  re-pooling). Script now guards against this; run
  `scripts/curation/fix_gold_pool_contamination.py` to repair the live DB, then
  re-run the two retrieval benches. The other 11 are exact-file twins under
  different paths.
- **holdout vs gallery: 215/1,046 (21%) at cosine ≥ 0.99** — exact twins
  (isolation crops cut from the same source photos). The holdout is NOT clean as
  a future test set; any holdout-based eval must exclude these or the twins must
  be re-pooled.

## Implications (re-ranked roadmap)
1. **Tier 2 is the chokepoint**, not Tier 3 — and the fix order is now measured:
   (a) v1-restrict the production probe (free, already doubles the pipeline),
   (b) fix DG routing — more real-photo DG training crops / class rebalancing,
   (c) gallery label QA. The 0.90 bar is unreachable on the current gallery
   either way; with (a)+(b) faction ~0.8 looks plausible, then the "unknown"
   threshold handles the rest.
2. Gallery curation (the DG recipe) remains the Tier 3 lever — and it ALSO trains
   Tier 2, so it pays twice.
3. Embedding backbone is NOT the problem (paint AUC 0.835 on clean labels) —
   DINOv3 ablation correctly deferred (also: repo is gated, no HF token on file).
4. Holdout pool needs a dedup pass before it's ever used as a test set.
