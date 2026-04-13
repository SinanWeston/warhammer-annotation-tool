# Phase 1 prototype — retrieval pipeline (OWLv2 + DINOv3)

**Date**: 2026-04-13
**Phase**: 1 (Prototype Tier 1 + Tier 3, no training)
**Retrieval model**: `facebook/dinov2-base`
**Detector**: `google/owlv2-base-patch16-ensemble`
**Gallery**: 24 images across 17 unique units
**Queries**: 6

## Headline metrics (Wilson 95% CI)

| Metric | Value (95% CI) | Notes |
|---|---|---|
| Unit top-1 | 66.7% (30.0%–90.3%) | Cosine k-NN, max-sim aggregation |
| Unit top-3 | 66.7% (30.0%–90.3%) | |
| Unit top-5 | 83.3% (43.6%–97.0%) | Exit criterion: ≥ 50% |
| Unit MRR | 0.722 | Mean reciprocal rank |
| Faction top-1 (via retrieval) | 66.7% (30.0%–90.3%) | Faction of top-1 unit |
| Detection recall @ IoU 0.5 | 83.3% (74.6%–89.5%) | OWLv2 vs YOLO 66.0% baseline. Exit criterion: ≥ 66%. |
| Detection precision @ IoU 0.5 | 0.6% (0.5%–0.8%) | OWLv2 vs YOLO 76.3% baseline. |
| "Unknown" threshold | 0.812 | Cosine sim at FPR 10% — Phase 4 calibration input |

## Comparison vs Phase 0 baseline

| Metric | Phase 0 YOLO | Phase 1 retrieval | Delta |
|---|---|---|---|
| Faction top-1 (aggregate) | 63.8% (15-class softmax on matched) | 66.7% (via retrieval) | +2.9 pp |
| Detection recall @ 0.5 | 66.0% (YOLO) | 83.3% (OWLv2) | +17.3 pp |
| Detection precision @ 0.5 | 76.3% (YOLO) | 0.6% (OWLv2) | -75.7 pp |

## Per-faction breakdown

### YOLO-easy (Phase 0 ≥ 90% faction top-1)

| Faction | Queries | Top-1 | Top-3 | Top-5 | MRR |
|---|---|---|---|---|---|
| space_marines | 0 | — | — | — | — |
| tyranids | 1 | 0/1 = 0% | 0/1 = 0% | 0/1 = 0% | 0.083 |

### YOLO-problem (Phase 0 ≤ 15% faction top-1)

| Faction | Queries | Top-1 | Top-3 | Top-5 | MRR |
|---|---|---|---|---|---|
| chaos_space_marines | 1 | 1/1 = 100% | 1/1 = 100% | 1/1 = 100% | 1.000 |
| death_guard | 1 | 1/1 = 100% | 1/1 = 100% | 1/1 = 100% | 1.000 |
| genestealer_cult | 2 | 1/2 = 50% | 1/2 = 50% | 2/2 = 100% | 0.625 |

## Named failure examples

**`scripts/phase1/queries/tyranids/termagants/14kujha_a92f261b1099__14.jpg`** — true unit: `tyranids/termagants`, true rank: 12
  1. `thousand_sons/rubric_marines` — sim 0.622
  2. `chaos_space_marines/legionaries` — sim 0.540
  3. `death_guard/plague_marines` — sim 0.531
  4. `death_guard/lord_of_contagion` — sim 0.511
  5. `genestealer_cult/genestealers` — sim 0.503

**`scripts/phase1/queries/genestealer_cult/aberrants/1061044_3995318f2400__02.jpg`** — true unit: `genestealer_cult/aberrants`, true rank: 4
  1. `death_guard/deathshroud_terminators` — sim 0.812
  2. `thousand_sons/rubric_marines` — sim 0.774
  3. `death_guard/plague_marines` — sim 0.770
  4. `genestealer_cult/aberrants` — sim 0.765
  5. `space_marines/sanguinary_guard` — sim 0.745

**`scripts/phase1/queries/chaos_space_marines/legionaries/138245_351bd85403f3__03.jpg`** — true unit: `chaos_space_marines/legionaries`, true rank: 1
  1. `chaos_space_marines/legionaries` — sim 0.937
  2. `thousand_sons/rubric_marines` — sim 0.841
  3. `death_guard/plague_marines` — sim 0.802
  4. `space_marines/captain` — sim 0.796
  5. `space_marines/sanguinary_guard` — sim 0.786

## Qualitative notes (fill by hand on Day 3)

- [ ] Are correct matches at high sim (≥0.7) while wrong are at ≤0.5? Flat distribution is a red flag.
- [ ] Failure mode bucket counts: (a) unit not in gallery, (b) paint-scheme cross-match, (c) semantically similar but wrong unit.
- [ ] Does DINOv3 vs DINOv2 matter? Include the swap delta.
- [ ] How does the YOLO-easy block compare to YOLO-problem? Does retrieval move the problem block more?
- [ ] Are there under-represented gallery units affecting their queries?

## Exit criteria assessment

- Unit top-5 ≥ 50%: **83.3%** — ❌ MISS (Wilson lower bound 43.6% < 50%)
- OWLv2 detection recall ≥ 66%: **83.3%** — ✅ PASS

## Reproduction

```bash
yolo_env/bin/python3 scripts/phase1/extract_gt_crops.py
# fill scripts/phase1/labels.csv by hand
yolo_env/bin/python3 scripts/phase1/auto_split.py
yolo_env/bin/python3 scripts/phase1/build_gallery.py
yolo_env/bin/python3 scripts/phase1/embed_gallery.py
yolo_env/bin/python3 scripts/phase1/eval_retrieval.py
yolo_env/bin/python3 scripts/phase1/eval_detection.py
yolo_env/bin/python3 scripts/phase1/generate_report.py
```
