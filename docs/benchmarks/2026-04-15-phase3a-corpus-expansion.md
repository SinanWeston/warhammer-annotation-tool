# Phase 3a — gallery expansion from the full annotation corpus

**Date**: 2026-04-15
**Commit**: 8770dde (+ Phase 3a pipeline results)
**Phase**: 3a (retrieval gallery expansion — tap the unused 97% of the annotation corpus)
**Retrieval model**: `facebook/dinov2-base`
**Tier 2 classifier**: KNN-vote on DINOv2 gallery embeddings (k=5)
**Queries**: 51 (vs Phase 2's 13 — 3.9× wider eval)
**Factions covered in the gallery**: 23 (vs Phase 2's 9)

## Exit criteria

From `scripts/phase3/README.md`:

- Gallery ≥ 300 crops across ≥ 18 factions, ≥ 3 depth per query unit
- Eval ≥ 30 queries (up from Phase 2's 13)
- Unscoped unit top-3 ≥ 80% **with Wilson lower bound ≥ 70%**
- Per-faction top-3 breakdown across the 14 previously-uncovered factions

| Criterion | Target | Actual | Verdict |
|---|---|---|---|
| Gallery crop count | ≥ 300 | 274 | ❌ MISS (-26) |
| Factions in gallery | ≥ 18 | **23** | ✅ PASS |
| Query count | ≥ 30 | **51** | ✅ PASS |
| Gallery depth ≥ 3 per query unit | all | 20 / 51 | ❌ MISS |
| Unscoped unit top-3 point estimate | ≥ 80% | 74.5% | ❌ MISS |
| Unscoped unit top-3 Wilson lower bound | ≥ 70% | 61.1% | ❌ MISS |
| Per-faction breakdown covers 14 new factions | yes | yes (14/14) | ✅ PASS |

**Overall**: ❌ Exit bar not cleared. Phase 3a delivered the breadth it targeted (23 factions, 51 queries) but the unit-discrimination bar moved against us once the eval set widened — unscoped top-3 fell from Phase 2's 84.6% (on 13 queries) to 74.5%. Gallery depth is the proximate cause: 109 / 139 gallery units (78%) have only a single reference crop, so many queries are matching against a single exemplar.

## Tier 2 — faction classifier

| Metric | Value (Wilson 95% CI) |
|---|---|
| KNN-vote faction top-1 | **54.9%** (41.4%–67.7%) |

**No movement from Phase 2's 53.8%.** Adding 182 new gallery crops across 14 previously-uncovered factions did not lift KNN-vote accuracy. This confirms Phase 2.5's diagnosis: the problem isn't data volume, it's that DINOv2 embeddings aren't faction-linearly-separable by majority vote. A linear probe on the same embeddings is the cheapest next attempt if Tier 2 is ever revisited.

## Tier 3 retrieval — variants side-by-side

| Variant | Unit top-1 | Unit top-3 | Unit top-5 | MRR |
|---|---|---|---|---|
| unscoped (no Tier 2)      | 58.8% (45.2%–71.2%) | 74.5% (61.1%–84.5%) | 80.4% | 0.688 |
| scoped_actual (always scope) | 47.1% (34.1%–60.5%) | 52.9% (39.5%–65.9%) | 54.9% | 0.502 |
| scoped_gated @ conf ≥ 0.5 | 51.0% (37.7%–64.1%) | 62.7% (49.0%–74.7%) | 66.7% | 0.588 |
| scoped_oracle (upper bound) | 74.5% (61.1%–84.5%) | **92.2%** (81.5%–96.9%) | 98.0% | 0.847 |

**Unscoped is still the production path.** Same verdict as Phase 2.5 — scoping by a 55% Tier 2 drags every headline number down by 12–22 pp. Gated scoping never beats unscoped.

**The oracle ceiling is still 92% top-3** on this harder eval. Within-faction embedding discrimination is fine; the architectural bottleneck remains Tier 2, not Tier 3.

## Delta vs Phase 2 (same metrics, wider eval)

| Metric | Phase 2 (13q, 9 factions) | Phase 3a (51q, 23 factions) | Δ |
|---|---|---|---|
| Unscoped unit top-1 | 61.5% | 58.8% | −2.7 pp |
| Unscoped unit top-3 | 84.6% | 74.5% | −10.1 pp |
| Unscoped unit top-5 | 92.3% | 80.4% | −11.9 pp |
| Tier 2 faction top-1 | 53.8% | 54.9% | +1.1 pp |
| Scoped_oracle top-3 | 100% | 92.2% | −7.8 pp |
| Unscoped top-3 Wilson LB | 57.8% | 61.1% | **+3.3 pp** |

The point estimates regressed because the eval set is harder (14 new factions, many 1-crop units). The Wilson lower bound *tightened* by 3.3 pp — we now have a more honest measurement, even if the headline number is lower.

## Per-faction breakdown (unscoped retrieval)

### Previously-uncovered factions (Phase 3a new)

| Faction | Queries | Top-1 | Top-3 |
|---|---|---|---|
| adepta_sororitas    | 1 | 0/1 (0%) | 0/1 (0%) |
| adeptus_mechanicus  | 2 | 1/2 (50%) | 1/2 (50%) |
| black_templars      | 2 | 2/2 (100%) | 2/2 (100%) |
| chaos_daemons       | 5 | 3/5 (60%) | 3/5 (60%) |
| chaos_knights       | 1 | 1/1 (100%) | 1/1 (100%) |
| custodes            | 4 | 0/4 (0%) | 3/4 (75%) |
| deathwatch          | 1 | 0/1 (0%) | 0/1 (0%) |
| grey_knights        | 1 | 0/1 (0%) | 1/1 (100%) |
| harlequins          | 4 | 2/4 (50%) | 3/4 (75%) |
| imperial_guard      | 4 | 3/4 (75%) | 4/4 (100%) |
| imperial_knights    | 1 | 1/1 (100%) | 1/1 (100%) |
| orks                | 2 | 1/2 (50%) | 1/2 (50%) |
| tau_empire          | 3 | 3/3 (100%) | 3/3 (100%) |
| ynnari              | 4 | 3/4 (75%) | 3/4 (75%) |

**All 14 uncovered factions are now represented.** 7 of 14 hit 100% top-3; the weakest performers (adepta_sororitas 0/1, deathwatch 0/1) both have just 1 query — Wilson CI on 0/1 is 0–79%, so no conclusion possible.

### Phase 2 factions (re-eval on fresh crops)

| Faction | Queries | Top-1 | Top-3 |
|---|---|---|---|
| chaos_space_marines | 1 | 1/1 (100%) | 1/1 (100%) |
| death_guard         | 1 | 1/1 (100%) | 1/1 (100%) |
| drukhari            | 1 | 0/1 (0%) | 1/1 (100%) |
| eldar               | 2 | 2/2 (100%) | 2/2 (100%) |
| genestealer_cult    | 2 | 1/2 (50%) | 1/2 (50%) |
| necrons             | 2 | 2/2 (100%) | 2/2 (100%) |
| space_marines       | 1 | 0/1 (0%) | 0/1 (0%) |
| thousand_sons       | 2 | 0/2 (0%) | 1/2 (50%) |
| tyranids            | 4 | 3/4 (75%) | 3/4 (75%) |

The Phase 0 per-class crisis classes — **CSM, death_guard, GSC** — are no longer the bottom of the table. Thousand Sons remains soft (1/2 top-3), consistent with Phase 2's failure mode (visually near-identical to CSM).

## Named failures (unscoped rank > 5)

- **chaos_daemons / daemonettes** → rank 81. Single gallery exemplar, eval crop is a tiny side-of-group shot; near-zero similarity to the reference.
- **custodes / custodian_wardens** → rank 55. Heavy gold armour matched far more strongly against Eldar/Necron metallic finishes than the thin 1-crop custodes set.
- **deathwatch / chaplain** → rank 21. Deathwatch gallery is dominated by veterans in black; the chaplain's skull-helm silhouette pulled matches toward space_marines/chaplains not in this gallery.
- **harlequins / harlequin_troupe** → rank 13. Gallery has 1 troupe crop vs 2 query troupes — depth problem.
- **orks / warboss** → rank 12. Only 1 warboss in the gallery; matched mostly against squig and tyranid ripper crops due to lumpy silhouette.
- **genestealer_cult / neophyte_hybrids** → rank 11. 
- **adeptus_mechanicus / tech_priest** → rank 6.
- **space_marines / cypher** → rank 6. Distinctive model but 1 reference crop.

**Common thread: depth=1 on the query unit.** Every named failure is a gallery singleton. Retrieval can't generalise off a single reference image when paint schemes vary.

## Gallery depth distribution

| Depth (crops per unit) | Units at this depth |
|---|---|
| 1 | 109 |
| 2 | 10 |
| 3 | 6 |
| 4 | 2 |
| 5 | 3 |
| 7 | 1 |
| 8 | 2 |
| 9 | 2 |
| 11 | 1 |
| 15 | 1 |
| 17 | 1 |
| 20 | 1 |

78% of the gallery is at depth 1. The exit criterion of "≥ 3 depth per query unit" is hit for only 20/51 units. This is the single biggest lever for a Phase 3a.1 touch-up.

## Headline findings

1. **Breadth target met, accuracy target missed.** 23 factions × 51 queries is a real eval surface — 3.9× Phase 2's query count. But unscoped top-3 regressed from 84.6% → 74.5% because the broader mix includes units with only 1 gallery exemplar.

2. **The Phase 0 crisis classes recovered.** CSM, death_guard, GSC — all 100% / 100% / 50% unscoped top-3. The retrieval architecture *does* rescue the YOLO-bad classes, confirming Phase 1's core hypothesis. The residual problem is gallery depth, not embedding discrimination.

3. **Depth = 1 is the dominant failure mode.** Every named failure is a singleton gallery unit. The fix is not more labelling breadth — it's targeted depth for the 51 query units.

4. **Tier 2 KNN-vote is definitively a dead end.** 54.9% with 3× more data ≈ 53.8% with the Phase 2 data. Same embeddings, same voting scheme. Linear probe or retrain-on-crops YOLO are the only paths back to scoping.

5. **Scoped oracle dropped from 100% → 92.2%.** Within-faction discrimination is still strong but no longer perfect — the 5.9 pp ceiling gap is the cost of adding the long tail of 1-crop units.

## What this means for STRATEGY.md

- **Phase 3a delivered breadth, not accuracy.** Partial pass: faction coverage and query count are where they need to be; unit-level top-3 regressed against the tighter exit bar.
- **Phase 3a.1 (depth-focused labelling) is the cheapest next step.** Bring the 109 singleton units up to ≥3 crops each. The candidate crops already exist in `backend/training_data_annotations/` — it's labelling hours, not new data acquisition. Expected to lift unscoped top-3 above the 80% bar; this is the same "gallery depth" lever that moved Phase 1→Phase 2 by +8–18 pp.
- **Phase 3b (synthetic data) remains deferred** — still cheaper to label existing corpus than to rig BlenderProc.
- **Ship unscoped retrieval as production** — this is unchanged from Phase 2.5. Scoped variants remain latency optimisations only, and the gated variant now demonstrably under-performs on a real eval.

## Caveats

- **51 queries is honest, not tight.** Wilson 95% CIs on headline percentages are ±12–13 pp. Direction is reliable; exact percentages remain soft at this sample size.
- **Many factions have n=1.** adepta_sororitas, deathwatch, space_marines, etc. can't be scored individually with any confidence. A follow-up targeting ≥ 3 queries per faction would cost ~20 more labels.
- **Slug normalisation affected raw accuracy.** The post-labelling normalisation pass collapsed typos and faction remappings (e.g. plague marines mis-tagged as non–death_guard). This is a correctness gain, not a measurement leak — but the delta vs Phase 2 includes some slug-hygiene improvement.
- **Detection (Tier 1) not re-measured.** OWLv2 result carries over from Phase 1. Not a bottleneck given Phase 0's finding that detection works; discrimination is the failure mode.

## Reproduction

```bash
# Optional: re-extract crops (already on disk)
yolo_env/bin/python3 scripts/phase3/extract_from_corpus.py

# Pipeline
yolo_env/bin/python3 scripts/phase3/auto_split.py
yolo_env/bin/python3 scripts/phase3/build_gallery.py
yolo_env/bin/python3 scripts/phase3/embed_gallery.py
yolo_env/bin/python3 scripts/phase3/eval_scoped_retrieval.py
# Report (this file is hand-authored; generate_report.py writes a Phase 2-named
# file — kept for backwards compat but superseded here)
```

See [../../STRATEGY.md](../../STRATEGY.md) §7 for phase context and
[../../scripts/phase3/README.md](../../scripts/phase3/README.md) for the Phase 3a
data-flow spec.
